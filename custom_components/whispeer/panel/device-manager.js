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
              <span class="device-type-badge {{badgeClass}}">{{type}}</span>
              <button class="pill-edit" onclick="deviceManager.configureDevice('{{id}}')">⚙️</button>
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
              <button type="button" class="btn btn-small" onclick="deviceManager.addInlineCommand()">+ Add Command</button>
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
        <div class="command-toggle-full-width">
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
  }

  renderDeviceCard(device) {
    const { id, name, type, commands = {} } = device;
    const deviceTypeConfig = APP_CONFIG.DEVICE_TYPES[type] || { label: type, badge: 'type-ble' };

    const commandsHTML = this.renderDeviceCommands(device);
    const automations = DataManager.getDeviceAutomations(id);
    const automationBadge = automations.length > 0
      ? `<span class="automation-count-badge" title="${automations.length} automation(s)">${automations.length}</span>`
      : '';

    return this.template('deviceCard', {
      id,
      name,
      type: deviceTypeConfig.label,
      badgeClass: deviceTypeConfig.badge,
      commands: commandsHTML,
      automationBadge
    });
  }

  // ------------------------------------------------------------------
  // Stored codes section
  // ------------------------------------------------------------------

  async loadAndRenderStoredCodes() {
    const section = document.getElementById('storedCodesSection');
    if (section) {
      section.innerHTML = '<div class="stored-codes-loading">Loading stored codes…</div>';
    }
    try {
      const token = DataManager.getHomeAssistantToken();
      const url = token
        ? `/api/whispeer/stored_codes?access_token=${encodeURIComponent(token)}`
        : '/api/whispeer/stored_codes';
      const response = await Utils.api.get(url);
      this.storedCodes = (response && response.codes) ? response.codes : [];
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

    // Build flat index for onclick reference (avoids embedding codes in HTML)
    this._storedCodesFlat = codes.slice();

    // Group by device
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
        <button class="btn btn-small btn-outlined" onclick="deviceManager.loadAndRenderStoredCodes()">🔄 Refresh</button>
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
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post('/api/whispeer/send_stored_code', {
        identifier,
        source,
        device,
        command,
        code
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (response && response.status === 'success') {
        Notification.success(`Command "${command}" executed successfully`);
      } else {
        throw new Error(response?.message || 'Command failed');
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

  // ------------------------------------------------------------------

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
      } else if (command.type === 'numeric' || command.type === 'group') {
        commandCode = command.values?.[subCmd];
      } else {
        commandCode = command.values?.code || subCmd;
      }

      if (!commandCode) {
        throw new Error(`No command code found for "${commandName}"`);
      }

      await DataManager.sendCommand(deviceId, device.type, cmd, commandCode, subCmd);
      
      if (command.type === 'numeric' || command.type === 'group') {
        this.updateGroupCommandState(deviceId, cmd, subCmd);
      }
      
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
      toggleElement.classList.toggle('on');
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
      // 'sample_switch': {
      //   type: 'switch',
      //   values: {
      //     on: '',
      //     off: ''
      //   },
      //   props: {
      //     shape: 'square',
      //     color: '#4caf50'
      //   }
      // },
      // 'sample_light': {
      //   type: 'light',
      //   values: {
      //     on: '',
      //     off: ''
      //   },
      //   props: {
      //     shape: 'circle',
      //     color: '#ffeb3b'
      //   }
      // },
      // 'sample_numeric': {
      //   type: 'numeric',
      //   values: {
      //     '0': '',
      //     '1': '',
      //     '2': '',
      //     '3': ''
      //   },
      //   props: {
      //     shape: 'rounded',
      //     color: '#ff9800'
      //   }
      // },
      // 'sample_group': {
      //   type: 'group',
      //   values: {
      //     'option_a': '',
      //     'option_b': '',
      //     'option_c': ''
      //   },
      //   props: {
      //     shape: 'rounded',
      //     color: '#9c27b0'
      //   }
      // }
    };
  }

  openAddDeviceModal() {
    this.currentDevice = null;
    this.tempCommands = this.createSampleCommands();
    this.showDeviceModal('Add Device', {});
  }

  configureDevice(deviceId) {
    const device = DataManager.getDevice(deviceId);
    if (!device) {
      Notification.error('Device not found');
      return;
    }

    this.currentDevice = device;
    this.tempCommands = Utils.deepClone(device.commands || {});
    this.showDeviceModal('Edit Device', device);

    // Refresh automations in background and update the section if it has changed
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
    const deviceType = device.type || 'ir';

    const typeOptions = [
      { value: 'ir', label: 'Infrared' },
      { value: 'rf', label: 'Radio Frequency' },
      { value: 'ble', label: 'Bluetooth LE' }
    ].map(opt =>
      `<option value="${opt.value}"${opt.value === deviceType ? ' selected' : ''}>${opt.label}</option>`
    ).join('');

    const emitInterval = (device.emit_interval !== undefined && device.emit_interval !== null && device.emit_interval !== '')
      ? device.emit_interval : '';

    const frequency = (device.frequency !== undefined && device.frequency !== null && device.frequency !== '')
      ? device.frequency : '';

    const showFrequency = deviceType === 'rf' && frequency !== '';

    const frequencyField = `
      <div class="device-field-group" id="frequencyField" data-field="frequency"${showFrequency ? '' : ' style="display:none"'}>
        <div class="input-group">
          <div class="input-group-prepend">
            <div class="input-group-text">Frequency</div>
          </div>
          <input type="number" name="frequency" class="form-input" step="any"
                 value="${this._escapeAttr(String(frequency))}" disabled>
        </div>
      </div>
    `;

    return `
      <div class="device-fields-wrap">
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <div class="input-group-text">Name</div>
            </div>
            <input type="text" name="name" class="form-input" placeholder="Device name"
                   value="${this._escapeAttr(device.name || '')}" required>
          </div>
        </div>
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <div class="input-group-text">Type</div>
            </div>
            <select name="type" class="form-select">
              ${typeOptions}
            </select>
          </div>
        </div>
        <div class="device-field-group">
          <div class="input-group">
            <div class="input-group-prepend">
              <div class="input-group-text">Learn/Send from</div>
            </div>
            <select name="interface" class="form-select">
              <option value="">&#8987; Loading...</option>
            </select>
          </div>
        </div>
        <div class="device-field-row" id="rfToolsRow" style="display:none">
          ${frequencyField}
          <div class="device-field-group" data-field="emit_interval">
            <div class="input-group">
              <div class="input-group-prepend">
                <div class="input-group-text">Emit interval</div>
              </div>
              <input type="number" name="emit_interval" class="form-input"
                     placeholder="0.4" step="any" min="0"
                     value="${this._escapeAttr(String(emitInterval))}">
            </div>
          </div>
        </div>
        <div class="device-field-row" id="broadlinkToolsRow" style="display:none">
          <button type="button" class="btn btn-small btn-outlined" id="findFrequencyBtn"
                  onclick="deviceManager.findFrequency()">📡 Find frequency</button>
          <label class="fast-sweep-toggle" id="fastSweepLabel">
            <input type="checkbox" id="fastSweepCheckbox" name="fast_sweep">
            <span>Use 'fast sweep'</span>
          </label>
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
    if (this._getCurrentDeviceType() === 'ble') {
      this.openBleScannerModal();
      return;
    }

    const commandsList = Utils.$('#commandsList');
    if (!commandsList) return;

    const form = this.createInlineCommandForm();
    commandsList.insertAdjacentHTML('beforeend', form);
  }

  _getCurrentDeviceType() {
    const sel = Utils.$('#deviceForm select[name="type"]');
    return sel ? sel.value : '';
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
      } else if (type === 'numeric' || type === 'group') {
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
          ${(type === 'numeric' || type === 'group') ? 
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
    
    const typeSelect = deviceForm.querySelector('select[name="type"]');
    if (typeSelect) {
      // On type change, don't preserve selection (user is changing type intentionally)
      typeSelect.addEventListener('change', () => this.onDeviceTypeChange(false));
      // Initial load should preserve selection for edit mode
      this.onDeviceTypeChange(true);
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
    const currentDevice = this.currentDevice;
    
    // Clear current interfaces and show loading
    interfaceSelect.innerHTML = '<option value="">⏳ Loading interfaces...</option>';
    interfaceSelect.disabled = true;
    
    try {
      const interfaces = await DataManager.loadInterfaces(deviceType);
      
      // Clear loading state
      interfaceSelect.disabled = false;
      
      if (interfaces && interfaces.length > 0) {
        let selectedIndex = null;
        
        interfaceSelect.innerHTML = interfaces.map((iface, index) => {
          // Todos los objetos deben tener label
          if (typeof iface === 'object' && iface.label) {
            // Usar el índice como value y guardar el objeto en data-interface
            const interfaceData = JSON.stringify(iface).replace(/"/g, '&quot;');
            
            // Check if this interface should be selected when editing
            let shouldSelect = false;
            if (preserveSelection && currentDevice && currentDevice.emitter) {
              // Match by entity_id
              if (currentDevice.emitter.entity_id && iface.entity_id === currentDevice.emitter.entity_id) {
                shouldSelect = true;
                selectedIndex = index;
              }
              // Fallback: match by label
              else if (currentDevice.interface === iface.label) {
                shouldSelect = true;
                selectedIndex = index;
              }
            }
            
            return `<option value="${index}" data-interface="${interfaceData}" ${shouldSelect ? 'selected' : ''}>${iface.label}</option>`;
          } else {
            console.error('Invalid interface object, missing label:', iface);
            return ''; // Skip invalid interfaces
          }
        }).filter(option => option).join(''); // Remove empty options
        
        // Set the selected interface if found
        if (selectedIndex !== null) {
          interfaceSelect.value = selectedIndex.toString();
        }
        
        console.log(`Loaded ${interfaces.length} interfaces for ${deviceType}:`, interfaces);
      } else {
        interfaceSelect.innerHTML = '<option value="">❌ No interfaces available</option>';
        console.log(`No interfaces found for device type: ${deviceType}`);
      }
    } catch (error) {
      console.error('Failed to load interfaces:', error);

      // Clear loading state
      interfaceSelect.disabled = false;

      interfaceSelect.innerHTML = '<option value="">⚠️ Error loading interfaces</option>';
      Notification.error('Failed to load interfaces');
    }

    this._updateFrequencyField(deviceType);
    // Update broadlink tools after interfaces are loaded (selected option now has data)
    this._updateBroadlinkToolsVisibility();
  }

  _updateFrequencyField(deviceType) {
    const freqField = document.getElementById('frequencyField');
    const rfToolsRow = document.getElementById('rfToolsRow');
    const broadlinkToolsRow = document.getElementById('broadlinkToolsRow');

    if (rfToolsRow) {
      rfToolsRow.style.display = (deviceType === 'rf' || deviceType === 'ir') ? '' : 'none';
    }

    // Show frequency field if value exists or device is RF
    const freq = this.currentDevice?.frequency || this._detectedFrequency || '';
    if (freqField) {
      const show = freq !== '' && freq != null;
      freqField.style.display = show ? '' : 'none';
      if (show) {
        const freqInput = freqField.querySelector('input[name="frequency"]');
        if (freqInput) freqInput.value = freq;
      }
    }

    // Show broadlink tools only when interface is broadlink
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

    // Auto-check fast sweep when frequency is available
    const fastSweepCb = document.getElementById('fastSweepCheckbox');
    if (fastSweepCb) {
      const hasFreq = !!(this.currentDevice?.frequency || this._detectedFrequency);
      if (hasFreq) {
        fastSweepCb.checked = true;
      }
    }
  }

  async handleDeviceFormSubmit(e) {
    e.preventDefault();
    
    this.saveAllInlineCommands();
    
    const formData = new FormData(e.target);
    const deviceData = Object.fromEntries(formData.entries());
    deviceData.commands = this.tempCommands;

    // Convert emit_interval to number if present and validate positive
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

    // Remove transient fields that shouldn't be persisted
    delete deviceData.fast_sweep;

    // Read frequency from disabled field (FormData skips disabled inputs)
    const freqInput = e.target.querySelector('input[name="frequency"]');
    if (freqInput && freqInput.value !== '') {
      deviceData.frequency = parseFloat(freqInput.value);
    } else if (this._detectedFrequency != null) {
      deviceData.frequency = this._detectedFrequency;
    }

    // Add emitter information based on device type and interface
    const deviceType = deviceData.type;
    const interfaceIndex = deviceData.interface;
    
    if (interfaceIndex !== '' && interfaceIndex !== undefined) {
      try {
        // Get the interface object from the select option
        const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
        const selectedOption = interfaceSelect.options[interfaceIndex];
        
        if (selectedOption && selectedOption.dataset.interface) {
          const interfaceObj = JSON.parse(selectedOption.dataset.interface.replace(/&quot;/g, '"'));
          
          // Create emitter data with complete interface object
          const emitterData = {
            device_type: deviceType,
            interface_index: parseInt(interfaceIndex),
            ...interfaceObj // Store everything from the interface object
          };
          
          // Store interface label for backward compatibility
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
    if (this.tempCommands[commandName]) {
      delete this.tempCommands[commandName];
      Notification.success(`Command "${commandName}" deleted`);
      this.refreshCommandsList();
    }
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

    // BLE: send directly to the BLE emit endpoint — no saved device needed
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
        const token = DataManager.getHomeAssistantToken();
        const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.BLE_EMIT, {
          adapter: hciName,
          raw_hex: code
        }, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
        if (response?.status === 'success') {
          Notification.success(`Test "${name}" sent successfully`);
        } else {
          Notification.error(`Test failed: ${response?.message || 'Unknown error'}`);
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

    const optionValueInput = optionField.querySelector(`[data-option-value]`);
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
    // Always fire once immediately
    this.executeCommand(deviceId, commandName);

    const device = DataManager.getDevice(deviceId);
    const interval = parseFloat(device?.emit_interval);

    // If interval is 0 or not set, don't repeat
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
    
    // Get the interface object from the selected option's data-interface attribute
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

    const commandContainer = buttonElement.closest('.command-container');
    const nameInput = commandContainer.querySelector('.command-inline-input.name');
    const commandBaseName = nameInput?.value.trim() || `cmd_${Date.now()}`;

    const optionField = buttonElement.closest('.option-field');
    let keyInput, valueInput;

    if (optionKey) {
      // For predefined options like 'on'/'off'
      valueInput = optionField.querySelector(`input[data-option="${optionKey}"]`);
    } else {
      // For dynamic options
      keyInput = optionField.querySelector('input[data-option-key]');
      valueInput = optionField.querySelector('input[data-option-value]');
      optionKey = keyInput?.value.trim() || `opt_${Date.now()}`;
    }

    const commandName = `${commandBaseName}_${optionKey}`;
    await this.performLearnCommand(deviceInfo, commandName, valueInput);
  }

  async performLearnCommand(deviceInfo, commandName, codeInput) {
    // Interface should already be an object from getCurrentDeviceInfo()
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

    // Show learning modal
    const originalButton = codeInput.parentElement?.querySelector('.command-inline-btn.learn');
    if (originalButton) {
      originalButton.disabled = true;
      originalButton.textContent = '⏳ Preparing...';
    }

    let sessionId = null;
    let learningToast = null;
    const isRF = deviceInfo.type === 'rf';

    // Check fast sweep flag
    const fastSweepCb = document.getElementById('fastSweepCheckbox');
    const fastSweep = isRF && fastSweepCb && fastSweepCb.checked;
    const freqInput = document.querySelector('#frequencyField input[name="frequency"]');
    const knownFrequency = freqInput ? parseFloat(freqInput.value) : null;

    try {
      // Step 1: Prepare for learning
      Notification.info(`Preparing ${deviceInfo.type.toUpperCase()} device for learning...`);

      const emitterData = { ...interfaceObject };
      if (fastSweep && knownFrequency) {
        emitterData.frequency = knownFrequency;
      }

      const prepareResult = await CommandManager.learnCommand(
        deviceInfo.type,
        emitterData,
        fastSweep,
      );

      if (prepareResult.status !== 'prepared') {
        throw new Error(prepareResult.message || 'Failed to prepare device for learning');
      }

      sessionId = prepareResult.session_id;

      // Step 2: Show phase-appropriate toast
      if (originalButton) {
        originalButton.textContent = '📡 Learning...';
      }

      if (isRF && !fastSweep) {
        learningToast = Notification.permanent('Hold a button on the remote to identify the frequency');
      } else {
        learningToast = Notification.permanent('Press a button on the remote control');
      }

      // Step 3: Poll for learned command
      const timeout = 90000; // 90s for RF (2 phases), 30s effectively for IR
      const pollInterval = 1000;
      let elapsed = 0;
      let commandLearned = false;
      let currentPhase = isRF ? 'sweeping' : 'capturing';

      while (elapsed < timeout && !commandLearned) {
        await new Promise(resolve => setTimeout(resolve, pollInterval));
        elapsed += pollInterval;

        try {
          const checkResult = await CommandManager.checkLearnedCommand(sessionId, deviceInfo.type);

          // Handle phase transitions for RF
          if (checkResult.phase && checkResult.phase !== currentPhase) {
            currentPhase = checkResult.phase;
            if (currentPhase === 'capturing') {
              if (learningToast) { learningToast.close(); learningToast = null; }
              learningToast = Notification.permanent('Frequency detected! Release the button, then press the desired button briefly...');
              // Give user time to release and press the correct button
              await new Promise(resolve => setTimeout(resolve, 3000));
              if (learningToast) { learningToast.close(); learningToast = null; }
              learningToast = Notification.permanent('Press a button on the remote control');
            }
          }

          if (checkResult.status === 'success') {
            if (checkResult.learning_status === 'completed' && checkResult.command_data) {
              const commandCode = checkResult.command_data;
              codeInput.value = commandCode;

              if (learningToast) { learningToast.close(); learningToast = null; }

              Notification.success('Command learned successfully!');

              if (isRF && checkResult.detected_frequency != null) {
                this._setDetectedFrequency(checkResult.detected_frequency);
              }

              commandLearned = true;
              break;

            } else if (checkResult.learning_status === 'learning') {
              continue;
            } else if (checkResult.learning_status === 'error') {
              throw new Error(checkResult.message || 'Learning failed');
            } else if (checkResult.learning_status === 'timeout') {
              throw new Error('Learning session timed out');
            }
          } else if (checkResult.status === 'error') {
            throw new Error(checkResult.message || 'Learning failed');
          }

        } catch (pollError) {
          console.error('Polling error:', pollError);
          const errorMessage = pollError.message || '';
          if (errorMessage.includes('session not found') ||
              errorMessage.includes('timed out') ||
              errorMessage.includes('Learning failed') ||
              errorMessage.includes('Learning session timed out')) {
            throw pollError;
          }
        }
      }

      if (!commandLearned) {
        throw new Error('Learning timed out - no button press detected within timeout');
      }

    } catch (error) {
      console.error('Learn command error:', error);
      if (learningToast) { learningToast.close(); learningToast = null; }
      Notification.error(`Failed to learn command: ${error.message}`);

    } finally {
      if (originalButton) {
        originalButton.disabled = false;
        originalButton.textContent = 'Learn';
      }
      if (learningToast) { learningToast.close(); }
    }
  }

  _setDetectedFrequency(frequency) {
    this._detectedFrequency = frequency;

    const freqField = document.getElementById('frequencyField');
    if (freqField) {
      freqField.style.display = '';
      const freqInput = freqField.querySelector('input[name="frequency"]');
      if (freqInput) freqInput.value = frequency;
    }

    // Auto-check fast sweep
    const fastSweepCb = document.getElementById('fastSweepCheckbox');
    if (fastSweepCb) {
      fastSweepCb.checked = true;
    }
  }

  async findFrequency() {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo || !deviceInfo.interface) {
      Notification.error('Please select an interface first');
      return;
    }

    const findBtn = document.getElementById('findFrequencyBtn');
    if (findBtn) {
      findBtn.disabled = true;
      findBtn.textContent = '📡 Sweeping...';
    }

    let learningToast = null;

    try {
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post('/api/services/whispeer/find_frequency', {
        emitter: deviceInfo.interface
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });

      if (response.status !== 'success') {
        throw new Error(response.message || 'Failed to start frequency sweep');
      }

      const sessionId = response.session_id;
      learningToast = Notification.permanent('Hold a button on the remote to identify the frequency...');

      const timeout = 45000;
      const pollInterval = 1000;
      let elapsed = 0;
      let found = false;

      while (elapsed < timeout && !found) {
        await new Promise(resolve => setTimeout(resolve, pollInterval));
        elapsed += pollInterval;

        const checkResult = await CommandManager.checkLearnedCommand(sessionId, 'rf');

        if (checkResult.status === 'success' && checkResult.learning_status === 'completed') {
          if (checkResult.detected_frequency != null) {
            this._setDetectedFrequency(checkResult.detected_frequency);
            if (learningToast) { learningToast.close(); learningToast = null; }
            Notification.success(`Frequency detected: ${checkResult.detected_frequency} MHz`);
            found = true;
          } else {
            throw new Error('Sweep completed but no frequency detected');
          }
        } else if (checkResult.learning_status === 'error' || checkResult.learning_status === 'timeout') {
          throw new Error(checkResult.message || 'Frequency sweep failed');
        }
      }

      if (!found) {
        throw new Error('Frequency sweep timed out');
      }

    } catch (error) {
      console.error('Find frequency error:', error);
      if (learningToast) { learningToast.close(); learningToast = null; }
      Notification.error(`Failed to find frequency: ${error.message}`);
    } finally {
      if (findBtn) {
        findBtn.disabled = false;
        findBtn.textContent = '📡 Find frequency';
      }
      if (learningToast) { learningToast.close(); }
    }
  }

  // ------------------------------------------------------------------
  // BLE Scanner Modal
  // ------------------------------------------------------------------

  // Known consumer manufacturer IDs to filter out by default
  static BLE_CONSUMER_MFR_IDS = new Set([
    '76',    // Apple (0x004C)
    '224',   // Google (0x00E0)
    '117',   // Samsung (0x0075)
    '6',     // Microsoft (0x0006)
    '7',     // Microsoft (0x0007)
    '301',   // Xiaomi (0x012D)
  ]);

  openBleScannerModal() {
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

    const adapterMac = ifaceData.mac;
    const hciName = ifaceData.hci_name;

    const scannerHTML = `
      <div class="ble-scanner-header">
        <div class="ble-scanner-status">📡 Scanning on ${this._escapeHtml(hciName)}…</div>
        <div class="ble-scanner-actions">
          <button class="btn btn-small btn-outlined" id="bleStopBtn" onclick="deviceManager.stopBlePoll()">⏹ Stop Listening</button>
          <button class="btn btn-small btn-outlined" id="bleClearBtn" onclick="deviceManager.clearBleTable()">🗑 Clear</button>
          <button class="btn btn-small" id="bleImportBtn" onclick="deviceManager.importSelectedBleCommands()" disabled>Import Selected</button>
        </div>
      </div>
      <div class="ble-filter-bar">
        <label class="ble-filter-toggle">
          <input type="checkbox" id="bleConsumerFilter" checked onchange="deviceManager._applyBleFilters()">
          Hide consumer devices
        </label>
        <label class="ble-filter-toggle">
          <input type="checkbox" id="bleHideEmptyFilter" checked onchange="deviceManager._applyBleFilters()">
          Hide empty
        </label>
        <input type="text" id="bleAddressFilter" class="form-input ble-address-input" placeholder="Filter by address…" oninput="deviceManager._applyBleFilters()">
      </div>
      <div class="ble-scanner-table-wrap">
        <table class="ble-scanner-table">
          <thead>
            <tr>
              <th>Device</th>
              <th>Data Field</th>
              <th>Test</th>
              <th>Import</th>
              <th>Import As</th>
            </tr>
          </thead>
          <tbody id="bleScannerBody"></tbody>
        </table>
      </div>
    `;

    this._bleScannerModal = new Modal({
      title: 'BLE Advertisement Scanner',
      content: scannerHTML,
      className: 'ble-scanner-modal'
    });
    // Stop scanning when the modal is dismissed (close btn, backdrop, Escape)
    const origClose = this._bleScannerModal.close.bind(this._bleScannerModal);
    this._bleScannerModal.close = () => {
      deviceManager.stopBlePoll();
      return origClose();
    };
    this._bleScannerModal.open();

    this.startBlePoll(adapterMac, hciName);
  }

  startBlePoll(adapterMac, hciName) {
    this._bleScanActive = true;
    this._bleScanAddresses = new Set();
    this._bleScanHciName = hciName;
    this._bleScanAdapterMac = adapterMac;

    this._blePollTimer = setInterval(() => {
      if (this._bleScanActive) {
        this._fetchAndMergeBleScan(adapterMac, hciName);
      }
    }, 2000);

    this._bleAgeTimer = setInterval(() => this._updateAgeDisplays(), 1000);

    // Fetch immediately
    this._fetchAndMergeBleScan(adapterMac, hciName);
  }

  stopBlePoll() {
    this._bleScanActive = false;
    clearInterval(this._blePollTimer);
    this._blePollTimer = null;
    clearInterval(this._bleAgeTimer);
    this._bleAgeTimer = null;

    const statusEl = this._bleScannerModal?.element?.querySelector('.ble-scanner-status');
    if (statusEl) statusEl.textContent = '⏹ Paused';

    const stopBtn = document.getElementById('bleStopBtn');
    if (stopBtn) {
      stopBtn.textContent = '▶ Start Listening';
      stopBtn.onclick = () => deviceManager.resumeBlePoll();
    }
  }

  resumeBlePoll() {
    const adapterMac = this._bleScanAdapterMac;
    const hciName = this._bleScanHciName;
    if (!adapterMac || !hciName) return;

    this._bleScanActive = true;

    const statusEl = this._bleScannerModal?.element?.querySelector('.ble-scanner-status');
    if (statusEl) statusEl.textContent = `📡 Scanning on ${this._escapeHtml(hciName)}…`;

    const stopBtn = document.getElementById('bleStopBtn');
    if (stopBtn) {
      stopBtn.textContent = '⏹ Stop Listening';
      stopBtn.onclick = () => deviceManager.stopBlePoll();
    }

    this._blePollTimer = setInterval(() => {
      if (this._bleScanActive) this._fetchAndMergeBleScan(adapterMac, hciName);
    }, 2000);
    this._bleAgeTimer = setInterval(() => this._updateAgeDisplays(), 1000);

    this._fetchAndMergeBleScan(adapterMac, hciName);
  }

  clearBleTable() {
    const tbody = document.getElementById('bleScannerBody');
    if (tbody) tbody.innerHTML = '';
    this._bleScanAddresses = new Set();
  }

  async _fetchAndMergeBleScan(adapterMac, hciName) {
    try {
      const token = DataManager.getHomeAssistantToken();
      const url = token
        ? `${APP_CONFIG.ENDPOINTS.BLE_SCAN}?adapter_mac=${encodeURIComponent(adapterMac)}&access_token=${encodeURIComponent(token)}`
        : `${APP_CONFIG.ENDPOINTS.BLE_SCAN}?adapter_mac=${encodeURIComponent(adapterMac)}`;
      const response = await Utils.api.get(url);
      const devices = (response && response.devices) ? response.devices : [];

      devices.forEach(d => {
        if (this._bleScanAddresses.has(d.address)) return;
        this._bleScanAddresses.add(d.address);
        this._appendScannerRow(d, hciName);
      });
    } catch (e) {
      console.error('BLE scan fetch error:', e);
    }
  }

  _appendScannerRow(device, hciName) {
    const tbody = document.getElementById('bleScannerBody');
    if (!tbody) return;

    const addr = device.address || '';
    const name = device.name || 'Unknown';
    const rssi = device.rssi != null ? `${device.rssi} dBm` : '';
    const initialAgo = device.last_seen_ago != null ? device.last_seen_ago : 9999;
    const fetchedAt = Date.now();

    // Determine if this is a consumer device
    const mfrIds = Object.keys(device.manufacturer_data || {});
    const isConsumer = mfrIds.some(id => DeviceManager.BLE_CONSUMER_MFR_IDS.has(id));

    // Build <select> options from manufacturer_data and service_data
    let optionsHtml = '';
    for (const [mfrId, dataHex] of Object.entries(device.manufacturer_data || {})) {
      const preview = dataHex.length > 16 ? dataHex.substring(0, 16) + '…' : dataHex;
      const val = JSON.stringify({ ad_type: 'manufacturer', field_id: parseInt(mfrId), data_hex: dataHex });
      optionsHtml += `<option value='${this._escapeAttr(val)}'>Mfr 0x${parseInt(mfrId).toString(16).toUpperCase().padStart(4, '0')} — ${preview}</option>`;
    }
    for (const [uuid, dataHex] of Object.entries(device.service_data || {})) {
      const preview = dataHex.length > 16 ? dataHex.substring(0, 16) + '…' : dataHex;
      const val = JSON.stringify({ ad_type: 'service', field_id: uuid, data_hex: dataHex });
      optionsHtml += `<option value='${this._escapeAttr(val)}'>SVC ${uuid.length > 8 ? uuid.substring(0, 8) + '…' : uuid} — ${preview}</option>`;
    }

    const hasData = !!optionsHtml;
    const selectHtml = hasData
      ? `<select class="ble-field-select form-select">${optionsHtml}</select>`
      : `<select class="ble-field-select form-select" disabled><option>No data fields</option></select>`;

    const ageDisplay = Math.round(initialAgo);

    const tr = document.createElement('tr');
    tr.className = 'ble-row-new';
    tr.dataset.address = addr.toLowerCase();
    tr.dataset.consumer = isConsumer ? 'true' : 'false';
    tr.dataset.hasData = hasData ? 'true' : 'false';
    tr.dataset.initialAgo = initialAgo;
    tr.dataset.fetchedAt = fetchedAt;
    tr.dataset.ageSeconds = initialAgo;
    tr.dataset.raw = device.raw || '';

    tr.innerHTML = `
      <td>
        <div class="ble-device-addr">${this._escapeHtml(addr)}</div>
        <div class="ble-device-name">${this._escapeHtml(name)}<small>${rssi ? ' ' + rssi + ' ·' : ''} <span class="ble-age-span">${ageDisplay}</span>s</small></div>
      </td>
      <td>${selectHtml}</td>
      <td><button class="btn btn-small command-inline-btn test" onclick="deviceManager._testBleEmit(this, '${this._escapeAttr(hciName)}')">Test</button></td>
      <td><input type="checkbox" class="ble-import-check" onchange="deviceManager._updateBleImportBtn()"></td>
      <td><input type="text" class="ble-import-name form-input" placeholder="Import as…"></td>
    `;

    tbody.appendChild(tr);
    this._sortScannerTable();
    this._applyBleFilters();
  }

  _sortScannerTable() {
    const tbody = document.getElementById('bleScannerBody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => parseFloat(a.dataset.ageSeconds || 9999) - parseFloat(b.dataset.ageSeconds || 9999));
    rows.forEach(tr => tbody.appendChild(tr));
  }

  _updateAgeDisplays() {
    const now = Date.now();
    document.querySelectorAll('#bleScannerBody tr').forEach(tr => {
      const initialAgo = parseFloat(tr.dataset.initialAgo || 0);
      const fetchedAt = parseInt(tr.dataset.fetchedAt || now);
      const currentAgo = initialAgo + (now - fetchedAt) / 1000;
      tr.dataset.ageSeconds = currentAgo;
      const span = tr.querySelector('.ble-age-span');
      if (span) span.textContent = Math.round(currentAgo);
    });
    // Do NOT re-sort here — sorting moves DOM nodes and breaks open <select> dropdowns.
    // Sorting only happens when new rows arrive (_appendScannerRow calls _sortScannerTable).
  }

  async _testBleEmit(btn, hciName) {
    const row = btn.closest('tr');
    const select = row.querySelector('.ble-field-select');
    if (!select || !select.value) return;

    let payload;
    try {
      payload = JSON.parse(select.value);
    } catch (e) { return; }

    btn.disabled = true;
    btn.textContent = '…';

    try {
      const token = DataManager.getHomeAssistantToken();
      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.BLE_EMIT, {
        adapter: hciName,
        ad_type: payload.ad_type,
        field_id: payload.field_id,
        data_hex: payload.data_hex
      }, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });

      if (response && response.status === 'success') {
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

  _applyBleFilters() {
    const hideConsumer = document.getElementById('bleConsumerFilter')?.checked;
    const hideEmpty = document.getElementById('bleHideEmptyFilter')?.checked;
    const addrFilter = (document.getElementById('bleAddressFilter')?.value || '').toLowerCase();
    const rows = document.querySelectorAll('#bleScannerBody tr');

    rows.forEach(tr => {
      let hidden = false;
      if (hideConsumer && tr.dataset.consumer === 'true') hidden = true;
      if (hideEmpty && tr.dataset.hasData === 'false') hidden = true;
      if (addrFilter && !tr.dataset.address.includes(addrFilter)) hidden = true;
      tr.style.display = hidden ? 'none' : '';
    });
  }

  _updateBleImportBtn() {
    const btn = document.getElementById('bleImportBtn');
    if (!btn) return;
    const anyChecked = document.querySelectorAll('#bleScannerBody .ble-import-check:checked').length > 0;
    btn.disabled = !anyChecked;
  }

  importSelectedBleCommands() {
    const rows = document.querySelectorAll('#bleScannerBody tr');
    let imported = 0;

    rows.forEach(tr => {
      const checkbox = tr.querySelector('.ble-import-check');
      if (!checkbox || !checkbox.checked) return;

      const select = tr.querySelector('.ble-field-select');
      const nameInput = tr.querySelector('.ble-import-name');
      if (!select || !select.value) return;

      const cmdName = (nameInput?.value || '').trim() || tr.dataset.address || `ble_cmd_${imported}`;

      let payload;
      try {
        payload = JSON.parse(select.value);
      } catch (e) { return; }

      // Use raw advertisement bytes when available; fall back to data_hex
      const code = tr.dataset.raw || payload.data_hex;

      this.tempCommands[cmdName] = {
        type: 'button',
        values: {
          code
        },
        props: {
          color: '#2196f3',
          icon: '📡',
          display: 'both'
        }
      };
      imported++;
    });

    this.stopBlePoll();
    if (this._bleScannerModal) {
      this._bleScannerModal.close();
      this._bleScannerModal = null;
    }

    if (imported > 0) {
      Notification.success(`Imported ${imported} BLE command(s)`);
      // Re-render commands list in device modal
      const commandsList = Utils.$('#commandsList');
      if (commandsList) {
        commandsList.innerHTML = this.renderCommandsList(this.tempCommands);
      }
    }
  }
}

window.DeviceManager = DeviceManager;
