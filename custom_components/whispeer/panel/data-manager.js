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
    ir: { label: 'Infrared', badge: 'type-ir' },
    rf: { label: 'Radio Frequency', badge: 'type-rf' },
    ble: { label: 'Bluetooth LE', badge: 'type-ble' }
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
      console.log(`Loading interfaces for device type: ${deviceType}`);
      
      const response = await Utils.api.post(APP_CONFIG.ENDPOINTS.INTERFACES, {
        type: deviceType
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

  // Broadlink specific functions
  static async discoverBroadlinkDevices() {
    try {
      const response = await Utils.api.post('/api/services/whispeer/discover_broadlink_devices', {});
      
      if (response.devices && Array.isArray(response.devices)) {
        return response.devices;
      }
      
      return [];
    } catch (error) {
      console.error('Failed to discover Broadlink devices:', error);
      return [];
    }
  }

  static async learnBroadlinkCommand(deviceName, commandName, commandType, deviceIp, frequency = 433.92) {
    try {
      const response = await Utils.api.post('/api/services/whispeer/learn_broadlink_command', {
        device_name: deviceName,
        command_name: commandName,
        command_type: commandType,
        device_ip: deviceIp,
        frequency: frequency
      });
      
      return response;
    } catch (error) {
      console.error('Failed to learn Broadlink command:', error);
      throw error;
    }
  }

  static async learnCommand(deviceType, emitterData) {
    try {
      // First, prepare the device for learning
      const prepareResponse = await Utils.api.post('/api/services/whispeer/prepare_to_learn', {
        device_type: deviceType,
        emitter: emitterData
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
      const response = await Utils.api.post('/api/services/whispeer/check_learned_command', {
        session_id: sessionId,
        device_type: deviceType
      });
      
      return response;
    } catch (error) {
      console.error('Failed to check learned command:', error);
      throw error;
    }
  }

  static async sendBroadlinkSignal(commandData, deviceIp) {
    try {
      const response = await Utils.api.post('/api/services/whispeer/send_broadlink_signal', {
        command_data: commandData,
        device_ip: deviceIp
      });
      
      return response;
    } catch (error) {
      console.error('Failed to send Broadlink signal:', error);
      throw error;
    }
  }

  static extractBroadlinkIpFromInterface(interfaceString) {
    // Extract IP from various formats:
    // "Model (IP Address)" format
    // "Model (HASS, IP Address)" format  
    // "Model Name (192.168.1.100)" format
    
    // First try to match patterns with parentheses
    let match = interfaceString.match(/\(([^)]*)\)$/);
    if (match) {
      const content = match[1];
      
      // Check if content has comma (HASS format)
      if (content.includes(',')) {
        const parts = content.split(',').map(part => part.trim());
        // Look for IP address in the parts
        for (const part of parts) {
          if (this.isValidIpAddress(part)) {
            return part;
          }
        }
      } else if (this.isValidIpAddress(content)) {
        // Direct IP address
        return content;
      }
    }
    
    // If no parentheses or no valid IP found, try to find IP anywhere in the string
    const ipPattern = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
    const ipMatches = interfaceString.match(ipPattern);
    if (ipMatches) {
      for (const ip of ipMatches) {
        if (this.isValidIpAddress(ip)) {
          return ip;
        }
      }
    }
    
    return null;
  }

  static isValidIpAddress(ip) {
    const parts = ip.split('.');
    if (parts.length !== 4) return false;
    
    for (const part of parts) {
      const num = parseInt(part, 10);
      if (isNaN(num) || num < 0 || num > 255) return false;
    }
    
    return true;
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
