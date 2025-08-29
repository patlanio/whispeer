class Component {
  constructor(selector, options = {}) {
    this.element = Utils.$(selector);
    this.options = { ...this.defaultOptions, ...options };
    this.state = {};
    this.templates = {};
    this.init();
  }

  get defaultOptions() {
    return {};
  }

  init() {
  }

  setState(newState) {
    this.state = { ...this.state, ...newState };
    this.render();
  }

  render() {
  }

  destroy() {
    if (this.element) {
      this.element.remove();
    }
  }

  template(name, data = {}) {
    if (!this.templates[name]) {
      console.warn(`Template '${name}' not found`);
      return '';
    }
    
    let html = this.templates[name];
    Object.entries(data).forEach(([key, value]) => {
      const regex = new RegExp(`{{\\s*${key}\\s*}}`, 'g');
      html = html.replace(regex, value);
    });
    
    return html;
  }

  on(event, selector, callback) {
    if (typeof selector === 'function') {
      callback = selector;
      selector = null;
    }

    if (selector) {
      this.element.addEventListener(event, (e) => {
        if (e.target.matches(selector) || e.target.closest(selector)) {
          callback.call(this, e);
        }
      });
    } else {
      this.element.addEventListener(event, callback.bind(this));
    }
  }

  find(selector) {
    return this.element.querySelector(selector);
  }

  findAll(selector) {
    return Array.from(this.element.querySelectorAll(selector));
  }

  show() {
    this.element.style.display = '';
    return this;
  }

  hide() {
    this.element.style.display = 'none';
    return this;
  }

  toggle() {
    if (this.element.style.display === 'none') {
      this.show();
    } else {
      this.hide();
    }
    return this;
  }

  addClass(className) {
    this.element.classList.add(className);
    return this;
  }

  removeClass(className) {
    this.element.classList.remove(className);
    return this;
  }

  toggleClass(className) {
    this.element.classList.toggle(className);
    return this;
  }

  hasClass(className) {
    return this.element.classList.contains(className);
  }
}

class FormBuilder {
  constructor() {
    this.fields = [];
  }

  static create() {
    return new FormBuilder();
  }

  addField(type, options = {}) {
    this.fields.push({ type, options });
    return this;
  }

  input(name, options = {}) {
    return this.addField('input', { name, type: 'text', ...options });
  }

  select(name, optionsData = [], options = {}) {
    return this.addField('select', { name, options: optionsData, ...options });
  }

  textarea(name, options = {}) {
    return this.addField('textarea', { name, ...options });
  }

  checkbox(name, options = {}) {
    return this.addField('checkbox', { name, ...options });
  }

  radio(name, optionsData = [], options = {}) {
    return this.addField('radio', { name, options: optionsData, ...options });
  }

  color(name, options = {}) {
    return this.addField('color', { name, ...options });
  }

  number(name, options = {}) {
    return this.addField('number', { name, ...options });
  }

  hidden(name, value) {
    return this.addField('hidden', { name, value });
  }

  row(fields) {
    return this.addField('row', { fields });
  }

  build() {
    const form = Utils.createElement('form', { className: 'dynamic-form' });
    
    this.fields.forEach(field => {
      const fieldElement = this.createField(field);
      form.appendChild(fieldElement);
    });

    return form;
  }

  createField(field) {
    const { type, options } = field;
    const wrapper = Utils.createElement('div', { className: 'form-group' });

    if (type !== 'hidden' && options.label) {
      const label = Utils.createElement('label', {
        className: 'form-label',
        innerHTML: options.label
      });
      wrapper.appendChild(label);
    }

    let input;
    switch (type) {
      case 'input':
        input = Utils.createElement('input', {
          type: options.type || 'text',
          name: options.name,
          className: 'form-input',
          placeholder: options.placeholder || '',
          value: options.value || '',
          required: options.required || false
        });
        break;

      case 'select':
        input = Utils.createElement('select', {
          name: options.name,
          className: 'form-select'
        });
        
        (options.options || []).forEach(opt => {
          const optionElement = Utils.createElement('option', {
            value: typeof opt === 'object' ? opt.value : opt,
            innerHTML: typeof opt === 'object' ? opt.label : opt
          });
          
          if (opt.selected || opt.value === options.value) {
            optionElement.selected = true;
          }
          
          input.appendChild(optionElement);
        });
        break;

      case 'textarea':
        input = Utils.createElement('textarea', {
          name: options.name,
          className: 'form-input',
          placeholder: options.placeholder || '',
          innerHTML: options.value || '',
          rows: options.rows || 3
        });
        break;

      case 'checkbox':
        input = Utils.createElement('input', {
          type: 'checkbox',
          name: options.name,
          value: options.value || '1',
          checked: options.checked || false
        });
        break;

      case 'radio':
        const radioGroup = Utils.createElement('div', { className: 'radio-group' });
        (options.options || []).forEach(opt => {
          const radioWrapper = Utils.createElement('div', { className: 'radio-option' });
          const radio = Utils.createElement('input', {
            type: 'radio',
            name: options.name,
            value: typeof opt === 'object' ? opt.value : opt,
            checked: opt.checked || opt.value === options.value
          });
          
          const radioLabel = Utils.createElement('label', {
            innerHTML: typeof opt === 'object' ? opt.label : opt
          });
          
          radioWrapper.appendChild(radio);
          radioWrapper.appendChild(radioLabel);
          radioGroup.appendChild(radioWrapper);
        });
        wrapper.appendChild(radioGroup);
        return wrapper;

      case 'color':
        input = Utils.createElement('input', {
          type: 'color',
          name: options.name,
          className: 'color-picker',
          value: options.value || '#000000'
        });
        break;

      case 'number':
        input = Utils.createElement('input', {
          type: 'number',
          name: options.name,
          className: 'form-input',
          value: options.value || '',
          min: options.min,
          max: options.max,
          step: options.step
        });
        break;

      case 'hidden':
        input = Utils.createElement('input', {
          type: 'hidden',
          name: options.name,
          value: options.value || ''
        });
        return input;

      case 'row':
        const rowWrapper = Utils.createElement('div', { className: 'form-row' });
        options.fields.forEach(fieldConfig => {
          const fieldElement = this.createField(fieldConfig);
          rowWrapper.appendChild(fieldElement);
        });
        return rowWrapper;

      default:
        input = Utils.createElement('input', {
          type: 'text',
          name: options.name,
          className: 'form-input'
        });
    }

    if (options.disabled) {
      input.disabled = true;
    }

    if (options.readonly) {
      input.readOnly = true;
    }

    wrapper.appendChild(input);
    return wrapper;
  }

  getFormData(form) {
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
      if (data[key]) {
        if (Array.isArray(data[key])) {
          data[key].push(value);
        } else {
          data[key] = [data[key], value];
        }
      } else {
        data[key] = value;
      }
    }
    
    return data;
  }
}

class Modal extends Component {
  constructor(options = {}) {
    super(null, options);
  }

  get defaultOptions() {
    return {
      title: '',
      content: '',
      size: 'medium',
      closable: true,
      backdrop: true,
      className: ''
    };
  }

  init() {
    this.create();
    this.bindEvents();
  }

  create() {
    this.element = Utils.createElement('div', {
      className: `modal ${this.options.className}`,
      innerHTML: this.getTemplate()
    });

    document.body.appendChild(this.element);
  }

  getTemplate() {
    return `
      <div class="modal-content ${this.options.size}">
        <div class="modal-header">
          <h3 class="modal-title">${this.options.title}</h3>
          ${this.options.closable ? '<button type="button" class="close-btn">&times;</button>' : ''}
        </div>
        <div class="modal-body">
          ${this.options.content}
        </div>
      </div>
    `;
  }

  bindEvents() {
    if (this.options.closable) {
      this.on('click', '.close-btn', () => this.close());
    }

    if (this.options.backdrop) {
      this.on('click', (e) => {
        if (e.target === this.element) {
          this.close();
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.options.closable) {
        this.close();
      }
    });
  }

  open() {
    this.element.style.display = 'block';
    Utils.animation.fadeIn(this.element);
    document.body.style.overflow = 'hidden';
    return this;
  }

  close() {
    Utils.animation.fadeOut(this.element, 200);
    document.body.style.overflow = '';
    setTimeout(() => {
      this.element.style.display = 'none';
    }, 200);
    return this;
  }

  setTitle(title) {
    const titleElement = this.find('.modal-title');
    if (titleElement) {
      titleElement.textContent = title;
    }
    return this;
  }

  setContent(content) {
    const bodyElement = this.find('.modal-body');
    if (bodyElement) {
      if (typeof content === 'string') {
        bodyElement.innerHTML = content;
      } else {
        bodyElement.innerHTML = '';
        bodyElement.appendChild(content);
      }
    }
    return this;
  }

  destroy() {
    this.close();
    setTimeout(() => {
      super.destroy();
    }, 200);
  }
}

class Toast {
  static container = null;

  static init() {
    if (!Toast.container) {
      Toast.container = Utils.createElement('div', {
        className: 'toast-container',
        style: 'position: fixed; top: 20px; right: 20px; z-index: 10000;'
      });
      document.body.appendChild(Toast.container);
    }
  }

  static show(message, type = 'info', duration = 3000) {
    Toast.init();

    const toast = Utils.createElement('div', {
      className: `toast toast-${type}`,
      innerHTML: `
        <div class="toast-content">
          <span class="toast-message">${Utils.sanitizeHTML(message)}</span>
          <button class="toast-close">&times;</button>
        </div>
      `,
      style: `
        background: var(--surface-color);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 8px;
        box-shadow: var(--shadow);
        transform: translateX(100%);
        transition: transform 0.3s ease;
        max-width: 300px;
        word-wrap: break-word;
      `
    });

    const typeColors = {
      success: '#4caf50',
      error: '#f44336',
      warning: '#ff9800',
      info: '#2196f3'
    };

    if (typeColors[type]) {
      toast.style.borderLeftColor = typeColors[type];
      toast.style.borderLeftWidth = '4px';
    }

    Toast.container.appendChild(toast);

    setTimeout(() => {
      toast.style.transform = 'translateX(0)';
    }, 10);

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => Toast.remove(toast));

    if (duration > 0) {
      setTimeout(() => Toast.remove(toast), duration);
    }

    // Add close method to the toast instance
    toast.close = () => Toast.remove(toast);

    return toast;
  }

  static permanent(message, type = 'info') {
    return Toast.show(message, type, 0); // 0 duration means permanent
  }

  static remove(toast) {
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }

  static success(message, duration) {
    return Toast.show(message, 'success', duration);
  }

  static error(message, duration) {
    return Toast.show(message, 'error', duration);
  }

  static warning(message, duration) {
    return Toast.show(message, 'warning', duration);
  }

  static info(message, duration) {
    return Toast.show(message, 'info', duration);
  }
}

class Notification {
  static show(message, type = 'info') {
    return Toast.show(message, type);
  }

  static success(message) {
    return Toast.success(message);
  }

  static error(message) {
    return Toast.error(message);
  }

  static warning(message) {
    return Toast.warning(message);
  }

  static info(message) {
    return Toast.info(message);
  }

  static permanent(message, type = 'info') {
    return Toast.permanent(message, type);
  }
}

window.Component = Component;
window.FormBuilder = FormBuilder;
window.Modal = Modal;
window.Toast = Toast;
window.Notification = Notification;
