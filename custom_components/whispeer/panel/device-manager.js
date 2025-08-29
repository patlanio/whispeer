class DeviceManager extends Component {
  constructor(selector) {
    super(selector);
    this.currentDevice = null;
    this.tempCommands = {};
    this.deviceModal = null;
    this.commandModal = null;
  }

  init() {
    this.setupTemplates();
    this.bindEvents();
    this.loadDevices();
  }

  setupTemplates() {
    this.templates = {
      deviceCard: `
        <div class="device-card" data-device-id="{{id}}">
          <div class="device-header">
            <div class="device-name">{{name}}</div>
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
          <div class="modal-controls" style="display: flex; justify-content: space-between; margin-top: 20px;">
            <button type="button" class="btn btn-outlined" onclick="deviceManager.closeDeviceModal()">Cancel</button>
            <div>
              {{deleteButton}}
              <button type="submit" class="btn">{{saveButtonText}}</button>
            </div>
          </div>
        </form>
      `,

      commandButton: `
        <button class="btn btn-small command-btn" 
                onclick="deviceManager.executeCommand('{{deviceId}}', '{{commandName}}')"
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

  loadDevices() {
    DataManager.loadDevices();
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
      `;
      return;
    }

    const devicesHTML = devices.map(device => this.renderDeviceCard(device)).join('');
    
    this.element.innerHTML = `
      <div class="devices-grid">
        ${devicesHTML}
        ${this.template('addDeviceCard')}
      </div>
    `;
  }

  renderDeviceCard(device) {
    const { id, name, type, commands = {} } = device;
    const deviceTypeConfig = APP_CONFIG.DEVICE_TYPES[type] || { label: type, badge: 'type-ble' };
    
    const commandsHTML = this.renderDeviceCommands(device);

    return this.template('deviceCard', {
      id,
      name,
      type: deviceTypeConfig.label,
      badgeClass: deviceTypeConfig.badge,
      commands: commandsHTML
    });
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
        return this.renderGroupCommand(deviceId, commandName, command);
      default:
        return this.renderButtonCommand(deviceId, commandName, command);
    }
  }

  renderButtonCommand(deviceId, commandName, command) {
    const { props = {} } = command;
    const color = props.color || '#03a9f4';
    const icon = props.icon || '💡';
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
      'sample_light': {
        type: 'light',
        values: {
          on: '',
          off: ''
        },
        props: {
          shape: 'circle',
          color: '#ffeb3b'
        }
      },
      'sample_numeric': {
        type: 'numeric',
        values: {
          '0': '',
          '1': '',
          '2': '',
          '3': ''
        },
        props: {
          shape: 'rounded',
          color: '#ff9800'
        }
      },
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
  }

  showDeviceModal(title, device = {}) {
    const isEdit = !!device.id;
    const formFields = this.buildDeviceForm(device);
    const commandsList = this.renderCommandsList(this.tempCommands);
    
    const deleteButton = isEdit ? 
      '<button type="button" class="btn btn-delete" onclick="deviceManager.deleteDevice()">Delete Device</button>' : '';

    const modalContent = this.template('deviceForm', {
      title,
      formFields,
      commandsList,
      deleteButton,
      saveButtonText: isEdit ? 'Save Changes' : 'Save'
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
    const form = FormBuilder.create()
      .input('name', {
        label: 'Device Name',
        value: device.name || '',
        required: true,
        placeholder: 'Enter device name'
      })
      .row([
        { 
          type: 'select', 
          options: { 
            name: 'type',
            label: 'Device Type',
            value: device.type || 'ir',
            options: [
              { value: 'ir', label: 'Infrared' },
              { value: 'rf', label: 'Radio Frequency' },
              { value: 'ble', label: 'Bluetooth LE' }
            ]
          }
        },
        { 
          type: 'select', 
          options: { 
            name: 'interface',
            label: 'Interface',
            value: device.interface || '',
            options: []
          }
        }
      ])
      .hidden('id', device.id || '');

    return form.build().innerHTML;
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

  createInlineCommandForm(command = null, isExisting = false) {
    const name = command?.name || '';
    const type = command?.type || 'button';
    const values = command?.values || {};
    const props = command?.props || {};
    
    const id = Utils.generateId();
    const buttonText = isExisting ? 'Save' : 'Add';
    const deleteButton = isExisting ? 
      `<button type="button" class="command-inline-btn delete" onclick="deviceManager.deleteCommand('${name}')">Delete</button>` : '';

    let codeField = '';
    if (type === 'button') {
      const learnButton = `<button type="button" class="command-inline-btn learn" 
                onclick="deviceManager.learnCommand(this)">Learn</button>`;
      
      codeField = `
        <input type="text" class="command-inline-input code" 
               placeholder="code" value="${values.code || ''}" 
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
                    onclick="deviceManager.learnOptionCommand(this, '${key}')">Learn</button>`;
          
          optionsHtml += `
            <div class="option-field">
              <input type="${type === 'numeric' ? 'number' : 'text'}" 
                     placeholder="${type === 'numeric' ? 'Number' : 'Option'}" 
                     value="${key}" class="command-inline-input" data-option-key>
              <input type="text" placeholder="Command code" value="${value}" class="command-inline-input" data-option-value>
              ${learnButton}
              <button type="button" class="command-inline-btn test" 
                      onclick="deviceManager.testOptionCommand(this, '${key}')">Test</button>
              <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">❌</button>
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
              <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">❌</button>
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
          <button type="button" class="command-inline-btn save" 
                  onclick="deviceManager.saveInlineCommand(this)">${buttonText}</button>
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
      typeSelect.addEventListener('change', () => this.onDeviceTypeChange());
      this.onDeviceTypeChange();
    }
  }

  async onDeviceTypeChange() {
    const typeSelect = Utils.$('#deviceForm select[name="type"]');
    const interfaceSelect = Utils.$('#deviceForm select[name="interface"]');
    
    if (!typeSelect || !interfaceSelect) return;

    const deviceType = typeSelect.value;
    
    // Clear current interfaces and show loading
    interfaceSelect.innerHTML = '<option value="">⏳ Loading interfaces...</option>';
    interfaceSelect.disabled = true;
    
    try {
      const interfaces = await DataManager.loadInterfaces(deviceType);
      
      // Clear loading state
      interfaceSelect.disabled = false;
      
      if (interfaces && interfaces.length > 0) {
        interfaceSelect.innerHTML = interfaces.map((iface, index) => {
          // Todos los objetos deben tener label
          if (typeof iface === 'object' && iface.label) {
            // Usar el índice como value y guardar el objeto en data-interface
            const interfaceData = JSON.stringify(iface).replace(/"/g, '&quot;');
            return `<option value="${index}" data-interface="${interfaceData}">${iface.label}</option>`;
          } else {
            console.error('Invalid interface object, missing label:', iface);
            return ''; // Skip invalid interfaces
          }
        }).filter(option => option).join(''); // Remove empty options
        
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
  }

  async handleDeviceFormSubmit(e) {
    e.preventDefault();
    
    this.saveAllInlineCommands();
    
    const formData = new FormData(e.target);
    const deviceData = Object.fromEntries(formData.entries());
    deviceData.commands = this.tempCommands;

    // Add emitter information based on device type and interface
    const deviceType = deviceData.type;
    const deviceInterface = deviceData.interface;
    
    if (deviceInterface) {
      const emitterData = { interface: deviceInterface };
      
      if (deviceType === 'ir' || deviceType === 'rf') {
        // Extract IP from Broadlink interface
        const deviceIp = DataManager.extractBroadlinkIpFromInterface(deviceInterface);
        if (deviceIp) {
          emitterData.ip = deviceIp;
          
          // Try to get additional Broadlink device info from metadata
          try {
            const interfacesResponse = await DataManager.getInterfaces(deviceType);
            if (interfacesResponse && interfacesResponse.interfaces) {
              // Look for matching interface in the response
              const matchingInterface = interfacesResponse.interfaces.find(iface => 
                iface.label === deviceInterface || iface.ip === deviceIp
              );
              if (matchingInterface) {
                if (matchingInterface.mac) emitterData.mac = matchingInterface.mac;
                if (matchingInterface.type) emitterData.type = matchingInterface.type;
                if (matchingInterface.model) emitterData.model = matchingInterface.model;
                if (matchingInterface.manufacturer) emitterData.manufacturer = matchingInterface.manufacturer;
              }
            }
          } catch (error) {
            console.warn('Could not get interface metadata:', error);
          }
          
          // Add frequency for RF devices
          if (deviceType === 'rf') {
            emitterData.frequency = "433.92"; // Default frequency
          }
        }
      } else if (deviceType === 'ble') {
        // For BLE devices, the interface is the Bluetooth adapter
        emitterData.adapter = deviceInterface;
      }
      
      deviceData.emitter = emitterData;
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
      const saveButton = container.querySelector('.command-inline-btn.save');
      if (saveButton) {
        this.saveInlineCommandSilent(saveButton);
      }
    });
  }

  saveInlineCommandSilent(button) {
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
    if (!this.currentDevice) {
      Notification.warning('Save the device first to test commands');
      return;
    }

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
    const newField = `
      <div class="option-field">
        <input type="${type === 'numeric' ? 'number' : 'text'}" 
               placeholder="${type === 'numeric' ? 'Number' : 'Option'}" 
               value="" class="command-inline-input" data-option-key>
        <input type="text" placeholder="Command code" value="" class="command-inline-input" data-option-value>
        <button type="button" class="command-inline-btn test" 
                onclick="deviceManager.testOptionCommand(this)">Test</button>
        <button type="button" class="command-inline-btn delete" onclick="deviceManager.removeOptionField(this)">❌</button>
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

  // Broadlink learning functions
  canLearnCommand() {
    // Check if current device type supports learning
    const typeSelect = Utils.$('#deviceForm select[name="type"]');
    if (!typeSelect) return false;
    
    const deviceType = typeSelect.value;
    return deviceType === 'ir' || deviceType === 'rf';
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

    if (!nameInput.value.trim()) {
      Notification.error('Please enter a command name first');
      nameInput.focus();
      return;
    }

    await this.performLearnCommand(deviceInfo, nameInput.value.trim(), codeInput);
  }

  async learnOptionCommand(buttonElement, optionKey = null) {
    const deviceInfo = this.getCurrentDeviceInfo();
    if (!deviceInfo) {
      Notification.error('Please save the device first');
      return;
    }
    
    const commandContainer = buttonElement.closest('.command-container');
    const nameInput = commandContainer.querySelector('.command-inline-input.name');
    
    if (!nameInput.value.trim()) {
      Notification.error('Please enter a command name first');
      nameInput.focus();
      return;
    }

    const optionField = buttonElement.closest('.option-field');
    let keyInput, valueInput;
    
    if (optionKey) {
      // For predefined options like 'on'/'off'
      valueInput = optionField.querySelector(`input[data-option="${optionKey}"]`);
    } else {
      // For dynamic options
      keyInput = optionField.querySelector('input[data-option-key]');
      valueInput = optionField.querySelector('input[data-option-value]');
      
      if (keyInput && !keyInput.value.trim()) {
        Notification.error('Please enter an option name first');
        keyInput.focus();
        return;
      }
      
      optionKey = keyInput ? keyInput.value.trim() : 'option';
    }

    const commandName = `${nameInput.value.trim()}_${optionKey}`;
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

    // Show learning modal
    const originalButton = codeInput.parentElement.querySelector('.command-inline-btn.learn');
    if (originalButton) {
      originalButton.disabled = true;
      originalButton.textContent = '⏳ Preparing...';
    }

    let sessionId = null;
    let learningToast = null;

    try {
      // Step 1: Prepare for learning
      Notification.info(`Preparing ${deviceInfo.type.toUpperCase()} device for learning...`);
      
      const prepareResult = await CommandManager.learnCommand(
        deviceInfo.type,
        interfaceObject  // Send the complete interface object as emitter
      );

      if (prepareResult.status !== 'prepared') {
        throw new Error(prepareResult.message || 'Failed to prepare device for learning');
      }

      sessionId = prepareResult.session_id;

      // Step 2: Device is ready, show permanent toast and start polling
      if (originalButton) {
        originalButton.textContent = '📡 Ready to Learn';
      }

      // Show permanent toast asking user to press remote button
      learningToast = Notification.permanent('Press a button on the remote control');

      // Step 3: Poll for learned command
      const timeout = 30000; // 30 seconds
      const pollInterval = 1000; // 1 second
      let elapsed = 0;
      let commandLearned = false;

      while (elapsed < timeout && !commandLearned) {
        await new Promise(resolve => setTimeout(resolve, pollInterval));
        elapsed += pollInterval;

        try {
          const checkResult = await CommandManager.checkLearnedCommand(sessionId, deviceInfo.type);
          
          if (checkResult.status === 'success') {
            if (checkResult.learning_status === 'completed' && checkResult.command_data) {
              // Command learned successfully!
              const commandCode = checkResult.command_data;
              codeInput.value = commandCode;
              
              // Close permanent toast and show success
              if (learningToast) {
                learningToast.close();
                learningToast = null;
              }
              
              Notification.success(`Command "${commandName}" learned successfully!`);
              Notification.info(`Code: ${commandCode.substring(0, 20)}...`);
              commandLearned = true;
              break; // Exit the polling loop immediately
              
            } else if (checkResult.learning_status === 'learning') {
              // Still learning, continue polling
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
          // Only continue polling for expected errors (like storage full)
          const errorMessage = pollError.message || '';
          if (errorMessage.includes('session not found') || 
              errorMessage.includes('timed out') ||
              errorMessage.includes('Learning failed') ||
              errorMessage.includes('Learning session timed out')) {
            throw pollError;
          }
          // For other errors (like storage full), continue polling silently
        }
      }

      // If we exit the loop without learning a command, it's a timeout
      if (!commandLearned) {
        throw new Error('Learning timed out - no button press detected within 30 seconds');
      }

    } catch (error) {
      console.error('Learn command error:', error);
      
      // Close permanent toast if it exists
      if (learningToast) {
        learningToast.close();
        learningToast = null;
      }
      
      // Show error toast
      Notification.error(`Failed to learn command: ${error.message}`);
      
    } finally {
      // Restore button
      if (originalButton) {
        originalButton.disabled = false;
        originalButton.textContent = 'Learn';
      }
      
      // Clean up any remaining toast
      if (learningToast) {
        learningToast.close();
      }
    }
  }
}

window.DeviceManager = DeviceManager;
