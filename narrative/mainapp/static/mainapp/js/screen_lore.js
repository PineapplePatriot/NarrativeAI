/* Chat-local lore editor. No model request is made until the user asks for a draft. */
(() => {
  let loaded = '', data = null, book = null, busy = false;
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const thread = () => window.TG && TG.state.active_thread;
  async function request(action, extra = {}) {
    const t = thread(); if (!t || busy) return;
    const tid = t.id;
    busy = true;
    try {
      const response = await fetch(TG_CFG.screen_lore_api + (action ? '' : '?thread_id=' + tid), action ? {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': TG_CFG.csrf},
        body: JSON.stringify({action, thread_id: tid, ...extra}),
      } : {});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Could not load lore.');
      if (!thread() || thread().id !== tid) return;
      data = result;
      if (result.thread) TG.state.active_thread = result.thread;
      thread().lore = result.summary;
      book = structuredClone(action === 'draft' ? result.draft : result.book || {title: 'Chat lore', entries: []});
      render();
      if (action) document.getElementById('screenLoreStatus').textContent = action === 'draft' ? 'Draft ready. Review it before saving.' : 'Saved for this chat.';
    } catch (error) {
      const target = document.getElementById('screenLoreStatus'); if (target) target.textContent = error.message;
    } finally {
      busy = false;
      if (thread() && thread().id !== tid) {loaded = ''; sync();}
    }
  }
  function button(text, fn) { const b = el('button', text, 'tg-fmt-btn'); b.type = 'button'; b.addEventListener('click', fn); return b; }
  function field(label, value, change, multiline = false) {
    const wrap = el('label', null, 'tg-field-group'); wrap.append(el('span', label));
    const input = el(multiline ? 'textarea' : 'input', null, multiline ? 'tg-textarea' : 'tg-input');
    input.value = value || ''; input.addEventListener('input', () => change(input.value)); wrap.append(input); return wrap;
  }
  function editor(target) {
    if (!book) return;
    target.append(field('Lorebook title', book.title, value => book.title = value));
    (book.entries || []).forEach((entry, index) => {
      const row = el('fieldset'); row.append(el('legend', entry.comment || 'Entry ' + (index + 1)));
      row.append(field('Entry name', entry.comment, value => entry.comment = value));
      row.append(field('Keywords (separated by commas)', (entry.keys || []).join(', '), value => entry.keys = value.split(',').map(s => s.trim()).filter(Boolean)));
      row.append(field('Facts', entry.content, value => entry.content = value, true));
      const label = el('label'); const always = el('input'); always.type = 'checkbox'; always.checked = !!entry.constant;
      always.addEventListener('change', () => entry.constant = always.checked); label.append(always, document.createTextNode(' Always include this entry'));
      row.append(label, button('Remove entry', () => {book.entries.splice(index, 1); render(true);})); target.append(row);
      const enabledLabel = el('label'); const enabled = el('input'); enabled.type = 'checkbox'; enabled.checked = entry.enabled !== false;
      enabled.addEventListener('change', () => entry.enabled = enabled.checked);
      enabledLabel.append(enabled, document.createTextNode(' Entry enabled')); row.append(enabledLabel);
    });
    target.append(button('Add entry', () => {book.entries ||= []; book.entries.push({comment: '', keys: [], content: '', enabled: true}); render(true);}));
    target.append(button('Save to this chat', () => request('save', {book})));
  }
  function render(open = false) {
    const root = document.getElementById('screenLorePanel'); const t = thread(); if (!root || !t) return;
    const wasOpen = root.querySelector('details')?.open;
    root.replaceChildren();
    const pending = t.lore?.pending;
    const details = el('details'); details.open = open || wasOpen || false;
    details.append(el('summary', pending ? 'New setting: set up lore for this chat' : 'Chat lore · ' + (t.lore?.title || t.lore?.mode || 'character books')));
    const content = el('div', null, 'screen-lore-editor'); details.append(content);
    root.append(details, el('div', '', 'screen-lore-status')); root.lastChild.id = 'screenLoreStatus';
    if (!data) {content.append(el('p', 'Loading chat lore…'), button('Retry', () => request())); return;}
    if (pending) content.append(el('p', 'This character’s setting changed. Create chat lore or copy a book and adapt it here. Your original books stay separate.'));
    const controls = el('div', null, 'screen-lore-actions');
    controls.append(button('New book', () => {book = {title: 'Chat lore', entries: []}; render(true);}));
    const sources = el('select', null, 'tg-select'); sources.append(new Option('Copy one of my books…', ''));
    (data?.sources || []).forEach(source => sources.append(new Option(source.title, source.id)));
    sources.addEventListener('change', () => {if (sources.value) request('copy', {source_id: Number(sources.value)});});
    controls.append(sources, button('Use character books', () => request('mode', {mode: 'inherit'})),
      button('Continue without lore', () => request('mode', {mode: 'off'})));
    content.append(controls);
    const matches = el('details'); matches.append(el('summary', 'Matched lore in saved chat messages'));
    matches.addEventListener('toggle', async () => {
      if (!matches.open) return;
      try {
        const response = await fetch(TG_CFG.screen_lore_api + '?thread_id=' + t.id);
        const result = await response.json();
        if (!response.ok) throw Error(result.error || 'Could not check lore.');
        matches.querySelector('ul')?.remove();
        const list = el('ul');
        const report = result.activation?.report || [];
        if (!report.length) list.append(el('li', 'No entries matched in the saved messages.'));
        report.forEach(item => list.append(el('li', [item.book, item.label, item.status, item.reason].filter(Boolean).join(' · '))));
        matches.append(list);
      } catch (error) {document.getElementById('screenLoreStatus').textContent = error.message;}
    });
    content.append(matches);
    const directions = el('textarea', null, 'tg-textarea'); directions.placeholder = 'Directions for Bulba’s lore draft (optional)';
    content.append(directions, button('Ask Bulba for a draft (uses tokens)', () => request('draft', {directions: directions.value})));
    if (data?.draft) content.append(el('p', 'Bulba’s draft is a suggestion. Review the entries and save to apply.'));
    editor(content);
  }
  function sync() {
    const t = thread(); if (!t) return;
    const signature = JSON.stringify([t.id, (t.members || []).map(m => [m.mode, m.modern_persona, m.scenario])]);
    if (signature !== loaded) {loaded = signature; data = null; book = null; request();}
    render();
  }
  window.addEventListener('telechat-rendered', sync);
  document.addEventListener('DOMContentLoaded', sync);
})();
