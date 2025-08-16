class Utils {
  static $ = (selector, context = document) => {
    if (typeof selector === 'string') {
      return context.querySelector(selector);
    }
    return selector;
  };

  static $$ = (selector, context = document) => {
    return Array.from(context.querySelectorAll(selector));
  };

  static createElement = (tag, attributes = {}, children = []) => {
    const element = document.createElement(tag);
    
    Object.entries(attributes).forEach(([key, value]) => {
      if (key === 'className') {
        element.className = value;
      } else if (key === 'innerHTML') {
        element.innerHTML = value;
      } else if (key.startsWith('on')) {
        element.addEventListener(key.slice(2).toLowerCase(), value);
      } else {
        element.setAttribute(key, value);
      }
    });

    children.forEach(child => {
      if (typeof child === 'string') {
        element.appendChild(document.createTextNode(child));
      } else if (child instanceof Element) {
        element.appendChild(child);
      }
    });

    return element;
  };

  static parseHTML = (html) => {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content.firstChild;
  };

  static debounce = (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  };

  static throttle = (func, delay) => {
    let timeoutId;
    let lastExecTime = 0;
    return function (...args) {
      const currentTime = Date.now();
      
      if (currentTime - lastExecTime > delay) {
        func.apply(this, args);
        lastExecTime = currentTime;
      } else {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
          func.apply(this, args);
          lastExecTime = Date.now();
        }, delay - (currentTime - lastExecTime));
      }
    };
  };

  static deepClone = (obj) => {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj instanceof Date) return new Date(obj.getTime());
    if (obj instanceof Array) return obj.map(item => Utils.deepClone(item));
    if (typeof obj === 'object') {
      const clonedObj = {};
      Object.keys(obj).forEach(key => {
        clonedObj[key] = Utils.deepClone(obj[key]);
      });
      return clonedObj;
    }
  };

  static isEmpty = (value) => {
    if (value == null) return true;
    if (Array.isArray(value) || typeof value === 'string') return value.length === 0;
    if (typeof value === 'object') return Object.keys(value).length === 0;
    return false;
  };

  static generateId = () => {
    return '_' + Math.random().toString(36).substr(2, 9);
  };

  static sanitizeHTML = (str) => {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  };

  static formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  static camelToKebab = (str) => {
    return str.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`);
  };

  static kebabToCamel = (str) => {
    return str.replace(/-([a-z])/g, (g) => g[1].toUpperCase());
  };

  static getUrlParams = () => {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    for (let [key, value] of params) {
      result[key] = value;
    }
    return result;
  };

  static setUrlParam = (key, value) => {
    const url = new URL(window.location);
    url.searchParams.set(key, value);
    window.history.pushState({}, '', url);
  };

  static copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      return true;
    }
  };

  static validateEmail = (email) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  };

  static validateHex = (hex) => {
    return /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/.test(hex);
  };

  static storage = {
    get: (key, defaultValue = null) => {
      try {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : defaultValue;
      } catch {
        return defaultValue;
      }
    },
    
    set: (key, value) => {
      try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
      } catch {
        return false;
      }
    },
    
    remove: (key) => {
      localStorage.removeItem(key);
    },
    
    clear: () => {
      localStorage.clear();
    }
  };

  static api = {
    get: async (url, options = {}) => {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return response.json();
    },

    post: async (url, data = {}, options = {}) => {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        body: JSON.stringify(data),
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return response.json();
    },

    put: async (url, data = {}, options = {}) => {
      const response = await fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        body: JSON.stringify(data),
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return response.json();
    },

    delete: async (url, options = {}) => {
      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return response.json();
    }
  };

  static events = {
    emitter: new EventTarget(),
    
    on: (event, callback) => {
      Utils.events.emitter.addEventListener(event, callback);
    },
    
    off: (event, callback) => {
      Utils.events.emitter.removeEventListener(event, callback);
    },
    
    emit: (event, data = {}) => {
      Utils.events.emitter.dispatchEvent(new CustomEvent(event, { detail: data }));
    }
  };

  static animation = {
    fadeIn: (element, duration = 300) => {
      element.style.opacity = '0';
      element.style.display = 'block';
      
      const start = performance.now();
      const animate = (timestamp) => {
        const progress = (timestamp - start) / duration;
        element.style.opacity = Math.min(progress, 1);
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        }
      };
      
      requestAnimationFrame(animate);
    },

    fadeOut: (element, duration = 300) => {
      const start = performance.now();
      const initialOpacity = parseFloat(getComputedStyle(element).opacity);
      
      const animate = (timestamp) => {
        const progress = (timestamp - start) / duration;
        element.style.opacity = initialOpacity * (1 - Math.min(progress, 1));
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          element.style.display = 'none';
        }
      };
      
      requestAnimationFrame(animate);
    },

    slideDown: (element, duration = 300) => {
      element.style.overflow = 'hidden';
      element.style.height = '0';
      element.style.display = 'block';
      
      const targetHeight = element.scrollHeight;
      const start = performance.now();
      
      const animate = (timestamp) => {
        const progress = (timestamp - start) / duration;
        element.style.height = `${targetHeight * Math.min(progress, 1)}px`;
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          element.style.height = '';
          element.style.overflow = '';
        }
      };
      
      requestAnimationFrame(animate);
    },

    slideUp: (element, duration = 300) => {
      element.style.overflow = 'hidden';
      const initialHeight = element.offsetHeight;
      const start = performance.now();
      
      const animate = (timestamp) => {
        const progress = (timestamp - start) / duration;
        element.style.height = `${initialHeight * (1 - Math.min(progress, 1))}px`;
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          element.style.display = 'none';
          element.style.height = '';
          element.style.overflow = '';
        }
      };
      
      requestAnimationFrame(animate);
    }
  };
}

window.Utils = Utils;
