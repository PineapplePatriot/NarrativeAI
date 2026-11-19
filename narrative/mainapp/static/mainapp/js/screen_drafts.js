/* Unsent Screen text stays per account/chat/episode, including when storage is unavailable. */
(() => {
  const memory = new Map();
  const key = name => 'narrative-screen-draft:' + (window.TG?.state?.account_id ?? 'temporary') + ':' + name;
  window.ScreenDrafts = {
    persistent: true,
    get(name, fallback = {}) {
      const id = key(name);
      if (memory.has(id)) return memory.get(id);
      if (window.TG?.state?.account_id != null) {
        try {const value = sessionStorage.getItem(id); if (value != null) {const parsed = JSON.parse(value); if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {memory.set(id, parsed); return parsed;}}} catch (_) {this.persistent = false;}
      }
      return fallback;
    },
    put(name, value) {
      const id = key(name); memory.set(id, value);
      if (window.TG?.state?.account_id != null) {try {sessionStorage.setItem(id, JSON.stringify(value));} catch (_) {this.persistent = false;}}
    },
    clear(name, fields = null) {
      if (fields) {const value = {...this.get(name)}; fields.forEach(field => delete value[field]); this.put(name, value); return;}
      const id = key(name); memory.delete(id); try {sessionStorage.removeItem(id);} catch (_) {}
    },
    all(prefix) {
      const start = key(prefix), records = new Map();
      if (window.TG?.state?.account_id != null) {
        try {for (let i = 0; i < sessionStorage.length; i++) {const id = sessionStorage.key(i); if (id?.startsWith(start)) records.set(id, JSON.parse(sessionStorage.getItem(id)));}} catch (_) {}
      }
      memory.forEach((value, id) => {if (id.startsWith(start)) records.set(id, value);});
      return [...records.values()];
    },
    bind(root, name) {
      const saved = this.get(name);
      [...(root.matches('[data-screen-field]') ? [root] : []), ...root.querySelectorAll('[data-screen-field]')].forEach(input => {
        if (input.dataset.screenBound) return;
        input.dataset.screenBound = 'true';
        const field = input.dataset.screenField;
        const boolean = input.type === 'checkbox' || input.tagName === 'DETAILS';
        const prop = input.tagName === 'DETAILS' ? 'open' : boolean ? 'checked' : 'value';
        if (Object.prototype.hasOwnProperty.call(saved, field)) input[prop] = saved[field];
        const save = () => {if (input.isConnected) this.put(name, {...this.get(name), [field]: input[prop]});};
        input.addEventListener(input.tagName === 'DETAILS' ? 'toggle' : 'input', save);
        if (input.tagName === 'DETAILS') input.addEventListener('click', () => queueMicrotask(save));
        if (input.tagName !== 'DETAILS') input.addEventListener('change', save);
      });
    },
  };
})();
