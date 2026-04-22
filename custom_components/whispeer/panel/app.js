class WhispeerApp {
  constructor() {
    this.deviceManager = null;
    this.autoRefreshInterval = null; // deprecated
    this.settingsSubmitHandler = null;  // Store the handler reference
    this.init();
  }

  init() {
    this.loadSettings();
    WSManager.connect();
    this.initializeComponents();
    this.bindGlobalEvents();
    WSManager.onReady(() => this.startApplication());
  }

  loadSettings() {
    DataManager.loadSettings();
    this.applySettings();
  }

  applySettings() {
    const settings = DataManager.settings;
    
    if (settings.theme && settings.theme !== 'auto') {
      document.body.className = `theme-${settings.theme}`;
    }

    // Auto refresh removed; UI refresh occurs on CRUD events
  }

  initializeComponents() {
    this.deviceManager = new DeviceManager('#devicesContainer');
    
    this.setupHeader();
    this.setupModals();
  }

  setupHeader() {
    const header = Utils.$('.header-controls');
    if (!header) return;

    const settingsBtn = Utils.createElement('button', {
      className: 'btn btn-small',
      innerHTML: '⚙️ Settings',
      onclick: () => this.openSettingsModal()
    });

    const refreshBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-outlined',
      innerHTML: '🔄 Refresh',
      onclick: () => this.refreshDevices()
    });

    const clearBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-danger btn-outlined',
      innerHTML: '🗑️ Clear Devices',
      onclick: () => this.clearDevices()
    });

    const exportBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-outlined',
      innerHTML: '⬇️ Export',
      onclick: () => this.exportDevices()
    });

    const importBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-outlined',
      innerHTML: '⬆️ Import',
      onclick: () => this.importDevices()
    });

    // Hidden file input for import
    this._importInput = Utils.createElement('input', {
      type: 'file',
      accept: '.json,application/json'
    });
    this._importInput.style.display = 'none';
    this._importInput.addEventListener('change', (e) => this._handleImportFile(e));
    document.body.appendChild(this._importInput);

    header.appendChild(refreshBtn);
    header.appendChild(exportBtn);
    header.appendChild(importBtn);
    header.appendChild(clearBtn);
    header.appendChild(settingsBtn);
  }

  setupModals() {
    this.setupSettingsModal();
  }

  setupSettingsModal() {
    const settingsForm = FormBuilder.create()
      // Removed auto refresh interval setting
      .select('theme', [
        { value: 'auto', label: 'Auto (System)' },
        { value: 'light', label: 'Light' },
        { value: 'dark', label: 'Dark' }
      ], {
        label: 'Theme',
        value: DataManager.settings.theme
      })
      .build();

    const submitBtn = Utils.createElement('button', {
      type: 'submit',
      className: 'btn',
      innerHTML: 'Save Settings'
    });

    settingsForm.appendChild(submitBtn);

    settingsForm.addEventListener('submit', (e) => {
      e.preventDefault();
      this.handleSettingsSubmit(e);
    });

    this.settingsModal = new Modal({
      title: 'Settings',
      content: settingsForm.outerHTML,  // Convert to HTML string
      className: 'settings-modal'
    });
  }

  bindGlobalEvents() {
    window.addEventListener('beforeunload', () => {
      this.cleanup();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
        e.preventDefault();
        this.refreshDevices();
      }
    });

    Utils.events.on('deviceUpdated', () => {
      this.refreshDevices();
    });

    Utils.events.on('error', (e) => {
      this.handleError(e.detail);
    });

    // Bidirectional state sync: reflect state changes triggered
    // from HA Lovelace cards or automations back to our panel.
    WSManager.onReady(() => {
      WSManager.subscribe('whispeer_state_update', (event) => {
        const { device_id, command_name, state, type } = event.data || {};
        if (!device_id || !command_name || state === undefined) return;

        const isToggle = state === 'on' || state === 'off'
          || type === 'switch' || type === 'light';

        if (isToggle) {
          const wrapper = document.querySelector(
            `[data-entity="${device_id}:${command_name}"]`
          );
          if (wrapper) {
            const toggle = wrapper.querySelector('.command-toggle');
            if (toggle) {
              toggle.classList.toggle('on', state === 'on');
              toggle.classList.toggle('off', state !== 'on');
            }
          }
        } else {
          // select / number / options: highlight the active button.
          if (window.deviceManager) {
            window.deviceManager.updateGroupCommandState(
              String(device_id), command_name, state
            );
          }
        }
      });
    });
  }

  async startApplication() {
    this.showLoadingState();
    try {
      await this.deviceManager.loadDevices();
      this.deviceManager.loadAndRenderStoredCodes().catch(e => {
        console.error('Failed to load stored codes on startup:', e);
      });
    } catch (e) {
      console.error('Failed to load devices on startup:', e);
      // Render empty state so UI is usable
      this.deviceManager.renderDevices();
    } finally {
      this.hideLoadingState();
    }
  }

  showLoadingState() {
    const container = Utils.$('#devicesContainer');
    if (container) {
      container.innerHTML = '<div class="loading">Loading devices...</div>';
    }
  }

  hideLoadingState() {
    const loading = Utils.$('.loading');
    if (loading) {
      Utils.animation.fadeOut(loading);
    }
  }

  async refreshDevices() {
    this.showLoadingState();
    try {
      await this.deviceManager.loadDevices();
      Notification.success('Devices refreshed successfully');
    } catch (error) {
      Notification.error('Failed to refresh devices');
      console.error('Refresh error:', error);
      // Render empty state so UI remains usable
      this.deviceManager.renderDevices();
    } finally {
      this.hideLoadingState();
    }
  }

  async clearDevices() {
    this.showLoadingState();
    try {
      await DataManager.clearDevices();
      await this.deviceManager.loadDevices();
      Notification.success('All devices cleared');
    } catch (error) {
      Notification.error('Failed to clear devices');
      console.error('Clear error:', error);
      this.deviceManager.renderDevices();
    } finally {
      this.hideLoadingState();
    }
  }

  exportDevices() {
    const devices = DataManager.getAllDevices();
    if (devices.length === 0) {
      Notification.warning('No devices to export');
      return;
    }

    const payload = {
      version: 1,
      exported_at: new Date().toISOString(),
      devices: devices.map(d => ({ ...d }))
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `whispeer-devices-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    Notification.success(`Exported ${devices.length} device(s)`);
  }

  importDevices() {
    if (this._importInput) {
      this._importInput.value = '';
      this._importInput.click();
    }
  }

  async _handleImportFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    let payload;
    try {
      const text = await file.text();
      payload = JSON.parse(text);
    } catch (err) {
      Notification.error('Invalid JSON file');
      return;
    }

    // Accept either a wrapped export { devices: [...] } or a bare array
    let incoming = [];
    if (Array.isArray(payload)) {
      incoming = payload;
    } else if (payload && Array.isArray(payload.devices)) {
      incoming = payload.devices;
    } else {
      Notification.error('Unrecognised format: expected a devices array');
      return;
    }

    if (incoming.length === 0) {
      Notification.warning('No devices found in file');
      return;
    }

    this.showLoadingState();
    try {
      const existing = DataManager.getAllDevices();
      const existingByName = {};
      existing.forEach(d => { existingByName[d.name] = d; });

      let created = 0;
      let updated = 0;

      for (const imported of incoming) {
        const match = existingByName[imported.name];

        if (match) {
          // Merge commands: imported commands overwrite existing ones, missing ones are added
          const mergedCommands = { ...(match.commands || {}), ...(imported.commands || {}) };
          await DataManager.updateDevice(match.id, { ...imported, id: match.id, commands: mergedCommands });
          updated++;
        } else {
          // New device — strip id so backend assigns a fresh one
          const { id: _ignored, ...rest } = imported;
          await DataManager.addDevice(rest);
          created++;
        }
      }

      await this.deviceManager.loadDevices();
      Notification.success(`Import complete: ${created} created, ${updated} updated`);
    } catch (err) {
      Notification.error(`Import failed: ${err.message}`);
      console.error('Import error:', err);
      this.deviceManager.renderDevices();
    } finally {
      this.hideLoadingState();
    }
  }

  openSettingsModal() {
    this.settingsModal.open();
    
    // Rebind the submit event after modal opens
    setTimeout(() => {
      const form = this.settingsModal.element.querySelector('form');
      if (form) {
        // Remove any existing listener first
        if (this.settingsSubmitHandler) {
          form.removeEventListener('submit', this.settingsSubmitHandler);
        }
        
        // Create and store the new handler
        this.settingsSubmitHandler = (e) => {
          e.preventDefault();
          this.handleSettingsSubmit(e);
        };
        
        // Add the new listener
        form.addEventListener('submit', this.settingsSubmitHandler);
      }
    }, 100);
  }

  handleSettingsSubmit(e) {
    const formData = new FormData(e.target);
    const settings = Object.fromEntries(formData.entries());
    
    // Removed auto refresh interval handling

    DataManager.updateSettings(settings);
    this.applySettings();
    this.settingsModal.close();
    
    Notification.success('Settings saved successfully');
  }

  startAutoRefresh(interval = 5000) {
    // deprecated
  }

  stopAutoRefresh() {
    // deprecated
  }

  async syncWithBackend() {
    // deprecated: syncing is now performed on CRUD operations
  }

  handleError(error) {
    console.error('Application error:', error);
    Notification.error(error.message || 'An unexpected error occurred');
  }

  cleanup() {
    this.stopAutoRefresh();
    
    if (this.deviceManager) {
      this.deviceManager.destroy();
    }

    if (this.settingsModal) {
      this.settingsModal.destroy();
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new WhispeerApp();
});

window.deviceManager = null;

document.addEventListener('DOMContentLoaded', () => {
  window.deviceManager = window.app.deviceManager;
});

window.WhispeerApp = WhispeerApp;
