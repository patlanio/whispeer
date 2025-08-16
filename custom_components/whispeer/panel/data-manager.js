const APP_CONFIG = {
  API_BASE: '',
  ENDPOINTS: {
    DEVICES: '/api/whispeer/devices',
    SEND_COMMAND: '/api/services/whispeer/send_command',
    SYNC_DEVICES: '/api/services/whispeer/sync_devices',
    REMOVE_DEVICE: '/api/services/whispeer/remove_device',
    INTERFACES: '/api/services/whispeer/get_interfaces'
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
    ble: { label: 'Bluetooth LE', badge: 'type-ble' },
    rf: { label: 'Radio Frequency', badge: 'type-rf' },
    ir: { label: 'Infrared', badge: 'type-ir' }
  }
};

class DataManager {
  static devices = {};
  static settings = {
    refreshInterval: 5000,
    theme: 'auto',
    language: 'en'
  };

  static loadDevices() {
    const stored = Utils.storage.get(APP_CONFIG.STORAGE_KEYS.DEVICES, {});
    DataManager.devices = stored;
    return DataManager.devices;
  }

  static saveDevices() {
    Utils.storage.set(APP_CONFIG.STORAGE_KEYS.DEVICES, DataManager.devices);
    DataManager.syncWithBackend();
  }

  static addDevice(device) {
    const id = device.id || Utils.generateId();
    DataManager.devices[id] = { ...device, id };
    DataManager.saveDevices();
    return id;
  }

  static updateDevice(id, updates) {
    if (DataManager.devices[id]) {
      DataManager.devices[id] = { ...DataManager.devices[id], ...updates };
      DataManager.saveDevices();
      return true;
    }
    return false;
  }

  static deleteDevice(id) {
    if (DataManager.devices[id]) {
      delete DataManager.devices[id];
      DataManager.saveDevices();
      return true;
    }
    return false;
  }

  static getDevice(id) {
    return DataManager.devices[id] || null;
  }

  static getAllDevices() {
    return Object.values(DataManager.devices);
  }

  static loadSettings() {
    const stored = Utils.storage.get(APP_CONFIG.STORAGE_KEYS.SETTINGS, {});
    DataManager.settings = { ...DataManager.settings, ...stored };
    return DataManager.settings;
  }

  static saveSettings() {
    Utils.storage.set(APP_CONFIG.STORAGE_KEYS.SETTINGS, DataManager.settings);
  }

  static updateSettings(updates) {
    DataManager.settings = { ...DataManager.settings, ...updates };
    DataManager.saveSettings();
  }

  static async syncWithBackend() {
    try {
      const token = DataManager.getHomeAssistantToken();
      if (!token) return;

      await Utils.api.post(APP_CONFIG.ENDPOINTS.SYNC_DEVICES, {
        devices: DataManager.devices
      }, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
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
      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.INTERFACES, {
        type: deviceType
      });
      
      // Handle both array format (old) and object format (new API response)
      if (response.interfaces) {
        // New format: return interface names or IDs
        return response.interfaces.map(iface => 
          typeof iface === 'string' ? iface : (iface.id || iface.name)
        );
      }
      
      return [];
    } catch (error) {
      console.error('Failed to load interfaces:', error);
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
}

window.APP_CONFIG = APP_CONFIG;
window.DataManager = DataManager;
window.CommandManager = CommandManager;
