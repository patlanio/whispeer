class WSManager {
  // -- Connection --
  static _ws = null;
  static _msgId = 1;
  static _ready = false;
  static _connecting = false;
  static _token = null;
  static _reconnectDelay = 1000;
  static _reconnectTimer = null;

  // -- Pending calls: msgId → { resolve, reject } --
  static _pending = new Map();

  // -- Message queue while authenticating --
  static _messageQueue = [];

  // -- Event subscriptions --
  // _eventSubs: Map<eventType, { haSubId: number|null, callbacks: Set<Function> }>
  static _eventSubs = new Map();
  // _haSubIdToEventType: Map<number, string>
  static _haSubIdToEventType = new Map();

  // -- Command subscriptions (subscribeMessage-style) --
  // _commandSubs: Map<msgId, Function>
  static _commandSubs = new Map();

  // -- Ready callbacks --
  static _onReadyCallbacks = [];

  /**
   * Resolve the best available HA access token from all known sources.
   * Called both at initial connect and on every reconnect attempt.
   */
  static _getToken() {
    // 1. Global function injected by the panel backend
    if (typeof window.getHomeAssistantToken === 'function') {
      const t = window.getHomeAssistantToken();
      if (t) return t;
    }

    // 2. HA's modern WebSocket connection object (home-assistant-js-websocket)
    try {
      const conn = window.hassConnection || window.parent?.hassConnection;
      const t = conn?.options?.auth?.accessToken;
      if (t) return t;
    } catch (_) {}

    // 3. hassTokens key in localStorage (written by HA frontend)
    try {
      const raw = localStorage.getItem('hassTokens');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.access_token) return parsed.access_token;
      }
    } catch (_) {}

    // 4. hass object on <home-assistant> element in parent frame
    try {
      const el = window.parent?.document?.querySelector('home-assistant');
      const t = el?.__hass?.auth?.data?.access_token
             || el?.hass?.auth?.data?.access_token;
      if (t) return t;
    } catch (_) {}

    return null;
  }

  /**
   * Connect to the HA WebSocket API and authenticate.
   * If no token is available yet, retries every 500 ms until it is.
   */
  static connect() {
    const token = WSManager._getToken();
    if (!token) {
      // HA parent frame might not be ready yet — wait and retry
      setTimeout(() => WSManager.connect(), 500);
      return;
    }
    WSManager._token = token;
    WSManager._doConnect();
  }

  static _doConnect() {
    if (WSManager._connecting || WSManager._isOpen()) return;
    WSManager._connecting = true;
    WSManager._ready = false;

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${location.host}/api/websocket`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[WSManager] WebSocket constructor failed:', err);
      WSManager._connecting = false;
      WSManager._scheduleReconnect();
      return;
    }

    WSManager._ws = ws;
    ws.addEventListener('message', WSManager._onMessage);
    ws.addEventListener('close', WSManager._onClose);
    ws.addEventListener('error', (e) => console.warn('[WSManager] WS error:', e));
  }

  static _isOpen() {
    return (
      WSManager._ws !== null &&
      WSManager._ws.readyState === WebSocket.OPEN
    );
  }

  static _onMessage(event) {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    const { type, id } = msg;

    if (type === 'auth_required') {
      WSManager._ws.send(JSON.stringify({
        type: 'auth',
        access_token: WSManager._token,
      }));
      return;
    }

    if (type === 'auth_ok') {
      WSManager._connecting = false;
      WSManager._ready = true;
      WSManager._reconnectDelay = 1000;
      console.log('[WSManager] Connected and authenticated');

      WSManager._resubscribeAll();

      const queue = WSManager._messageQueue.splice(0);
      queue.forEach(m => WSManager._ws.send(JSON.stringify(m)));

      const cbs = WSManager._onReadyCallbacks.splice(0);
      cbs.forEach(cb => { try { cb(); } catch (e) {} });
      return;
    }

    if (type === 'auth_invalid') {
      console.error('[WSManager] Authentication rejected — will retry with fresh token');
      WSManager._connecting = false;
      WSManager._ws.close();
      // Clear any stale cached token and retry after a short delay
      WSManager._token = null;
      WSManager._scheduleReconnect();
      return;
    }

    if (type === 'result') {
      const p = WSManager._pending.get(id);
      if (p) {
        WSManager._pending.delete(id);
        if (msg.success) {
          p.resolve(msg.result);
        } else {
          p.reject(new Error(msg.error?.message || 'WebSocket command failed'));
        }
      }
      return;
    }

    if (type === 'event') {
      const cmdCb = WSManager._commandSubs.get(id);
      if (cmdCb) {
        try { cmdCb(msg.event); } catch (e) {
          console.error('[WSManager] Command subscription callback error:', e);
        }
        return;
      }

      const eventType = WSManager._haSubIdToEventType.get(id);
      if (eventType) {
        const info = WSManager._eventSubs.get(eventType);
        if (info) {
          info.callbacks.forEach(cb => {
            try { cb(msg.event); } catch (e) {
              console.error('[WSManager] Event callback error:', e);
            }
          });
        }
      }
      return;
    }
  }

  static _onClose() {
    WSManager._ready = false;
    WSManager._connecting = false;
    console.warn('[WSManager] Connection lost — reconnecting…');

    WSManager._pending.forEach(p => p.reject(new Error('WebSocket disconnected')));
    WSManager._pending.clear();

    WSManager._haSubIdToEventType.clear();
    WSManager._commandSubs.clear();
    for (const info of WSManager._eventSubs.values()) {
      info.haSubId = null;
    }

    WSManager._scheduleReconnect();
  }

  static _scheduleReconnect() {
    if (WSManager._reconnectTimer) return;
    WSManager._reconnectTimer = setTimeout(() => {
      WSManager._reconnectTimer = null;
      if (!WSManager._ready && !WSManager._connecting) {
        const fresh = WSManager._getToken();
        if (fresh) {
          WSManager._token = fresh;
          WSManager._doConnect();
        } else {
          // Token not yet available — try again via connect()
          WSManager.connect();
        }
      }
    }, WSManager._reconnectDelay);
    WSManager._reconnectDelay = Math.min(WSManager._reconnectDelay * 2, 30000);
  }

  static _resubscribeAll() {
    for (const [eventType, info] of WSManager._eventSubs.entries()) {
      if (info.callbacks.size === 0) continue;
      const id = WSManager._msgId++;
      info.haSubId = id;
      WSManager._haSubIdToEventType.set(id, eventType);
      WSManager._ws.send(JSON.stringify({
        type: 'subscribe_events',
        event_type: eventType,
        id,
      }));
    }
  }

  static _rawSend(msg) {
    if (WSManager._ready && WSManager._isOpen()) {
      WSManager._ws.send(JSON.stringify(msg));
    } else {
      WSManager._messageQueue.push(msg);
    }
  }

  /**
   * Send a command and return a Promise resolving to the result object.
   * @param {string} type - WS command type, e.g. 'whispeer/get_devices'
   * @param {object} data - Additional payload fields
   */
  static call(type, data = {}) {
    return new Promise((resolve, reject) => {
      const id = WSManager._msgId++;
      WSManager._pending.set(id, { resolve, reject });
      WSManager._rawSend({ type, id, ...data });
    });
  }

  /**
   * Send a command and stream subsequent events to *callback*.
   * Returns a Promise that resolves to an unsubscribe function once the
   * initial result arrives.
   * @param {string} type - WS command type, e.g. 'bluetooth/subscribe_advertisements'
   * @param {object} data - Additional payload fields
   * @param {Function} callback - Called with each event object
   */
  static subscribeCommand(type, data, callback) {
    return new Promise((resolve, reject) => {
      const id = WSManager._msgId++;
      WSManager._commandSubs.set(id, callback);
      WSManager._pending.set(id, {
        resolve: () => {
          resolve(() => { WSManager._commandSubs.delete(id); });
        },
        reject,
      });
      WSManager._rawSend({ type, id, ...data });
    });
  }

  /**
   * Subscribe to a HA event type.
   * Returns an unsubscribe function — call it to stop receiving events.
   * @param {string} eventType - HA event type, e.g. 'state_changed'
   * @param {Function} callback - Called with the event object
   */
  static subscribe(eventType, callback) {
    if (!WSManager._eventSubs.has(eventType)) {
      const info = { haSubId: null, callbacks: new Set() };
      WSManager._eventSubs.set(eventType, info);

      if (WSManager._ready) {
        const id = WSManager._msgId++;
        info.haSubId = id;
        WSManager._haSubIdToEventType.set(id, eventType);
        WSManager._rawSend({ type: 'subscribe_events', event_type: eventType, id });
      }
    }

    const info = WSManager._eventSubs.get(eventType);
    info.callbacks.add(callback);

    return () => {
      info.callbacks.delete(callback);
    };
  }

  /**
   * Call cb immediately if the WS connection is authenticated, otherwise
   * queue it to be called once authentication succeeds.
   */
  static onReady(cb) {
    if (WSManager._ready) {
      try { cb(); } catch (e) {}
    } else {
      WSManager._onReadyCallbacks.push(cb);
    }
  }
}

window.WSManager = WSManager;
