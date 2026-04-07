class WhispeerApp {
  constructor() {
    this.deviceManager = null;
    this.autoRefreshInterval = null; // deprecated
    this.settingsSubmitHandler = null;  // Store the handler reference
    this.init();
  }

  init() {
    this.loadSettings();
    this.initializeComponents();
    this.bindGlobalEvents();
    this.startApplication();
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

    const codesBtn = Utils.createElement('button', {
      className: 'btn btn-small btn-outlined',
      innerHTML: '📋 Codes',
      onclick: () => this.showCodesTable()
    });

    header.appendChild(refreshBtn);
    header.appendChild(codesBtn);
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

    // On device updates, just re-render; syncing happens in DataManager
    Utils.events.on('deviceUpdated', () => {
      this.refreshDevices();
    });

    Utils.events.on('error', (e) => {
      this.handleError(e.detail);
    });
  }

  async startApplication() {
    this.showLoadingState();
    try {
      await this.deviceManager.loadDevices();
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

  async showCodesTable() {
    const token = DataManager.getHomeAssistantToken();
    let codes = [];
    try {
      const url = token
        ? `/api/whispeer/stored_codes?access_token=${encodeURIComponent(token)}`
        : '/api/whispeer/stored_codes';
      const response = await Utils.api.get(url);
      codes = (response && response.codes) ? response.codes : [];
    } catch (e) {
      console.error('Failed to load learned codes:', e);
    }

    let rows = '';
    codes.forEach(c => {
      const preview = c.code_preview || '-';
      const identifier = c.identifier || c.mac || '-';
      rows += `<tr>`
        + `<td>${c.device}</td>`
        + `<td>${c.command}</td>`
        + `<td>${identifier}</td>`
        + `<td>${c.source}</td>`
        + `<td>${c.code_length}</td>`
        + `<td title="${c.code}">${preview}</td>`
        + `</tr>`;
    });

    if (!rows) {
      rows = '<tr><td colspan="6">No learned codes found in Home Assistant</td></tr>';
    }

    const tableHTML = `
      <table border="1" cellpadding="4" cellspacing="0">
        <thead>
          <tr>
            <th>Device</th>
            <th>Command</th>
            <th>Identifier</th>
            <th>Source</th>
            <th>Code Length</th>
            <th>Code (preview)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    this.codesModal = new Modal({
      title: 'HA Learned Remote Codes',
      content: tableHTML,
      className: 'codes-modal'
    });
    this.codesModal.open();
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
