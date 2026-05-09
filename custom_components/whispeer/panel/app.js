class WhispeerApp {
  constructor() {
    this.deviceManager = null;
    this.init();
  }

  init() {
    WSManager.connect();
    this.initializeComponents();
    this.bindGlobalEvents();
    WSManager.onReady(() => this.startApplication());
  }

  initializeComponents() {
    this.deviceManager = new DeviceManager('#devicesContainer');
    
    this.setupHeader();
    this.setupModals();
  }

  setupHeader() {
    const header = Utils.$('.header-controls');
    if (!header) return;

    const addDeviceBtn = Utils.createElement('button', {
      className: 'btn btn-small',
      innerHTML: 'Add device',
      onclick: () => this.deviceManager?.openAddDeviceModal()
    });

    const settingsBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-outlined',
      innerHTML: '⚙️',
      onclick: () => this.openSettingsModal()
    });

    this._importInput = Utils.createElement('input', {
      type: 'file',
      accept: '.json,application/json'
    });
    this._importInput.style.display = 'none';
    this._importInput.addEventListener('change', (e) => this._handleImportFile(e));
    document.body.appendChild(this._importInput);

    header.appendChild(settingsBtn);
    header.appendChild(addDeviceBtn);
  }

  setupModals() {
    this.setupSettingsModal();
  }

  setupSettingsModal() {
    const content = `
      <div class="advanced-actions">
        <button type="button" class="btn btn-small btn-outlined" id="advancedExportBtn">⬇️ Export</button>
        <button type="button" class="btn btn-small btn-outlined" id="advancedImportBtn">⬆️ Import</button>
        <button type="button" class="btn btn-small btn-danger btn-outlined" id="advancedClearBtn">🗑️ Clear Devices</button>
      </div>
    `;

    this.settingsModal = new Modal({
      title: 'Advanced',
      content,
      className: 'settings-modal'
    });
  }

  bindGlobalEvents() {
    window.addEventListener('beforeunload', () => {
      this.cleanup();
    });

    Utils.events.on('error', (e) => {
      this.handleError(e.detail);
    });

    WSManager.onReady(() => {
      WSManager.subscribe('whispeer_state_update', (event) => {
        const { device_id, command_name, state, type } = event.data || {};
        if (!device_id || !command_name || state === undefined) return;

        const isToggle = state === 'on' || state === 'off'
          || type === 'switch' || type === 'light';

        const isDomainEntity = command_name === 'climate'
          || command_name === 'fan'
          || command_name === 'media_player'
          || command_name === 'domain_light';

        if (isDomainEntity && window.deviceManager?.applyDomainStateUpdate) {
          window.deviceManager.applyDomainStateUpdate(
            String(device_id),
            command_name,
            {
              state,
              attributes: event.data?.attributes || {},
              entity_domain: type || '',
            }
          );
        }

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
          const mergedCommands = { ...(match.commands || {}), ...(imported.commands || {}) };
          await DataManager.updateDevice(match.id, { ...imported, id: match.id, commands: mergedCommands });
          updated++;
        } else {
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
    this._bindAdvancedActions();
  }

  _bindAdvancedActions() {
    if (!this.settingsModal?.element) return;
    const root = this.settingsModal.element;
    const exportBtn = root.querySelector('#advancedExportBtn');
    const importBtn = root.querySelector('#advancedImportBtn');
    const clearBtn = root.querySelector('#advancedClearBtn');

    if (exportBtn) exportBtn.onclick = () => this.exportDevices();
    if (importBtn) importBtn.onclick = () => this.importDevices();
    if (clearBtn) {
      clearBtn.onclick = async () => {
        await this.clearDevices();
        this.settingsModal.close();
      };
    }
  }

  async syncWithBackend() {
  }

  handleError(error) {
    console.error('Application error:', error);
    Notification.error(error.message || 'An unexpected error occurred');
  }

  cleanup() {
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
