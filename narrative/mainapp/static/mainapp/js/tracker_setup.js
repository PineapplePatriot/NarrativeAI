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
const gameOwns = id => ['inventory', 'conditions'].includes(id) &&
    ((config.game || 'default') === 'default' ? DATA.game_default_mode : config.game) === 'full';

// --- Tracker cards, grouped by panel ---
function renderPanels() {
    $('panels').innerHTML = DATA.panels.map(panel => {
        const cards = DATA.trackers.filter(t => t.panel === panel.id).map(t => {
            const c = config.trackers[t.id];
            const fields = t.id === 'custom' ? config.custom_fields : t.fields;
            if (gameOwns(t.id)) return `
            <div class="tracker on" data-id="${t.id}">
              <label class="check title"><input type="checkbox" checked disabled><span>${t.icon} ${esc(t.label)}</span></label>
              <p class="help">Kept by the app while Dice and inventory is on for ${esc(DATA.character_name)}: the AI changes it
                through the app, and nothing is guessed.</p>
            </div>`;
            return `
            <div class="tracker ${c.on ? 'on' : ''}" data-id="${t.id}">
              <label class="check title"><input type="checkbox" data-f="on" ${c.on ? 'checked' : ''}>
                <span>${t.icon} ${esc(t.label)}</span></label>
              <p class="help">${esc(t.help)}</p>
              <div class="chips">${fields.map(f => `<span class="chip">${esc(f.label)}</span>`).join('')
                || '<span class="help">No fields yet: add them below.</span>'}</div>
              <label class="check small"><input type="checkbox" data-f="prompt" ${c.prompt ? 'checked' : ''} ${c.on ? '' : 'disabled'}>
                Add to the chat prompt, so the AI stays consistent with it</label>
            </div>`;
        }).join('');
        return `<section class="card"><h2>${panel.icon} ${esc(panel.label)}</h2><div class="grid">${cards}</div></section>`;
    }).join('');
}

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

function renderAll() { renderPanels(); renderCustom(); renderLayout(); }
renderAll();
