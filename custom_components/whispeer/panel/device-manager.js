class DeviceManager extends Component {
  constructor(selector) {
    super(selector);
    this.currentDevice = null;
    this.tempCommands = {};
    this.deviceModal = null;
    this.commandModal = null;
    this.storedCodes = null;
    this._storedCodesFlat = [];
    this._detectedFrequency = null;
    this._fastLearning = false;
    this._fastLearnStop = false;
    this._climateData = null;
    this._climateLearning = false;
    this._climateLearningCell = null;
    this._climateLearningGen = 0;
    this._climateTestMode = false;
    this._bleScannerToken = 0;
  }

  init() {
    this.setupTemplates();
    this.bindEvents();
  }

  setupTemplates() {
    this.templates = {
      deviceCard: `
        <div class="device-card" data-device-id="{{id}}">
          <div class="device-header">
            <div class="device-name">{{automationBadge}}<span>{{name}}</span></div>
            <div class="device-header-right">
                <button type="button" class="device-type-badge {{badgeClass}}" onclick="deviceManager.configureDevice('{{configureId}}')">{{type}}</button>
            </div>
          </div>
          <div class="device-commands">{{commands}}</div>
        </div>
      `,
      
      addDeviceCard: `
        <div class="add-device-card" onclick="deviceManager.openAddDeviceModal()">
          <div class="add-device-icon">➕</div>
          <div>Add New Device</div>
        </div>
      `,

      deviceForm: `
        <form id="deviceForm">
          {{formFields}}
          <div class="commands-section">
            <div class="commands-header">
              <h4>Commands</h4>
              <div class="commands-header-actions">
                <button type="button" class="btn btn-small btn-outlined" id="fastLearnBtn" style="display:none" onclick="deviceManager.startFastLearn()">⚡ Fast Learn</button>
                <button type="button" class="btn btn-small btn-danger" id="fastLearnStopBtn" style="display:none" onclick="deviceManager.stopFastLearn()">⏹ Stop</button>
                <button type="button" class="btn btn-small btn-outlined" id="bulkLearnBtn" style="display:none" onclick="deviceManager.openBulkLearnModal()">📡 Bulk Learn</button>
                <button type="button" class="btn btn-small" onclick="deviceManager.addInlineCommand()">+ Add Command</button>
              </div>
            </div>
            <div class="commands-list" id="commandsList">{{commandsList}}</div>
          </div>
          <div class="modal-controls">
            <div class="modal-controls-left">
              <button type="button" class="btn btn-outlined" onclick="deviceManager.closeDeviceModal()">Cancel</button>
              {{deleteButton}}
            </div>
            <button type="submit" class="btn">{{saveButtonText}}</button>
          </div>
        </form>
        {{automationsSection}}
      `,

      commandButton: `
        <button class="btn btn-small command-btn"
                onmousedown="deviceManager.startLongPress('{{deviceId}}', '{{commandName}}')"
                onmouseup="deviceManager.stopLongPress()"
                onmouseleave="deviceManager.stopLongPress()"
                ontouchstart="deviceManager.startLongPress('{{deviceId}}', '{{commandName}}')"
                ontouchend="deviceManager.stopLongPress()"
                ontouchcancel="deviceManager.stopLongPress()"
                style="{{buttonStyle}}">
          {{buttonContent}}
        </button>
      `,

      commandToggle: `
        <div class="command-toggle-full-width" data-entity="{{deviceId}}:{{commandName}}">
          <span class="command-toggle-label">{{name}}</span>
          <div class="command-toggle {{state}}" 
               onclick="deviceManager.toggleCommand('{{deviceId}}', '{{commandName}}', '{{type}}')">
          </div>
        </div>
      `
    };
  }

  bindEvents() {
    Utils.events.on('deviceUpdated', () => this.renderDevices());
    Utils.events.on('deviceDeleted', () => this.renderDevices());
    Utils.events.on('commandExecuted', (e) => this.handleCommandResult(e.detail));
  }

  async loadDevices() {
    await Promise.all([
      DataManager.loadDevices(),
      DataManager.loadAutomations()
    ]);
    this.renderDevices();
  }

  renderDevices() {
    if (!this.element) return;

    const devices = DataManager.getAllDevices();

    if (devices.length === 0) {
      this.element.innerHTML = `
        <div class="empty-state">
          <h3>No devices found</h3>
          <p>Add your first device to get started</p>
        </div>
        <div class="devices-grid">
          ${this.template('addDeviceCard')}
        </div>
        <div id="storedCodesSection"></div>
      `;
    } else {
      const devicesHTML = devices.map(device => this.renderDeviceCard(device)).join('');
      this.element.innerHTML = `
        <div class="devices-grid">
          ${devicesHTML}
          ${this.template('addDeviceCard')}
        </div>
        <div id="storedCodesSection"></div>
      `;
    }

    this._renderStoredCodesIntoSection(this.storedCodes);

    this._syncEntityStates();
  }

  async _syncEntityStates() {
    try {
      const result = await WSManager.call('whispeer/get_entity_states');
      const states = result?.states || {};
      const domainStates = result?.domain_states || {};
      for (const [key, state] of Object.entries(states)) {
        const wrapper = document.querySelector(`[data-entity="${key}"]`);
        if (wrapper) {
          const toggle = wrapper.querySelector('.command-toggle');
          if (toggle) {
            toggle.classList.toggle('on', state === 'on');
            toggle.classList.toggle('off', state !== 'on');
            continue;
          }
        }

        const colonIdx = key.indexOf(':');
        if (colonIdx === -1) continue;
        const deviceId = key.substring(0, colonIdx);
        const commandName = key.substring(colonIdx + 1);
        this.updateGroupCommandState(deviceId, commandName, state);
      }

      for (const [key, payload] of Object.entries(domainStates)) {
        const colonIdx = key.indexOf(':');
        if (colonIdx === -1) continue;
        const deviceId = key.substring(0, colonIdx);
        const commandName = key.substring(colonIdx + 1);
        this.applyDomainStateUpdate(deviceId, commandName, payload);
      }
    } catch (e) {
      console.warn('[DeviceManager] Failed to sync entity states:', e);
    }
  }

  applyDomainStateUpdate(deviceId, commandName, payload) {
    const device = DataManager.getDevice(deviceId);
    if (!device || !device.domain) return;

    if (commandName === 'climate') {
      this._applyClimateEntityState(deviceId, payload);
      return;
    }
    if (commandName === 'fan') {
      this._applyFanEntityState(deviceId, payload);
      return;
    }
    if (commandName === 'media_player') {
      this._applyMediaPlayerEntityState(deviceId, payload);
      return;
    }
    if (commandName === 'domain_light') {
      this._applyDomainLightEntityState(deviceId, payload);
    }
  }

  _applyClimateEntityState(deviceId, payload) {
    const device = DataManager.getDevice(deviceId);
    if (!device || device.domain !== 'climate') return;

    const st = this._getClimateCardState(deviceId);
    const attrs = payload?.attributes || {};
    const hvacRaw = String(payload?.state || '').toLowerCase();

    st.on = hvacRaw !== 'off' && hvacRaw !== 'unknown' && hvacRaw !== 'unavailable' && !!hvacRaw;

    const cfg = device.config || {};
    const modes = cfg.modes || [];
    const fans = cfg.fan_modes || [];
    const minT = parseInt(cfg.min_temp ?? 16);
    const maxT = parseInt(cfg.max_temp ?? 30);

    if (modes.includes(hvacRaw)) {
      st.mode = hvacRaw;
    }

    if (typeof attrs.fan_mode === 'string' && fans.includes(attrs.fan_mode)) {
      st.fan = attrs.fan_mode;
    }

    const temp = Number(attrs.temperature);
    if (!Number.isNaN(temp)) {
      st.temp = Math.max(minT, Math.min(maxT, Math.round(temp)));
    }

    this._climateUpdateCardUI(deviceId);
  }

  _applyFanEntityState(deviceId, payload) {
    const device = DataManager.getDevice(deviceId);
    if (!device || device.domain !== 'fan') return;

    const attrs = payload?.attributes || {};
    const isOn = String(payload?.state || '').toLowerCase() === 'on';

    const toggle = document.querySelector(`[data-fan-power="${deviceId}"] .command-toggle`);
    if (toggle) {
      toggle.classList.toggle('on', isOn);
      toggle.classList.toggle('off', !isOn);
    }

    const speedButtons = document.querySelectorAll(`[data-fan-speeds="${deviceId}"] .btn-group-item`);
    speedButtons.forEach(btn => btn.classList.remove('active'));

    const model = device.config?.fan_model || 'direct';
    if (!isOn) return;

    if (model === 'direct') {
      const preset = String(attrs.preset_mode || '');
      speedButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.speed === preset);
      });
      return;
    }

    const percentage = Number(attrs.percentage);
    const count = Number(device.config?.speeds_count || speedButtons.length || 1);
    if (Number.isNaN(percentage) || count <= 0) return;
    const level = Math.max(1, Math.min(count, Math.round((percentage / 100) * count)));
    speedButtons.forEach(btn => {
      btn.classList.toggle('active', Number(btn.dataset.level) === level);
    });
  }

  _applyMediaPlayerEntityState(deviceId, payload) {
    const device = DataManager.getDevice(deviceId);
    if (!device || device.domain !== 'media_player') return;

    const isOn = String(payload?.state || '').toLowerCase() === 'on';
    const attrs = payload?.attributes || {};
    const source = String(attrs.source || '');

    const powerButtons = document.querySelectorAll(`.device-card[data-device-id="${deviceId}"] .btn`);
    powerButtons.forEach(btn => {
      const text = (btn.textContent || '').toLowerCase();
      if (text.includes('on')) {
        btn.classList.toggle('active', isOn);
      } else if (text.includes('off')) {
        btn.classList.toggle('active', !isOn);
      }
    });

    document.querySelectorAll(`.device-card[data-device-id="${deviceId}"] .btn-group-item`).forEach(btn => {
      const label = (btn.textContent || '').trim();
      btn.classList.toggle('active', !!source && label === source);
    });
  }

  _applyDomainLightEntityState(deviceId, payload) {
    const device = DataManager.getDevice(deviceId);
    if (!device || device.domain !== 'light') return;
    const isOn = String(payload?.state || '').toLowerCase() === 'on';
    document.querySelectorAll(`.device-card[data-device-id="${deviceId}"] .btn`).forEach(btn => {
      const text = (btn.textContent || '').toLowerCase();
      if (text.includes('on')) {
        btn.classList.toggle('active', isOn);
      } else if (text.includes('off')) {
        btn.classList.toggle('active', !isOn);
      }
    });
  }

  renderDeviceCard(device) {
    const { id, name, commands = {} } = device;
    const domain = device.domain || 'default';
    const deviceTypeConfig = APP_CONFIG.DEVICE_TYPES[device.type] || { label: (device.type || '').toUpperCase(), badge: 'type-ir' };
    const typePrefix = deviceTypeConfig.label || (device.type || '').toUpperCase();
    const configureId = this._escapeJsSingleQuote(id);

    let typeLabel, badgeClass, commandsHTML;
    if (domain !== 'default') {
      const domainConfig = APP_CONFIG.DEVICE_DOMAINS[domain] || { label: domain, badge: 'type-ir' };
      typeLabel = `${typePrefix} ${domainConfig.label} ⚙️`;
      badgeClass = deviceTypeConfig.badge;
      if (domain === 'climate') {
        commandsHTML = this._renderClimateCard(device);
      } else if (domain === 'fan') {
        commandsHTML = this._renderFanCard(device);
      } else if (domain === 'media_player') {
        commandsHTML = this._renderMediaPlayerCard(device);
      } else if (domain === 'light') {
        commandsHTML = this._renderLightCard(device);
      } else {
        const genericCommands = this._domainToGenericCommands(domain, device);
        commandsHTML = this.renderDeviceCommands({ ...device, commands: genericCommands });
      }
    } else {
      typeLabel = `${typePrefix} ⚙️`;
      badgeClass = deviceTypeConfig.badge;
      commandsHTML = this.renderDeviceCommands(device);
    }

    const automations = DataManager.getDeviceAutomations(id);
    const automationBadge = automations.length > 0
      ? `<span class="automation-count-badge" title="${automations.length} automation(s)">${automations.length}</span>`
      : '';

    return this.template('deviceCard', {
      id,
      configureId,
      name,
      type: typeLabel,
      badgeClass,
      commands: commandsHTML,
      automationBadge
    });
  }

  _createCommand(type, values, props = {}) {
    return { type, values: values || {}, props: props || {} };
  }

  _domainToGenericCommands(domain, device) {
    const config = device?.config || {};
    const commands = device?.commands || {};

    if (domain === 'fan') {
      const out = {};
      out.off = this._createCommand('button', { code: commands.off || '' }, { display: 'text', icon: '' });
      const speedMap = (commands.speeds && typeof commands.speeds === 'object')
        ? commands.speeds
        : ((commands.forward && typeof commands.forward === 'object') ? commands.forward : commands);
      const speeds = config.fan_model === 'incremental'
        ? Array.from({ length: Number(config.speeds_count || 3) }, (_, i) => String(i + 1))
        : ((config.speeds && config.speeds.length > 0)
          ? config.speeds
          : (Object.keys(speedMap).filter(k => k !== 'off' && k !== 'forward' && k !== 'reverse').length > 0
            ? Object.keys(speedMap).filter(k => k !== 'off' && k !== 'forward' && k !== 'reverse')
            : ['low', 'medium', 'high']));
      const values = {};
      for (const s of speeds) {
        const code = config.fan_model === 'incremental' ? commands.speed : speedMap[s];
        values[s] = code || '';
      }
      out.speed = this._createCommand('options', values, { display: 'text', icon: '' });
      for (const [key, value] of Object.entries(commands)) {
        if (['off', 'power', 'speed', 'default', 'forward', 'reverse', 'speeds'].includes(key)) continue;
        if (speeds.includes(key)) continue;
        if (typeof value === 'string') {
          out[key] = this._createCommand('button', { code: value }, { display: 'text', icon: '' });
        }
      }
      return out;
    }

    if (domain === 'media_player') {
      const out = {};
      out.power = this._createCommand('switch', {
        on: commands.on || '',
        off: commands.off || '',
      }, { display: 'text', icon: '' });
      out.volume = this._createCommand('options', {
        mute: commands.mute || '',
        up: commands.volumeUp || '',
        down: commands.volumeDown || '',
      }, { display: 'text', icon: '' });
      out.channel = this._createCommand('group', {
        prev: commands.previousChannel || '',
        next: commands.nextChannel || '',
      }, { display: 'text', icon: '' });
      out.source = this._createCommand('options', commands.sources || {}, { display: 'text', icon: '' });
      return out;
    }

    if (domain === 'light') {
      return {
        power: this._createCommand('light', {
          on: commands.on || '',
          off: commands.off || '',
        }, { display: 'text', icon: '' }),
        scene: this._createCommand('options', {
          brighten: commands.brighten || '',
          dim: commands.dim || '',
          colder: commands.colder || '',
          warmer: commands.warmer || '',
          night: commands.night || '',
        }, { display: 'text', icon: '' }),
      };
    }

    return device?.commands || {};
  }

  _genericToDomainCommands(domain, genericCommands = {}) {
    if (domain === 'fan') {
      const outCommands = { speeds: {} };
      const cfg = { fan_model: 'direct', speeds: [] };

      const offCommand = genericCommands.off || genericCommands.power;
      if (offCommand?.type === 'button') outCommands.off = offCommand.values?.code || '';
      if (offCommand?.type === 'switch') outCommands.off = offCommand.values?.off || '';

      const speed = genericCommands.speed;
      const values = speed?.values || {};
      cfg.speeds = Object.keys(values).filter(k => values[k] !== undefined);
      for (const [k, v] of Object.entries(values)) {
        if ((v || '').trim() !== '') {
          outCommands.speeds[k] = v;
        }
      }

      for (const [key, cmd] of Object.entries(genericCommands)) {
        if (['off', 'power', 'speed', 'reverse_speed'].includes(key)) continue;
        if (cmd?.type === 'button') {
          outCommands[key] = cmd.values?.code || '';
        }
      }

      if (Object.keys(outCommands.speeds).length === 0) {
        delete outCommands.speeds;
      }

      return { config: cfg, commands: outCommands, table: {} };
    }

    if (domain === 'media_player') {
      const outCommands = {};
      const power = genericCommands.power?.values || {};
      outCommands.on = power.on || '';
      outCommands.off = power.off || '';

      const volume = genericCommands.volume?.values || {};
      outCommands.mute = volume.mute || '';
      outCommands.volumeUp = volume.up || '';
      outCommands.volumeDown = volume.down || '';

      const channel = genericCommands.channel?.values || {};
      outCommands.previousChannel = channel.prev || '';
      outCommands.nextChannel = channel.next || '';

      outCommands.sources = genericCommands.source?.values || {};
      return { config: null, commands: outCommands, table: {} };
    }

    if (domain === 'light') {
      const outCommands = {};
      const power = genericCommands.power?.values || {};
      outCommands.on = power.on || '';
      outCommands.off = power.off || '';

      const scene = genericCommands.scene?.values || {};
      outCommands.brighten = scene.brighten || '';
      outCommands.dim = scene.dim || '';
      outCommands.colder = scene.colder || '';
      outCommands.warmer = scene.warmer || '';
      outCommands.night = scene.night || '';
      return { config: null, commands: outCommands, table: {} };
    }

    return { config: null, commands: genericCommands, table: {} };
  }


  async loadAndRenderStoredCodes() {
    const section = document.getElementById('storedCodesSection');
    if (section) {
      section.innerHTML = '<div class="stored-codes-loading">Loading stored codes…</div>';
    }
    try {
      const result = await WSManager.call('whispeer/get_stored_codes');
      this.storedCodes = result?.codes || [];
    } catch (e) {
      console.error('Failed to load stored codes:', e);
      this.storedCodes = [];
    }
    this._renderStoredCodesIntoSection(this.storedCodes);
  }

  _renderStoredCodesIntoSection(codes) {
    const section = document.getElementById('storedCodesSection');
    if (!section) return;

    if (!codes) {
      section.innerHTML = '';
      return;
    }

    this._storedCodesFlat = codes.slice();

    const grouped = {};
    codes.forEach(c => {
      if (!grouped[c.device]) grouped[c.device] = [];
      grouped[c.device].push(c);
    });

    const cardsHTML = Object.entries(grouped).map(([device, cmds]) => {
      const commandsHTML = cmds.map(c => {
        const idx = this._storedCodesFlat.indexOf(c);
        const codeType = this._detectCodeType(c.code);
        const typeBadge = codeType
          ? `<span class="cmd-type-badge type-${codeType}">${codeType.toUpperCase()}</span>`
          : '';
        const tooltip = `${c.identifier} | ${c.source} | ${c.code_preview}`;
        return `<button class="btn btn-small command-btn stored-cmd-btn"
                        title="${this._escapeAttr(tooltip)}"
                        onclick="deviceManager.executeStoredCommandByIndex(${idx})">
                  ${this._escapeHtml(c.command)}${typeBadge}
                </button>`;
      }).join('');

      return `<div class="device-card stored-device-card">
        <div class="device-header">
          <div class="device-name">${this._escapeHtml(device)}</div>
        </div>
        <div class="device-commands">${commandsHTML}</div>
      </div>`;
    }).join('');

    const noCodesMsg = cardsHTML
      ? ''
      : '<p class="no-stored-codes">No stored codes found</p>';

    section.innerHTML = `
      <hr class="stored-codes-divider">
      <div class="stored-codes-header">
        <h3 class="stored-codes-title">Existing codes in Home Assistant</h3>
      </div>
      <div class="devices-grid">
        ${cardsHTML}${noCodesMsg}
      </div>
    `;
  }

  executeStoredCommandByIndex(index) {
    const c = this._storedCodesFlat[index];
    if (!c) {
      Notification.error('Stored command not found');
      return;
    }
    this.executeStoredCommand(c.identifier, c.source, c.device, c.command, c.code);
  }

  async executeStoredCommand(identifier, source, device, command, code) {
    try {
      const result = await WSManager.call('whispeer/send_stored_code', {
        identifier,
        source,
        device,
        command,
        code,
      });
      if (result?.status === 'success') {
        Notification.success(`Command "${command}" executed successfully`);
      } else {
        throw new Error(result?.message || 'Command failed');
      }
    } catch (error) {
      Notification.error(`Failed to execute command: ${error.message}`);
      console.error('Stored command error:', error);
    }
  }

  _detectCodeType(code) {
    if (!code || code.length < 4) return null;
    try {
      const b64 = code.replace(/-/g, '+').replace(/_/g, '/');
      const decoded = atob(b64.substring(0, 4));
      return decoded.charCodeAt(0) === 0x26 ? 'ir' : 'rf';
    } catch (e) {
      return null;
    }
  }

  _renderAutomationsSection(deviceId) {
    const automations = DataManager.getDeviceAutomations(deviceId);
    if (!automations || automations.length === 0) return '';

    const items = automations.map(a => {
      const href = a.id ? `/config/automation/edit/${a.id}` : null;
      const label = this._escapeHtml(a.name || a.entity_id || a.id);
      const content = href
        ? `<a class="automation-link" href="${href}" target="_top">${label}</a>`
        : `<span>${label}</span>`;
      return `<li class="automation-list-item">${content}</li>`;
    }).join('');

    return `
      <div class="device-automations-section">
        <h4 class="device-automations-title">Automations using this device</h4>
        <ul class="device-automations-list">${items}</ul>
      </div>
    `;
  }

  _escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  _escapeAttr(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }


  renderDeviceCommands(device) {
    const { commands = {}, id } = device;
    const commandsByType = CommandManager.getCommandsByType(commands);
    
    let html = '';
    
    Object.entries(commandsByType).forEach(([type, typeCommands]) => {
      Object.entries(typeCommands).forEach(([name, command]) => {
        html += this.renderCommandControl(id, name, command);
      });
    });

    return html;
  }

  renderCommandControl(deviceId, commandName, command) {
    const { type, props = {} } = command;

    switch (type) {
      case 'button':
        return this.renderButtonCommand(deviceId, commandName, command);
      case 'light':
      case 'switch':
        return this.renderToggleCommand(deviceId, commandName, command);
      case 'numeric':
        return this.renderNumericCommand(deviceId, commandName, command);
      case 'group':
      case 'options':
        return this.renderGroupCommand(deviceId, commandName, command);
      default:
        return this.renderButtonCommand(deviceId, commandName, command);
    }
  }

  renderButtonCommand(deviceId, commandName, command) {
    const { props = {} } = command;
    const color = props.color || '#03a9f4';
    const icon = props.icon || '';
    const display = props.display || 'both';
    
    let buttonContent = '';
    if (display === 'icon') {
      buttonContent = icon;
    } else if (display === 'text') {
      buttonContent = commandName;
    } else {
      buttonContent = `${icon} ${commandName}`;
    }

    return this.template('commandButton', {
      deviceId,
      commandName,
      buttonStyle: `background-color: ${color}`,
      buttonContent
    });
  }

  renderToggleCommand(deviceId, commandName, command) {
    return this.template('commandToggle', {
      deviceId,
      commandName,
      name: commandName,
      type: command.type,
      state: 'off'
    });
  }

  renderNumericCommand(deviceId, commandName, command) {
    const { values = {} } = command;
    const optionButtons = Object.entries(values).map(([key, value]) => 
      `<button class="btn-group-item" 
               onclick="deviceManager.executeCommand('${deviceId}', '${commandName}:${key}')"
               data-value="${value}"
               data-command="${commandName}"
               data-option="${key}">
         ${key}
       </button>`
    ).join('');

    return `
      <div class="input-group-container" data-command="${commandName}">
        <div class="input-group-prepend">
          <span class="input-group-text">${commandName}</span>
        </div>
        <div class="btn-group-wrapper">
          <div class="btn-group" data-command="${commandName}">${optionButtons}</div>
        </div>
      </div>
    `;
  }

  renderGroupCommand(deviceId, commandName, command) {
    const { values = {} } = command;
    const optionButtons = Object.entries(values).map(([key, value]) => 
      `<button class="btn-group-item" 
               onclick="deviceManager.executeCommand('${deviceId}', '${commandName}:${key}')"
               data-value="${value}"
               data-command="${commandName}"
               data-option="${key}">
         ${key}
       </button>`
    ).join('');

    return `
      <div class="input-group-container" data-command="${commandName}">
        <div class="input-group-prepend">
          <span class="input-group-text">${commandName}</span>
        </div>
        <div class="btn-group-wrapper">
          <div class="btn-group" data-command="${commandName}">${optionButtons}</div>
        </div>
      </div>
    `;
  }

  async executeCommand(deviceId, commandName) {
    try {
      const device = DataManager.getDevice(deviceId);
      if (!device || !device.commands) {
        throw new Error('Device or command not found');
      }

      const [cmd, subCmd] = commandName.split(':');
      const command = device.commands[cmd];
      
      if (!command) {
        throw new Error(`Command "${cmd}" not found`);
      }

      let commandCode;
      
      if (command.type === 'button') {
        commandCode = command.values?.code;
      } else if (command.type === 'light' || command.type === 'switch') {
        commandCode = subCmd === 'on' ? command.values?.on : command.values?.off;
      } else if (command.type === 'numeric' || command.type === 'options' || command.type === 'group') {
        commandCode = command.values?.[subCmd];
      } else {
        commandCode = command.values?.code || subCmd;
      }

      if (!commandCode) {
        throw new Error(`No command code found for "${commandName}"`);
      }

      await DataManager.sendCommand(deviceId, device.type, cmd, commandCode, subCmd);

      Notification.success(`Command "${commandName}" executed successfully`);
      Utils.events.emit('commandExecuted', { deviceId, commandName, success: true });
    } catch (error) {
      Notification.error(`Failed to execute command: ${error.message}`);
      Utils.events.emit('commandExecuted', { deviceId, commandName, success: false, error });
    }
  }

  async toggleCommand(deviceId, commandName, type) {
    const toggleElement = event.target;
    const currentState = toggleElement.classList.contains('on') ? 'off' : 'on';
    const subCommand = currentState;

    try {
      const device = DataManager.getDevice(deviceId);
      if (!device || !device.commands) {
        throw new Error('Device or command not found');
      }

      const command = device.commands[commandName];
      if (!command) {
        throw new Error(`Command "${commandName}" not found`);
      }

      const commandCode = currentState === 'on' ? command.values?.on : command.values?.off;
      if (!commandCode) {
        throw new Error(`No command code found for "${commandName}:${currentState}"`);
      }

      await DataManager.sendCommand(deviceId, device.type, commandName, commandCode, subCommand);
      Notification.success(`${commandName} turned ${currentState}`);
    } catch (error) {
      Notification.error(`Failed to toggle ${commandName}: ${error.message}`);
    }
  }

  updateGroupCommandState(deviceId, commandName, selectedOption) {
    const deviceCard = document.querySelector(`[data-device-id="${deviceId}"]`);
    if (!deviceCard) return;

    const commandContainer = deviceCard.querySelector(`[data-command="${commandName}"]`);
    if (!commandContainer) return;

    const allButtons = commandContainer.querySelectorAll('.btn-group-item');
    allButtons.forEach(btn => btn.classList.remove('active'));

    const selectedButton = commandContainer.querySelector(`[data-option="${selectedOption}"]`);
    if (selectedButton) {
      selectedButton.classList.add('active');
    }
  }

  createSampleCommands() {
    return {
      'sample_button': {
        type: 'button',
        values: {
          code: ''
        },
        props: {
          shape: 'rounded',
          color: '#03a9f4'
        }
      },
    };
  }

  openAddDeviceModal() {
    this.currentDevice = null;
    this.tempCommands = this.createSampleCommands();
    this._climateData = null;
    this.showDeviceModal('Add Device', {});
  }

  configureDevice(deviceId) {
    const device = DataManager.getDevice(deviceId);
    if (!device) {
      Notification.error('Device not found');
      return;
    }

    this.currentDevice = device;
    const domain = device.domain || 'default';
    this.tempCommands = domain === 'default'
      ? Utils.deepClone(device.commands || {})
      : this._domainToGenericCommands(domain, device);
    this._climateData = domain !== 'default' ? {
      config: Utils.deepClone(device.config || {}),
      table: Utils.deepClone(device.table || {}),
      commands: Utils.deepClone(device.commands || {}),
      source: device.source || 'scratch',
      sensors: Utils.deepClone(device.sensors || {}),
      _smartirNum: device._smartirNum || ''
    } : null;
    this.showDeviceModal('Edit Device', device);

    DataManager.loadAutomations().then(() => {
      const section = document.querySelector('.device-automations-section');
      const modalBody = document.querySelector('.device-modal .modal-body');
      if (!modalBody) return;

      const newSection = this._renderAutomationsSection(deviceId);

      if (section) {
        section.outerHTML = newSection || '';
      } else if (newSection) {
        modalBody.insertAdjacentHTML('beforeend', newSection);
      }
    }).catch(() => {});
  }

  showDeviceModal(title, device = {}) {
    const isEdit = !!device.id;
    const formFields = this.buildDeviceForm(device);
    const commandsList = this.renderCommandsList(this.tempCommands);

    const deleteButton = isEdit ?
      '<button type="button" class="btn btn-delete" onclick="deviceManager.deleteDevice()">Delete Device</button>' : '';

    const automationsSection = isEdit ? this._renderAutomationsSection(device.id) : '';

    const modalContent = this.template('deviceForm', {
      title,
      formFields,
      commandsList,
      deleteButton,
      saveButtonText: isEdit ? 'Save Changes' : 'Save',
      automationsSection
    });

    if (!this.deviceModal) {
      this.deviceModal = new Modal({
        title,
        content: modalContent,
        className: 'device-modal'
      });
    } else {
      this.deviceModal.setTitle(title);
      this.deviceModal.setContent(modalContent);
    }

    this.deviceModal.open();
    this.bindDeviceModalEvents();
  }

  buildDeviceForm(device = {}) {
    const deviceDomain = device.domain || 'default';
    const deviceType = device.type || 'ir';

    const domainOptions = [
      { value: 'default',      label: 'Default (commands)' },
      { value: 'climate',      label: 'Climate' },
      { value: 'fan',          label: 'Fan' },
      { value: 'media_player', label: 'Media Player' },
      { value: 'light',        label: 'Light' },
    ].map(opt =>
      `<option value="${opt.value}"${opt.value === deviceDomain ? ' selected' : ''}>${opt.label}</option>`
    ).join('');

    const typeOptions = [
      { value: 'ir',  label: 'Infrared' },
      { value: 'rf',  label: 'Radio Frequency' },
      { value: 'ble', label: 'Bluetooth LE' },
    ].map(opt =>
      `<option value="${opt.value}"${opt.value === deviceType ? ' selected' : ''}>${opt.label}</option>`
    ).join('');

    const emitInterval = (device.emit_interval !== undefined && device.emit_interval !== null && device.emit_interval !== '')
      ? device.emit_interval : '';

    const frequency = (device.frequency !== undefined && device.frequency !== null && device.frequency !== '')
      ? device.frequency : '';

    const showFrequency = deviceType === 'rf';
    const showCommunity = deviceDomain !== 'default' && deviceType === 'ir';
    const communityCode = (device._smartirNum !== undefined && device._smartirNum !== null)
      ? String(device._smartirNum)
      : '';
    const docsUrl = this._getSmartIRDocsUrl(deviceDomain);

    const frequencyField = `
      <div class="device-field-group ${showFrequency ? '' : 'hidden'}" id="frequencyField" data-field="frequency">
        <div class="input-group">
          <div class="input-group-prepend">
            <label class="input-group-text" for="deviceFrequency">Frequency</label>
          </div>
          <input type="number" id="deviceFrequency" name="frequency" class="form-input" step="any"
                 placeholder="e.g. 433.92"
                 value="${this._escapeAttr(String(frequency))}">
          <button type="button" class="input-group-append-btn" id="findFrequencyBtn"
                  onclick="deviceManager.findFrequency()">Find</button>
        </div>
      </div>
    `;

    const communityField = `
      <div class="device-field-group ${showCommunity ? '' : 'hidden'}" id="communityField" data-field="community">
        <div class="input-group">
          <div class="input-group-prepend">
            <label class="input-group-text" for="smartirCommunityCode">Community code <a id="communityHelpLink" href="${this._escapeAttr(docsUrl)}" target="_blank" rel="noopener">(?)</a></label>
          </div>
          <input type="text" id="smartirCommunityCode" class="form-input" placeholder="e.g. 1120"
                 value="${this._escapeAttr(communityCode)}">
          <button type="button" class="input-group-append-btn" id="communityImportBtn"
                  onclick="deviceManager._importSmartIR()">Import</button>
        </div>
      </div>
    `;

    return `
      <div class="device-fields-wrap">
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <label class="input-group-text" for="deviceName">Name</label>
            </div>
            <input type="text" id="deviceName" name="name" class="form-input" placeholder="Device name"
                   value="${this._escapeAttr(device.name || '')}" required>
          </div>
        </div>
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <label class="input-group-text" for="deviceDomain">Domain</label>
            </div>
            <select id="deviceDomain" name="domain" class="form-select">
              ${domainOptions}
            </select>
          </div>
        </div>
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <label class="input-group-text" for="deviceType">Type</label>
            </div>
            <select id="deviceType" name="type" class="form-select">
              ${typeOptions}
            </select>
          </div>
        </div>
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <label class="input-group-text" for="deviceInterface">Learn/Send from</label>
            </div>
            <select id="deviceInterface" name="interface" class="form-select">
              <option value="">&#8987; Loading...</option>
            </select>
          </div>
        </div>
        ${frequencyField}
        ${communityField}
        <div class="device-field-group hidden" data-field="emit_interval">
          <div class="input-group">
            <div class="input-group-prepend">
              <label class="input-group-text" for="deviceEmitInterval">Emit interval</label>
            </div>
            <input type="number" id="deviceEmitInterval" name="emit_interval" class="form-input"
                   placeholder="0.4" step="any" min="0"
                   value="${this._escapeAttr(String(emitInterval))}">
          </div>
        </div>
        <div class="device-field-row" id="broadlinkToolsRow" style="display:none">
        </div>
      </div>
      <input type="hidden" name="id" value="${this._escapeAttr(device.id || '')}">
    `;
  }

  renderCommandsList(commands) {
    if (Utils.isEmpty(commands)) {
      commands = this.createSampleCommands();
    }

    let html = '';
    
    Object.entries(commands).forEach(([name, command]) => {
      const commandWithName = { ...command, name };
      html += this.createInlineCommandForm(commandWithName, true);
    });

    return html;
  }

  renderCommandGroupContent(type, commands) {
    let html = '';
    
    Object.entries(commands).forEach(([name, command]) => {
      const commandWithName = { ...command, name };
      html += this.createInlineCommandForm(commandWithName, true);
    });

    return html;
  }

  addInlineCommand() {
    const commandsList = Utils.$('#commandsList');
    if (!commandsList) return;

    const form = this.createInlineCommandForm();
    commandsList.insertAdjacentHTML('beforeend', form);
  }

  openBulkLearnModal() {
    this.openBleScannerModal(false, null);
  }

  _getCurrentDeviceType() {
    const sel = Utils.$('#deviceForm select[name="type"]');
    return sel ? sel.value : '';
  }

  _getCurrentDomain() {
    const sel = Utils.$('#deviceForm select[name="domain"]');
    return sel ? sel.value : 'default';
  }

  _onDomainChange(preserveSelection = false) {
    const domain = this._getCurrentDomain();
    const isDomainManaged = domain === 'climate';
    const deviceType = this._getCurrentDeviceType();

    const fastLearnBtn = document.getElementById('fastLearnBtn');
    if (fastLearnBtn) {
      fastLearnBtn.style.display = (!isDomainManaged && (deviceType === 'ir' || deviceType === 'rf')) ? '' : 'none';
    }
    const bulkLearnBtn = document.getElementById('bulkLearnBtn');
    if (bulkLearnBtn) {
      bulkLearnBtn.style.display = 'none';
    }

    const commandsSection = document.querySelector('#deviceForm .commands-section');
    if (commandsSection) {
      commandsSection.style.display = isDomainManaged ? 'none' : '';
    }

    if (!isDomainManaged && domain !== 'default') {
      this.tempCommands = this._domainToGenericCommands(domain, {
        domain,
        config: this._climateData?.config || {},
        commands: this._climateData?.commands || {},
      });
      this.refreshCommandsList();
    }

    let domainSection = document.getElementById('domainSection');
    if (isDomainManaged) {
      if (!domainSection) {
        domainSection = document.createElement('div');
        domainSection.id = 'domainSection';
        const commandsSectionEl = document.querySelector('#deviceForm .commands-section');
        if (commandsSectionEl) {
          commandsSectionEl.insertAdjacentElement('afterend', domainSection);
        } else {
          document.querySelector('#deviceForm .modal-controls')?.insertAdjacentElement('beforebegin', domainSection);
        }
      }
      domainSection.style.display = '';
      this._renderDomainSection(domainSection, domain);
    } else if (domainSection) {
      domainSection.style.display = 'none';
    }

    this._updateCommunityField();

    this.onDeviceTypeChange(preserveSelection);
  }

  _getSmartIRDocsUrl(domain) {
    if (domain === 'climate') return 'https://github.com/smartHomeHub/SmartIR/blob/master/docs/CLIMATE.md#available-codes-for-climate-devices';
    if (domain === 'fan') return 'https://github.com/smartHomeHub/SmartIR/blob/master/docs/FAN.md#available-codes-for-fan-devices';
    if (domain === 'media_player') return 'https://github.com/smartHomeHub/SmartIR/blob/master/docs/MEDIA_PLAYER.md#available-codes-for-media-player-devices';
    if (domain === 'light') return 'https://github.com/smartHomeHub/SmartIR/tree/master/codes/light';
    return 'https://github.com/smartHomeHub/SmartIR';
  }

  _updateCommunityField() {
    const field = document.getElementById('communityField');
    if (!field) return;
    const domain = this._getCurrentDomain();
    const show = domain !== 'default' && this._getCurrentDeviceType() === 'ir';
    field.classList.toggle('hidden', !show);
    const link = document.getElementById('communityHelpLink');
    if (link) link.href = this._getSmartIRDocsUrl(domain);
    document.querySelectorAll('.community-hint-link').forEach(el => {
      el.style.display = show ? '' : 'none';
    });
  }

  focusCommunityCode() {
    const input = document.getElementById('smartirCommunityCode');
    if (!input) return;
    const field = document.getElementById('communityField');
    if (field) field.classList.remove('hidden');
    input.focus();
    input.select();
  }

  _renderScratchTitle() {
    return `Start from scratch <a href="#" class="community-hint-link" style="display:none" onclick="deviceManager.focusCommunityCode(); return false;">or learn from community</a>`;
  }

  _escapeJsSingleQuote(str) {
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'");
  }

  createInlineCommandForm(command = null, isExisting = false) {
    const name = command?.name || '';
    const type = command?.type || 'button';
    const values = command?.values || {};
    const props = command?.props || {};
    
    const id = Utils.generateId();
    const deleteButton = isExisting
      ? `<button type="button" class="command-inline-btn delete" onclick="deviceManager.deleteCommand('${this._escapeAttr(name)}')">Delete</button>`
      : `<button type="button" class="command-inline-btn delete" onclick="this.closest('.command-container').remove()">Delete</button>`;

    let codeField = '';
    if (type === 'button') {
      const learnButton = `<button type="button" class="command-inline-btn learn" 
                onclick="deviceManager.learnCommand(this)">Learn</button>`;
      
      codeField = `
        <input type="text" class="command-inline-input code" 
               placeholder="code" value="${this._escapeAttr(values.code || '')}" 
               data-field="code">
        ${learnButton}
        <button type="button" class="command-inline-btn test" 
                onclick="deviceManager.testInlineCommand(this)">Test</button>
      `;
    }

    const config = APP_CONFIG.COMMAND_TYPES[type];
    
    let optionsSection = '';
    if (config && config.hasOptions) {
      const options = values || {};
      let optionsHtml = '';
      
      if (type === 'light' || type === 'switch') {
        const learnButtonOn = `<button type="button" class="command-inline-btn learn" 
                  onclick="deviceManager.learnOptionCommand(this, 'on')">Learn</button>`;
        const learnButtonOff = `<button type="button" class="command-inline-btn learn" 
                  onclick="deviceManager.learnOptionCommand(this, 'off')">Learn</button>`;
        
        optionsHtml += `
          <div class="option-field">
            <input type="text" value="on" readonly class="command-inline-input">
            <input type="text" placeholder="On command code" value="${options.on || ''}" class="command-inline-input" data-option="on">
            ${learnButtonOn}
            <button type="button" class="command-inline-btn test" 
                    onclick="deviceManager.testOptionCommand(this, 'on')">Test</button>
          </div>
          <div class="option-field">
            <input type="text" value="off" readonly class="command-inline-input">
            <input type="text" placeholder="Off command code" value="${options.off || ''}" class="command-inline-input" data-option="off">
            ${learnButtonOff}
            <button type="button" class="command-inline-btn test" 
                    onclick="deviceManager.testOptionCommand(this, 'off')">Test</button>
          </div>
        `;
      } else if (type === 'numeric' || type === 'options' || type === 'group') {
        const filteredOptions = Object.entries(options).filter(([key, value]) => 
          key !== 'type' && key !== 'props' && key !== 'name'
        );
        
        filteredOptions.forEach(([key, value]) => {
          const learnButton = `<button type="button" class="command-inline-btn learn"
                    onclick="deviceManager.learnOptionCommand(this)">Learn</button>`;

          optionsHtml += `
            <div class="option-field">
              <input type="${type === 'numeric' ? 'number' : 'text'}"
                     placeholder="${type === 'numeric' ? 'Number' : 'Option'}"
                     value="${key}" class="command-inline-input" data-option-key>
              <input type="text" placeholder="Command code" value="${value}" class="command-inline-input" data-option-value>
              ${learnButton}
              <button type="button" class="command-inline-btn test"
                      onclick="deviceManager.testOptionCommand(this, '${key}')">Test</button>
              <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">Delete</button>
            </div>
          `;
        });

        if (filteredOptions.length === 0) {
          const learnButton = `<button type="button" class="command-inline-btn learn"
                    onclick="deviceManager.learnOptionCommand(this)">Learn</button>`;

          optionsHtml += `
            <div class="option-field">
              <input type="${type === 'numeric' ? 'number' : 'text'}"
                     placeholder="${type === 'numeric' ? 'Number' : 'Option'}"
                     value="" class="command-inline-input" data-option-key>
              <input type="text" placeholder="Command code" value="" class="command-inline-input" data-option-value>
              ${learnButton}
              <button type="button" class="command-inline-btn test"
                      onclick="deviceManager.testOptionCommand(this)">Test</button>
              <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">Delete</button>
            </div>
          `;
        }
      }
      
      optionsSection = `
        <div class="command-options-section" data-type="${type}">
          <div class="options-list">
            ${optionsHtml}
          </div>
          ${(type === 'numeric' || type === 'options' || type === 'group') ? 
            `<button type="button" class="btn btn-small" onclick="deviceManager.addOptionField(this, '${type}')">+ Add Option</button>` : ''}
        </div>
      `;
    }

    return `
      <div class="command-container" data-command-id="${id}">
        <div class="command-inline-form">
          <select class="command-inline-select" onchange="deviceManager.onInlineTypeChange(this)">
            ${Object.entries(APP_CONFIG.COMMAND_TYPES).map(([key, config]) => 
              `<option value="${key}" ${key === type ? 'selected' : ''}>${config.title}</option>`
            ).join('')}
          </select>
          <input type="text" class="command-inline-input name" 
                 placeholder="Command name" value="${name}">
          ${isExisting && name ? `<input type="hidden" class="original-command-name" value="${name}">` : ''}
          ${codeField}
          ${deleteButton}
        </div>
        ${optionsSection}
      </div>
    `;
  }

  bindDeviceModalEvents() {
    const deviceForm = Utils.$('#deviceForm');
    if (!deviceForm) return;

    deviceForm.addEventListener('submit', (e) => this.handleDeviceFormSubmit(e));

    const domainSelect = deviceForm.querySelector('select[name="domain"]');
    if (domainSelect) {
      domainSelect.addEventListener('change', () => this._onDomainChange(false));
    }

    const typeSelect = deviceForm.querySelector('select[name="type"]');
    if (typeSelect) {
      typeSelect.addEventListener('change', () => this.onDeviceTypeChange(false));
      this._onDomainChange(true);
    }

    const interfaceSelect = deviceForm.querySelector('select[name="interface"]');
    if (interfaceSelect) {
      interfaceSelect.addEventListener('change', () => this._updateBroadlinkToolsVisibility());
    }
  }

  async onDeviceTypeChange(preserveSelection = false) {
    const typeSelect = Utils.$('#deviceForm select[name="type"]');
    const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');

    if (!typeSelect || !interfaceSelect) return;

    const deviceType = typeSelect.value;
    const domain = this._getCurrentDomain();
    const isDomainManaged = domain !== 'default';

    const fastLearnBtn = document.getElementById('fastLearnBtn');
    if (fastLearnBtn) {
      fastLearnBtn.style.display = (!isDomainManaged && (deviceType === 'ir' || deviceType === 'rf')) ? '' : 'none';
    }
    const bulkLearnBtn = document.getElementById('bulkLearnBtn');
    if (bulkLearnBtn) {
      bulkLearnBtn.style.display = 'none';
    }

    const currentDevice = this.currentDevice;

    interfaceSelect.innerHTML = '<option value="">⏳ Loading interfaces...</option>';
    interfaceSelect.disabled = true;

    const interfaceDeviceType = isDomainManaged || domain !== 'default' ? 'ir' : deviceType;

    try {
      const interfaces = await DataManager.loadInterfaces(interfaceDeviceType);

      interfaceSelect.disabled = false;

      if (interfaces && interfaces.length > 0) {
        let selectedIndex = null;

        interfaceSelect.innerHTML = interfaces.map((iface, index) => {
          if (typeof iface === 'object' && iface.label) {
            const interfaceData = JSON.stringify(iface).replace(/"/g, '&quot;');

            let shouldSelect = false;
            if (preserveSelection && currentDevice && currentDevice.emitter) {
              if (currentDevice.emitter.entity_id && iface.entity_id === currentDevice.emitter.entity_id) {
                shouldSelect = true;
                selectedIndex = index;
              }
            }

            return `<option value="${index}" data-interface="${interfaceData}" ${shouldSelect ? 'selected' : ''}>${iface.label}</option>`;
          } else {
            console.error('Invalid interface object, missing label:', iface);
            return '';
          }
        }).filter(option => option).join('');

        if (selectedIndex !== null) {
          interfaceSelect.value = selectedIndex.toString();
        }
      } else {
        interfaceSelect.innerHTML = '<option value="">❌ No interfaces available</option>';
        console.log(`No interfaces found for device type: ${interfaceDeviceType}`);
      }
    } catch (error) {
      console.error('Failed to load interfaces:', error);

      interfaceSelect.disabled = false;

      interfaceSelect.innerHTML = '<option value="">⚠️ Error loading interfaces</option>';
      Notification.error('Failed to load interfaces');
    }

    this._updateFrequencyField(deviceType);
    this._updateCommunityField();
    this._updateBroadlinkToolsVisibility();
  }

  _updateFrequencyField(deviceType) {
    const freqField = document.getElementById('frequencyField');
    const broadlinkToolsRow = document.getElementById('broadlinkToolsRow');

    const freq = this.currentDevice?.frequency || this._detectedFrequency || '';
    if (freqField) {
      const show = deviceType === 'rf';
      freqField.classList.toggle('hidden', !show);
      if (show && (freq !== '' && freq != null)) {
        const freqInput = freqField.querySelector('input[name="frequency"]');
        if (freqInput) freqInput.value = freq;
      }
    }

    this._updateBroadlinkToolsVisibility();
  }

  _updateBroadlinkToolsVisibility() {
    const broadlinkToolsRow = document.getElementById('broadlinkToolsRow');
    if (!broadlinkToolsRow) return;

    const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
    const typeSelect = Utils.$('#deviceForm select[name="type"]');
    const deviceType = typeSelect ? typeSelect.value : '';

    let isBroadlink = false;
    if (interfaceSelect) {
      const selectedOpt = interfaceSelect.options[interfaceSelect.selectedIndex];
      if (selectedOpt && selectedOpt.dataset.interface) {
        try {
          const ifaceObj = JSON.parse(selectedOpt.dataset.interface.replace(/&quot;/g, '"'));
          isBroadlink = (ifaceObj.manufacturer || '').toLowerCase().includes('broadlink');
        } catch (_) {}
      }
    }

    const show = isBroadlink && (deviceType === 'rf');
    broadlinkToolsRow.style.display = show ? '' : 'none';

  }

  async handleDeviceFormSubmit(e) {
    e.preventDefault();
    this.stopFastLearn();
    this.saveAllInlineCommands();

    const formData = new FormData(e.target);
    const deviceData = Object.fromEntries(formData.entries());
    deviceData.commands = this.tempCommands;

    const deviceDomain = deviceData.domain || 'default';
    if (deviceDomain === 'climate') {
      const domainData = this._collectDomainData(deviceDomain);
      if (domainData) {
        deviceData.config = domainData.config;
        if (domainData.table && Object.keys(domainData.table).length > 0) {
          deviceData.table = domainData.table;
        }
        deviceData.commands = domainData.commands;
        deviceData.source = domainData.source;
        if (deviceDomain === 'climate') {
          deviceData.sensors = domainData.sensors;
        }
      }
    } else if (deviceDomain !== 'default') {
      const mapped = this._genericToDomainCommands(deviceDomain, this.tempCommands);
      deviceData.config = mapped.config;
      deviceData.commands = mapped.commands;
      if (mapped.table && Object.keys(mapped.table).length > 0) {
        deviceData.table = mapped.table;
      } else {
        delete deviceData.table;
      }
      deviceData.source = deviceData.source || 'scratch';
    }

    if (deviceData.emit_interval !== undefined && deviceData.emit_interval !== '') {
      const parsed = parseFloat(deviceData.emit_interval);
      if (isNaN(parsed) || parsed < 0) {
        Notification.error('Emit interval must be a positive number');
        return;
      }
      deviceData.emit_interval = parsed;
    } else {
      delete deviceData.emit_interval;
    }

    const freqInput = e.target.querySelector('input[name="frequency"]');
    if (freqInput && freqInput.value !== '') {
      deviceData.frequency = parseFloat(freqInput.value);
    } else if (this._detectedFrequency != null) {
      deviceData.frequency = this._detectedFrequency;
    }

    const deviceType = deviceData.type;
    const interfaceIndex = deviceData.interface;
    
    if (interfaceIndex !== '' && interfaceIndex !== undefined) {
      try {
        const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
        const selectedOption = interfaceSelect.options[interfaceIndex];
        
        if (selectedOption && selectedOption.dataset.interface) {
          const interfaceObj = JSON.parse(selectedOption.dataset.interface.replace(/&quot;/g, '"'));
          
          const emitterData = {
            device_type: deviceType,
            interface_index: parseInt(interfaceIndex),
            ...interfaceObj
          };
          
          deviceData.interface = interfaceObj.label;
          deviceData.emitter = emitterData;
          
          console.log('Saving device with emitter data:', emitterData);
        } else {
          console.warn('Could not find interface data for selected option');
        }
      } catch (error) {
        console.error('Error processing interface data:', error);
      }
    }

    if (this.currentDevice) {
      DataManager.updateDevice(this.currentDevice.id, deviceData);
      Notification.success('Device updated successfully');
    } else {
      DataManager.addDevice(deviceData);
      Notification.success('Device added successfully');
    }

    this.closeDeviceModal();
    this.renderDevices();
    Utils.events.emit('deviceUpdated');
  }

  saveAllInlineCommands() {
    const commandContainers = document.querySelectorAll('#commandsList .command-container');
    commandContainers.forEach(container => {
      this._saveContainerSilent(container);
    });
  }

  saveInlineCommandSilent(button) {
    const container = button.closest('.command-container');
    this._saveContainerSilent(container);
  }

  _saveContainerSilent(container) {
    if (!container) return;
    const form = container.querySelector('.command-inline-form');
    if (!form) return;

    const typeSelect = form.querySelector('.command-inline-select');
    const nameInput = form.querySelector('.command-inline-input.name');
    const originalNameInput = form.querySelector('.original-command-name');
    const codeInputs = form.querySelectorAll('[data-field]');

    const name = nameInput.value.trim();
    const originalName = originalNameInput?.value;
    const type = typeSelect.value;

    if (!name) {
      return;
    }

    const values = {};
    
    codeInputs.forEach(input => {
      values[input.dataset.field] = input.value.trim();
    });

    const optionsSection = container.querySelector('.command-options-section');
    if (optionsSection) {
      const optionFields = optionsSection.querySelectorAll('.option-field');
      
      optionFields.forEach(field => {
        if (type === 'light' || type === 'switch') {
          const optionInput = field.querySelector('[data-option]');
          if (optionInput) {
            const key = optionInput.dataset.option;
            const value = optionInput.value.trim();
            if (key && value) {
              values[key] = value;
            }
          }
        } else {
          const keyInput = field.querySelector('[data-option-key]');
          const valueInput = field.querySelector('[data-option-value]');
          
          if (keyInput && valueInput) {
            const key = keyInput.value.trim();
            const value = valueInput.value.trim();
            
            if (key && value) {
              values[key] = value;
            }
          }
        }
      });
    }

    if (type === 'button' && !values.code) {
      return;
    }

    if ((type === 'light' || type === 'switch') && (!values.on || !values.off)) {
      return;
    }

    try {
      const command = CommandManager.createCommand(type, { name, values });
      const validation = CommandManager.validateCommand(command);

      if (validation.valid) {
        if (originalName && originalName !== name && this.tempCommands[originalName]) {
          const newTempCommands = {};
          Object.keys(this.tempCommands).forEach(key => {
            if (key === originalName) {
              newTempCommands[name] = command;
            } else {
              newTempCommands[key] = this.tempCommands[key];
            }
          });
          this.tempCommands = newTempCommands;
        } else {
          this.tempCommands[name] = command;
        }

        if (originalNameInput) {
          originalNameInput.value = name;
        }
      }
    } catch (error) {
      console.warn('Auto-save failed for command:', name, error);
    }
  }

  saveInlineCommand(button) {
    const container = button.closest('.command-container');
    const form = container.querySelector('.command-inline-form');
    
    const typeSelect = form.querySelector('.command-inline-select');
    const nameInput = form.querySelector('.command-inline-input.name');
    const originalNameInput = form.querySelector('.original-command-name');
    const codeInputs = form.querySelectorAll('[data-field]');

    const name = nameInput.value.trim();
    const originalName = originalNameInput?.value;
    const type = typeSelect.value;

    if (!name) {
      Notification.error('Command name is required');
      return;
    }

    const values = {};
    codeInputs.forEach(input => {
      values[input.dataset.field] = input.value.trim();
    });

    const optionsSection = container.querySelector('.command-options-section');
    if (optionsSection) {
      const optionFields = optionsSection.querySelectorAll('.option-field');
      
      optionFields.forEach(field => {
        if (type === 'light' || type === 'switch') {
          const optionInput = field.querySelector('[data-option]');
          if (optionInput) {
            const key = optionInput.dataset.option;
            const value = optionInput.value.trim();
            if (key && value) {
              values[key] = value;
            }
          }
        } else {
          const keyInput = field.querySelector('[data-option-key]');
          const valueInput = field.querySelector('[data-option-value]');
          
          if (keyInput && valueInput) {
            const key = keyInput.value.trim();
            const value = valueInput.value.trim();
            
            if (key && value) {
              values[key] = value;
            }
          }
        }
      });
    }

    const config = APP_CONFIG.COMMAND_TYPES[type];
    if (config && config.hasOptions && Object.keys(values).length === 0) {
      Notification.error(`Please add at least one option for ${type} command`);
      return;
    }

    if (type === 'button' && !values.code) {
      Notification.error('Button commands require a code');
      return;
    }

    if ((type === 'light' || type === 'switch') && (!values.on || !values.off)) {
      Notification.error('Light/Switch commands require both "on" and "off" options');
      return;
    }

    const command = CommandManager.createCommand(type, { name, values });
    const validation = CommandManager.validateCommand(command);

    if (!validation.valid) {
      Notification.error(validation.errors.join(', '));
      return;
    }

    if (originalName && originalName !== name && this.tempCommands[originalName]) {
      const newTempCommands = {};
      Object.keys(this.tempCommands).forEach(key => {
        if (key === originalName) {
          newTempCommands[name] = command;
        } else {
          newTempCommands[key] = this.tempCommands[key];
        }
      });
      this.tempCommands = newTempCommands;
    } else {
      this.tempCommands[name] = command;
    }

    Notification.success(`Command "${name}" saved`);
    
    if (originalNameInput) {
      originalNameInput.value = name;
    }

    if (!originalName || (originalName && originalName !== name)) {
      this.refreshCommandsList();
    }
  }

  deleteCommand(commandName) {
    this._saveAllContainersSilent(commandName);
    if (this.tempCommands[commandName]) {
      delete this.tempCommands[commandName];
      Notification.success(`Command "${commandName}" deleted`);
      this.refreshCommandsList();
    }
  }

  _saveAllContainersSilent(excludeName) {
    const containers = document.querySelectorAll('#commandsList .command-container');
    containers.forEach(container => {
      const nameInput = container.querySelector('.command-inline-input.name');
      const name = nameInput?.value.trim();
      if (!name || name === excludeName) return;
      this._saveContainerSilent(container);
    });
  }

  async testInlineCommand(button) {
    const container = button.closest('.command-container');
    const form = container.querySelector('.command-inline-form');
    const nameInput = form.querySelector('.command-inline-input.name');
    const codeInput = form.querySelector('[data-field="code"]');

    const name = nameInput.value.trim();
    const code = codeInput?.value.trim();

    if (!name) {
      Notification.error('Command name is required');
      return;
    }

    if (!code) {
      Notification.error('Command code is required for testing');
      return;
    }

    const deviceType = this._getCurrentDeviceType();

      if (deviceType === 'ble') {
        const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
        const selectedOpt = interfaceSelect?.options[interfaceSelect?.selectedIndex];
        const ifaceDataStr = selectedOpt?.dataset?.interface;
        let hciName = null;
        if (ifaceDataStr) {
          try {
            hciName = JSON.parse(ifaceDataStr.replace(/&quot;/g, '"')).hci_name;
          } catch (_) {}
        }
        if (!hciName) {
          Notification.error('Select a BLE adapter before testing');
          return;
        }
        try {
          const result = await WSManager.call('whispeer/ble_emit', {
            adapter: hciName,
            raw_hex: code,
          });
          if (result?.status === 'success') {
            Notification.success(`Test "${name}" sent successfully`);
          } else {
            Notification.error(`Test failed: ${result?.message || 'Unknown error'}`);
        }
      } catch (error) {
        Notification.error(`Test failed: ${error.message}`);
      }
      return;
    }

    if (!this.currentDevice) {
      Notification.warning('Save the device first to test commands');
      return;
    }

    try {
      await DataManager.sendCommand(this.currentDevice.id, this.currentDevice.type, name, code);
      Notification.success(`Test command "${name}" sent successfully`);
    } catch (error) {
      Notification.error(`Test failed: ${error.message}`);
    }
  }

  async testOptionCommand(button, optionKey = null) {
    if (!this.currentDevice) {
      Notification.warning('Save the device first to test commands');
      return;
    }

    const container = button.closest('.command-container');
    const form = container.querySelector('.command-inline-form');
    const nameInput = form.querySelector('.command-inline-input.name');
    const optionField = button.closest('.option-field');
    
    const commandName = nameInput.value.trim();
    
    let finalOptionKey = optionKey;
    if (!finalOptionKey) {
      const keyInput = optionField.querySelector('[data-option-key]');
      finalOptionKey = keyInput?.value.trim();
    }
    
    if (!commandName) {
      Notification.error('Command name is required');
      return;
    }
    
    if (!finalOptionKey) {
      Notification.error('Option key is required');
      return;
    }

    const optionValueInput = optionField.querySelector(`[data-option-value]`)
      || (finalOptionKey ? optionField.querySelector(`[data-option="${finalOptionKey}"]`) : null);
    const commandCode = optionValueInput?.value.trim();
    
    if (!commandCode) {
      Notification.error('Command code is required for testing');
      return;
    }

    try {
      const fullCommandName = `${commandName}.${finalOptionKey}`;
      await DataManager.sendCommand(this.currentDevice.id, this.currentDevice.type, commandName, commandCode, finalOptionKey);
      Notification.success(`Test command "${fullCommandName}" sent successfully`);
    } catch (error) {
      Notification.error(`Test failed: ${error.message}`);
    }
  }

  toggleCommandGroup(type) {
    const group = Utils.$(`.command-group[data-type="${type}"]`);
    if (group) {
      group.classList.toggle('collapsed');
    }
  }

  onInlineTypeChange(select) {
    const container = select.closest('.command-container');
    const form = container.querySelector('.command-inline-form');
    const type = select.value;
    const config = APP_CONFIG.COMMAND_TYPES[type];
    
    const nameInput = form.querySelector('.command-inline-input.name');
    const name = nameInput.value;
    
    let commandData = { name, type };
    if (name && this.tempCommands[name]) {
      commandData = { ...this.tempCommands[name], name, type };
    }
    
    const newForm = this.createInlineCommandForm(commandData, !!this.tempCommands[name]);
    container.outerHTML = newForm;
  }

  addOptionField(button, type) {
    const optionsList = button.closest('.command-options-section').querySelector('.options-list');
    const learnButton = `<button type="button" class="command-inline-btn learn"
              onclick="deviceManager.learnOptionCommand(this)">Learn</button>`;
    const newField = `
      <div class="option-field">
        <input type="${type === 'numeric' ? 'number' : 'text'}"
               placeholder="${type === 'numeric' ? 'Number' : 'Option'}"
               value="" class="command-inline-input" data-option-key>
        <input type="text" placeholder="Command code" value="" class="command-inline-input" data-option-value>
        ${learnButton}
        <button type="button" class="command-inline-btn test"
                onclick="deviceManager.testOptionCommand(this)">Test</button>
        <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">Delete</button>
      </div>
    `;
    optionsList.insertAdjacentHTML('beforeend', newField);
  }

  removeOptionField(button) {
    const optionField = button.closest('.option-field');
    optionField.remove();
  }

  refreshCommandsList() {
    const commandsList = Utils.$('#commandsList');
    if (commandsList) {
      commandsList.innerHTML = this.renderCommandsList(this.tempCommands);
    }
  }

  deleteDevice() {
    if (!this.currentDevice) return;

    if (confirm(`Are you sure you want to delete "${this.currentDevice.name}"?`)) {
      DataManager.deleteDevice(this.currentDevice.id);
      Notification.success('Device deleted successfully');
      this.closeDeviceModal();
      this.renderDevices();
      Utils.events.emit('deviceDeleted');
    }
  }

  closeDeviceModal() {
    this._cancelClimateLearn();
    this.stopFastLearn();
    if (this.deviceModal) {
      this.deviceModal.close();
    }
    this.currentDevice = null;
    this.tempCommands = {};
    this._detectedFrequency = null;
  }

  handleCommandResult(result) {
    const { deviceId, commandName, success, error } = result;

    if (success) {
      const device = DataManager.getDevice(deviceId);
      if (device) {
        console.log(`Command ${commandName} executed successfully on ${device.name}`);
      }
    } else {
      console.error(`Command ${commandName} failed:`, error);
    }
  }

  startLongPress(deviceId, commandName) {
    this.executeCommand(deviceId, commandName);

    const device = DataManager.getDevice(deviceId);
    const interval = parseFloat(device?.emit_interval);

    if (!interval || interval <= 0) return;

    const ms = Math.max(interval * 1000, 100);
    this._longPressTimer = setInterval(() => {
      this.executeCommand(deviceId, commandName);
    }, ms);
  }

  stopLongPress() {
    if (this._longPressTimer) {
      clearInterval(this._longPressTimer);
      this._longPressTimer = null;
    }
  }

  getCurrentDeviceInfo() {
    const form = Utils.$('#deviceForm');
    if (!form) return null;
    
    const formData = new FormData(form);
    const deviceData = Object.fromEntries(formData.entries());
    
    const interfaceSelect = form.querySelector('select[name="interface"]');
    const selectedOption = interfaceSelect.selectedOptions[0];
    let interfaceObject = null;
    
    if (selectedOption && selectedOption.hasAttribute('data-interface')) {
      try {
        const interfaceData = selectedOption.getAttribute('data-interface').replace(/&quot;/g, '"');
        interfaceObject = JSON.parse(interfaceData);
      } catch (e) {
        console.error('Failed to parse interface from selected option:', e);
      }
    }
    
    return {
      name: deviceData.name,
      type: deviceData.type,
      interface: interfaceObject
    };
  }

  async learnCommand(buttonElement) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo) {
      Notification.error('Please save the device first');
      return;
    }

    if (deviceInfo.type === 'ble') {
      const commandContainer = buttonElement.closest('.command-container');
      const commandForm = commandContainer?.querySelector('.command-inline-form');
      const codeInput = commandForm?.querySelector('input.command-inline-input.code');
      this.openBleScannerModal(true, (code) => {
        if (codeInput) codeInput.value = code;
      });
      return;
    }

    this._fastLearnStop = false;

    const commandContainer = buttonElement.closest('.command-container');
    const commandForm = commandContainer.querySelector('.command-inline-form');
    const nameInput = commandForm.querySelector('input.command-inline-input.name');
    const codeInput = commandForm.querySelector('input.command-inline-input.code');

    const commandName = nameInput?.value.trim() || `cmd_${Date.now()}`;
    await this.performLearnCommand(deviceInfo, commandName, codeInput);
  }

  async learnOptionCommand(buttonElement, optionKey = null) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo) {
      Notification.error('Please save the device first');
      return;
    }

    const optionField = buttonElement.closest('.option-field');
    let valueInput;

    if (optionKey) {
      valueInput = optionField.querySelector(`input[data-option="${optionKey}"]`);
    } else {
      valueInput = optionField.querySelector('input[data-option-value]');
    }

    if (deviceInfo.type === 'ble') {
      this.openBleScannerModal(true, (code) => {
        if (valueInput) valueInput.value = code;
      });
      return;
    }

    this._fastLearnStop = false;

    const commandContainer = buttonElement.closest('.command-container');
    const nameInput = commandContainer.querySelector('.command-inline-input.name');
    const commandBaseName = nameInput?.value.trim() || `cmd_${Date.now()}`;

    if (!optionKey) {
      const keyInput = optionField.querySelector('input[data-option-key]');
      optionKey = keyInput?.value.trim() || `opt_${Date.now()}`;
    }

    const commandName = `${commandBaseName}_${optionKey}`;
    await this.performLearnCommand(deviceInfo, commandName, valueInput);
  }

  async performLearnCommand(deviceInfo, commandName, codeInput) {
    const interfaceObject = deviceInfo.interface;

    if (!interfaceObject || typeof interfaceObject !== 'object') {
      console.error('No valid interface object:', interfaceObject);
      Notification.error('Please select an interface first');
      return;
    }

    if (!codeInput) {
      Notification.error('Could not find the code input field');
      return;
    }

    const originalButton = codeInput.parentElement?.querySelector('.command-inline-btn.learn');
    if (originalButton) {
      originalButton.disabled = true;
      originalButton.textContent = 'Preparing';
    }

    let learningToast = null;
    let learned = false;
    const learnGen = this._climateLearningGen;
    const isRF = deviceInfo.type === 'rf';
    const isBroadlink = (interfaceObject?.manufacturer || '').toLowerCase().includes('broadlink');

    const emitterData = { ...interfaceObject };
    if (isRF && isBroadlink) {
      const freqInput = document.querySelector('#frequencyField input[name="frequency"]');
      const knownFrequency = freqInput ? parseFloat(freqInput.value) : NaN;
      if (!isNaN(knownFrequency)) {
        emitterData.frequency = knownFrequency;
      }
    }

    try {
      if (isRF && isBroadlink && (emitterData.frequency == null || Number.isNaN(Number(emitterData.frequency)))) {
        const entityId = interfaceObject?.entity_id;
        if (!entityId) {
          throw new Error('Please select a Broadlink interface first');
        }

        learningToast = Notification.permanent('Hold a button on the remote to identify the frequency...');
        this._activeLearnToast = learningToast;

        const detectedFrequency = await this._runFrequencySweep(entityId);

        if (learningToast) { learningToast.close(); learningToast = null; }
        this._setDetectedFrequency(detectedFrequency);
        emitterData.frequency = detectedFrequency;
      }

      learningToast = Notification.permanent(`Preparing ${deviceInfo.type.toUpperCase()} device for learning...`);
      this._activeLearnToast = learningToast;

      const prepareResult = await CommandManager.learnCommand(deviceInfo.type, emitterData);

      if (this._climateLearningGen !== learnGen) {
        learningToast.close();
        return false;
      }

      if (prepareResult.status !== 'prepared') {
        throw new Error(prepareResult.message || 'Failed to prepare device for learning');
      }

      const sessionId = prepareResult.session_id;
      let deviceReady = false;
      let currentPhase = 'capturing';

      if (learningToast) { learningToast.close(); learningToast = null; }
      learningToast = Notification.permanent('⏳ Preparing device, please wait…');
      this._activeLearnToast = learningToast;

      await new Promise((resolve, reject) => {
        this._activeLearnReject = reject;
        const timeoutHandle = setTimeout(() => {
          unsubscribe();
          reject(new Error('Learning timed out - no button press detected within timeout'));
        }, 30000);

        const unsubscribe = WSManager.subscribe('whispeer_learn_update', (event) => {
          const data = event.data;
          if (data.session_id !== sessionId) return;

          const status = data.learning_status;
          const phase = data.phase;

          if (phase && phase !== currentPhase) {
            currentPhase = phase;
            if (phase === 'capturing') {
              if (learningToast) { learningToast.close(); learningToast = null; }
              learningToast = Notification.permanent('Frequency detected! Release the button, then press the desired button briefly…');
              this._activeLearnToast = learningToast;
              setTimeout(() => {
                if (learningToast) { learningToast.close(); learningToast = null; }
                deviceReady = true;
                if (originalButton) originalButton.textContent = 'Learning';
                learningToast = Notification.permanent('Press a button on the remote control');
                this._activeLearnToast = learningToast;
              }, 3000);
            }
          }

          if (status === 'completed' && data.command_data) {
            clearTimeout(timeoutHandle);
            unsubscribe();
            codeInput.value = data.command_data;
            if (learningToast) { learningToast.close(); learningToast = null; }
            Notification.success('Command learned successfully!');
            learned = true;
            if (isRF && data.detected_frequency != null) {
              this._setDetectedFrequency(data.detected_frequency);
            }
            resolve(true);
          } else if (status === 'learning') {
            if (!deviceReady && phase !== 'sweeping') {
              deviceReady = true;
              if (learningToast) { learningToast.close(); learningToast = null; }
              if (originalButton) originalButton.textContent = 'Learning';
              if (currentPhase === 'sweeping') {
                learningToast = Notification.permanent('Hold a button on the remote to identify the frequency');
              } else {
                learningToast = Notification.permanent('Press a button on the remote control');
              }
              this._activeLearnToast = learningToast;
            }
          } else if (status === 'error' || status === 'timeout') {
            clearTimeout(timeoutHandle);
            unsubscribe();
            reject(new Error(
              data.message ||
              (status === 'timeout' ? 'Learning session timed out' : 'Learning failed')
            ));
          }
        });
      });

    } catch (error) {
      if (error?._climateCancelled || this._climateLearningGen !== learnGen) {
        if (learningToast) { learningToast.close(); learningToast = null; }
        return false;
      }
      console.error('Learn command error:', error);
      if (learningToast) { learningToast.close(); learningToast = null; }
      Notification.error(`Failed to learn command: ${error.message}`);
      return false;
    } finally {
      this._activeLearnReject = null;
      if (this._activeLearnToast === learningToast) this._activeLearnToast = null;
      if (originalButton) {
        originalButton.disabled = false;
        originalButton.textContent = 'Learn';
      }
      if (learningToast) learningToast.close();
    }

    return learned;
  }

  _setDetectedFrequency(frequency) {
    this._detectedFrequency = frequency;

    const freqField = document.getElementById('frequencyField');
    if (freqField) {
      freqField.classList.remove('hidden');
      const freqInput = freqField.querySelector('input[name="frequency"]');
      if (freqInput) freqInput.value = frequency;
    }
  }

  stopFastLearn() {
    this._fastLearnStop = true;
    this._fastLearning = false;
    const btn = document.getElementById('fastLearnBtn');
    const stopBtn = document.getElementById('fastLearnStopBtn');
    if (btn) { btn.disabled = false; btn.textContent = '⚡ Fast Learn'; }
    if (stopBtn) { stopBtn.style.display = 'none'; }
  }

  _getLearnBtnCodeInput(learnBtn) {
    const optionField = learnBtn.closest('.option-field');
    if (optionField) {
      return optionField.querySelector('input[data-option]') ||
             optionField.querySelector('input[data-option-value]');
    }
    const form = learnBtn.closest('.command-inline-form');
    return form ? form.querySelector('input[data-field="code"]') : null;
  }

  _findNextEmptyLearnButton() {
    const commandsList = Utils.$('#commandsList');
    if (!commandsList) return null;

    for (const btn of commandsList.querySelectorAll('.command-inline-btn.learn')) {
      const codeInput = this._getLearnBtnCodeInput(btn);
      if (codeInput && codeInput.value.trim() === '') {
        return btn;
      }
    }
    return null;
  }

  async startFastLearn() {
    if (this._fastLearning) return;

    const deviceType = this._getCurrentDeviceType();
    if (deviceType !== 'ir' && deviceType !== 'rf') return;

    this._fastLearning = true;
    this._fastLearnStop = false;

    const btn = document.getElementById('fastLearnBtn');
    const stopBtn = document.getElementById('fastLearnStopBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⚡ Fast learning...'; }
    if (stopBtn) { stopBtn.style.display = ''; }

    try {
      while (!this._fastLearnStop) {
        let learnBtn = this._findNextEmptyLearnButton();

        if (!learnBtn) {
          this.addInlineCommand();
          await new Promise(resolve => setTimeout(resolve, 50));
          learnBtn = this._findNextEmptyLearnButton();
        }

        if (!learnBtn) break;

        learnBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        const focusInput = this._getLearnBtnCodeInput(learnBtn);
        if (focusInput) focusInput.focus();

        await new Promise(resolve => setTimeout(resolve, 400));

        const learned = await this._fastLearnOne(learnBtn);

        if (!learned) {
          break;
        }
      }
    } finally {
      this.stopFastLearn();
    }
  }

  async _fastLearnOne(learnButton) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo) return false;

    const commandContainer = learnButton.closest('.command-container');
    const commandForm = commandContainer?.querySelector('.command-inline-form');
    const nameInput = commandForm?.querySelector('input.command-inline-input.name');

    if (nameInput && !nameInput.value.trim()) {
      nameInput.value = `cmd_${Date.now()}`;
    }
    const baseName = nameInput?.value.trim() || `cmd_${Date.now()}`;

    let commandName;
    let codeInput;

    const optionField = learnButton.closest('.option-field');
    if (optionField) {
      const byOption = optionField.querySelector('input[data-option]');
      const byOptionValue = optionField.querySelector('input[data-option-value]');
      const optionKey = byOption
        ? byOption.dataset.option
        : (optionField.querySelector('input[data-option-key]')?.value.trim() || `opt_${Date.now()}`);
      commandName = `${baseName}_${optionKey}`;
      codeInput = byOption || byOptionValue;
    } else {
      commandName = baseName;
      codeInput = commandForm?.querySelector('input[data-field="code"]');
    }

    if (!codeInput) return false;

    const originalValue = codeInput.value;

    try {
      await this.performLearnCommand(deviceInfo, commandName, codeInput);
    } catch (_) {
      return false;
    }

    return codeInput.value.trim() !== '' && codeInput.value.trim() !== originalValue;
  }

  async findFrequency() {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo || !deviceInfo.interface) {
      Notification.error('Please select an interface first');
      return;
    }

    const entityId = deviceInfo.interface?.entity_id;
    if (!entityId) {
      Notification.error('Please select a Broadlink interface first');
      return;
    }

    const findBtn = document.getElementById('findFrequencyBtn');
    if (findBtn) {
      findBtn.disabled = true;
      findBtn.textContent = '📡 Sweeping...';
    }

    let learningToast = null;

    try {
      learningToast = Notification.permanent('Hold a button on the remote to identify the frequency...');
      const frequency = await this._runFrequencySweep(entityId);
      Notification.success(`Frequency detected: ${frequency} MHz`);
      this._setDetectedFrequency(frequency);

    } catch (error) {
      console.error('Find frequency error:', error);
      Notification.error(`Failed to find frequency: ${error.message}`);
    } finally {
      if (findBtn) {
        findBtn.disabled = false;
        findBtn.textContent = 'Find';
      }
      if (learningToast) learningToast.close();
    }
  }

  async _runFrequencySweep(entityId) {
    const result = await WSManager.call('whispeer/find_frequency', { entity_id: entityId });
    if (result?.status !== 'success') {
      throw new Error(result?.message || 'Failed to start frequency sweep');
    }

    const sessionId = result.session_id;

    return await new Promise((resolve, reject) => {
      const timeoutHandle = setTimeout(() => {
        unsubscribe();
        reject(new Error('Frequency sweep timed out'));
      }, 30000);

      const unsubscribe = WSManager.subscribe('whispeer_frequency_update', (event) => {
        const data = event.data;
        if (data.session_id !== sessionId) return;

        if (data.status === 'completed' && data.frequency != null) {
          clearTimeout(timeoutHandle);
          unsubscribe();
          resolve(Number(data.frequency));
        } else if (data.status === 'error' || data.status === 'timeout') {
          clearTimeout(timeoutHandle);
          unsubscribe();
          reject(new Error(data.message || 'Frequency sweep failed'));
        }
      });
    });
  }


  openBleScannerModal(pickMode = false, onPick = null) {
    const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
    if (!interfaceSelect) {
      Notification.error('No interface selected');
      return;
    }
    const selectedOption = interfaceSelect.options[interfaceSelect.selectedIndex];
    if (!selectedOption || !selectedOption.dataset.interface) {
      Notification.error('Please select a BLE interface first');
      return;
    }

    let ifaceData;
    try {
      ifaceData = JSON.parse(selectedOption.dataset.interface.replace(/&quot;/g, '"'));
    } catch (e) {
      Notification.error('Invalid interface data');
      return;
    }

    this._bleAdapter = ifaceData.hci_name;
    this._blePickMode = pickMode;
    this._blePickCallback = onPick;

    this._closeBleScanner();

    this._bleScannerToken += 1;

    this._bleDevices = [];
    this._bleSortCol = 'time';
    this._bleSortAsc = false;
    this._bleFilter = '';
    this._bleGroupBy = 'source';
    this._bleCollapsed = new Set();
    this._bleListening = true;

    const importSection = pickMode ? '' : `
      <div class="ble-adv-import-group">
        <span class="ble-adv-import-prepend">Import selected as</span>
        <select class="form-select ble-adv-import-select" id="bleImportType" disabled onchange="deviceManager._updateBleImportType()">
          <option value="button">Button</option>
          <option value="switch">Switch</option>
          <option value="light">Light</option>
          <option value="numeric">Numeric Range</option>
          <option value="options">Options</option>
          <option value="group">Group</option>
        </select>
        <button class="input-group-append-btn" id="bleImportBtn" onclick="deviceManager.importSelectedBleCommands()" disabled>⬆ Import</button>
      </div>`;

    const lastColHeader = pickMode ? '<th></th>' : '<th>Import As</th>';

    const scannerHTML = `
      <div class="ble-adv-actions">
        <div class="ble-adv-actions-left">
          <span class="ble-adv-warning">Still experimental</span>
          <button class="btn btn-small btn-outlined" id="bleListenBtn" onclick="deviceManager._toggleBleListening()">⏹ Stop Listening</button>
          <button class="btn btn-small btn-outlined" onclick="deviceManager._clearBleTable()">🗑 Clear</button>
        </div>
        ${importSection}
      </div>
      <div class="ble-adv-toolbar">
        <input type="text" class="ble-adv-search" id="bleAdvSearch" placeholder="Search…" oninput="deviceManager._onBleSearch(this.value)">
        <div class="ble-adv-toolbar-actions">
          <select class="form-select ble-adv-select" id="bleGroupSelect" onchange="deviceManager._onBleGroupChange(this.value)">
            <option value="source">Group by Source</option>
            <option value="">No grouping</option>
          </select>
          <select class="form-select ble-adv-select" id="bleSortSelect" onchange="deviceManager._onBleSortChange(this.value)">
            <option value="time">Order by Updated</option>
            <option value="address">Order by Address</option>
            <option value="name">Order by Name</option>
            <option value="rssi">Order by RSSI</option>
          </select>
        </div>
      </div>
      <div class="ble-adv-table-wrap">
        <table class="ble-adv-table">
          <thead>
            <tr>
              <th>Address</th>
              <th>Name</th>
              <th>Device</th>
              <th>Source</th>
              <th>Updated</th>
              <th>RSSI</th>
              <th>Test</th>
              ${lastColHeader}
            </tr>
          </thead>
          <tbody id="bleAdvBody"></tbody>
        </table>
      </div>
    `;

    this._bleScannerModal = new Modal({
      title: 'Bluetooth Advertisement Monitor',
      content: scannerHTML,
      className: 'ble-scanner-modal'
    });
    const origClose = this._bleScannerModal.close.bind(this._bleScannerModal);
    this._bleScannerModal.close = () => {
      this._closeBleScanner();
      return origClose();
    };
    this._bleScannerModal.open();

    this._subscribeBleAdvertisements();
  }

  async _subscribeBleAdvertisements() {
    const token = this._bleScannerToken;
    try {
      const unsub = await WSManager.subscribeCommand(
        'bluetooth/subscribe_advertisements', {},
        (event) => this._handleBleAdvEvent(event)
      );
      if (token !== this._bleScannerToken) {
        try { unsub(); } catch (_) {}
        return;
      }
      this._bleUnsub = unsub;
    } catch (e) {
      console.error('Failed to subscribe to BLE advertisements:', e);
      Notification.error('Failed to subscribe to Bluetooth advertisements');
    }

    this._bleTimeTimer = setInterval(() => this._updateBleRelativeTimes(), 1000);
  }

  _handleBleAdvEvent(event) {
    if (!this._bleListening) return;
    if (event.add) {
      for (const entry of event.add) {
        const idx = this._bleDevices.findIndex(d => d.address === entry.address);
        if (idx === -1) {
          this._bleDevices.push(entry);
        } else {
          this._bleDevices[idx] = entry;
        }
      }
    }
    if (event.remove) {
      for (const entry of event.remove) {
        const idx = this._bleDevices.findIndex(d => d.address === entry.address);
        if (idx !== -1) this._bleDevices.splice(idx, 1);
      }
    }
    this._renderBleTable();
  }

  _toggleBleListening() {
    this._bleListening = !this._bleListening;
    const btn = document.getElementById('bleListenBtn');
    if (btn) {
      btn.textContent = this._bleListening ? '⏹ Stop Listening' : '▶ Start Listening';
    }
  }

  _clearBleTable() {
    this._bleDevices = [];
    this._renderBleTable();
  }

  _getBleFilteredAndSorted() {
    let data = [...this._bleDevices];

    if (this._bleFilter) {
      const q = this._bleFilter.toLowerCase();
      data = data.filter(d =>
        (d.address || '').toLowerCase().includes(q) ||
        (d.name || '').toLowerCase().includes(q) ||
        (d.source || '').toLowerCase().includes(q)
      );
    }

    const col = this._bleSortCol;
    const dir = this._bleSortAsc ? 1 : -1;
    data.sort((a, b) => {
      let av, bv;
      if (col === 'rssi') {
        av = a.rssi ?? -999;
        bv = b.rssi ?? -999;
        return (av - bv) * dir;
      }
      if (col === 'time') {
        av = a.time ?? 0;
        bv = b.time ?? 0;
        return (av - bv) * dir;
      }
      av = (a[col] || '').toLowerCase();
      bv = (b[col] || '').toLowerCase();
      return av < bv ? -dir : av > bv ? dir : 0;
    });

    return data;
  }

  _renderBleTable() {
    const tbody = document.getElementById('bleAdvBody');
    if (!tbody) return;

    const data = this._getBleFilteredAndSorted();
    const groupBy = this._bleGroupBy;
    let html = '';

const colspan = this._blePickMode ? 7 : 8;

    if (groupBy) {
      const groups = new Map();
      for (const d of data) {
        const key = d[groupBy] || 'Unknown';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(d);
      }
      for (const [groupName, items] of groups) {
        const collapsed = this._bleCollapsed.has(groupName);
        const arrow = collapsed ? '▶' : '▼';
        html += `<tr class="ble-adv-group-row" onclick="deviceManager._toggleBleGroup('${this._escapeAttr(groupName)}')">
          <td colspan="${colspan}"><span class="ble-adv-group-arrow">${arrow}</span> ${this._escapeHtml(groupName)} (${items.length})</td>
        </tr>`;
        if (!collapsed) {
          for (const d of items) {
            html += this._renderBleRow(d);
          }
        }
      }
    } else {
      for (const d of data) {
        html += this._renderBleRow(d);
      }
    }

    if (data.length === 0) {
      html = `<tr><td colspan="${colspan}" class="ble-adv-empty">No advertisements found</td></tr>`;
    }

    tbody.innerHTML = html;
  }

  _renderBleRow(d) {
    const addr = this._escapeHtml(d.address || '');
    const name = this._escapeHtml(d.name || '');
    const device = '';
    const source = this._escapeHtml(d.source || '');
    const relTime = this._formatRelativeTime(d.time);
    const rssi = d.rssi != null ? d.rssi : '';
    const addrAttr = this._escapeAttr(d.address || '');

    const lastCol = this._blePickMode
      ? `<td onclick="event.stopPropagation()"><button class="btn btn-small" onclick="deviceManager._onBleRowClick('${addrAttr}', event)">Use this</button></td>`
      : `<td class="ble-adv-import-col" onclick="event.stopPropagation()"><input type="text" class="ble-import-name form-input" placeholder="Import as…" oninput="deviceManager._updateBleImportBtn()"></td>`;

    return `<tr class="ble-adv-row" data-address="${addrAttr}" onclick="deviceManager._onBleRowClick('${addrAttr}', event)">
      <td class="ble-adv-addr">${addr}</td>
      <td>${name}</td>
      <td>${device}</td>
      <td>${source}</td>
      <td class="ble-adv-time" data-time="${d.time || 0}">${relTime}</td>
      <td class="ble-adv-rssi">${rssi}</td>
      <td class="ble-adv-test-col" onclick="event.stopPropagation()">
        <button class="btn btn-small command-inline-btn test ble-test-btn" onclick="deviceManager._testBleRaw(this, '${addrAttr}')">Test</button>
      </td>
      ${lastCol}
    </tr>`;
  }

  _formatRelativeTime(epochSeconds) {
    if (!epochSeconds) return '';
    const now = Date.now() / 1000;
    const diff = Math.max(0, Math.round(now - epochSeconds));
    if (diff < 1) return 'Now';
    if (diff < 60) return `${diff} seconds ago`;
    if (diff < 3600) {
      const m = Math.floor(diff / 60);
      return `${m} minute${m > 1 ? 's' : ''} ago`;
    }
    const h = Math.floor(diff / 3600);
    return `${h} hour${h > 1 ? 's' : ''} ago`;
  }

  _updateBleRelativeTimes() {
    const cells = document.querySelectorAll('#bleAdvBody .ble-adv-time');
    cells.forEach(td => {
      const t = parseFloat(td.dataset.time);
      if (t) td.textContent = this._formatRelativeTime(t);
    });
  }

  _onBleSearch(value) {
    this._bleFilter = value;
    this._renderBleTable();
  }

  _onBleGroupChange(value) {
    this._bleGroupBy = value;
    this._bleCollapsed.clear();
    this._renderBleTable();
  }

  _onBleSortChange(value) {
    this._bleSortCol = value;
    this._bleSortAsc = value !== 'time' && value !== 'rssi';
    this._renderBleTable();
  }

  _toggleBleGroup(groupName) {
    if (this._bleCollapsed.has(groupName)) {
      this._bleCollapsed.delete(groupName);
    } else {
      this._bleCollapsed.add(groupName);
    }
    this._renderBleTable();
  }

  _onBleRowClick(address, event) {
    const entry = this._bleDevices.find(d => d.address === address);
    if (!entry) return;

    if (this._blePickMode) {
      const code = entry.raw || '';
      this._closeBleScanner();
      if (this._blePickCallback) {
        this._blePickCallback(code);
        this._blePickCallback = null;
      }
      return;
    }

    if (event?.target?.classList.contains('ble-import-name')) return;

    this._openBleDeviceInfoDialog(entry);
  }

  _updateBleImportBtn() {
    const btn = document.getElementById('bleImportBtn');
    const typeSelect = document.getElementById('bleImportType');
    if (!btn) return;
    const filledCount = Array.from(
      document.querySelectorAll('#bleAdvBody .ble-import-name')
    ).filter(inp => inp.value.trim()).length;

    btn.disabled = filledCount === 0;
    if (typeSelect) {
      typeSelect.disabled = filledCount === 0;
      this._updateBleImportType(filledCount);
    }
  }

  _updateBleImportType(filledCount) {
    const typeSelect = document.getElementById('bleImportType');
    if (!typeSelect) return;
    const count = filledCount != null ? filledCount : Array.from(
      document.querySelectorAll('#bleAdvBody .ble-import-name')
    ).filter(inp => inp.value.trim()).length;

    Array.from(typeSelect.options).forEach(opt => {
      const multiOnly = opt.value !== 'button';
      opt.disabled = multiOnly && count <= 1;
      opt.hidden = multiOnly && count <= 1;
    });
    if (count <= 1 && typeSelect.value !== 'button') {
      typeSelect.value = 'button';
    }
  }

  importSelectedBleCommands() {
    const typeSelect = document.getElementById('bleImportType');
    const importType = typeSelect?.value || 'button';

    const toImport = [];
    document.querySelectorAll('#bleAdvBody tr.ble-adv-row').forEach(tr => {
      const nameInput = tr.querySelector('.ble-import-name');
      const cmdName = nameInput?.value.trim();
      if (!cmdName) return;
      const address = tr.dataset.address;
      const entry = this._bleDevices.find(d => d.address === address);
      if (!entry) return;
      const code = entry.raw || '';
      toImport.push({ cmdName, code });
    });

    if (toImport.length === 0) {
      Notification.error('Fill in at least one "Import as" name');
      return;
    }

    if (importType === 'button') {
      toImport.forEach(({ cmdName, code }) => {
        this.tempCommands[cmdName] = {
          type: 'button',
          values: { code },
          props: { color: '#2196f3', icon: '📡', display: 'both' }
        };
      });
    } else if (importType === 'light' || importType === 'switch') {
      if (toImport.length < 2) {
        Notification.error(`${importType} type requires at least 2 entries (on and off)`);
        return;
      }
      const commandName = toImport[0].cmdName;
      this.tempCommands[commandName] = {
        type: importType,
        values: { on: toImport[0].code, off: toImport[1].code },
        props: { color: importType === 'light' ? '#ffeb3b' : '#2196f3', icon: importType === 'light' ? '💡' : '🔌', display: 'both' }
      };
    } else {
      const commandName = toImport[0].cmdName;
      const values = {};
      toImport.forEach(({ cmdName, code }) => { values[cmdName] = code; });
      this.tempCommands[commandName] = {
        type: importType,
        values,
        props: { color: '#2196f3', icon: '📡', display: 'both' }
      };
    }

    this._closeBleScanner();
    Notification.success(`Imported BLE command(s) as ${importType}`);
    const commandsList = Utils.$('#commandsList');
    if (commandsList) {
      commandsList.innerHTML = this.renderCommandsList(this.tempCommands);
    }
  }

  _openBleDeviceInfoDialog(entry) {
    const hexDisplay = (hexStr) => {
      if (!hexStr) return '';
      const bytes = hexStr.match(/.{2}/g) || [];
      return bytes.map(b => `0x${b.toUpperCase()}`).join(' ');
    };

    let mfrHtml = '';
    for (const [id, data] of Object.entries(entry.manufacturer_data || {})) {
      mfrHtml += `<tr><td><b>${this._escapeHtml(id)}</b></td><td class="ble-hex-data">${hexDisplay(data)}</td></tr>`;
    }
    if (!mfrHtml) mfrHtml = '<tr><td colspan="2" class="ble-adv-empty">—</td></tr>';

    let svcDataHtml = '';
    for (const [uuid, data] of Object.entries(entry.service_data || {})) {
      svcDataHtml += `<tr><td><b>${this._escapeHtml(uuid)}</b></td><td class="ble-hex-data">${hexDisplay(data)}</td></tr>`;
    }
    if (!svcDataHtml) svcDataHtml = '<tr><td colspan="2" class="ble-adv-empty">—</td></tr>';

    let svcUuidsHtml = '';
    for (const uuid of (entry.service_uuids || [])) {
      svcUuidsHtml += `<tr><td>${this._escapeHtml(uuid)}</td></tr>`;
    }
    if (!svcUuidsHtml) svcUuidsHtml = '<tr><td class="ble-adv-empty">—</td></tr>';

    const pickButton = this._blePickMode
      ? `<button class="btn btn-small" onclick="deviceManager._blePickFromDialog('${this._escapeAttr(entry.address)}')">Use this</button>`
      : '';

    const content = `
      <div class="ble-info-section">
        <p>
          <b>Address</b>: ${this._escapeHtml(entry.address)}<br>
          <b>Name</b>: ${this._escapeHtml(entry.name || '')}<br>
          <b>Source</b>: ${this._escapeHtml(entry.source || '')}
        </p>
      </div>
      <h3>Advertisement Data</h3>
      <h4>Manufacturer Data</h4>
      <table class="ble-info-table" width="100%"><tbody>${mfrHtml}</tbody></table>
      <h4>Service Data</h4>
      <table class="ble-info-table" width="100%"><tbody>${svcDataHtml}</tbody></table>
      <h4>Service UUIDs</h4>
      <table class="ble-info-table" width="100%"><tbody>${svcUuidsHtml}</tbody></table>
      <div class="ble-info-actions">
        <button class="btn btn-outlined" onclick="deviceManager._copyBleEntryToClipboard('${this._escapeAttr(entry.address)}')">Copy to clipboard</button>
        ${pickButton}
      </div>
    `;

    this._bleInfoModal = new Modal({
      title: 'Device Information',
      content,
      className: 'ble-info-modal'
    });
    this._bleInfoModal.open();
  }

  async _copyBleEntryToClipboard(address) {
    const entry = this._bleDevices.find(d => d.address === address);
    if (!entry) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(entry, null, 2));
      Notification.success('Copied to clipboard');
    } catch (e) {
      Notification.error('Failed to copy');
    }
  }

  _blePickFromDialog(address) {
    const entry = this._bleDevices.find(d => d.address === address);
    if (!entry) return;
    const code = entry.raw || '';
    if (this._bleInfoModal) {
      this._bleInfoModal.element?.remove();
      this._bleInfoModal = null;
    }
    this._closeBleScanner();
    if (this._blePickCallback) {
      this._blePickCallback(code);
      this._blePickCallback = null;
    }
  }

  async _testBleRaw(btn, address) {
    const entry = this._bleDevices.find(d => d.address === address);
    if (!entry?.raw) {
      Notification.error('No raw data available for this device');
      return;
    }

    btn.disabled = true;
    btn.textContent = '…';

    try {
      const result = await WSManager.call('whispeer/ble_emit', {
        adapter: this._bleAdapter,
        raw_hex: entry.raw,
      });
      if (result?.status === 'success') {
        btn.textContent = '✅';
        btn.classList.add('test-ok');
      } else {
        btn.textContent = '❌';
        btn.classList.add('test-fail');
      }
    } catch (e) {
      btn.textContent = '❌';
      btn.classList.add('test-fail');
    }

    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = 'Test';
      btn.classList.remove('test-ok', 'test-fail');
    }, 2000);
  }

  _closeBleScanner() {
    this._bleListening = false;
    this._bleScannerToken += 1;
    if (this._bleUnsub) {
      try { this._bleUnsub(); } catch (_) {}
      this._bleUnsub = null;
    }
    clearInterval(this._bleTimeTimer);
    this._bleTimeTimer = null;

    if (this._bleScannerModal) {
      this._bleScannerModal.element?.remove();
      this._bleScannerModal = null;
    }
    this._bleDevices = [];
  }


  _getClimateData() {
    if (!this._climateData) {
      this._climateData = {
        config: null,
        table: {},
        commands: {},
        source: 'scratch',
        sensors: { power: null, humidity: null, temperature: null }
      };
    }
    return this._climateData;
  }

  _getClimateData() {
    if (!this._climateData) {
      this._climateData = {
        config: null,
        table: {},
        commands: {},
        source: 'scratch',
        sensors: { power: null, humidity: null, temperature: null }
      };
    }
    return this._climateData;
  }


  _renderDomainSection(container, domain) {
    if (domain === 'climate') {
      this._renderClimateSection(container);
    } else if (domain === 'fan') {
      this._renderFanSection(container);
    } else if (domain === 'media_player') {
      this._renderMediaPlayerSection(container);
    } else if (domain === 'light') {
      this._renderLightSection(container);
    } else {
      container.innerHTML = '';
    }
  }


  _renderFanSection(container) {
    const cd = this._getClimateData();
    const cfg = cd.config || {};
    const hasDirectSpeeds = (cfg.speeds || []).length > 0 || Object.keys(cd.commands?.speeds || {}).length > 0;
    const hasIncremental = cfg.fan_model === 'incremental' && cd.commands?.speed !== undefined;
    const hasCommands = hasDirectSpeeds || hasIncremental;

    if (hasCommands) {
      container.innerHTML = this._buildFanTableHTML(cd);
      return;
    }

    const allSpeeds = ['lowest', 'low', 'mediumLow', 'medium', 'mediumHigh', 'high', 'turbo'];
    const activeSpeeds = cfg.speeds || ['low', 'medium', 'high'];

    const speedCheckboxes = allSpeeds.map(s =>
      `<label class="climate-checkbox">
        <input type="checkbox" name="fan_speed" value="${s}" ${activeSpeeds.includes(s) ? 'checked' : ''}>
        <span>${s}</span>
      </label>`
    ).join('');

    container.innerHTML = `
      <div class="climate-section">
        <div id="climatePanelsWrap">
          <div class="climate-panel">
            <div class="climate-panel-header"><span>${this._renderScratchTitle()}</span></div>
            <div class="climate-panel-body">
              <div class="climate-scratch-row" style="gap:8px;align-items:center;flex-wrap:wrap">
                <span class="climate-checkgroup-label" style="margin:0">Model</span>
                <label class="climate-checkbox">
                  <input type="radio" name="fan_model" value="direct" checked>
                  <span>Direct (one code per speed)</span>
                </label>
                <label class="climate-checkbox">
                  <input type="radio" name="fan_model" value="incremental">
                  <span>Incremental (one button, N presses)</span>
                </label>
              </div>
              <div class="climate-checkgroup" id="fanSpeedCheckboxes">
                <span class="climate-checkgroup-label">Speeds</span>
                ${speedCheckboxes}
              </div>
              <div id="fanIncrementalOpts" style="display:none;margin-top:6px">
                <div class="input-group" style="width:220px">
                  <div class="input-group-prepend"><div class="input-group-text">Speeds count</div></div>
                  <input type="number" id="fanSpeedsCount" class="form-input" value="3" min="1" max="10">
                </div>
              </div>
              <button type="button" class="btn btn-small" style="margin-top:8px"
                      onclick="deviceManager._generateFanCommands()">Generate</button>
            </div>
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll('input[name="fan_model"]').forEach(r => {
      r.addEventListener('change', () => {
        const isIncremental = container.querySelector('input[name="fan_model"]:checked')?.value === 'incremental';
        const speedBoxes = document.getElementById('fanSpeedCheckboxes');
        const incrOpts = document.getElementById('fanIncrementalOpts');
        if (speedBoxes) speedBoxes.style.display = isIncremental ? 'none' : '';
        if (incrOpts) incrOpts.style.display = isIncremental ? '' : 'none';
      });
    });
  }

  _buildFanTableHTML(cd) {
    const cfg = cd.config || {};
    const model = cfg.fan_model || 'direct';
    const isTestMode = !!this._climateTestMode;
    const speedMap = (cd.commands && typeof cd.commands.speeds === 'object')
      ? cd.commands.speeds
      : cd.commands;

    let cellsHTML;
    if (model === 'incremental') {
      cellsHTML = `
        ${this._domainCell('__off__', 'off', cd.commands?.off || '', isTestMode, "deviceManager._onFanCellClick('__off__')")}
        ${this._domainCell('__speed__', 'speed', cd.commands?.speed || '', isTestMode, "deviceManager._onFanCellClick('__speed__')")}
      `;
    } else {
      const speeds = (cfg.speeds && cfg.speeds.length > 0)
        ? cfg.speeds
        : Object.keys(speedMap || {}).filter(k => !['off', 'speed', 'forward', 'reverse', 'default', 'speeds'].includes(k));
      cellsHTML = `
        ${this._domainCell('__off__', 'off', cd.commands?.off || '', isTestMode, "deviceManager._onFanCellClick('__off__')")}
        ${speeds.map(s =>
          this._domainCell(`__speed_${s}__`, s, speedMap?.[s] || '', isTestMode, `deviceManager._onFanCellClick('__speed_${s}__')`)
        ).join('')}
      `;
    }

    return `
      <div class="climate-section">
        <div id="climatePanelsWrap" style="display:none"></div>
        <div id="fanTableSection">
          <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
            <button type="button" class="btn btn-small btn-danger"
                    onclick="deviceManager._resetDomainData()">Reset</button>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">${cellsHTML}</div>
        </div>
      </div>
    `;
  }

  _generateFanCommands() {
    const model = document.querySelector('input[name="fan_model"]:checked')?.value || 'direct';
    const cd = this._getClimateData();

    if (model === 'incremental') {
      const count = parseInt(document.getElementById('fanSpeedsCount')?.value ?? 3);
      cd.config = { fan_model: 'incremental', speeds_count: count };
      cd.commands = { off: '', speed: '' };
    } else {
      const speeds = [...document.querySelectorAll('input[name="fan_speed"]:checked')].map(cb => cb.value);
      if (speeds.length === 0) { Notification.error('Select at least one speed'); return; }
      cd.config = { fan_model: 'direct', speeds };
      const previousSpeeds = (cd.commands && typeof cd.commands.speeds === 'object') ? cd.commands.speeds : {};
      cd.commands = { off: cd.commands?.off || '', speeds: {} };
      for (const s of speeds) cd.commands.speeds[s] = previousSpeeds[s] || '';
    }
    cd.source = 'scratch';
    cd.table = {};

    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'fan');
    Notification.success('Fan structure generated');
  }

  async _onFanCellClick(cellKey) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }

    const cd = this._getClimateData();
    this._climateLearningCell = cellKey;
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'fan');

    const spinner = this._startCellSpinner(cellKey);
    const fakeInput = { value: '' };

    try {
      await this.performLearnCommand(deviceInfo, `fan_${cellKey}`, fakeInput);
      if (fakeInput.value) {
        cd.commands = cd.commands || {};
        if (cellKey === '__off__') {
          cd.commands.off = fakeInput.value;
        } else if (cellKey === '__speed__') {
          cd.commands.speed = fakeInput.value;
        } else {
          const speedName = cellKey.replace(/^__speed_/, '').replace(/__$/, '');
          cd.commands.speeds = cd.commands.speeds || {};
          cd.commands.speeds[speedName] = fakeInput.value;
        }
      }
    } finally {
      this._stopCellSpinner(spinner);
      this._climateLearningCell = null;
      if (domainSection) this._renderDomainSection(domainSection, 'fan');
    }
  }


  _renderMediaPlayerSection(container) {
    const cd = this._getClimateData();
    const cmds = cd.commands || {};
    const hasCommands = Object.keys(cmds).filter(k => k !== 'sources').length > 0;

    if (hasCommands) {
      container.innerHTML = this._buildMediaPlayerTableHTML(cd);
      return;
    }

    const allButtons = ['on', 'off', 'previousChannel', 'nextChannel', 'volumeUp', 'volumeDown', 'mute'];
    const activeButtons = Object.keys(cmds).filter(k => k !== 'sources');
    const defaultActive = activeButtons.length > 0 ? activeButtons : ['on', 'off', 'volumeUp', 'volumeDown', 'mute'];

    const buttonCheckboxes = allButtons.map(b =>
      `<label class="climate-checkbox">
        <input type="checkbox" name="mp_button" value="${b}" ${defaultActive.includes(b) ? 'checked' : ''}>
        <span>${b}</span>
      </label>`
    ).join('');

    container.innerHTML = `
      <div class="climate-section">
        <div id="climatePanelsWrap">
          <div class="climate-panel">
            <div class="climate-panel-header"><span>${this._renderScratchTitle()}</span></div>
            <div class="climate-panel-body">
              <div class="climate-checkgroup">
                <span class="climate-checkgroup-label">Buttons</span>
                ${buttonCheckboxes}
              </div>
              <button type="button" class="btn btn-small" style="margin-top:8px"
                      onclick="deviceManager._generateMediaPlayerCommands()">Generate</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  _buildMediaPlayerTableHTML(cd) {
    const isTestMode = !!this._climateTestMode;
    const buttons = Object.keys(cd.commands || {}).filter(k => k !== 'sources');

    const cells = buttons.map(key =>
      this._domainCell(`__mp_${key}__`, key, cd.commands[key] || '', isTestMode, `deviceManager._onMediaPlayerCellClick('${key}')`)
    ).join('');

    const sourceEntries = Object.entries(cd.commands?.sources || {});
    const sourceCells = sourceEntries.map(([name, code]) => {
      const hasCode = Array.isArray(code) ? code.length > 0 : !!code;
      const cellKey = `__mp_source_${name}__`;
      const isLearning = this._climateLearningCell === cellKey;
      let inner;
      if (isLearning) {
        inner = `<span class="climate-cell-icon learning"><span class="climate-spinner">⠋</span></span>`;
      } else if (hasCode) {
        inner = `<span class="climate-cell-icon present${isTestMode ? ' test' : ''}">${isTestMode ? '📡' : '✓'}</span>`;
      } else {
        inner = `<span class="climate-cell-icon empty">⚠</span>`;
      }
      return `<div class="climate-cell" data-cell="${this._escapeAttr(cellKey)}"
                   onclick="deviceManager._onMediaPlayerCellClick('source_${this._escapeAttr(name)}')"
                   title="source: ${this._escapeHtml(name)}"
                   style="display:inline-flex;flex-direction:column;align-items:center;padding:6px 10px;cursor:pointer;min-width:60px">
        ${inner}<span style="font-size:0.75rem;margin-top:2px">${this._escapeHtml(name)}</span>
      </div>`;
    }).join('');

    return `
      <div class="climate-section">
        <div id="climatePanelsWrap" style="display:none"></div>
        <div id="mpTableSection">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-weight:500">Commands</span>
            <button type="button" class="btn btn-small btn-danger"
                    onclick="deviceManager._resetDomainData()">Reset</button>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">${cells}</div>
          ${sourceEntries.length ? `
            <div style="margin-top:8px;font-weight:500">Sources</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px">${sourceCells}</div>
          ` : ''}
          <button type="button" class="btn btn-small" style="margin-top:8px"
                  onclick="deviceManager._addMediaPlayerSource()">+ Add source</button>
        </div>
      </div>
    `;
  }

  _generateMediaPlayerCommands() {
    const buttons = [...document.querySelectorAll('input[name="mp_button"]:checked')].map(cb => cb.value);
    if (buttons.length === 0) { Notification.error('Select at least one button'); return; }

    const cd = this._getClimateData();
    cd.commands = {};
    for (const b of buttons) cd.commands[b] = cd.commands[b] || '';
    cd.commands.sources = cd.commands.sources || {};
    cd.source = 'scratch';
    cd.config = null;
    cd.table = {};

    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'media_player');
    Notification.success('Media player structure generated');
  }

  async _onMediaPlayerCellClick(key) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }

    const cd = this._getClimateData();
    const isSource = key.startsWith('source_');
    const cellKey = isSource ? `__mp_source_${key.slice(7)}__` : `__mp_${key}__`;

    this._climateLearningCell = cellKey;
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'media_player');

    const spinner = this._startCellSpinner(cellKey);
    const fakeInput = { value: '' };

    try {
      await this.performLearnCommand(deviceInfo, `mp_${key}`, fakeInput);
      if (fakeInput.value) {
        cd.commands = cd.commands || {};
        if (isSource) {
          const sourceName = key.slice(7);
          cd.commands.sources = cd.commands.sources || {};
          cd.commands.sources[sourceName] = fakeInput.value;
        } else {
          cd.commands[key] = fakeInput.value;
        }
      }
    } finally {
      this._stopCellSpinner(spinner);
      this._climateLearningCell = null;
      if (domainSection) this._renderDomainSection(domainSection, 'media_player');
    }
  }

  _addMediaPlayerSource() {
    const name = prompt('Source name (e.g. HDMI, Netflix):');
    if (!name || !name.trim()) return;
    const cd = this._getClimateData();
    cd.commands = cd.commands || {};
    cd.commands.sources = cd.commands.sources || {};
    if (cd.commands.sources[name.trim()] !== undefined) {
      Notification.warning('Source already exists');
      return;
    }
    cd.commands.sources[name.trim()] = '';
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'media_player');
  }


  _renderLightSection(container) {
    const cd = this._getClimateData();
    const hasCommands = Object.keys(cd.commands || {}).length > 0;

    if (hasCommands) {
      container.innerHTML = this._buildLightTableHTML(cd);
      return;
    }

    const allButtons = ['on', 'off', 'brighten', 'dim', 'colder', 'warmer', 'night'];
    const activeButtons = Object.keys(cd.commands || {});
    const defaultActive = activeButtons.length > 0 ? activeButtons : ['on', 'off', 'brighten', 'dim'];

    const buttonCheckboxes = allButtons.map(b =>
      `<label class="climate-checkbox">
        <input type="checkbox" name="light_button" value="${b}" ${defaultActive.includes(b) ? 'checked' : ''}>
        <span>${b}</span>
      </label>`
    ).join('');

    container.innerHTML = `
      <div class="climate-section">
        <div id="climatePanelsWrap">
          <div class="climate-panel">
            <div class="climate-panel-header"><span>${this._renderScratchTitle()}</span></div>
            <div class="climate-panel-body">
              <div class="climate-checkgroup">
                <span class="climate-checkgroup-label">Buttons</span>
                ${buttonCheckboxes}
              </div>
              <button type="button" class="btn btn-small" style="margin-top:8px"
                      onclick="deviceManager._generateLightCommands()">Generate</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  _buildLightTableHTML(cd) {
    const isTestMode = !!this._climateTestMode;
    const keys = Object.keys(cd.commands || {});

    const cells = keys.map(key =>
      this._domainCell(`__light_${key}__`, key, cd.commands[key] || '', isTestMode, `deviceManager._onLightCellClick('${key}')`)
    ).join('');

    return `
      <div class="climate-section">
        <div id="climatePanelsWrap" style="display:none"></div>
        <div id="lightTableSection">
          <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
            <button type="button" class="btn btn-small btn-danger"
                    onclick="deviceManager._resetDomainData()">Reset</button>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">${cells}</div>
        </div>
      </div>
    `;
  }

  _generateLightCommands() {
    const buttons = [...document.querySelectorAll('input[name="light_button"]:checked')].map(cb => cb.value);
    if (buttons.length === 0) { Notification.error('Select at least one button'); return; }

    const cd = this._getClimateData();
    cd.commands = {};
    for (const b of buttons) cd.commands[b] = '';
    cd.source = 'scratch';
    cd.config = null;
    cd.table = {};

    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'light');
    Notification.success('Light structure generated');
  }

  async _onLightCellClick(key) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }

    const cd = this._getClimateData();
    const cellKey = `__light_${key}__`;

    this._climateLearningCell = cellKey;
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'light');

    const spinner = this._startCellSpinner(cellKey);
    const fakeInput = { value: '' };

    try {
      await this.performLearnCommand(deviceInfo, `light_${key}`, fakeInput);
      if (fakeInput.value) {
        cd.commands = cd.commands || {};
        cd.commands[key] = fakeInput.value;
      }
    } finally {
      this._stopCellSpinner(spinner);
      this._climateLearningCell = null;
      if (domainSection) this._renderDomainSection(domainSection, 'light');
    }
  }


  _domainCell(cellKey, label, code, isTestMode, onclick) {
    const hasCode = !!code;
    const isLearning = this._climateLearningCell === cellKey;
    let inner;
    if (isLearning) {
      inner = `<span class="climate-cell-icon learning"><span class="climate-spinner">⠋</span></span>`;
    } else if (hasCode) {
      inner = `<span class="climate-cell-icon present${isTestMode ? ' test' : ''}">${isTestMode ? '📡' : '✓'}</span>`;
    } else {
      inner = `<span class="climate-cell-icon empty">⚠</span>`;
    }
    return `<div class="climate-cell" data-cell="${this._escapeAttr(cellKey)}"
                onclick="${onclick}" title="${this._escapeAttr(label)}"
                style="display:inline-flex;flex-direction:column;align-items:center;padding:6px 10px;cursor:pointer;min-width:60px">
      ${inner}
      <span style="font-size:0.75rem;margin-top:2px">${this._escapeHtml(label)}</span>
    </div>`;
  }

  _renderClimateSection(container) {
    const cd = this._getClimateData();
    const cfg = cd.config || {};

    const allModes = ['cool', 'heat', 'dry', 'fan_only', 'auto'];
    const allFanModes = ['auto', 'low', 'mid', 'high', 'turbo'];
    const activeModes = cfg.modes || ['cool', 'heat', 'dry', 'fan_only'];
    const activeFans = cfg.fan_modes || ['auto', 'low', 'mid', 'high'];

    const hasTable = cd.config && (cd.config.modes || []).length > 0;

    const modeCheckboxes = allModes.map(m =>
      `<label class="climate-checkbox">
        <input type="checkbox" name="climate_mode" value="${m}" ${activeModes.includes(m) ? 'checked' : ''}>
        <span>${m}</span>
      </label>`
    ).join('');

    const fanCheckboxes = allFanModes.map(f =>
      `<label class="climate-checkbox">
        <input type="checkbox" name="climate_fan" value="${f}" ${activeFans.includes(f) ? 'checked' : ''}>
        <span>${f}</span>
      </label>`
    ).join('');

    const panelsDisplay = hasTable ? 'display:none' : '';
    const tableDisplay = hasTable ? '' : 'display:none';

    container.innerHTML = `
      <div class="climate-section">
        <div id="climatePanelsWrap" style="${panelsDisplay}">
          <div class="climate-panel">
            <div class="climate-panel-header">
              <span>${this._renderScratchTitle()}</span>
            </div>
            <div class="climate-panel-body">
              <div class="climate-scratch-row">
                <div class="input-group" style="flex:1">
                  <div class="input-group-prepend"><div class="input-group-text">Min temp</div></div>
                  <input type="number" id="climateMinTemp" class="form-input" value="${cfg.min_temp ?? 16}" min="0" max="50" style="width:70px">
                </div>
                <div class="input-group" style="flex:1">
                  <div class="input-group-prepend"><div class="input-group-text">Max temp</div></div>
                  <input type="number" id="climateMaxTemp" class="form-input" value="${cfg.max_temp ?? 30}" min="0" max="50" style="width:70px">
                </div>
              </div>
              <div class="climate-checkgroup">
                <span class="climate-checkgroup-label">Modes</span>
                ${modeCheckboxes}
              </div>
              <div class="climate-checkgroup">
                <span class="climate-checkgroup-label">Fan speeds</span>
                ${fanCheckboxes}
              </div>
              <button type="button" class="btn btn-small" style="margin-top:8px" onclick="deviceManager._generateClimateTable()">Generate table</button>
            </div>
          </div>
        </div>

        <div id="climateSensorsRow" class="climate-sensors-row" style="${hasTable ? '' : 'display:none'}">
          <div class="input-group" style="flex:1">
            <div class="input-group-prepend"><div class="input-group-text">Power sensor</div></div>
            <select id="climatePowerSensor" class="form-select"><option value="">— none —</option></select>
          </div>
          <div class="input-group" style="flex:1">
            <div class="input-group-prepend"><div class="input-group-text">Humidity sensor</div></div>
            <select id="climateHumiditySensor" class="form-select"><option value="">— none —</option></select>
          </div>
          <div class="input-group" style="flex:1">
            <div class="input-group-prepend"><div class="input-group-text">Temp sensor</div></div>
            <select id="climateTempSensor" class="form-select"><option value="">— none —</option></select>
            <button type="button" class="btn btn-small btn-danger" style="margin-left:6px"
                    onclick="deviceManager._resetClimateTable()">Reset</button>
          </div>
        </div>

        <div id="climateTableSection" style="${tableDisplay}">
          ${hasTable ? this._buildClimateTableHTML() : ''}
        </div>
      </div>
    `;

    this._populateSensorSelects(cd.sensors || {});
  }

  async _populateSensorSelects(currentSensors) {
    try {
      const result = await WSManager.call('whispeer/get_ha_entities', {
        domains: ['sensor', 'binary_sensor']
      });
      const entities = result?.entities || [];
      const selects = [
        { id: 'climatePowerSensor', key: 'power' },
        { id: 'climateHumiditySensor', key: 'humidity' },
        { id: 'climateTempSensor', key: 'temperature' }
      ];
      for (const { id, key } of selects) {
        const sel = document.getElementById(id);
        if (!sel) continue;
        sel.innerHTML = '<option value="">— none —</option>' +
          entities.map(e =>
            `<option value="${this._escapeAttr(e.entity_id)}" ${currentSensors[key] === e.entity_id ? 'selected' : ''}>${this._escapeHtml(e.friendly_name || e.entity_id)}</option>`
          ).join('');
      }
    } catch (e) {
      console.warn('[Climate] Failed to load sensor entities:', e);
    }
  }

  _buildClimateTableHTML() {
    const cd = this._getClimateData();
    const cfg = cd.config || {};
    const modes = cfg.modes || [];
    const fans = cfg.fan_modes || [];
    const minT = parseInt(cfg.min_temp ?? 16);
    const maxT = parseInt(cfg.max_temp ?? 30);

    if (modes.length === 0 || fans.length === 0) return '';

    const temps = [];
    for (let t = minT; t <= maxT; t++) temps.push(t);

    const isTestMode = !!this._climateTestMode;
    const toggleLabel = isTestMode ? 'test mode' : 'learn mode';
    const toggleClass = isTestMode ? 'climate-mode-toggle is-test' : 'climate-mode-toggle';
    const nFans = fans.length;

    const modeHeaders = modes.map(m =>
      `<th class="climate-mode-header" colspan="${nFans}">${m}</th>`
    ).join('');

    const offCode = (cd.commands || {}).off || '';
    const offHasCode = !!offCode;
    const offIsLearning = this._climateLearningCell === '__off__';
    const offIconSpan = offHasCode
      ? `<span class="climate-cell-icon present${isTestMode ? ' test' : ''}">${isTestMode ? '🛜' : '✓'}</span>`
      : `<span class="climate-cell-icon empty">⚠</span>`;

    const fanHeaders = modes.flatMap(() =>
      fans.map(f => `<th class="climate-fan-header">${f}</th>`)
    ).join('');

    const fastLearnCols = modes.flatMap(m =>
      fans.map(f =>
        `<td class="climate-fast-learn-cell">
          <button type="button" class="climate-fast-learn-btn"
            onclick="deviceManager._startClimateColumnFastLearn('${m}','${f}')"
            title="Fast learn ${m} / ${f}">
            <span class="climate-fast-learn-icon">⚡</span><span class="climate-fast-learn-text"> learn</span>
          </button>
        </td>`
      )
    ).join('');

    const rows = temps.map(temp => {
      const cells = modes.flatMap(mode =>
        fans.map(fan => {
          const code = ((cd.table[mode] || {})[fan] || {})[String(temp)] || '';
          const hasCode = !!code;
          const cellKey = `${mode}__${fan}__${temp}`;
          const isLearning = this._climateLearningCell === cellKey;
          let inner;
          if (isLearning) {
            inner = `<span class="climate-cell-icon learning"><span class="climate-spinner">⠋</span></span>`;
          } else if (hasCode) {
            inner = `<span class="climate-cell-icon present${isTestMode ? ' test' : ''}">${isTestMode ? '🛜' : '✓'}</span>`;
          } else {
            inner = `<span class="climate-cell-icon empty">⚠</span>`;
          }
          return `<td class="climate-cell" data-cell="${this._escapeAttr(cellKey)}"
                      onclick="deviceManager._onClimateCellClick('${mode}','${fan}',${temp})"
                      title="${mode} / ${fan} / ${temp}°C">${inner}</td>`;
        })
      ).join('');
      return `<tr><th class="climate-temp-header">${temp}°C</th>${cells}</tr>`;
    }).join('');

    return `
      <div class="climate-table-scroll">
        <table class="climate-table">
          <thead>
            <tr>
              <td class="climate-off-cell${offIsLearning ? ' learning' : (offHasCode ? ' present' : ' empty')}"
                  data-cell="__off__"
                  onclick="deviceManager._onClimateOffClick()"
                  title="off">
                ${offIsLearning
                  ? '<span class="climate-cell-icon learning"><span class="climate-spinner">⠋</span></span>'
                  : offIconSpan}
                <span class="climate-off-label">off</span>
              </td>
              ${modeHeaders}
            </tr>
            <tr>
              <th class="climate-fan-speed-label">fan speed</th>
              ${fanHeaders}
            </tr>
            <tr class="climate-fast-learn-row">
              <td class="climate-corner-cell">
                <button type="button" class="${toggleClass}"
                        onclick="deviceManager._toggleClimateMode(this)">
                  ${toggleLabel}
                </button>
              </td>
              ${fastLearnCols}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  _refreshClimateTable() {
    const section = document.getElementById('climateTableSection');
    if (section) section.innerHTML = this._buildClimateTableHTML();
  }

  _toggleClimateMode(btn) {
    this._climateTestMode = !this._climateTestMode;
    this._refreshClimateTable();
  }

  _resetClimateTable() {
    if (!confirm('Reset will clear all learned IR codes and show the import/generate sections again. Continue?')) return;
    const cd = this._getClimateData();
    cd.config = null;
    cd.table = {};
    cd.commands = {};
    cd.source = 'scratch';
    cd._smartirNum = '';
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, 'climate');
  }

  _resetDomainData() {
    const domain = this._getCurrentDomain();
    if (!confirm('Reset will clear all learned IR codes and show the import/generate sections again. Continue?')) return;
    const cd = this._getClimateData();
    cd.config = null;
    cd.table = {};
    cd.commands = {};
    cd.source = 'scratch';
    cd._smartirNum = '';
    const domainSection = document.getElementById('domainSection');
    if (domainSection) this._renderDomainSection(domainSection, domain);
  }

  _cancelClimateLearn() {
    if (this._climateLearningCell) {
      this._climateLearning = false;
      this._climateLearningGen++;
      this._climateLearningCell = null;
      this._activeLearnToast?.close();
      this._activeLearnToast = null;
      const reject = this._activeLearnReject;
      this._activeLearnReject = null;
      if (reject) reject(Object.assign(new Error('cancelled'), { _climateCancelled: true }));
      this._refreshClimateTable();
    }
  }

  async _onClimateCellClick(mode, fan, temp) {
    if (this._climateTestMode) {
      await this._testClimateCell(mode, fan, temp);
    } else {
      this._cancelClimateLearn();
      await this._learnClimateCell(mode, fan, temp);
    }
  }

  async _testClimateCell(mode, fan, temp) {
    const cd = this._getClimateData();
    const code = ((cd.table[mode] || {})[fan] || {})[String(temp)] || '';
    if (!code) { Notification.error('No code learned for this cell'); return; }
    try {
      await this._climateSendCode(`${mode}_${fan}_${temp}`, code);
      Notification.success(`Sent: ${mode} / ${fan} / ${temp}°C`);
    } catch (e) {
      Notification.error(`Test failed: ${e.message}`);
    }
  }

  async _climateSendCode(name, code) {
    if (this.currentDevice) {
      const result = await DataManager.sendCommand(this.currentDevice.id, 'climate', name, code);
      if (result?.status !== 'success') {
        throw new Error(result?.message || 'Failed to send climate command');
      }
      return result;
    }
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) {
      throw new Error('No interface selected');
    }
    const result = await WSManager.call('whispeer/send_command', {
      device_id: 'preview',
      device_type: 'climate',
      command_name: name,
      command_code: code,
      emitter: deviceInfo.interface,
    });
    if (result?.status !== 'success') {
      throw new Error(result?.message || 'Failed to send climate preview command');
    }
    return result;
  }

  async _onClimateOffClick() {
    if (this._climateTestMode) {
      const cd = this._getClimateData();
      const code = cd.commands?.off;
      if (!code) { Notification.error('No code learned for off'); return; }
      try {
        await this._climateSendCode('off', code);
        Notification.success('Off command sent');
      } catch (e) {
        Notification.error(`Test failed: ${e.message}`);
      }
    } else {
      const deviceInfo = this.getCurrentDeviceInfo();
      if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }
      this._climateLearning = false;
      this._climateLearningGen++;
      const myGen = this._climateLearningGen;
      const cellKey = '__off__';
      this._climateLearningCell = cellKey;
      this._refreshClimateTable();
      const spinner = this._startCellSpinner(cellKey);
      const fakeInput = { value: '' };
      try {
        await this.performLearnCommand(deviceInfo, 'climate_off', fakeInput);
        if (fakeInput.value && this._climateLearningGen === myGen) {
          const cd = this._getClimateData();
          cd.commands = cd.commands || {};
          cd.commands.off = fakeInput.value;
        }
      } finally {
        this._stopCellSpinner(spinner);
        if (this._climateLearningGen === myGen) {
          this._climateLearningCell = null;
          this._refreshClimateTable();
        }
      }
    }
  }

  async _importSmartIR() {
    const numInput = document.getElementById('smartirDeviceNum');
    const communityInput = document.getElementById('smartirCommunityCode');
    const num = (communityInput?.value || numInput?.value || '').trim();
    if (!num) {
      Notification.error('Enter a SmartIR device number');
      return;
    }

    const domain = this._getCurrentDomain();
    const subpath = domain === 'media_player' ? 'media_player' : domain;
    const url = `https://raw.githubusercontent.com/smartHomeHub/SmartIR/master/codes/${subpath}/${num}.json`;
    Notification.info(`Fetching SmartIR ${domain} device ${num}…`);

    let json;
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      json = await resp.json();
    } catch (err) {
      Notification.error(`Failed to import SmartIR: ${err.message}`);
      return;
    }

    const cd = this._getClimateData();
    cd._smartirNum = num;
    cd.source = 'smartir';

    if (domain === 'climate') {
      this._parseSmartIRClimate(cd, json);
      Notification.success(`SmartIR climate ${num} imported (${(cd.config?.modes || []).length} modes, ${(cd.config?.fan_modes || []).length} fan speeds)`);
    } else if (domain === 'fan') {
      this._parseSmartIRFan(cd, json);
      Notification.success(`SmartIR fan ${num} imported (${(cd.config?.speeds || []).length} speeds)`);
    } else if (domain === 'media_player') {
      this._parseSmartIRMediaPlayer(cd, json);
      Notification.success(`SmartIR media player ${num} imported`);
    } else if (domain === 'light') {
      this._parseSmartIRLight(cd, json);
      Notification.success(`SmartIR light ${num} imported`);
    }

    if (communityInput) communityInput.value = num;
    if (numInput) numInput.value = num;

    if (domain === 'climate') {
      const domainSection = document.getElementById('domainSection');
      if (domainSection) this._renderDomainSection(domainSection, domain);
    } else {
      this.tempCommands = this._domainToGenericCommands(domain, {
        domain,
        config: cd.config,
        commands: cd.commands,
      });
      this.refreshCommandsList();
    }
  }

  _parseSmartIRClimate(cd, json) {
    const modes = (json.operationModes || []).map(m => m.toLowerCase());
    const fans = (json.fanModes || []).map(f => f.toLowerCase());
    const minTemp = json.minTemperature ?? 16;
    const maxTemp = json.maxTemperature ?? 30;

    cd.config = { min_temp: minTemp, max_temp: maxTemp, modes, fan_modes: fans };
    cd.commands = { off: json.commands?.off || '' };
    cd.table = {};

    for (const mode of modes) {
      const srcMode = json.commands?.[mode];
      if (!srcMode || typeof srcMode !== 'object') continue;
      cd.table[mode] = {};
      for (const fan of fans) {
        const srcFan = srcMode[fan] || {};
        if (!srcFan || typeof srcFan !== 'object') continue;
        cd.table[mode][fan] = {};
        for (const [tempKey, code] of Object.entries(srcFan)) {
          cd.table[mode][fan][String(tempKey)] = code;
        }
      }
    }
  }

  _parseSmartIRFan(cd, json) {
    const declaredSpeeds = Array.isArray(json.speed)
      ? json.speed
      : (Array.isArray(json.speeds) ? json.speeds : []);
    const commandsRoot = json.commands || {};
    const pickSpeedMap = (container) => {
      if (!container || typeof container !== 'object' || Array.isArray(container)) return {};
      if (container.default && typeof container.default === 'object' && !Array.isArray(container.default)) {
        return container.default;
      }
      if (container.speed && typeof container.speed === 'object' && !Array.isArray(container.speed)) {
        return container.speed;
      }
      return container;
    };

    const forwardSrc = pickSpeedMap(commandsRoot.forward || commandsRoot);
    const reverseSrc = pickSpeedMap(commandsRoot.reverse || null);

    const derivedSpeeds = Object.keys(forwardSrc || {}).filter(k => k !== 'off' && k !== 'default' && k !== 'forward' && k !== 'reverse');
    const speeds = declaredSpeeds.length > 0 ? declaredSpeeds : derivedSpeeds;

    cd.config = { fan_model: 'direct', speeds };
    cd.commands = { off: commandsRoot.off || '', speeds: {} };
    for (const speed of speeds) {
      const raw = forwardSrc[speed];
      if (raw && typeof raw === 'string') {
        cd.commands.speeds[speed] = raw;
      } else if (raw && typeof raw === 'object' && typeof raw.code === 'string') {
        cd.commands.speeds[speed] = raw.code;
      }
    }
    if (Object.keys(cd.commands.speeds).length === 0) {
      for (const [key, value] of Object.entries(commandsRoot)) {
        if (['off', 'default', 'speed', 'forward', 'reverse', 'speeds'].includes(key)) continue;
        if (typeof value === 'string' && value) {
          cd.commands.speeds[key] = value;
        }
      }
    }
    cd.table = {};
  }

  _parseSmartIRMediaPlayer(cd, json) {
    const flatKeys = ['on', 'off', 'previousChannel', 'nextChannel', 'volumeUp', 'volumeDown', 'mute'];
    cd.commands = {};
    for (const key of flatKeys) {
      if (json.commands?.[key]) cd.commands[key] = json.commands[key];
    }
    if (json.commands?.sources) {
      cd.commands.sources = {};
      for (const [name, code] of Object.entries(json.commands.sources)) {
        cd.commands.sources[name] = code;
      }
    }
    cd.config = null;
    cd.table = {};
  }

  _parseSmartIRLight(cd, json) {
    const keys = ['on', 'off', 'brighten', 'dim', 'colder', 'warmer', 'night'];
    cd.config = {
      brightness: json.brightness || [],
      colorTemperature: json.colorTemperature || []
    };
    cd.commands = {};
    for (const key of keys) {
      if (json.commands?.[key]) cd.commands[key] = json.commands[key];
    }
    cd.table = {};
  }

  _generateClimateTable() {
    const minTemp = parseInt(document.getElementById('climateMinTemp')?.value ?? 16);
    const maxTemp = parseInt(document.getElementById('climateMaxTemp')?.value ?? 30);
    const modes = [...document.querySelectorAll('input[name="climate_mode"]:checked')].map(cb => cb.value);
    const fans = [...document.querySelectorAll('input[name="climate_fan"]:checked')].map(cb => cb.value);

    if (modes.length === 0) { Notification.error('Select at least one mode'); return; }
    if (fans.length === 0) { Notification.error('Select at least one fan speed'); return; }
    if (minTemp > maxTemp) { Notification.error('Min temp must be ≤ max temp'); return; }

    const cd = this._getClimateData();
    cd.source = 'scratch';
    cd.config = { min_temp: minTemp, max_temp: maxTemp, modes, fan_modes: fans };
    cd.table = cd.table || {};

    for (const mode of modes) {
      cd.table[mode] = cd.table[mode] || {};
      for (const fan of fans) {
        cd.table[mode][fan] = cd.table[mode][fan] || {};
        for (let t = minTemp; t <= maxTemp; t++) {
          cd.table[mode][fan][String(t)] = cd.table[mode][fan][String(t)] || '';
        }
      }
    }

    this._refreshClimateTable();
    const panelsWrap = document.getElementById('climatePanelsWrap');
    const tableSection = document.getElementById('climateTableSection');
    const sensorsRow = document.getElementById('climateSensorsRow');
    if (panelsWrap) panelsWrap.style.display = 'none';
    if (tableSection) tableSection.style.display = '';
    if (sensorsRow) sensorsRow.style.display = '';
    Notification.success('Table generated');
  }

  _collectClimateData() {    const cd = this._getClimateData();
    const sensors = {
      power: document.getElementById('climatePowerSensor')?.value || null,
      humidity: document.getElementById('climateHumiditySensor')?.value || null,
      temperature: document.getElementById('climateTempSensor')?.value || null
    };
    for (const k of Object.keys(sensors)) {
      if (!sensors[k]) sensors[k] = null;
    }
    return { ...cd, sensors };
  }

  _collectDomainData(domain) {
    if (domain === 'climate') return this._collectClimateData();
    return { ...this._getClimateData() };
  }

  async _learnClimateCell(mode, fan, temp) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }

    const myGen = this._climateLearningGen;
    const cellKey = `${mode}__${fan}__${temp}`;
    this._climateLearningCell = cellKey;
    this._refreshClimateTable();

    const spinner = this._startCellSpinner(cellKey);
    const fakeInput = { value: '' };
    let learned = false;

    try {
      learned = await this.performLearnCommand(deviceInfo, `climate_${mode}_${fan}_${temp}`, fakeInput);
      if (fakeInput.value && this._climateLearningGen === myGen) {
        const cd = this._getClimateData();
        cd.table[mode] = cd.table[mode] || {};
        cd.table[mode][fan] = cd.table[mode][fan] || {};
        cd.table[mode][fan][String(temp)] = fakeInput.value;
      }
    } finally {
      this._stopCellSpinner(spinner);
      if (this._climateLearningGen === myGen) {
        this._climateLearningCell = null;
        this._refreshClimateTable();
      }
    }

    return !!(learned && fakeInput.value);
  }

  _startCellSpinner(cellKey) {
    const el = document.querySelector(`[data-cell="${CSS.escape(cellKey)}"] .climate-spinner`);
    if (!el) return null;
    let frame = 0;
    const frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
    const handle = setInterval(() => {
      if (el) el.textContent = frames[frame++ % frames.length];
    }, 100);
    return handle;
  }

  _stopCellSpinner(handle) {
    if (handle) clearInterval(handle);
  }

  async _startClimateColumnFastLearn(mode, fan) {
    if (this._climateLearning) return;
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo?.interface) { Notification.error('Select an interface first'); return; }

    this._climateLearning = true;

    const cd = this._getClimateData();
    const cfg = cd.config || {};
    const minT = parseInt(cfg.min_temp ?? 16);
    const maxT = parseInt(cfg.max_temp ?? 30);

    this._climateLearningGen++;
    const myFastGen = this._climateLearningGen;
    const pendingTemps = [];
    for (let temp = minT; temp <= maxT; temp++) {
      const existing = ((cd.table[mode] || {})[fan] || {})[String(temp)];
      if (!existing) pendingTemps.push(temp);
    }

    if (pendingTemps.length === 0) {
      for (let temp = minT; temp <= maxT; temp++) {
        pendingTemps.push(temp);
      }
    }

    try {
      for (const temp of pendingTemps) {
        if (!this._climateLearning || this._climateLearningGen !== myFastGen) return;

        const learned = await this._learnClimateCell(mode, fan, temp);
        if (!learned || this._climateLearningGen !== myFastGen) {
          Notification.warning(`Fast learn stopped in ${mode} / ${fan} at ${temp}°C`);
          return;
        }

        await new Promise(r => setTimeout(r, 400));
      }
    } finally {
      this._climateLearning = false;
    }
    Notification.success(`Fast learn for ${mode} / ${fan} complete`);
  }


  _renderFanCard(device) {
    const { id, config = {}, commands = {} } = device;
    const model = config.fan_model || 'direct';

    if (model === 'incremental') {
      const count = config.speeds_count || 3;
      return `
        <div class="climate-card-controls">
          <div class="command-toggle-full-width" data-fan-power="${this._escapeAttr(id)}">
            <span class="command-toggle-label">off</span>
            <div class="command-toggle off" onclick="deviceManager._fanSendCommand('${id}', 'off')"></div>
          </div>
          <div class="input-group-container">
            <div class="input-group-prepend"><span class="input-group-text">Speed</span></div>
            <div class="btn-group-wrapper">
              <div class="btn-group" data-fan-speeds="${this._escapeAttr(id)}">
                ${Array.from({ length: count }, (_, i) =>
                  `<button class="btn-group-item" data-level="${i + 1}" onclick="deviceManager._fanSendIncrementalTo('${id}', ${i + 1}, ${count})">${i + 1}</button>`
                ).join('')}
              </div>
            </div>
          </div>
        </div>
      `;
    }

    const directSpeedMap = (commands.speeds && typeof commands.speeds === 'object')
      ? commands.speeds
      : commands;
    const speeds = (config.speeds && config.speeds.length > 0)
      ? config.speeds
      : Object.keys(directSpeedMap).filter(k => !['off', 'speed', 'forward', 'reverse', 'default', 'speeds'].includes(k));
    return `
      <div class="climate-card-controls">
        <div class="command-toggle-full-width" data-fan-power="${this._escapeAttr(id)}">
          <span class="command-toggle-label">off</span>
          <div class="command-toggle off" onclick="deviceManager._fanSendCommand('${id}', 'off')"></div>
        </div>
        ${speeds.length ? `
          <div class="input-group-container">
            <div class="input-group-prepend"><span class="input-group-text">Speed</span></div>
            <div class="btn-group-wrapper">
              <div class="btn-group" data-fan-speeds="${this._escapeAttr(id)}">
                ${speeds.map(s =>
                  `<button class="btn-group-item" data-speed="${s}" onclick="deviceManager._fanSendCommand('${id}', '${s}')">${s}</button>`
                ).join('')}
              </div>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  _renderMediaPlayerCard(device) {
    const { id, commands = {} } = device;
    const sources = commands.sources ? Object.keys(commands.sources) : [];
    const makeBtn = (cmd, label) => commands[cmd]
      ? `<button class="btn btn-small" onclick="deviceManager._mpSendCommand('${id}', '${cmd}')">${label}</button>`
      : '';

    const powerRow = [makeBtn('on', '⏻ On'), makeBtn('off', '⏻ Off')].filter(Boolean).join(' ');
    const volRow = [makeBtn('volumeDown', '🔉'), makeBtn('mute', '🔇'), makeBtn('volumeUp', '🔊')].filter(Boolean).join(' ');
    const chRow = [makeBtn('previousChannel', '⏮'), makeBtn('nextChannel', '⏭')].filter(Boolean).join(' ');

    const sourcesHTML = sources.length
      ? `<div class="input-group-container">
          <div class="input-group-prepend"><span class="input-group-text">Source</span></div>
          <div class="btn-group-wrapper"><div class="btn-group">
            ${sources.map(s =>
              `<button class="btn-group-item" onclick="deviceManager._mpSendSource('${id}', '${this._escapeAttr(s)}')">${this._escapeHtml(s)}</button>`
            ).join('')}
          </div></div>
        </div>`
      : '';

    return `
      <div class="climate-card-controls">
        ${powerRow ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${powerRow}</div>` : ''}
        ${volRow ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${volRow}</div>` : ''}
        ${chRow ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${chRow}</div>` : ''}
        ${sourcesHTML}
      </div>
    `;
  }

  _renderLightCard(device) {
    const { id, commands = {} } = device;
    const makeBtn = (cmd, label) => commands[cmd] !== undefined
      ? `<button class="btn btn-small" onclick="deviceManager._lightSendCommand('${id}', '${cmd}')">${label}</button>`
      : '';

    const row1 = [makeBtn('on', '💡 On'), makeBtn('off', '⭘ Off'), makeBtn('night', '🌙 Night')].filter(Boolean).join(' ');
    const row2 = [makeBtn('brighten', '☀️ Brighter'), makeBtn('dim', '🔅 Dimmer')].filter(Boolean).join(' ');
    const row3 = [makeBtn('warmer', '🔶 Warmer'), makeBtn('colder', '🔷 Cooler')].filter(Boolean).join(' ');

    return `
      <div class="climate-card-controls">
        ${row1 ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${row1}</div>` : ''}
        ${row2 ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${row2}</div>` : ''}
        ${row3 ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">${row3}</div>` : ''}
      </div>
    `;
  }

  async _fanSendCommand(deviceId, speedOrOff) {
    const device = DataManager.getDevice(deviceId);
    if (!device) return;
    try {
      if ((device.domain || 'default') === 'fan') {
        let result;
        if (speedOrOff === 'off') {
          result = await WSManager.call('whispeer/domain_action', {
            device_id: String(deviceId),
            domain: 'fan',
            action: 'off',
          });
        } else {
          result = await WSManager.call('whispeer/domain_action', {
            device_id: String(deviceId),
            domain: 'fan',
            action: 'set',
            preset_mode: speedOrOff,
          });
        }
        if (result?.status !== 'success') {
          throw new Error(result?.message || `Failed fan action ${speedOrOff}`);
        }
      } else {
        const speedMap = (device.commands?.speeds && typeof device.commands.speeds === 'object')
          ? device.commands.speeds
          : (device.commands || {});
        const code = speedOrOff === 'off'
          ? device.commands?.off
          : speedMap?.[speedOrOff];
        if (!code) { Notification.warning(`No code learned for "${speedOrOff}"`); return; }
        await DataManager.sendCommand(deviceId, 'ir', speedOrOff, code);
      }
      document.querySelectorAll(`[data-fan-speeds="${deviceId}"] .btn-group-item`).forEach(btn => {
        btn.classList.toggle('active', btn.dataset.speed === speedOrOff);
      });
      Notification.success(`Fan: ${speedOrOff}`);
    } catch (e) { Notification.error(e.message); }
  }

  async _fanSendIncrementalTo(deviceId, targetLevel, maxLevel) {
    const device = DataManager.getDevice(deviceId);
    if (!device) return;
    try {
      if ((device.domain || 'default') === 'fan') {
        const percentage = Math.round((targetLevel / maxLevel) * 100);
        const result = await WSManager.call('whispeer/domain_action', {
          device_id: String(deviceId),
          domain: 'fan',
          action: 'set',
          percentage,
        });
        if (result?.status !== 'success') {
          throw new Error(result?.message || 'Failed to set fan speed');
        }
      } else {
        const code = device.commands?.speed;
        if (!code) { Notification.warning('No speed code learned'); return; }
        for (let i = 0; i < targetLevel; i++) {
          await DataManager.sendCommand(deviceId, 'ir', 'speed', code);
          if (i < targetLevel - 1) await new Promise(r => setTimeout(r, 400));
        }
      }
      Notification.success(`Fan speed: ${targetLevel}`);
    } catch (e) { Notification.error(e.message); }
  }

  async _mpSendCommand(deviceId, cmdName) {
    const device = DataManager.getDevice(deviceId);
    if (!device) return;
    try {
      if ((device.domain || 'default') === 'media_player') {
        const actionMap = {
          on: 'on',
          off: 'off',
          volumeUp: 'volume_up',
          volumeDown: 'volume_down',
          mute: 'mute',
          previousChannel: 'previous',
          nextChannel: 'next',
        };
        const action = actionMap[cmdName];
        if (!action) throw new Error(`Unsupported media action ${cmdName}`);
        const result = await WSManager.call('whispeer/domain_action', {
          device_id: String(deviceId),
          domain: 'media_player',
          action,
        });
        if (result?.status !== 'success') {
          throw new Error(result?.message || `Failed media action ${cmdName}`);
        }
      } else {
        const code = device.commands?.[cmdName];
        if (!code) { Notification.warning(`No code learned for "${cmdName}"`); return; }
        await DataManager.sendCommand(deviceId, 'ir', cmdName, code);
      }
      Notification.success(`Sent: ${cmdName}`);
    } catch (e) { Notification.error(e.message); }
  }

  async _mpSendSource(deviceId, sourceName) {
    const device = DataManager.getDevice(deviceId);
    if (!device) return;
    try {
      if ((device.domain || 'default') === 'media_player') {
        const result = await WSManager.call('whispeer/domain_action', {
          device_id: String(deviceId),
          domain: 'media_player',
          action: 'select_source',
          source: sourceName,
        });
        if (result?.status !== 'success') {
          throw new Error(result?.message || `Failed selecting source ${sourceName}`);
        }
      } else {
        const codeOrArr = device.commands?.sources?.[sourceName];
        if (!codeOrArr) { Notification.warning(`No code for source "${sourceName}"`); return; }
        const codes = Array.isArray(codeOrArr) ? codeOrArr : [codeOrArr];
        for (let i = 0; i < codes.length; i++) {
          await DataManager.sendCommand(deviceId, 'ir', `source_${sourceName}`, codes[i]);
          if (i < codes.length - 1) await new Promise(r => setTimeout(r, 400));
        }
      }
      Notification.success(`Source: ${sourceName}`);
    } catch (e) { Notification.error(e.message); }
  }

  async _lightSendCommand(deviceId, cmdName) {
    const device = DataManager.getDevice(deviceId);
    if (!device) return;
    try {
      if ((device.domain || 'default') === 'light' && (cmdName === 'on' || cmdName === 'off')) {
        const result = await WSManager.call('whispeer/domain_action', {
          device_id: String(deviceId),
          domain: 'light',
          action: cmdName,
        });
        if (result?.status !== 'success') {
          throw new Error(result?.message || `Failed light action ${cmdName}`);
        }
      } else {
        const code = device.commands?.[cmdName];
        if (!code) { Notification.warning(`No code learned for "${cmdName}"`); return; }
        await DataManager.sendCommand(deviceId, 'ir', cmdName, code);
      }
      Notification.success(`Light: ${cmdName}`);
    } catch (e) { Notification.error(e.message); }
  }


  _renderClimateCard(device) {
    const { id } = device;
    const config = device.config || {};
    const modes = config.modes || [];
    const fans = config.fan_modes || [];
    const minT = parseInt(config.min_temp ?? 16);
    const maxT = parseInt(config.max_temp ?? 30);

    const temps = [];
    for (let t = minT; t <= maxT; t++) temps.push(t);

    const offToggle = `
      <div class="command-toggle-full-width" data-climate-power="${this._escapeAttr(id)}">
        <span class="command-toggle-label">off</span>
        <div class="command-toggle off" onclick="deviceManager._climateTogglePower('${id}')"></div>
      </div>`;

    const modeGroup = modes.length ? `
      <div class="input-group-container">
        <div class="input-group-prepend"><span class="input-group-text">Mode</span></div>
        <div class="btn-group-wrapper">
          <div class="btn-group" data-climate-modes="${this._escapeAttr(id)}">
            ${modes.map(m =>
              `<button class="btn-group-item" data-mode="${m}" onclick="deviceManager._climateSetMode('${id}', '${m}')">${m}</button>`
            ).join('')}
          </div>
        </div>
      </div>` : '';

    const fanGroup = fans.length ? `
      <div class="input-group-container">
        <div class="input-group-prepend"><span class="input-group-text">Fan</span></div>
        <div class="btn-group-wrapper">
          <div class="btn-group" data-climate-fans="${this._escapeAttr(id)}">
            ${fans.map(f =>
              `<button class="btn-group-item" data-fan="${f}" onclick="deviceManager._climateSetFan('${id}', '${f}')">${f}</button>`
            ).join('')}
          </div>
        </div>
      </div>` : '';

    const tempGroup = temps.length ? `
      <div class="input-group-container">
        <div class="input-group-prepend"><span class="input-group-text">Temp</span></div>
        <div class="btn-group-wrapper">
          <div class="btn-group" data-climate-temps="${this._escapeAttr(id)}">
            ${temps.map(t =>
              `<button class="btn-group-item" data-temp="${t}" onclick="deviceManager._climateSetTemp('${id}', ${t})">${t}</button>`
            ).join('')}
          </div>
        </div>
      </div>` : '';

    return `<div class="climate-card-controls" data-climate-card="${this._escapeAttr(id)}">${offToggle}${modeGroup}${fanGroup}${tempGroup}</div>`;
  }

  _getClimateCardState(deviceId) {
    if (!this._climateCardState) this._climateCardState = {};
    if (!this._climateCardState[deviceId]) {
      const device = DataManager.getDevice(deviceId);
      const cfg = device?.config || {};
      const modes = cfg.modes || [];
      const fans = cfg.fan_modes || [];
      const minT = parseInt(cfg.min_temp ?? 16);
      this._climateCardState[deviceId] = {
        on: false,
        mode: modes[0] || null,
        fan: fans[0] || null,
        temp: minT
      };
    }
    return this._climateCardState[deviceId];
  }

  async _climateDomainAction(deviceId, action, payload = {}) {
    const result = await WSManager.call('whispeer/domain_action', {
      device_id: String(deviceId),
      domain: 'climate',
      action,
      ...payload,
    });
    if (result?.status !== 'success') {
      throw new Error(result?.message || `Failed climate action: ${action}`);
    }
  }

  _climateUpdateCardUI(deviceId) {
    const st = this._getClimateCardState(deviceId);
    const container = document.querySelector(`[data-climate-card="${deviceId}"]`);
    if (container) {
      container.classList.toggle('is-off', !st.on);
    }
    const toggle = document.querySelector(`[data-climate-power="${deviceId}"] .command-toggle`);
    if (toggle) {
      toggle.classList.toggle('on', st.on);
      toggle.classList.toggle('off', !st.on);
    }
    document.querySelectorAll(`[data-climate-modes="${deviceId}"] .btn-group-item`).forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === st.mode);
    });
    document.querySelectorAll(`[data-climate-fans="${deviceId}"] .btn-group-item`).forEach(btn => {
      btn.classList.toggle('active', btn.dataset.fan === st.fan);
    });
    document.querySelectorAll(`[data-climate-temps="${deviceId}"] .btn-group-item`).forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.temp) === st.temp);
    });
  }

  _climateTogglePower(deviceId) {
    const st = this._getClimateCardState(deviceId);
    const turningOn = !st.on;
    st.on = turningOn;
    this._climateUpdateCardUI(deviceId);
    if (turningOn) {
      this._climateDomainAction(deviceId, 'set_mode', { mode: st.mode })
        .catch(e => Notification.error(e.message));
      return;
    }
    this._climateDomainAction(deviceId, 'off')
      .catch(e => Notification.error(e.message));
  }

  _climateSetMode(deviceId, mode) {
    const st = this._getClimateCardState(deviceId);
    st.mode = mode;
    if (st.on) {
      this._climateDomainAction(deviceId, 'set_mode', { mode })
        .catch(e => Notification.error(e.message));
    }
    this._climateUpdateCardUI(deviceId);
  }

  _climateSetFan(deviceId, fan) {
    const st = this._getClimateCardState(deviceId);
    st.fan = fan;
    this._climateDomainAction(deviceId, 'set_fan_mode', { fan_mode: fan })
      .catch(e => Notification.error(e.message));
    this._climateUpdateCardUI(deviceId);
  }

  _climateSetTemp(deviceId, temp) {
    const st = this._getClimateCardState(deviceId);
    st.temp = temp;
    this._climateDomainAction(deviceId, 'set_temperature', { temperature: temp })
      .catch(e => Notification.error(e.message));
    this._climateUpdateCardUI(deviceId);
  }
}

window.DeviceManager = DeviceManager;
