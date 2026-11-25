/* Chat-local lore. Local drafts survive chat switches, failed requests and background renders. */
(() => {
  const contexts = new Map();
  const thread = () => window.TG?.state?.active_thread;
  const el = (tag, value, cls) => {const n = document.createElement(tag); if (value != null) n.textContent = value; if (cls) n.className = cls; return n;};
  const clone = value => structuredClone(value);
  const empty = () => ({title: 'Chat lore', entries: []});
  const key = tid => 'lore:' + tid;
  function context(tid) {
    if (!contexts.has(tid)) contexts.set(tid, {tid, data: null, busy: false, signature: '', error: '',
      book: null, dirty: false, kind: 'saved', directions: '', version: null, open: false,
      ...window.ScreenDrafts?.get(key(tid))});
    return contexts.get(tid);
  }
  function persist(c) {
    window.ScreenDrafts?.put(key(c.tid), {book: c.dirty ? c.book : null, dirty: c.dirty, kind: c.kind,
      directions: c.directions, version: c.version, recovery: c.recovery, open: c.open});
  }
  function changed(c) {c.dirty = true; persist(c);}
  function replace(c, book, kind) {
    if (c.dirty && c.book) c.recovery = clone(c.book);
    c.book = clone(book || empty()); c.kind = kind; c.dirty = kind !== 'saved';
    c.version = c.data?.version; persist(c);
  }
  const signature = t => JSON.stringify([t.id, t.lore?.version, (t.members || []).map(m => [m.mode, m.modern_persona, m.scenario])]);
  async function request(c, action, extra = {}) {
    if (c.busy) return;
    c.busy = true; c.error = ''; render();
    try {
      const response = await fetch(TG_CFG.screen_lore_api + (action ? '' : '?thread_id=' + c.tid), action ? {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': TG_CFG.csrf},
        body: JSON.stringify({action, thread_id: c.tid, version: c.version, ...extra}),
      } : {});
      let result;
      try {result = await response.json();} catch (_) {throw Error(`Could not read the server response (HTTP ${response.status}). Your draft is preserved.`);}
      if (!response.ok) {
        if (result.current) c.data = result.current;
        throw Error(result.error || 'Could not save lore. Your draft is preserved.');
      }
      c.data = result;
      if (action === 'draft') replace(c, result.draft, 'Bulba draft');
      else if (result.preview_book) replace(c, result.preview_book, 'copied book');
      else if (action === 'save') {c.book = clone(result.book || empty()); c.kind = 'saved'; c.dirty = false; c.version = result.version;}
      else if (!c.dirty) {c.book = clone(result.book || empty()); c.version = result.version;}
      else if (action === 'mode') c.version = result.version;
      if (!action && c.dirty && c.version && c.version !== result.version) c.error = 'Saved lore changed while this draft was open. Your edits are preserved.';
      if (!c.version) c.version = result.version;
      c.message = action === 'draft' ? 'Draft ready. Review it before saving.' : result.preview_book ? 'Copy loaded. Save it to apply.' : action ? 'Saved for this chat.' : '';
      persist(c);
    } catch (error) {c.error = error.message;}
    finally {
      c.busy = false;
      if (thread()?.id === c.tid) {
        if (c.data?.summary) thread().lore = c.data.summary;
        c.signature = signature(thread()); render();
      }
    }
  }
  function button(label, fn) {const b = el('button', label, 'tg-fmt-btn'); b.type = 'button'; b.addEventListener('click', fn); return b;}
  function field(c, label, value, change, multiline = false) {
    const wrap = el('label', null, 'tg-field-group'); wrap.append(el('span', label));
    const input = el(multiline ? 'textarea' : 'input', null, multiline ? 'tg-textarea' : 'tg-input');
    input.value = value || ''; input.addEventListener('input', () => {change(input.value); changed(c);}); wrap.append(input); return wrap;
  }
  function editor(c, target) {
    if (!c.book) return;
    target.append(el('p', c.kind === 'saved' ? 'Editing the saved book.' : 'Reviewing ' + c.kind + '. Save to apply it.'));
    target.append(field(c, 'Lorebook title', c.book.title, value => c.book.title = value));
    (c.book.entries || []).forEach((entry, index) => {
      const row = el('fieldset'); row.append(el('legend', entry.comment || 'Entry ' + (index + 1)));
      row.append(field(c, 'Entry name', entry.comment, value => entry.comment = value));
      row.append(field(c, 'Keywords (separated by commas)', (entry.keys || []).join(', '), value => entry.keys = value.split(',').map(s => s.trim()).filter(Boolean)));
      row.append(field(c, 'Facts', entry.content, value => entry.content = value, true));
      for (const [name, label, checked] of [['constant', ' Always include this entry', !!entry.constant], ['enabled', ' Entry enabled', entry.enabled !== false]]) {
        const wrap = el('label'); const input = el('input'); input.type = 'checkbox'; input.checked = checked;
        input.addEventListener('change', () => {entry[name] = input.checked; changed(c);}); wrap.append(input, document.createTextNode(label)); row.append(wrap);
      }
      row.append(button('Remove entry', () => {c.book.entries.splice(index, 1); changed(c); render();})); target.append(row);
    });
    target.append(button('Add entry', () => {c.book.entries ||= []; c.book.entries.push({comment: '', keys: [], content: '', enabled: true}); changed(c); render();}));
    target.append(button('Save to this chat', () => request(c, 'save', {book: clone(c.book)})));
  }
  function render() {
    const root = document.getElementById('screenLorePanel'), t = thread(); if (!root) return;
    if (!t) {root.replaceChildren(); return;}
    const c = context(t.id); root.replaceChildren();
    const details = el('details'); details.open = c.open;
    details.append(el('summary', t.lore?.pending ? 'New setting: set up lore for this chat' : 'Chat lore · ' + (t.lore?.title || t.lore?.mode || 'character books')));
    details.addEventListener('toggle', () => {if (details.isConnected) {c.open = details.open; persist(c);}});
    details.addEventListener('click', () => queueMicrotask(() => {if (details.isConnected) {c.open = details.open; persist(c);}}));
    const content = el('div', null, 'screen-lore-editor'); details.append(content);
    const status = el('div', c.error || (c.busy ? 'Working…' : c.message || ''), 'screen-lore-status'); status.id = 'screenLoreStatus'; status.setAttribute('role', c.error ? 'alert' : 'status');
    root.append(details, status);
    if (!c.data) {content.append(el('p', 'Loading chat lore…'), button('Retry', () => request(c)));}
    else {
      if (t.lore?.pending) content.append(el('p', 'This character’s setting changed. Create chat lore or copy a book and adapt it here. Your original books stay separate.'));
      const controls = el('div', null, 'screen-lore-actions');
      controls.append(button('New book', () => {replace(c, empty(), 'new book'); render();}));
      const sources = el('select', null, 'tg-select'); sources.append(new Option('Copy one of my books…', ''));
      (c.data.sources || []).forEach(source => sources.append(new Option(source.title, source.id)));
      sources.addEventListener('change', () => {if (sources.value) request(c, 'copy', {source_id: Number(sources.value), preview: true});});
      controls.append(sources, button('Use character books', () => request(c, 'mode', {mode: 'inherit'})), button('Continue without lore', () => request(c, 'mode', {mode: 'off'})));
      content.append(controls);
      const directions = el('textarea', null, 'tg-textarea'); directions.value = c.directions; directions.placeholder = 'Directions for Bulba’s lore draft (optional)';
      directions.addEventListener('input', () => {c.directions = directions.value; persist(c);});
      content.append(directions, button('Ask Bulba for a draft (uses tokens)', () => request(c, 'draft', {directions: c.directions})));
      if (c.data.draft && c.kind !== 'Bulba draft') content.append(button('Open Bulba draft for review', () => {replace(c, c.data.draft, 'Bulba draft'); render();}));
      if (c.dirty) content.append(button('Load saved book', () => {replace(c, c.data.book, 'saved'); render();}));
      if (c.recovery) content.append(button('Recover previous local draft', () => {replace(c, c.recovery, 'recovered draft'); render();}));
      if (c.dirty && c.version !== c.data.version) {
        const saved = el('details'); saved.append(el('summary', 'Review the saved version on the server'));
        saved.append(el('strong', c.data.book?.title || 'No local book'));
        (c.data.book?.entries || []).forEach(e => saved.append(el('p', e.content)));
        content.append(saved, button('Save my draft instead of that version', () => {c.version = c.data.version; request(c, 'save', {book: clone(c.book)});}));
      }
      const matches = el('details'); matches.append(el('summary', 'Matched lore in saved chat messages'));
      matches.addEventListener('toggle', async () => {
        if (!matches.open) return;
        try {
          const response = await fetch(TG_CFG.screen_lore_api + '?thread_id=' + c.tid); const result = await response.json();
          if (!response.ok) throw Error(result.error || 'Could not check lore.');
          matches.querySelector('ul')?.remove(); const list = el('ul'); const report = result.activation?.report || [];
          if (!report.length) list.append(el('li', 'No entries matched in the saved messages.'));
          report.forEach(item => list.append(el('li', [item.book, item.label, item.status, item.reason].filter(Boolean).join(' · ')))); matches.append(list);
        } catch (error) {if (matches.isConnected) status.textContent = error.message;}
      });
      content.append(matches); editor(c, content);
    }
    root.querySelectorAll('input, textarea, select, button').forEach(input => input.disabled = c.busy);
  }
  function sync() {
    const t = thread(); if (!t) {render(); return;}
    const c = context(t.id), sig = signature(t);
    if (c.signature !== sig) {c.signature = sig; request(c);}
    else if (!document.getElementById('screenLorePanel')?.querySelector('details') || String(t.id) !== document.getElementById('screenLorePanel').dataset.threadId) render();
    const root = document.getElementById('screenLorePanel'); if (root) root.dataset.threadId = t.id;
  }
  window.addEventListener('telechat-rendered', sync);
  document.addEventListener('DOMContentLoaded', sync);
})();
