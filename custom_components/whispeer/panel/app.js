class WhispeerApp {
  constructor() {
    this.deviceManager = null;
    this.autoRefreshInterval = null;
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

    if (settings.refreshInterval > 0) {
      this.startAutoRefresh(settings.refreshInterval);
    }
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

    header.appendChild(refreshBtn);
    header.appendChild(settingsBtn);
  }

  setupModals() {
    this.setupSettingsModal();
  }

  setupSettingsModal() {
    const settingsForm = FormBuilder.create()
      .number('refreshInterval', {
        label: 'Auto Refresh Interval (seconds)',
        value: DataManager.settings.refreshInterval / 1000,
        min: 0,
        step: 1
      })
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
      this.syncWithBackend();
    });

    Utils.events.on('error', (e) => {
      this.handleError(e.detail);
    });
  }

  startApplication() {
    this.showLoadingState();
    
    setTimeout(() => {
      this.hideLoadingState();
      this.deviceManager.loadDevices();
    }, 500);
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
      await DataManager.syncWithBackend();
      DataManager.loadDevices();
      this.deviceManager.renderDevices();
      Notification.success('Devices refreshed successfully');
    } catch (error) {
      Notification.error('Failed to refresh devices');
      console.error('Refresh error:', error);
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
    
    settings.refreshInterval = parseInt(settings.refreshInterval) * 1000;

    DataManager.updateSettings(settings);
    this.applySettings();
    this.settingsModal.close();
    
    Notification.success('Settings saved successfully');
  }

  startAutoRefresh(interval = 5000) {
    this.stopAutoRefresh();
    
    if (interval > 0) {
      this.autoRefreshInterval = setInterval(() => {
        this.syncWithBackend();
      }, interval);
    }
  }

  stopAutoRefresh() {
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval);
      this.autoRefreshInterval = null;
    }
  }

  async syncWithBackend() {
    try {
      await DataManager.syncWithBackend();
    } catch (error) {
      console.error('Auto sync failed:', error);
    }
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
