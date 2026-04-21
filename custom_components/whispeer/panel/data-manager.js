const APP_CONFIG = {
  API_BASE: '',
  ENDPOINTS: {
    DEVICES: '/api/whispeer/devices',
    SEND_COMMAND: '/api/services/whispeer/send_command',
    SYNC_DEVICES: '/api/services/whispeer/sync_devices',
    REMOVE_DEVICE: '/api/services/whispeer/remove_device',
    INTERFACES: '/api/services/whispeer/get_interfaces',
    BLE_SCAN: '/api/whispeer/ble/scan',
    BLE_EMIT: '/api/whispeer/ble/emit'
  },
  STORAGE_KEYS: {
    DEVICES: 'whispeer_devices',
    SETTINGS: 'whispeer_settings'
  },
  COMMAND_TYPES: {
    button: {
      icon: '🔘',
      title: 'Button',
      fields: ['code'],
      props: ['shape', 'color', 'icon', 'display']
    },
    light: {
      icon: '💡',
      title: 'Light',
      fields: [],
      hasOptions: true
    },
    switch: {
      icon: '🔌',
      title: 'Switch',
      fields: [],
      hasOptions: true
    },
    numeric: {
      icon: '🔢',
      title: 'Numeric',
      fields: [],
      hasOptions: true
    },
    group: {
      icon: '📁',
      title: 'Group',
      fields: [],
      hasOptions: true
    }
  },
  EMOJIS: ['🏠', '🛋️', '🛏️', '🚪', '🚗', '💡', '🖥️', '🧊', '🌀', '🔌'],
  DEVICE_TYPES: {
    ir: { label: 'IR', badge: 'type-ir' },
    rf: { label: 'RF', badge: 'type-rf' },
    ble: { label: 'BLE', badge: 'type-ble' }
  }
};

class DataManager {
  static devices = {};
  static automations = {};
  static settings = {
    theme: 'auto',
    language: 'en'
  };

  static async loadDevices() {
    try {
      const token = DataManager.getHomeAssistantToken();
      console.log('[Whispeer] Loading devices from backend...', { tokenPresent: !!token });
      const response = await Utils.api.get(APP_CONFIG.ENDPOINTS.DEVICES, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      console.log('[Whispeer] Devices GET response:', response);
      const list = (response && response.devices) ? response.devices : [];
      // Normalize to id -> device map
      DataManager.devices = {};
      list.forEach(d => {
        const id = String(d.id);
        DataManager.devices[id] = { ...d, id };
      });
      console.log('[Whispeer] Devices normalized:', DataManager.devices);
      return DataManager.devices;
    } catch (error) {
      console.error('Failed to load devices from backend:', error);
      DataManager.devices = {};
      return DataManager.devices;
    }
  }

  static async saveDevices() {
    // Deprecated: syncing will be performed explicitly on CRUD operations
  }

  static async addDevice(device) {
    try {
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.DEVICES, device, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (response && response.status === 'success') {
        const id = String(response.id);
        DataManager.devices[id] = { id, ...device };
        await DataManager.syncWithBackend();
        // Emit event so UI refreshes immediately
        Utils.events.emit('deviceUpdated', { deviceId: id });
        return id;
      }
      throw new Error(response?.error || 'Failed to add device');
    } catch (error) {
      console.error('Failed to add device:', error);
      throw error;
    }
  }

  static async updateDevice(id, updates) {
    if (DataManager.devices[id]) {
      DataManager.devices[id] = { ...DataManager.devices[id], ...updates };
      await DataManager.syncWithBackend();
      Utils.events.emit('deviceUpdated', { deviceId: id });
      return true;
    }
    return false;
  }

  static async deleteDevice(id) {
    try {
      const token = DataManager.getHomeAssistantToken();
      await Utils.api.post(APP_CONFIG.ENDPOINTS.REMOVE_DEVICE, { device_id: id }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (DataManager.devices[id]) {
        delete DataManager.devices[id];
      }
      await DataManager.syncWithBackend();
      Utils.events.emit('deviceDeleted', { deviceId: id });
      return true;
    } catch (error) {
      console.error('Failed to delete device:', error);
      return false;
    }
  }

  static async clearDevices() {
    try {
      const token = DataManager.getHomeAssistantToken();
      // Prefer GET with token as query for iframe compatibility
      const url = token 
        ? `/api/whispeer/clear_devices?access_token=${encodeURIComponent(token)}`
        : '/api/whispeer/clear_devices';
      const response = await Utils.api.get(url);
      DataManager.devices = {};
      Utils.events.emit('deviceUpdated', {});
      return response;
    } catch (error) {
      console.error('Failed to clear devices:', error);
      // Do not attempt POST fallback; endpoint supports GET for iframe contexts
      throw error;
    }
  }

  static getDevice(id) {
    return DataManager.devices[id] || null;
  }

  static getAllDevices() {
    return Object.values(DataManager.devices);
  }

  static async loadAutomations() {
    try {
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.get('/api/whispeer/automations', {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (response && response.device_automations) {
        DataManager.automations = response.device_automations;
      } else {
        DataManager.automations = {};
      }
    } catch (error) {
      console.error('Failed to load automations:', error);
      DataManager.automations = {};
    }
    return DataManager.automations;
  }

  static getDeviceAutomations(deviceId) {
    return DataManager.automations[String(deviceId)] || [];
  }

  static loadSettings() {
    // Keep UI settings in memory only
    return DataManager.settings;
  }

  static saveSettings() {
    // No-op for now; could persist to backend later
  }

  static updateSettings(updates) {
    DataManager.settings = { ...DataManager.settings, ...updates };
    DataManager.saveSettings();
  }

  static async syncWithBackend() {
    try {
      const token = DataManager.getHomeAssistantToken();
      await Utils.api.post(APP_CONFIG.ENDPOINTS.SYNC_DEVICES, {
        devices: DataManager.devices
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
    } catch (error) {
      console.error('Failed to sync with backend:', error);
    }
  }

  static getHomeAssistantToken() {
    if (typeof getHomeAssistantToken === 'function') {
      return getHomeAssistantToken();
    }
    
    const urlParams = Utils.getUrlParams();
    return urlParams.access_token || 
           Utils.storage.get('hass_token') || 
           window.parent?.hassTokens?.access_token;
  }

  static async loadInterfaces(deviceType) {
    try {
      console.log(`Loading interfaces for device type: ${deviceType}`);
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.INTERFACES, {
        type: deviceType
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      
      console.log(`Interface response for ${deviceType}:`, response);
      
      if (response.status !== 'success') {
        console.error(`Failed to load interfaces: ${response.message}`);
        return [];
      }
      
      const interfaces = response.interfaces || [];
      
      // Validar que todos los elementos sean objetos con label
      const validInterfaces = interfaces.filter(iface => {
        if (typeof iface !== 'object' || !iface.label) {
          console.error('Invalid interface format, missing label:', iface);
          return false;
        }
        return true;
      });
      
      console.log(`Loaded ${validInterfaces.length} valid interfaces for ${deviceType}:`, validInterfaces);
      return validInterfaces;
      
    } catch (error) {
      console.error(`Failed to load interfaces for ${deviceType}:`, error);
      return [];
    }
  }

  static async sendCommand(deviceId, deviceType, commandName, commandCode, subCommand = null) {
    try {
      const token = DataManager.getHomeAssistantToken();
      if (!token) {
        throw new Error('No authentication token available');
      }

      const payload = {
        device_id: deviceId,
        device_type: deviceType,
        command_name: commandName,
        command_code: commandCode
      };

      if (subCommand) {
        payload.sub_command = subCommand;
      }

      // Include emitter data so backend can resolve the hub entity
      const device = DataManager.getDevice(deviceId);
      if (device && device.emitter) {
        payload.emitter = device.emitter;
      }

      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.SEND_COMMAND, payload, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      return response;
    } catch (error) {
      console.error('Failed to send command:', error);
      throw error;
    }
  }
}

class CommandManager {
  static validateCommand(command) {
    if (!command.type) {
      return { valid: false, errors: ['Type is required'] };
    }

    const config = APP_CONFIG.COMMAND_TYPES[command.type];
    if (!config) {
      return { valid: false, errors: ['Invalid command type'] };
    }

    const errors = [];
    
    if (config.fields && config.fields.length > 0) {
      config.fields.forEach(field => {
        if (!command.values || !command.values[field]) {
          errors.push(`${field} is required for ${command.type} commands`);
        }
      });
    }

    return { valid: errors.length === 0, errors };
  }

  static createCommand(type, data) {
    return {
      type: type,
      values: data.values || {},
      props: data.props || {}
    };
  }

  static cloneCommand(command) {
    return Utils.deepClone(command);
  }

  static getCommandsByType(commands) {
    const grouped = {};
    
    Object.entries(commands).forEach(([name, command]) => {
      const type = command.type || 'button';
      if (!grouped[type]) {
        grouped[type] = {};
      }
      grouped[type][name] = command;
    });

    return grouped;
  }

  static renderCommandPreview(command) {
    const { type, name, props = {} } = command;
    
    switch (type) {
      case 'button':
        return CommandManager.renderButtonPreview(command);
      case 'light':
      case 'switch':
        return CommandManager.renderTogglePreview(command);
      case 'numeric':
        return CommandManager.renderNumericPreview(command);
      case 'group':
        return CommandManager.renderGroupPreview(command);
      default:
        return `<span class="command-preview-default">${name}</span>`;
    }
  }

  static renderButtonPreview(command) {
    const { name, props = {} } = command;
    const shape = props.shape || 'rectangle';
    const color = props.color || '#03a9f4';
    const display = props.display || 'both';
    const icon = props.icon || '💡';

    const shapeClass = `shape-${shape}`;
    const displayText = display === 'icon' ? '' : (display === 'text' ? name : `${icon} ${name}`);
    const displayIcon = display === 'text' ? '' : icon;

    return `
      <button class="command-btn-preview ${shapeClass}" 
              style="background-color: ${color}; color: white;">
        ${displayIcon} ${displayText}
      </button>
    `;
  }

  static renderTogglePreview(command) {
    const { name } = command;
    return `
      <div class="command-toggle-preview">
        <span>${name}</span>
        <div class="command-toggle" data-state="off"></div>
      </div>
    `;
  }

  static renderNumericPreview(command) {
    const { name, options = {} } = command;
    const optionCount = Object.keys(options).length;
    return `
      <div class="command-numeric-preview">
        <span>${name}</span>
        <span class="command-options-summary">${optionCount} options</span>
      </div>
    `;
  }

  static renderGroupPreview(command) {
    const { name, options = {} } = command;
    const optionCount = Object.keys(options).length;
    return `
      <div class="command-group-preview">
        <span>📁 ${name}</span>
        <span class="command-options-summary">${optionCount} items</span>
      </div>
    `;
  }

  static async learnCommand(deviceType, emitterData, fastSweep = false) {
    try {
      const token = DataManager.getHomeAssistantToken();
      const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};
      // First, prepare the device for learning
      const payload = {
        device_type: deviceType,
        emitter: emitterData
      };
      if (fastSweep) {
        payload.fast_sweep = true;
      }
      const prepareResponse = await Utils.api.post('/api/services/whispeer/prepare_to_learn', payload, {
        headers: authHeaders
      });
      
      if (prepareResponse.status !== 'success') {
        throw new Error(prepareResponse.message || 'Failed to prepare device for learning');
      }
      
      const sessionId = prepareResponse.session_id;
      console.log(`Learning session started: ${sessionId}`);
      
      // Return the session info for the UI to handle
      return {
        status: 'prepared',
        session_id: sessionId,
        device_type: deviceType,
        message: 'Device prepared for learning'
      };
      
    } catch (error) {
      console.error('Failed to prepare for learning:', error);
      throw error;
    }
  }

  static async checkLearnedCommand(sessionId, deviceType) {
    try {
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post('/api/services/whispeer/check_learned_command', {
        session_id: sessionId,
        device_type: deviceType
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      
      return response;
    } catch (error) {
      console.error('Failed to check learned command:', error);
      throw error;
    }
  }

  static interfacesCache = {};
  static CACHE_TIMEOUT = 30000; // 30 seconds

  static async getInterfaces(deviceType) {
    try {
      // Check cache first
      const cacheKey = deviceType;
      const cached = this.interfacesCache[cacheKey];
      
      if (cached && (Date.now() - cached.timestamp) < this.CACHE_TIMEOUT) {
        console.log(`Using cached interfaces for ${deviceType}`);
        return cached.data;
      }
      
      console.log(`Fetching fresh interfaces for ${deviceType}`);
      const response = await Utils.api.post('/api/services/whispeer/get_interfaces', {
        type: deviceType
      });
      
      // Cache the response
      if (response.status === 'success') {
        this.interfacesCache[cacheKey] = {
          data: response,
          timestamp: Date.now()
        };
      }
      
      return response;
    } catch (error) {
      console.error(`Failed to get ${deviceType} interfaces:`, error);
      throw error;
    }
  }

  static getInterfacesList(deviceType) {
    const cached = this.interfacesCache[deviceType];
    if (cached && (Date.now() - cached.timestamp) < this.CACHE_TIMEOUT) {
      return cached.data;
    }
    return null;
  }

  static clearInterfacesCache() {
    this.interfacesCache = {};
  }
}

window.APP_CONFIG = APP_CONFIG;
window.DataManager = DataManager;
window.CommandManager = CommandManager;
