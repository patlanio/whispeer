class TemplateEngine {
  static templates = new Map();

  static register(name, template) {
    TemplateEngine.templates.set(name, template);
  }

  static get(name) {
    return TemplateEngine.templates.get(name);
  }

  static render(name, data = {}) {
    const template = TemplateEngine.get(name);
    if (!template) {
      console.warn(`Template '${name}' not found`);
      return '';
    }

    return TemplateEngine.compile(template, data);
  }

  static compile(template, data) {
    return template.replace(/\{\{([^}]+)\}\}/g, (match, key) => {
      const keys = key.trim().split('.');
      let value = data;
      
      for (const k of keys) {
        value = value?.[k];
      }
      
      return value !== undefined ? String(value) : '';
    });
  }

  static renderList(templateName, items, itemKey = 'item') {
    const template = TemplateEngine.get(templateName);
    if (!template) return '';

    return items.map(item => 
      TemplateEngine.compile(template, { [itemKey]: item, ...item })
    ).join('');
  }

  static clone(templateName) {
    const template = TemplateEngine.get(templateName);
    if (!template) return null;

    const element = Utils.parseHTML(template);
    return element ? element.cloneNode(true) : null;
  }
}

TemplateEngine.register('device-card', `
  <div class="device-card" data-device-id="{{id}}">
    <div class="device-header">
      <div class="device-name">{{name}}</div>
      <div class="device-header-right">
        <span class="device-type-badge {{badgeClass}}">{{type}}</span>
        <button class="pill-edit" onclick="deviceManager.configureDevice('{{id}}')">⚙️</button>
      </div>
    </div>
    <div class="device-info">{{interface}} • {{commandCount}} commands</div>
    <div class="device-commands">{{commands}}</div>
  </div>
`);

TemplateEngine.register('command-button', `
  <button class="btn btn-small command-btn" 
          onclick="deviceManager.executeCommand('{{deviceId}}', '{{commandName}}')"
          style="{{buttonStyle}}">
    {{buttonContent}}
  </button>
`);

TemplateEngine.register('form-input', `
  <div class="form-group">
    <label class="form-label">{{label}}</label>
    <input type="{{type}}" 
           name="{{name}}" 
           class="form-input" 
           placeholder="{{placeholder}}" 
           value="{{value}}"
           {{required}}>
  </div>
`);

TemplateEngine.register('modal-base', `
  <div class="modal-content {{size}}">
    <div class="modal-header">
      <h3 class="modal-title">{{title}}</h3>
      {{closeButton}}
    </div>
    <div class="modal-body">
      {{content}}
    </div>
    <div class="modal-footer">
      {{footer}}
    </div>
  </div>
`);

TemplateEngine.register('empty-state', `
  <div class="empty-state">
    <div class="empty-icon">{{icon}}</div>
    <h3>{{title}}</h3>
    <p>{{message}}</p>
    {{action}}
  </div>
`);

TemplateEngine.register('command-group', `
  <div class="command-group" data-type="{{type}}">
    <div class="command-group-header" onclick="deviceManager.toggleCommandGroup('{{type}}')">
      <div class="command-group-title">
        <span>{{icon}} {{title}}</span>
        <span class="command-group-count">{{count}}</span>
      </div>
      <span class="command-group-chevron">▼</span>
    </div>
    <div class="command-group-content">
      {{content}}
    </div>
  </div>
`);

window.TemplateEngine = TemplateEngine;
