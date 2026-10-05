// Story trackers on the chat page: the pill strip (HUD) above the messages and
// the tabbed side panel. Values are edited in place and saved to the chat;
// locked fields are never changed by the tracker AI.
(function () {
    const dataEl = document.getElementById('trackers-data');
    if (!dataEl) return;
    const DATA = JSON.parse(dataEl.textContent);
    const config = DATA.config;
    const specs = Object.fromEntries(DATA.specs.map(s => [s.id, s]));
    const enabled = DATA.specs.filter(s => config.trackers[s.id].on && s.fields.length);
    let state = DATA.state;
    let lockMode = false;
    let updating = false;
    let saveTimer = null;
    let activeTab = (enabled[0] || {}).panel;
    const recentlyChanged = new Set();

    const hud = document.getElementById('trackerHud');
    const panel = document.getElementById('trackerPanel');

    const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    const lockPath = (tid, fkey, ikey) => ikey == null ? `${tid}.${fkey}` : `${tid}[${String(ikey).toLowerCase()}].${fkey}`;
    const isLocked = p => state.locks.includes(p);
    const emptyValue = spec => spec.kind === 'object' ? {} : [];
    const value = tid => state.values[tid] ?? emptyValue(specs[tid]);

    function storage(key, val) {
        try {
            if (val === undefined) return localStorage.getItem(key);
            localStorage.setItem(key, val);
        } catch (e) { return null; }
    }

    function getCookie(name) {
        const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
        return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
    }

    async function post(body) {
        const resp = await fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        return resp.json();
    }

    // ---------------------------------------------------------------- HUD
    function hudPills() {
        const pills = [];
        const add = (tid, text, title) => text && pills.push(
            `<button class="hud-pill ${recentlyChanged.has(tid) ? 'changed' : ''}" data-open="${specs[tid].panel}" title="${esc(title || specs[tid].label)}">${text}</button>`);
        for (const spec of enabled) {
            const v = value(spec.id);
            const n = Array.isArray(v) ? v.length : 0;
            switch (spec.id) {
                case 'world':
                    add('world', v.location && `📍 ${esc(v.location)}`, 'Location');
                    add('world', (v.time || v.date) && `🕐 ${esc([v.time, v.date].filter(Boolean).join(', '))}`, 'Time');
                    add('world', (v.weather || v.temperature) && `🌦 ${esc([v.weather, v.temperature].filter(Boolean).join(', '))}`, 'Weather');
                    break;
                case 'characters': {
                    const names = v.map(c => c.name);
                    add('characters', n && `👥 ${esc(names.slice(0, 3).join(', '))}${n > 3 ? ` +${n - 3}` : ''}`);
                    break;
                }
                case 'relationships':
                    v.slice(0, 2).forEach(r => add('relationships', `❤️ ${esc(r.name)} ${r.affection}`, `Affection ${r.affection}, trust ${r.trust}, tension ${r.tension}`));
                    break;
                case 'stats':
                    v.slice(0, 3).forEach(s => add('stats', `📊 ${esc(s.name)} ${s.value}${s.max ? '/' + s.max : ''}`));
                    break;
                case 'conditions':
                    add('conditions', n && `🩹 ${esc(v.map(c => c.name).slice(0, 2).join(', '))}${n > 2 ? ` +${n - 2}` : ''}`);
                    break;
                case 'quests': {
                    const open = v.filter(q => !q.done);
                    add('quests', open.length && `🗺️ ${esc(open[0].title)}${open.length > 1 ? ` +${open.length - 1}` : ''}`);
                    break;
                }
                case 'custom':
                    spec.fields.slice(0, 3).forEach(f => {
                        if (v[f.key] !== undefined && v[f.key] !== '') add('custom', `🧩 ${esc(f.label)}: ${esc(fmt(f, v[f.key]))}`);
                    });
                    break;
                default:
                    add(spec.id, n && `${spec.icon} ${n}`, `${spec.label}: ${n}`);
            }
        }
        return pills;
    }

    function fmt(field, v) {
        if (field.type === 'bool') return v ? 'yes' : 'no';
        if (field.type === 'list') return (v || []).join(', ');
        return v;
    }

    function renderHud() {
        if (!hud) return;
        if (!config.layout.hud || !enabled.length) { hud.hidden = true; return; }
        hud.hidden = false;
        const pills = hudPills();
        hud.innerHTML = (pills.length ? pills.join('') : '<span class="hud-empty">Trackers will fill in after a few messages</span>')
            + `<span class="hud-actions">
                 <button class="hud-btn" data-act="update" title="Update all trackers now">${updating ? '⏳' : '↻'}</button>
                 ${config.layout.panel ? '<button class="hud-btn" data-act="toggle" title="Show or hide the tracker panel">▤</button>' : ''}
               </span>`;
    }

    // -------------------------------------------------------------- Panel
    // lockP: the field's lock path; path: where edits go ("world.location" or "characters#2.mood")
    function inputFor(field, v, lockP, path) {
        const locked = isLocked(lockP);
        const lockBtn = (lockMode || locked)
            ? `<button class="lock-btn ${locked ? 'locked' : ''}" data-lock="${esc(lockP)}" title="${locked ? 'Unlock: let the AI update this again' : 'Lock: the AI will not change this'}">${locked ? '🔒' : '🔓'}</button>`
            : '';
        let input;
        switch (field.type) {
            case 'bool':
                input = `<input type="checkbox" data-path="${esc(path)}" ${v ? 'checked' : ''}>`;
                break;
            case 'number':
                input = `<input type="number" data-path="${esc(path)}" value="${esc(v ?? '')}">`;
                break;
            case 'meter': {
                const pct = Math.round(((Number(v) || 0) - field.min) / (field.max - field.min) * 100);
                input = `<div class="meter-bar"><div class="meter-fill ${Number(v) < 0 ? 'neg' : ''}" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>
                         <input type="number" class="meter-num" min="${field.min}" max="${field.max}" data-path="${esc(path)}" value="${esc(v ?? field.min)}">`;
                break;
            }
            case 'list':
                input = `<input data-path="${esc(path)}" value="${esc((v || []).join(', '))}" placeholder="comma-separated">`;
                break;
            default:
                input = `<input data-path="${esc(path)}" value="${esc(v ?? '')}">`;
        }
        return `<label class="tf ${field.type}"><span class="tf-label">${esc(field.label)}</span>${input}${lockBtn}</label>`;
    }

    function trackerCard(spec) {
        const v = value(spec.id);
        let body;
        if (spec.kind === 'object') {
            body = spec.fields.map(f => inputFor(f, v[f.key], lockPath(spec.id, f.key), `${spec.id}.${f.key}`)).join('');
        } else {
            body = v.map((item, i) => `
              <div class="t-item" data-item="${i}">
                <div class="t-item-head">
                  <input class="t-item-key" data-path="${esc(spec.id)}#${i}.${spec.key}" value="${esc(item[spec.key])}">
                  <button class="icon-btn" data-remove="${i}" title="Remove">✕</button>
                </div>
                ${spec.fields.filter(f => f.key !== spec.key).map(f =>
                    inputFor(f, item[f.key], lockPath(spec.id, f.key, item[spec.key]), `${spec.id}#${i}.${f.key}`)).join('')}
              </div>`).join('') || '<p class="t-empty">Nothing tracked yet.</p>';
            body += `<button class="add-btn" data-add="1">+ Add</button>`;
        }
        return `
          <section class="t-card ${recentlyChanged.has(spec.id) ? 'changed' : ''}" data-tracker="${spec.id}">
            <header><span>${spec.icon} ${esc(spec.label)}</span>
              <button class="icon-btn" data-rerun="${spec.id}" title="Re-run only this tracker">↻</button></header>
            ${body}
          </section>`;
    }

    function renderPanel() {
        if (!panel) return;
        if (!config.layout.panel) { panel.hidden = true; return; }
        panel.classList.toggle('left', config.layout.side === 'left');
        const tabs = DATA.panels.filter(p => enabled.some(s => s.panel === p.id));
        if (!tabs.some(t => t.id === activeTab)) activeTab = (tabs[0] || {}).id;

        panel.innerHTML = `
          <div class="tp-head">
            <b>Story state</b>
            <span>
              <button class="icon-btn" data-act="update" title="Update all trackers now">${updating ? '⏳' : '↻'}</button>
              <button class="icon-btn ${lockMode ? 'active' : ''}" data-act="lockmode" title="Lock mode: pin values so the AI can't change them">🔒</button>
              <a class="icon-btn" href="${DATA.setup_url}" title="Choose trackers">⚙</a>
              <button class="icon-btn" data-act="toggle" title="Close">✕</button>
            </span>
          </div>
          ${tabs.length ? `<nav class="tp-tabs">${tabs.map(t =>
              `<button class="${t.id === activeTab ? 'active' : ''}" data-tab="${t.id}">${t.icon} ${esc(t.label)}</button>`).join('')}</nav>
            <div class="tp-body">${enabled.filter(s => s.panel === activeTab).map(trackerCard).join('')}</div>
            <div class="tp-foot">${scheduleText()}</div>`
            : `<p class="t-empty">No trackers are on for this character yet. <a href="${DATA.setup_url}">Choose trackers →</a></p>`}`;
    }

    function scheduleText() {
        const s = DATA.schedule;
        return s.mode === 'auto'
            ? `Updates automatically every ${s.interval} message${s.interval === 1 ? '' : 's'}.`
            : 'Updates only when you press ↻.';
    }

    function setPanelOpen(open) {
        if (!panel) return;
        panel.hidden = !open;
        storage('trackerPanelOpen', open ? '1' : '0');
    }

    function render() { renderHud(); if (panel && !panel.hidden) renderPanel(); }

    // ------------------------------------------------------------- Editing
    function setByPath(path, raw) {
        // "world.location" or "characters#2.mood" (list item by index)
        const m = path.match(/^(\w+)(?:#(\d+))?\.(\w+)$/);
        if (!m) return;
        const [, tid, idx, key] = m;
        const spec = specs[tid];
        const field = spec.fields.find(f => f.key === key);
        let v = raw;
        if (field.type === 'number' || field.type === 'meter') v = Number(raw) || 0;
        if (field.type === 'list') v = String(raw).split(',').map(s => s.trim()).filter(Boolean);
        if (!state.values[tid]) state.values[tid] = emptyValue(spec);
        if (idx === undefined) state.values[tid][key] = v;
        else {
            const item = state.values[tid][Number(idx)];
            // Renaming a list item moves its locks along with it
            if (key === spec.key) {
                const oldPrefix = `${tid}[${String(item[key]).toLowerCase()}].`;
                const newPrefix = `${tid}[${String(v).toLowerCase()}].`;
                state.locks = state.locks.map(p => p.startsWith(oldPrefix) ? newPrefix + p.slice(oldPrefix.length) : p);
            }
            item[key] = v;
        }
    }

    function scheduleSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(async () => {
            const resp = await post({ action: 'save_trackers', values: state.values, locks: state.locks });
            if (resp.success) { state = resp.state; renderHud(); }
        }, 600);
    }

    if (panel) {
        panel.addEventListener('input', e => {
            const input = e.target;
            if (!input.dataset.path) return;
            const path = input.dataset.path;
            setByPath(path, input.type === 'checkbox' ? input.checked : input.value);
            if (input.classList.contains('meter-num')) {
                const field = specs[path.match(/^(\w+)/)[1]].fields.find(f => path.endsWith('.' + f.key));
                const pct = Math.round(((Number(input.value) || 0) - field.min) / (field.max - field.min) * 100);
                input.previousElementSibling.firstElementChild.style.width = Math.max(0, Math.min(100, pct)) + '%';
            }
            scheduleSave();
        });

        panel.addEventListener('click', e => {
            const t = e.target.closest('button, a');
            if (!t) return;
            if (t.dataset.tab) { activeTab = t.dataset.tab; renderPanel(); }
            else if (t.dataset.lock) {
                const p = t.dataset.lock;
                state.locks = isLocked(p) ? state.locks.filter(x => x !== p) : [...state.locks, p];
                renderPanel(); scheduleSave();
            } else if (t.dataset.rerun) update([t.dataset.rerun]);
            else if (t.dataset.remove !== undefined) {
                const tid = t.closest('[data-tracker]').dataset.tracker;
                state.values[tid].splice(Number(t.dataset.remove), 1);
                render(); scheduleSave();
            } else if (t.dataset.add) {
                const tid = t.closest('[data-tracker]').dataset.tracker;
                const spec = specs[tid];
                const item = Object.fromEntries(spec.fields.map(f => [f.key,
                    f.type === 'bool' ? false : f.type === 'list' ? [] : (f.type === 'number' || f.type === 'meter') ? (f.min > 0 ? f.min : 0) : '']));
                item[spec.key] = 'New';
                if (!state.values[tid]) state.values[tid] = [];
                state.values[tid].push(item);
                renderPanel();
                const keys = panel.querySelectorAll(`[data-tracker="${tid}"] .t-item-key`);
                keys[keys.length - 1].select();
                scheduleSave();
            } else if (t.dataset.act === 'lockmode') { lockMode = !lockMode; renderPanel(); }
            else if (t.dataset.act === 'update') update();
            else if (t.dataset.act === 'toggle') setPanelOpen(false);
        });
    }

    if (hud) {
        hud.addEventListener('click', e => {
            const t = e.target.closest('button');
            if (!t) return;
            if (t.dataset.act === 'update') update();
            else if (t.dataset.act === 'toggle') { setPanelOpen(panel.hidden); render(); }
            else if (t.dataset.open && config.layout.panel) { activeTab = t.dataset.open; setPanelOpen(true); renderPanel(); }
        });
    }

    // -------------------------------------------------------------- Update
    async function update(only) {
        if (updating || !enabled.length) return;
        updating = true; render();
        try {
            const resp = await post({ action: 'update_trackers', only: only || null });
            if (resp.success) {
                state = resp.state;
                recentlyChanged.clear();
                (resp.changed || []).forEach(id => recentlyChanged.add(id));
                setTimeout(() => { recentlyChanged.clear(); render(); }, 4000);
            } else {
                console.warn('Tracker update failed:', resp.error);
                if (only) alert(resp.error);
            }
        } finally {
            updating = false; render();
        }
    }

    window.Trackers = {
        update,
        open() { setPanelOpen(true); renderPanel(); },
        afterReply(resp) { if (resp && resp.trackers_due) update(); },
        setState(next) { if (next) { state = next; render(); } },  // e.g. rewound after deleting messages
        get enabled() { return enabled.length > 0; },
    };

    // Start closed: trackers support the story, they aren't the main view. Opens if the user left it open.
    const saved = storage('trackerPanelOpen');
    const open = config.layout.panel && enabled.length && saved === '1';
    if (panel) panel.hidden = !open;
    renderHud();
    if (open) renderPanel();
})();
