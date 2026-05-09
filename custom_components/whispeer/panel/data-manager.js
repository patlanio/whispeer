const APP_CONFIG = {
  API_BASE: '',
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
      title: 'Numeric Range',
      fields: [],
      hasOptions: true
    },
    group: {
      icon: '📁',
      title: 'Group',
      fields: [],
      hasOptions: true
    },
    options: {
      icon: '📋',
      title: 'Options',
      fields: [],
      hasOptions: true
    }
  },
  EMOJIS: ['🏠', '🛋️', '🛏️', '🚪', '🚗', '💡', '🖥️', '🧊', '🌀', '🔌'],
  DEVICE_TYPES: {
    ir: { label: 'IR', badge: 'type-ir' },
    rf: { label: 'RF', badge: 'type-rf' },
    ble: { label: 'BLE', badge: 'type-ble' }
  },
  DEVICE_DOMAINS: {
    default:      { label: 'IR/RF/BLE', badge: 'type-ir' },
    climate:      { label: 'Climate', badge: 'type-climate' },
    fan:          { label: 'Fan', badge: 'type-fan' },
    media_player: { label: 'Media Player', badge: 'type-media-player' },
    light:        { label: 'Light', badge: 'type-light-ir' }
  }
};

class DataManager {
  static devices = {};
  static automations = {};
  static settings = {
    language: 'en'
  };

  static async loadDevices() {
    try {
      const result = await WSManager.call('whispeer/get_devices');
      const list = result?.devices || [];
      DataManager.devices = {};
      list.forEach(d => {
        const id = String(d.id);
        DataManager.devices[id] = { ...d, id };
      });
      return DataManager.devices;
    } catch (error) {
      console.error('[DataManager] Failed to load devices:', error);
      DataManager.devices = {};
      return DataManager.devices;
    }
  }

  static async saveDevices() {
  }

  static async addDevice(device) {
    try {
      const result = await WSManager.call('whispeer/add_device', { device });
      if (result?.status === 'success') {
        const id = String(result.id);
        DataManager.devices[id] = { ...device, id };
        await DataManager.syncWithBackend();
        Utils.events.emit('deviceUpdated', { deviceId: id });
        return id;
      }
      throw new Error(result?.message || 'Failed to add device');
    } catch (error) {
      console.error('[DataManager] Failed to add device:', error);
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
      await WSManager.call('whispeer/remove_device', { device_id: String(id) });
      if (DataManager.devices[id]) {
        delete DataManager.devices[id];
      }
      await DataManager.syncWithBackend();
      Utils.events.emit('deviceDeleted', { deviceId: id });
      return true;
    } catch (error) {
      console.error('[DataManager] Failed to delete device:', error);
      return false;
    }
  }

  static async clearDevices() {
    const result = await WSManager.call('whispeer/clear_devices');
    DataManager.devices = {};
    Utils.events.emit('deviceUpdated', {});
    return result;
  }

  static async clearWhispeerEntities() {
    return await WSManager.call('whispeer/clear_entities');
  }

  static getDevice(id) {
    return DataManager.devices[id] || null;
  }

  static getAllDevices() {
    return Object.values(DataManager.devices);
  }

  static async loadAutomations() {
    try {
      const result = await WSManager.call('whispeer/get_automations');
      DataManager.automations = result?.device_automations || {};
    } catch (error) {
      console.error('[DataManager] Failed to load automations:', error);
      DataManager.automations = {};
    }
    return DataManager.automations;
  }

  static getDeviceAutomations(deviceId) {
    return DataManager.automations[String(deviceId)] || [];
  }

  static loadSettings() {
    return DataManager.settings;
  }

  static saveSettings() {
  }

  static updateSettings(updates) {
    DataManager.settings = { ...DataManager.settings, ...updates };
    DataManager.saveSettings();
  }

  static async syncWithBackend() {
    try {
      await WSManager.call('whispeer/sync_devices', { devices: DataManager.devices });
    } catch (error) {
      console.error('[DataManager] Failed to sync with backend:', error);
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
      const result = await WSManager.call('whispeer/get_interfaces', { device_type: deviceType });
      if (result?.status !== 'success') {
        console.error('[DataManager] Failed to load interfaces:', result?.message);
        return [];
      }
      return (result?.interfaces || []).filter(
        iface => typeof iface === 'object' && iface.label
      );
    } catch (error) {
      console.error(`[DataManager] Failed to load interfaces for ${deviceType}:`, error);
      return [];
    }
  }

  static async sendCommand(deviceId, deviceType, commandName, commandCode, subCommand = null) {
    try {
      const payload = {
        device_id: String(deviceId),
        device_type: deviceType,
        command_name: commandName,
        command_code: commandCode,
      };
      if (subCommand) payload.sub_command = subCommand;
      const device = DataManager.getDevice(deviceId);
      if (device?.emitter) payload.emitter = device.emitter;
      return await WSManager.call('whispeer/send_command', payload);
    } catch (error) {
      console.error('[DataManager] Failed to send command:', error);
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

  static async learnCommand(deviceType, emitterData) {
    try {
      const result = await WSManager.call('whispeer/prepare_to_learn', {
        device_type: deviceType,
        emitter: emitterData,
      });
      if (result?.status !== 'success') {
        throw new Error(result?.message || 'Failed to prepare device for learning');
      }
      return {
        status: 'prepared',
        session_id: result.session_id,
        device_type: deviceType,
      };
    } catch (error) {
      console.error('[CommandManager] Failed to prepare for learning:', error);
      throw error;
    }
  }

  static interfacesCache = {};
  static CACHE_TIMEOUT = 30000;

  static async getInterfaces(deviceType) {
    const cached = this.interfacesCache[deviceType];
    if (cached && (Date.now() - cached.timestamp) < this.CACHE_TIMEOUT) {
      return cached.data;
    }
    const interfaces = await DataManager.loadInterfaces(deviceType);
    const response = { status: 'success', interfaces };
    this.interfacesCache[deviceType] = { data: response, timestamp: Date.now() };
    return response;
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
