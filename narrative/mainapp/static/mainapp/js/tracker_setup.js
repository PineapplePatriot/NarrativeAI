const $ = id => document.getElementById(id);
const DATA = JSON.parse($('setup-data').textContent);
let config = DATA.config;
let dirty = false;

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
function markDirty() { dirty = true; $('saveStatus').textContent = 'Unsaved changes'; $('saveStatus').className = 'status warn'; }
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

// With "Dice and inventory" on, the app itself keeps Inventory and Conditions (see mainapp/game.py)
const gameOwns = id => (id === 'milestones' && DATA.milestones_by_app) || (id === 'scrapbook' && DATA.scrapbook_by_app) || (['inventory', 'conditions'].includes(id) &&
    ((config.game || 'default') === 'default' ? DATA.game_default_mode : config.game) === 'full');

// --- Tracker cards, grouped by panel: tiles with a switch that light up in their group's colour when on ---
function renderPanels() {
    $('panels').innerHTML = DATA.panels.map(panel => {
        const list = DATA.trackers.filter(t => t.panel === panel.id);
        const on = list.filter(t => gameOwns(t.id) || config.trackers[t.id].on).length;
        const cards = list.map(t => {
            const c = config.trackers[t.id];
            const fields = t.id === 'custom' ? config.custom_fields : t.fields;
            if (gameOwns(t.id)) return `
            <div class="tracker on owned" data-id="${t.id}">
              <div class="tk-top"><span class="tk-ico" aria-hidden="true">${t.icon}</span><span class="tk-name">${esc(t.label)}</span>
                <span class="tk-auto">kept by the app</span></div>
              <p class="help">${t.id === 'milestones' || t.id === 'scrapbook' ? 'Kept by the app while that story extra is on (Extras page).'
                : `Kept by the app while Dice and inventory is on for ${esc(DATA.character_name)}: the AI changes it through the app, and nothing is guessed.`}</p>
            </div>`;
            return `
            <div class="tracker ${c.on ? 'on' : ''}" data-id="${t.id}">
              <label class="tk-top"><span class="tk-ico" aria-hidden="true">${t.icon}</span><span class="tk-name">${esc(t.label)}</span>
                <input type="checkbox" class="tk-switch" data-f="on" ${c.on ? 'checked' : ''} aria-label="${esc(t.label)}"></label>
              <p class="help">${esc(t.help)}</p>
              <div class="chips">${fields.map(f => `<span class="chip">${esc(f.label)}</span>`).join('')
                || '<span class="help">No fields yet: add them below.</span>'}</div>
              ${c.on ? `<label class="check small tk-prompt"><input type="checkbox" data-f="prompt" ${c.prompt ? 'checked' : ''}>
                Add to the chat prompt, so the AI stays consistent with it</label>` : ''}
            </div>`;
        }).join('');
        return `<section class="card tk-group" data-panel="${panel.id}">
            <h2><span>${panel.icon} ${esc(panel.label)}</span><small class="tk-count">${on} of ${list.length} on</small></h2>
            <div class="grid">${cards}</div></section>`;
    }).join('');
}

// A click anywhere on a tile switches it (the switch and the prompt line handle their own clicks)
$('panels').addEventListener('click', e => {
    const card = e.target.closest('.tracker');
    if (!card || card.classList.contains('owned') || e.target.closest('label, input, a, button')) return;
    const box = card.querySelector('[data-f="on"]');
    box.checked = !box.checked;
    box.dispatchEvent(new Event('change', { bubbles: true }));
});

$('panels').addEventListener('change', e => {
    const card = e.target.closest('.tracker');
    if (!card) return;
    config.trackers[card.dataset.id][e.target.dataset.f] = e.target.checked;
    markDirty();
    renderPanels();
});

// --- Custom fields ---
const TYPE_LABELS = { text: 'Text', number: 'Number', meter: 'Meter (bar)', bool: 'Yes / no', list: 'List' };

function renderCustom() {
    $('customFields').innerHTML = config.custom_fields.map((f, i) => `
      <div class="field-row" data-i="${i}">
        <input data-f="label" value="${esc(f.label)}" placeholder="Field name, e.g. Gold">
        <select data-f="type">${DATA.field_types.map(t => `<option value="${t}" ${t === f.type ? 'selected' : ''}>${TYPE_LABELS[t]}</option>`).join('')}</select>
        <input data-f="hint" value="${esc(f.hint)}" placeholder="Hint for the AI (optional)">
        ${f.type === 'meter' ? `<input data-f="min" type="number" value="${f.min ?? 0}" title="Min" class="num">
          <input data-f="max" type="number" value="${f.max ?? 100}" title="Max" class="num">` : ''}
        <button type="button" class="danger small" data-act="remove" title="Remove">✕</button>
      </div>`).join('') || '<p class="help">No custom fields yet.</p>';
}

$('customFields').addEventListener('input', e => {
    const row = e.target.closest('.field-row');
    if (!row || !e.target.dataset.f) return;
    const f = config.custom_fields[Number(row.dataset.i)];
    const key = e.target.dataset.f;
    f[key] = (key === 'min' || key === 'max') ? Number(e.target.value) : e.target.value;
    markDirty();
    if (key === 'type') renderCustom();
    if (key === 'label') renderPanels();
});
$('customFields').addEventListener('click', e => {
    if (e.target.dataset.act !== 'remove') return;
    config.custom_fields.splice(Number(e.target.closest('.field-row').dataset.i), 1);
    markDirty(); renderCustom(); renderPanels();
});
$('addFieldBtn').onclick = () => {
    config.custom_fields.push({ label: '', type: 'text', hint: '' });
    markDirty(); renderCustom();
    $('customFields').querySelector('.field-row:last-child input').focus();
};

// --- Story systems (mainapp/story.py): meters, the story clock, events, random tables ---
const SYSTEM_INFO = {
    meter: ['🎚', 'Slow meter', 'A value like Trust that moves at most one step per scene, then holds for a few replies.'],
    clock: ['🕰', 'Story clock', 'Story time. It moves with what happens (a talk: minutes; a night: hours), nothing else.'],
    event: ['📅', 'Event', 'Comes into the story when the clock reaches it: once, or every few days.'],
    table: ['🃏', 'Random table', 'A weighted list the AI draws from when its situation comes up. Only if you want chance.'],
};
const toHHMM = m => (m === null || m === undefined || m === '') ? '' :
    `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
const hasClock = () => config.systems.some(s => s.type === 'clock');

function numInput(key, value, label, attrs = '') {
    return `<label class="mini">${label}<input type="number" class="num" data-s="${key}" value="${esc(value ?? '')}" ${attrs}></label>`;
}

function systemCard(s, i) {
    const [icon, kind, help] = SYSTEM_INFO[s.type];
    let body = '';
    if (s.type === 'meter') {
        body = `<div class="mini-row">${numInput('min', s.min, 'From')}${numInput('max', s.max, 'To')}
                  ${numInput('start', s.start, 'Starts at')}${numInput('step', s.step, 'Most per scene', 'min="1"')}
                  ${numInput('cooldown', s.cooldown, 'Then holds for (replies)', 'min="0"')}</div>
                <div class="mini-row">${numInput('baseline', s.baseline, 'Fades back toward', 'placeholder="no fading"')}
                  ${numInput('drift_days', s.drift_days || '', 'one step every (story days)', 'min="0" placeholder="never"')}</div>
                <input data-s="about" value="${esc(s.about)}" placeholder="What moves it, in story words (e.g. he keeps his word; she sees him at his worst)">`;
    } else if (s.type === 'clock') {
        body = `<div class="mini-row">${numInput('start_day', s.start_day, 'Starts on day', 'min="1"')}
                  <label class="mini">at<input type="time" data-s="start_time" value="${toHHMM(s.start_time)}"></label></div>`;
    } else if (s.type === 'event') {
        body = `<div class="mini-row">${numInput('at_day', s.at_day, 'On day', 'min="1" placeholder="1"')}
                  <label class="mini">at<input type="time" data-s="at_time" value="${toHHMM(s.at_time)}"></label>
                  ${numInput('every_days', s.every_days || '', 'Repeats every (days)', 'min="0" placeholder="once"')}</div>
                <input data-s="guidance" value="${esc(s.guidance)}" placeholder="What happens (e.g. the masquerade begins; guests arrive masked)">`;
    } else {
        body = `<input data-s="when" value="${esc(s.when)}" placeholder="When it's drawn (e.g. when they walk out into the city)">
                <div class="entries">${(s.entries || []).map((e, j) => `
                  <div class="entry" data-j="${j}"><input data-e="text" value="${esc(e.text)}" placeholder="A result">
                    <label class="mini">weight<input type="number" class="num" min="1" data-e="weight" value="${e.weight}"></label>
                    <button type="button" class="danger small" data-act="entry-remove" title="Remove">✕</button></div>`).join('')}</div>
                <button type="button" class="secondary small" data-act="entry-add">+ Result</button>`;
    }
    const needsClock = s.type === 'event' && !hasClock();
    return `<div class="system ${needsClock ? 'warn' : ''}" data-i="${i}">
      <div class="system-head"><span class="kind">${icon} ${kind}</span>
        ${s.type === 'clock' ? '' : `<input class="label" data-s="label" value="${esc(s.label)}" placeholder="Name">`}
        <button type="button" class="danger small" data-act="remove" title="Remove">✕</button></div>
      <p class="help">${help}${needsClock ? ' <b>Needs a story clock to happen.</b>' : ''}</p>
      ${body}</div>`;
}

function renderSystems() {
    config.systems = config.systems || [];
    $('storySystems').innerHTML = config.systems.map(systemCard).join('') || '<p class="help">None yet.</p>';
    document.querySelector('[data-add="clock"]').disabled = hasClock();
    $('storyNote').textContent = config.systems.some(s => s.type === 'meter')
        ? 'Changing where a meter starts affects new chats; chats already going keep their current value.' : '';
}

function readSystemInput(el, s) {
    const key = el.dataset.s;
    if (el.type === 'time') {
        const [h, m] = el.value.split(':').map(Number);
        s[key] = el.value ? h * 60 + m : null;
    } else if (el.type === 'number') {
        s[key] = el.value === '' ? (key === 'baseline' || key === 'at_day' ? null : 0) : Number(el.value);
    } else s[key] = el.value;
}

$('storySystems').addEventListener('input', e => {
    const card = e.target.closest('.system');
    if (!card) return;
    const s = config.systems[Number(card.dataset.i)];
    if (e.target.dataset.s) readSystemInput(e.target, s);
    else if (e.target.dataset.e) {
        const entry = s.entries[Number(e.target.closest('.entry').dataset.j)];
        entry[e.target.dataset.e] = e.target.dataset.e === 'weight' ? Math.max(1, Number(e.target.value) || 1) : e.target.value;
    }
    markDirty();
});
$('storySystems').addEventListener('click', e => {
    const act = e.target.dataset.act;
    const card = e.target.closest('.system');
    if (!act || !card) return;
    const i = Number(card.dataset.i);
    if (act === 'remove') config.systems.splice(i, 1);
    else if (act === 'entry-add') config.systems[i].entries.push({ text: '', weight: 1 });
    else if (act === 'entry-remove') config.systems[i].entries.splice(Number(e.target.closest('.entry').dataset.j), 1);
    markDirty(); renderSystems();
});
document.querySelector('#storySystemsCard .add-row').addEventListener('click', e => {
    const type = e.target.dataset.add;
    if (!type) return;
    const fresh = {
        meter: { type, label: 'Trust', min: 0, max: 10, start: 2, step: 1, cooldown: 2, baseline: null, drift_days: 0, about: '' },
        clock: { type, label: 'Clock', start_day: 1, start_time: 8 * 60 },
        event: { type, label: '', at_day: 1, at_time: 20 * 60, every_days: 0, guidance: '' },
        table: { type, label: '', when: '', entries: [{ text: '', weight: 2 }, { text: '', weight: 1 }] },
    }[type];
    if (type === 'clock') config.systems.unshift(fresh); else config.systems.push(fresh);
    markDirty(); renderSystems();
    const cards = $('storySystems').querySelectorAll('.system');
    const input = cards[type === 'clock' ? 0 : cards.length - 1].querySelector('input');
    if (input) input.focus();
});

// --- Layout ---
function renderLayout() {
    $('layoutHud').checked = config.layout.hud;
    $('layoutPanel').checked = config.layout.panel;
    $('layoutSide').value = config.layout.side;
}
{
    const modes = DATA.game_modes || {};
    $('gameMode').innerHTML = `<option value="default">Your usual setting (${DATA.game_default})</option>` +
        Object.entries(modes).map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
    $('gameMode').value = config.game || 'default';
    $('gameMode').onchange = e => { config.game = e.target.value; markDirty(); renderPanels(); };
}
$('layoutHud').onchange = e => { config.layout.hud = e.target.checked; markDirty(); };
$('layoutPanel').onchange = e => { config.layout.panel = e.target.checked; markDirty(); };
$('layoutSide').onchange = e => { config.layout.side = e.target.value; markDirty(); };

// --- Save ---
function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

$('saveBtn').onclick = async () => {
    $('saveBtn').disabled = true;
    try {
        const resp = await fetch(SAVE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(config),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        config = data.config;
        dirty = false;
        renderAll();
        $('saveStatus').textContent = 'Saved'; $('saveStatus').className = 'status ok';
    } catch (err) {
        $('saveStatus').textContent = err.message; $('saveStatus').className = 'status bad';
    } finally {
        $('saveBtn').disabled = false;
    }
};

function renderAll() { renderPanels(); renderCustom(); renderSystems(); renderLayout(); }
renderAll();
