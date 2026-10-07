const $ = id => document.getElementById(id);
const DATA = JSON.parse($('preset-data').textContent);
let presets = DATA.presets;
let preset = DATA.preset;
let saveTimer = null;
let saving = false;
const collapsed = new Set();
const open = new Set();      // blocks whose editor is open
let dragId = null;

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
// Rough size of what is actually sent: {{// comments}} never are
const approxTokens = s => Math.floor((s || '').replace(/\{\{\/\/[\s\S]*?\}\}/g, '').length / 3) + 4;
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).replace(/-/g, '');
const blockById = id => preset.blocks.find(b => b.id === id);

function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

async function act(body) {
    const resp = await fetch(URLS.page, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
}

// ------------------------------------------------------------- Preset list
function renderList() {
    $('presetList').innerHTML = presets.map(p => `
      <button type="button" class="preset-item ${p.id === preset.id ? 'selected' : ''}" data-id="${p.id}">
        <span class="name">${esc(p.name)}</span>
        <span class="meta">${p.active ? '<b class="active">● active</b> · ' : ''}${p.enabled}/${p.blocks} blocks on</span>
      </button>`).join('');
}

$('presetList').addEventListener('click', e => {
    const item = e.target.closest('.preset-item');
    if (item) goTo(item.dataset.id);
});

function goTo(id) { window.location.href = `${URLS.page}?id=${id}`; }

// ---------------------------------------------------------- Preset header
function renderHead() {
    const summary = presets.find(p => p.id === preset.id);
    $('presetName').textContent = preset.name;
    $('activeBadge').innerHTML = summary && summary.active
        ? '<span class="badge-active">Active for all chats</span>'
        : '<button type="button" id="activateBtn">Use this preset</button>';
    const btn = $('activateBtn');
    if (btn) btn.onclick = async () => {
        try { presets = (await act({ action: 'activate', id: preset.id })).presets; renderList(); renderHead(); }
        catch (err) { alert(err.message); }
    };
    $('exportLink').href = URLS.export.replace('/0/', `/${preset.id}/`);
    $('exportStLink').href = URLS.export.replace('/0/', `/${preset.id}/`) + '?format=sillytavern';
    $('streaming').checked = preset.options.streaming !== false;
    $('postProcessing').innerHTML = Object.entries(DATA.post_processing)
        .map(([k, label]) => `<option value="${k}" ${k === preset.options.post_processing ? 'selected' : ''}>${esc(label)}</option>`).join('');

    const extras = [];
    if (preset.extras.function_calling) extras.push('function calling (here: Dice and inventory on the Extras page)');
    if ((preset.extras.unused_prompts || []).length) extras.push(`${preset.extras.unused_prompts.length} unused prompts`);
    const starter = preset.extras.starter;
    const credit = starter && (starter.based_on || []).length
        ? ` Made from a starter, based on ${starter.based_on.map(b => `<a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.name)}</a> by ${esc(b.author)}`).join(' and ')}.`
        : (starter ? ' Made from a starter.' : '');
    $('extrasNote').innerHTML = (extras.length
        ? `Kept from SillyTavern for export, but not used here yet: ${esc(extras.join(', '))}.` : '') + credit;
}

document.querySelector('.toolbar').addEventListener('click', async e => {
    const action = e.target.dataset.act;
    if (!action) return;
    try {
        if (action === 'rename') {
            const name = await editInPlace($('presetName'), preset.name);
            if (!name) return;
            const data = await act({ action, id: preset.id, name });
            presets = data.presets; preset.name = data.preset.name;
            renderList(); renderHead();
            return;
        }
        if (action === 'delete' && !confirm(`Delete “${preset.name}”? This cannot be undone.`)) return;
        await flushSave();
        goTo((await act({ action, id: preset.id })).selected);
    } catch (err) { alert(err.message); }
});

$('postProcessing').onchange = e => { preset.options.post_processing = e.target.value; scheduleSave(); };
$('streaming').onchange = e => { preset.options.streaming = e.target.checked; scheduleSave(); };

// ------------------------------------------------------------------ Blocks
function groupOf(headerId) {
    // [start, end) indexes of a header and the blocks under it
    const start = preset.blocks.findIndex(b => b.id === headerId);
    let end = start + 1;
    while (end < preset.blocks.length && preset.blocks[end].kind !== 'header') end++;
    return [start, end];
}

const ROLE_ICON = { system: '⚙', user: '🙂', assistant: '🤖' };
const PALETTE = ['#a78bfa', '#67e8f9', '#f9a8d4', '#fcd34d', '#86efac', '#fda4af', '#93c5fd', '#fdba74'];

function badges(b) {
    const out = [];
    if (b.role !== 'system') out.push(`<span class="chip role-${b.role}" title="Sent as a ${b.role} message">${ROLE_ICON[b.role]} ${b.role}</span>`);
    if (b.position === 'in_chat') out.push(`<span class="chip in-chat" data-depth-chip title="Inside the chat, ${b.depth} message(s) from the end">⤵ in chat @${b.depth}</span>`);
    return out.join('');
}

function editor(b) {
    if (b.kind === 'header') {
        return `<div class="editor" data-editor="${esc(b.id)}">
          <label>Group name<input data-f="name" value="${esc(b.name)}"></label>
          <div class="editor-actions"><button type="button" class="danger small" data-delete="${esc(b.id)}">Delete header (keeps its blocks)</button></div>
        </div>`;
    }
    const isMarker = b.kind === 'marker';
    const roles = ['system', 'user', 'assistant'].map(r => `<option ${r === b.role ? 'selected' : ''}>${r}</option>`).join('');
    return `<div class="editor" data-editor="${esc(b.id)}">
      <div class="editor-grid">
        <label>Name<input data-f="name" value="${esc(b.name)}"></label>
        <label>Role<select data-f="role">${roles}</select></label>
        <label>Placement<select data-f="position">
          <option value="relative" ${b.position === 'relative' ? 'selected' : ''}>Where it is in this list</option>
          <option value="in_chat" ${b.position === 'in_chat' ? 'selected' : ''}>Inside the chat, at a depth</option></select></label>
        <label ${b.position === 'in_chat' ? '' : 'hidden'}>Depth<input data-f="depth" type="number" min="0" value="${b.depth}">
          <span class="hint">0 = after the last message, 1 = before it…</span></label>
        <label ${b.position === 'in_chat' ? '' : 'hidden'}>Order<input data-f="order" type="number" value="${b.order}">
          <span class="hint">Lower goes first among blocks at the same depth.</span></label>
      </div>
      ${isMarker
        ? `<p class="help">This is a slot: the app fills it with <b>${esc(DATA.markers[b.marker] || b.marker)}</b>. You can move it, switch it off or change its role.</p>`
        : `<label>Text <span class="hint" data-tokens>~${approxTokens(b.content)} tokens</span>
             <textarea data-f="content" rows="${Math.min(18, Math.max(5, b.content.split('\n').length + 1))}">${esc(b.content)}</textarea></label>`}
      <div class="editor-actions">
        <button type="button" class="secondary small" data-duplicate="${esc(b.id)}">Duplicate</button>
        <button type="button" class="danger small" data-delete="${esc(b.id)}">Delete block</button>
      </div>
    </div>`;
}

function blockRow(b) {
    const isSlot = b.kind === 'marker';
    const tokens = b.kind === 'prompt' ? `<span class="tokens" data-row-tokens>~${approxTokens(b.content)}</span>` : '';
    return `
      <div class="block ${b.enabled ? 'on' : ''} ${isSlot ? 'slot' : ''} ${open.has(b.id) ? 'editing' : ''}" draggable="true" data-id="${esc(b.id)}">
        <span class="handle" title="Drag to move">⠿</span>
        <label class="switch" title="On / off"><input type="checkbox" data-toggle="${esc(b.id)}" ${b.enabled ? 'checked' : ''}><span></span></label>
        ${isSlot ? '<span class="slot-icon" title="Slot: filled in by the app">🔌</span>' : ''}
        <button type="button" class="block-name" data-open="${esc(b.id)}">${esc(b.name)}</button>
        ${badges(b)}${tokens}
        <span class="moves">
          <button type="button" class="icon" data-move="-1" title="Move up">↑</button>
          <button type="button" class="icon" data-move="1" title="Move down">↓</button>
        </span>
      </div>
      ${open.has(b.id) ? editor(b) : ''}`;
}

// The list as groups: [{header|null, blocks, color}]
function groupList() {
    const out = [];
    let current = { header: null, blocks: [] };
    for (const b of preset.blocks) {
        if (b.kind === 'header') {
            if (current.header || current.blocks.length) out.push(current);
            current = { header: b, blocks: [] };
        } else current.blocks.push(b);
    }
    if (current.header || current.blocks.length) out.push(current);
    out.forEach((g, i) => { g.key = g.header ? g.header.id : '__top'; g.color = PALETTE[i % PALETTE.length]; });
    return out;
}

const FOLD_KEY = `presetFold:${preset.id}`;
function saveFolds() { try { localStorage.setItem(FOLD_KEY, JSON.stringify([...collapsed])); } catch (e) { /* optional */ } }
(function loadFolds() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(FOLD_KEY)); } catch (e) { saved = null; }
    if (Array.isArray(saved)) saved.forEach(k => collapsed.add(k));
    else if (preset.blocks.length > 30) preset.blocks.filter(b => b.kind === 'header').forEach(b => collapsed.add(b.id));
})();

function matches(b, q, onlyOn) {
    if (onlyOn && !b.enabled) return false;
    if (!q) return true;
    return (b.name + ' ' + (b.content || '') + ' ' + (b.marker ? DATA.markers[b.marker] : '')).toLowerCase().includes(q);
}

// Token totals: written text only. Slots (chat, lore, trackers...) are filled when sending; see Preview.
const blockTokens = b => (b.kind === 'prompt' ? approxTokens(b.content) : 0);
const groupTokens = g => g.blocks.filter(b => b.enabled).reduce((n, b) => n + blockTokens(b), 0);
const totalOn = () => preset.blocks.filter(b => b.enabled).reduce((n, b) => n + blockTokens(b), 0);
const totalAll = () => preset.blocks.reduce((n, b) => n + blockTokens(b), 0);
const fmt = n => n.toLocaleString();
const share = n => `${Math.round(n / Math.max(totalOn(), 1) * 100)}%`;

function renderTotals() {
    const on = totalOn();
    const inChat = preset.blocks.filter(b => b.enabled && b.position === 'in_chat').reduce((n, b) => n + blockTokens(b), 0);
    const ctx = (preset.samplers || {}).context_size || {};
    const parts = [`<b>~${fmt(on)}</b> tokens switched on`];
    if (inChat) parts.push(`${fmt(inChat)} of them inside the chat`);
    parts.push(`~${fmt(totalAll())} if everything were on`);
    let ctxLine = '';
    if (ctx.on) {
        const pct = Math.round(on / ctx.value * 100);
        ctxLine = `<div class="ctx-bar" title="Preset text vs. your context size"><span style="width:${Math.min(pct, 100)}%"></span></div>
          <span class="${pct > 50 ? 'warn' : ''}">The preset alone uses ~${pct}% of your ${fmt(ctx.value)}-token context size; the rest is for the chat, lore and trackers.</span>`;
    } else {
        ctxLine = `<span>Context size is off (the whole chat is sent). Set one on the <a href="${URLS.samplers}">Samplers page</a> to see the preset's share.</span>`;
    }
    $('totals').innerHTML = `<div>${parts.join(' · ')}</div>${ctxLine}`;
}

function renderBlocks() {
    const all = preset.blocks.filter(b => b.kind !== 'header');
    $('blockCount').textContent = `${all.filter(b => b.enabled).length} of ${all.length} blocks on`;
    const q = $('search').value.trim().toLowerCase();
    const onlyOn = $('onlyOn').checked;
    const filtering = q || onlyOn;

    const html = groupList().map(g => {
        const shown = g.blocks.filter(b => matches(b, q, onlyOn));
        if (filtering && !shown.length && !(g.header && matches(g.header, q, false) && !onlyOn)) return '';
        const on = g.blocks.filter(b => b.enabled);
        const folded = !filtering && collapsed.has(g.key);
        const pct = g.blocks.length ? Math.round(on.length / g.blocks.length * 100) : 0;
        const head = g.header
            ? `<div class="group-head ${open.has(g.header.id) ? 'editing' : ''}" draggable="true" data-id="${esc(g.header.id)}">
                 <span class="handle" title="Drag to move the whole group">⠿</span>
                 <button type="button" class="fold" data-fold="${esc(g.key)}">${folded ? '▸' : '▾'}</button>
                 <button type="button" class="block-name" data-open="${esc(g.header.id)}" title="Click to rename">${esc(g.header.name)}</button>
                 <span class="gtokens" title="Switched-on text in this group (${share(groupTokens(g))} of the preset)">~${fmt(groupTokens(g))} tok</span>
                 <span class="meter" title="${on.length} of ${g.blocks.length} on"><span style="width:${pct}%"></span></span>
                 <span class="count">${on.length}/${g.blocks.length}</span>
               </div>
               ${open.has(g.header.id) ? editor(g.header) : ''}`
            : `<div class="group-head plain"><button type="button" class="fold" data-fold="__top">${folded ? '▸' : '▾'}</button>
                 <span class="muted-title">Not in a group</span><span class="gtokens">~${fmt(groupTokens(g))} tok</span>
                 <span class="count">${on.length}/${g.blocks.length}</span></div>`;
        const body = folded
            ? `<div class="folded-chips" data-fold="${esc(g.key)}">${on.slice(0, 8).map(b => `<span class="mini">${esc(b.name)}</span>`).join('')}
                 ${on.length > 8 ? `<span class="mini more">+${on.length - 8} more</span>` : ''}
                 ${!on.length ? '<span class="mini off">all off</span>' : ''}</div>`
            : `<div class="group-body">${(filtering ? shown : g.blocks).map(blockRow).join('') || '<p class="help">Empty group. Drag blocks here.</p>'}</div>`;
        return `<section class="gcard" id="group-${esc(g.key)}" style="--accent:${g.color}">${head}${body}</section>`;
    }).join('');
    $('blocks').innerHTML = html || '<p class="help">No blocks match.</p>';
    renderSlotPicker();
    renderMap();
}

// The request map: enabled blocks in order, sized by length; the chat shows as its own segment
function renderMap() {
    renderTotals();
    const segments = [];
    for (const g of groupList()) {
        let tokens = 0;
        for (const b of g.blocks) {
            if (!b.enabled) continue;
            if (b.kind === 'marker' && b.marker === 'chat_history') {
                if (tokens) segments.push({ g, tokens }); tokens = 0;
                segments.push({ chat: true, tokens: 0 });
            } else if (b.kind === 'prompt' && b.position !== 'in_chat') tokens += approxTokens(b.content);
            else if (b.kind === 'marker') tokens += 40;  // slots: rough size, filled at send time
        }
        if (tokens) segments.push({ g, tokens });
    }
    const total = segments.reduce((n, s) => n + s.tokens, 0) || 1;
    $('map').innerHTML = segments.map(s => s.chat
        ? `<span class="seg chat" title="Chat history goes here">💬 chat</span>`
        : `<button type="button" class="seg" data-jump="${esc(s.g.key)}" style="flex:${Math.max(s.tokens / total * 100, 2.5)};background:${s.g.color}"
             title="${esc(s.g.header ? s.g.header.name : 'Not in a group')}: ~${s.tokens} tokens"></button>`).join('')
        || '<span class="help">Nothing is switched on.</span>';
    const inChat = preset.blocks.filter(b => b.enabled && b.position === 'in_chat' && b.kind !== 'header').length;
    $('mapLegend').innerHTML = groupList().filter(g => g.blocks.some(b => b.enabled)).map(g =>
        `<button type="button" class="legend" data-jump="${esc(g.key)}"><i style="background:${g.color}"></i>${esc(g.header ? g.header.name : 'Not in a group')}</button>`).join('')
        + (inChat ? `<span class="legend static">⤵ ${inChat} block${inChat > 1 ? 's' : ''} inside the chat</span>` : '')
;
}

function renderSlotPicker() {
    const present = new Set(preset.blocks.filter(b => b.kind === 'marker').map(b => b.marker));
    const missing = Object.entries(DATA.markers).filter(([k]) => !present.has(k));
    $('addSlot').innerHTML = `<option value="">+ Slot…</option>` +
        missing.map(([k, label]) => `<option value="${k}">${esc(label)}</option>`).join('');
    $('addSlot').disabled = !missing.length;
}

function jumpTo(key) {
    collapsed.delete(key); saveFolds();
    $('search').value = ''; $('onlyOn').checked = false;
    renderBlocks();
    const el = document.getElementById(`group-${key}`);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1200); }
}
document.querySelector('[data-panel="blocks"] .map').addEventListener('click', e => { const t = e.target.closest('[data-jump]'); if (t) jumpTo(t.dataset.jump); });
$('mapLegend').addEventListener('click', e => { const t = e.target.closest('[data-jump]'); if (t) jumpTo(t.dataset.jump); });
$('search').addEventListener('input', renderBlocks);
$('onlyOn').addEventListener('change', renderBlocks);
$('foldAll').onclick = () => { groupList().forEach(g => collapsed.add(g.key)); saveFolds(); renderBlocks(); };
$('unfoldAll').onclick = () => { collapsed.clear(); saveFolds(); renderBlocks(); };

// Clicks: open editor, fold group, move, delete, duplicate
$('blocks').addEventListener('click', e => {
    const chips = e.target.closest('.folded-chips');
    if (chips) { collapsed.delete(chips.dataset.fold); saveFolds(); renderBlocks(); return; }
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.open) {
        open.has(t.dataset.open) ? open.delete(t.dataset.open) : open.add(t.dataset.open);
        renderBlocks();
    } else if (t.dataset.fold) {
        collapsed.has(t.dataset.fold) ? collapsed.delete(t.dataset.fold) : collapsed.add(t.dataset.fold);
        saveFolds(); renderBlocks();
    } else if (t.dataset.move) {
        const id = t.closest('[data-id]').dataset.id;
        const i = preset.blocks.findIndex(b => b.id === id);
        const j = i + Number(t.dataset.move);
        if (j < 0 || j >= preset.blocks.length) return;
        [preset.blocks[i], preset.blocks[j]] = [preset.blocks[j], preset.blocks[i]];
        renderBlocks(); scheduleSave();
    } else if (t.dataset.delete) {
        const b = blockById(t.dataset.delete);
        if (b.kind !== 'header' && !confirm(`Delete “${b.name}”?`)) return;
        preset.blocks = preset.blocks.filter(x => x.id !== b.id);
        open.delete(b.id);
        renderBlocks(); scheduleSave();
    } else if (t.dataset.duplicate) {
        const i = preset.blocks.findIndex(b => b.id === t.dataset.duplicate);
        const copy = { ...preset.blocks[i], id: uid(), name: preset.blocks[i].name + ' (copy)' };
        if (copy.kind === 'marker') { copy.kind = 'prompt'; copy.marker = null; }
        preset.blocks.splice(i + 1, 0, copy);
        open.add(copy.id);
        renderBlocks(); scheduleSave();
    }
});

$('blocks').addEventListener('change', e => {
    const id = e.target.dataset.toggle;
    if (id) {
        blockById(id).enabled = e.target.checked;
        renderBlocks(); scheduleSave();
        return;
    }
    const f = e.target.dataset.f;
    if (f === 'role' || f === 'position') {
        blockById(e.target.closest('[data-editor]').dataset.editor)[f] = e.target.value;
        renderBlocks(); scheduleSave();
    }
});

// Typing updates in place (no re-render, so the cursor stays put)
$('blocks').addEventListener('input', e => {
    const f = e.target.dataset.f;
    const ed = e.target.closest('[data-editor]');
    if (!f || !ed || f === 'role' || f === 'position') return;
    const b = blockById(ed.dataset.editor);
    b[f] = (f === 'depth' || f === 'order') ? Number(e.target.value) || 0 : e.target.value;
    if (f === 'name') {
        const row = $('blocks').querySelector(`[data-id="${CSS.escape(b.id)}"] .block-name`);
        if (row) row.textContent = b.name;
    }
    if (f === 'content') {
        ed.querySelector('[data-tokens]').textContent = `~${approxTokens(b.content)} tokens`;
        const row = $('blocks').querySelector(`[data-id="${CSS.escape(b.id)}"] [data-row-tokens]`);
        if (row) row.textContent = `~${approxTokens(b.content)}`;
        renderTotals();
    }
    if (f === 'depth') {
        const row = $('blocks').querySelector(`[data-id="${CSS.escape(b.id)}"]`);
        const chip = row.querySelector('[data-depth-chip]');
        if (chip) chip.textContent = `⤵ in chat @${b.depth}`;
    }
    scheduleSave();
});

// Drag and drop: blocks move alone, headers bring their whole group
$('blocks').addEventListener('dragstart', e => {
    const row = e.target.closest('[draggable][data-id]');
    if (!row) return;
    dragId = row.dataset.id;
    e.dataTransfer.effectAllowed = 'move';
    row.classList.add('dragging');
});
$('blocks').addEventListener('dragend', () => {
    dragId = null;
    $('blocks').querySelectorAll('.drop-before, .drop-after, .dragging').forEach(el => el.classList.remove('drop-before', 'drop-after', 'dragging'));
});
$('blocks').addEventListener('dragover', e => {
    const row = e.target.closest('[draggable][data-id]');
    if (!row || !dragId) return;
    e.preventDefault();
    const after = e.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2;
    $('blocks').querySelectorAll('.drop-before, .drop-after').forEach(el => el.classList.remove('drop-before', 'drop-after'));
    row.classList.add(after ? 'drop-after' : 'drop-before');
});
$('blocks').addEventListener('drop', e => {
    const row = e.target.closest('[draggable][data-id]');
    if (!row || !dragId) return;
    e.preventDefault();
    const after = row.classList.contains('drop-after');
    moveTo(dragId, row.dataset.id, after);
});

function moveTo(movingId, targetId, after) {
    if (movingId === targetId) return;
    const moving = blockById(movingId);
    const [from, to] = moving.kind === 'header' ? groupOf(movingId) : [preset.blocks.findIndex(b => b.id === movingId), null];
    const span = moving.kind === 'header' ? to - from : 1;
    const chunk = preset.blocks.slice(from, from + span);
    if (chunk.some(b => b.id === targetId)) return;  // dropped inside itself
    const rest = preset.blocks.filter(b => !chunk.includes(b));
    const target = blockById(targetId);
    let index = rest.findIndex(b => b.id === targetId);
    if (after) {
        // after a collapsed group's header, or when moving a group: go past the target's whole group
        if (target.kind === 'header' && (collapsed.has(targetId) || moving.kind === 'header')) {
            index++;
            while (index < rest.length && rest[index].kind !== 'header') index++;
        } else index++;
    }
    rest.splice(index, 0, ...chunk);
    preset.blocks = rest;
    renderBlocks(); scheduleSave();
}

// Adding blocks
function addBlock(block) {
    preset.blocks.push(block);
    open.add(block.id);
    renderBlocks(); scheduleSave();
    const row = $('blocks').querySelector(`[data-id="${CSS.escape(block.id)}"]`);
    if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const input = $('blocks').querySelector(`[data-editor="${CSS.escape(block.id)}"] input[data-f=name]`);
    if (input) input.select();
}
$('addPrompt').onclick = () => addBlock({ id: uid(), name: 'New prompt', kind: 'prompt', marker: null, role: 'system',
    content: '', enabled: true, position: 'relative', depth: 4, order: 100 });
$('addHeader').onclick = () => addBlock({ id: uid(), name: 'New group', kind: 'header', marker: null, role: 'system',
    content: '', enabled: true, position: 'relative', depth: 4, order: 100 });
$('addSlot').onchange = e => {
    const marker = e.target.value;
    if (!marker) return;
    addBlock({ id: uid(), name: DATA.markers[marker], kind: 'marker', marker, role: 'system', content: '',
        enabled: true, position: 'relative', depth: 4, order: 100 });
};

// --------------------------------------------------------- Utility prompts
function renderUtility() {
    $('utility').innerHTML = Object.entries(DATA.utility_labels).map(([key, [label, help]]) => `
      <label class="utility">${esc(label)} <span class="hint">${esc(help)}</span>
        <textarea data-utility="${key}" rows="2">${esc(preset.utility[key] || '')}</textarea></label>`).join('');
}
$('utility').addEventListener('input', e => {
    const key = e.target.dataset.utility;
    if (key) { preset.utility[key] = e.target.value; scheduleSave(); }
});

// ----------------------------------------------------------------- Saving
function setStatus(text, cls) { $('saveStatus').textContent = text; $('saveStatus').className = 'status ' + (cls || ''); }

function scheduleSave() {
    setStatus('Unsaved…', 'warn');
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 700);
}

async function save() {
    saveTimer = null;
    saving = true;
    setStatus('Saving…');
    try {
        const data = await act({ action: 'save_full', id: preset.id, blocks: preset.blocks,
                                 utility: preset.utility, options: preset.options, regex: preset.regex });
        presets = data.presets;
        renderList();
        setStatus('Saved', 'ok');
    } catch (err) {
        setStatus('Not saved: ' + err.message, 'bad');
    } finally {
        saving = false;
    }
}

async function flushSave() {
    if (saveTimer) { clearTimeout(saveTimer); await save(); }
}

window.addEventListener('beforeunload', e => {
    if (saveTimer || saving) { e.preventDefault(); e.returnValue = ''; }
});

// ------------------------------------------------------ Import / defaults
$('importFile').addEventListener('change', async () => {
    const file = $('importFile').files[0];
    if (!file) return;
    $('importStatus').textContent = 'Importing…';
    try {
        await flushSave();
        const data = await act({ action: 'import', data: JSON.parse(await file.text()), name: file.name.replace(/\.json$/i, '') });
        goTo(data.selected);
    } catch (err) {
        $('importStatus').textContent = `Could not import “${file.name}”: ${err.message}`;
    }
});

$('newDefaultBtn').onclick = async () => {
    try { await flushSave(); goTo((await act({ action: 'new_default' })).selected); }
    catch (err) { alert(err.message); }
};

// ---------------------------------------------------------------- Starters
function starterCard(s) {
    const credit = (s.based_on || []).map(b => `<a href="${esc(b.url)}" target="_blank" rel="noopener" title="${esc(b.used || '')}">${esc(b.name)}</a>`).join(', ');
    return `
      <div class="starter">
        <div class="starter-head"><b>${esc(s.title)}</b>
          <button type="button" class="secondary small" data-starter="${esc(s.id)}">Use</button></div>
        <p>${esc(s.tagline)}</p>
        ${credit ? `<p class="credit">Based on ${credit}</p>` : ''}
      </div>`;
}
function renderStarters() {
    const groups = DATA.starters || [];
    $('starterList').innerHTML = groups.map(g => g.yours
        ? `<p class="starter-model">For your model, <b>${esc(g.model_name)}</b></p>${g.starters.map(starterCard).join('')}`
        : `<details class="starter-group"><summary>For ${esc(g.model_name)}</summary>${g.starters.map(starterCard).join('')}</details>`
    ).join('') || '<p class="help">No starters yet.</p>';
}
$('starterList').addEventListener('click', async e => {
    const btn = e.target.closest('[data-starter]');
    if (!btn) return;
    btn.disabled = true;
    try { await flushSave(); goTo((await act({ action: 'use_starter', starter: btn.dataset.starter })).selected); }
    catch (err) { alert(err.message); btn.disabled = false; }
});
renderStarters();

// ------------------------------------------------------------------ Macros
$('macroHelp').innerHTML = DATA.macro_help.map(([macro, what]) =>
    `<div class="macro"><code>${esc(macro)}</code><span>${esc(what)}</span></div>`).join('');

// ----------------------------------------------------------------- Preview
$('previewCharacter').innerHTML = DATA.characters.length
    ? DATA.characters.map(c => `<option value="${esc(c.slug)}">${esc(c.name)}</option>`).join('')
    : '<option value="">No characters yet</option>';

$('previewBtn').onclick = async () => {
    $('preview').innerHTML = '<p class="help">Building…</p>';
    try {
        await flushSave();
        const data = await act({ action: 'preview', id: preset.id, character: $('previewCharacter').value });
        const total = data.messages.reduce((n, m) => n + m.tokens, 0);
        const params = Object.keys(data.params).length ? esc(JSON.stringify(data.params)) : 'none (model defaults)';
        $('preview').innerHTML = `
          <p class="help">${data.messages.length} messages · ~${total} tokens${data.model ? ' · model ' + esc(data.model) : ''} · samplers sent: ${params}</p>
          ${data.notes.map(n => `<p class="warn">⚠ ${esc(n)}</p>`).join('')}
          ${data.messages.map((m, i) => `
            <details class="msg ${m.role}" ${i === data.messages.length - 1 ? 'open' : ''}>
              <summary><span class="role">${m.role}</span> <span class="sources">${esc(m.sources.join(' + '))}</span>
                <span class="tokens">~${m.tokens}</span></summary>
              <pre>${esc(m.content)}</pre>
            </details>`).join('')}`;
    } catch (err) {
        $('preview').innerHTML = `<p class="warn">${esc(err.message)}</p>`;
    }
};

// ------------------------------------------------------------- Text rules
const MODE_LABELS = { display: 'On screen', prompt: 'Sent to the AI', saved: 'Saved' };
const openRules = new Set();
// Two lists share this editor: the preset's rules, and the user's own (run with every preset)
let myRules = DATA.my_rules || [];
let ruleScope = 'preset';
let myRulesTimer = null;
const ruleList = () => ruleScope === 'mine' ? myRules : preset.regex;
function setRuleList(list) { if (ruleScope === 'mine') myRules = list; else preset.regex = list; }
function rulesChanged() {
    if (ruleScope !== 'mine') { rulesChanged(); return; }
    clearTimeout(myRulesTimer);
    myRulesTimer = setTimeout(async () => {
        try {
            const data = await act({ action: 'save_my_rules', rules: myRules });
            $('ruleStatus').textContent = `Saved your ${data.rules.length} rule${data.rules.length === 1 ? '' : 's'}.`;
        } catch (err) { $('ruleStatus').textContent = err.message; }
    }, 600);
}

function ruleWhere(r) {
    const you = r.placement.includes(1), ai = r.placement.includes(2);
    const extra = [r.placement.includes(5) && 'lore entries', r.placement.includes(6) && 'thinking'].filter(Boolean);
    const who = [you && ai ? 'all messages' : you ? 'your messages' : ai ? 'AI replies' : '', ...extra]
        .filter(Boolean).join(', ') || 'nothing yet';
    const depth = r.min_depth != null || r.max_depth != null
        ? ` · ${r.min_depth != null ? `skips the newest ${r.min_depth}` : ''}${r.min_depth != null && r.max_depth != null ? ', ' : ''}${r.max_depth != null ? `only the newest ${r.max_depth + 1}` : ''}`
        : '';
    return who + depth;
}

function ruleEditor(r) {
    return `<div class="rule-editor">
        <label>Name <input type="text" data-rf="name" value="${esc(r.name)}"></label>
        <label>Find (a regex; <code>/pattern/flags</code> as in SillyTavern)
          <textarea data-rf="find" rows="3" class="mono">${esc(r.find)}</textarea></label>
        <label>Replace with (<code>$1</code>, <code>$&lt;name&gt;</code> and <code>{{match}}</code> insert what was found; empty removes it)
          <textarea data-rf="replace" rows="3" class="mono">${esc(r.replace)}</textarea></label>
        <div class="rule-grid">
          <label>Works
            <select data-rf="mode">${Object.entries(MODE_LABELS).map(([k, l]) =>
                `<option value="${k}" ${k === r.mode ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <fieldset><legend>On</legend>
            <label class="check small"><input type="checkbox" data-rp="2" ${r.placement.includes(2) ? 'checked' : ''}> AI replies</label>
            <label class="check small"><input type="checkbox" data-rp="1" ${r.placement.includes(1) ? 'checked' : ''}> Your messages</label>
            <label class="check small" title="Applied as lore entries go into the prompt (Saved and Sent to the AI rules)"><input type="checkbox" data-rp="5" ${r.placement.includes(5) ? 'checked' : ''}> Lore entries</label>
            <label class="check small" title="Applied to the model's thinking when it's saved (Saved rules)"><input type="checkbox" data-rp="6" ${r.placement.includes(6) ? 'checked' : ''}> Thinking</label>
          </fieldset>
          <label>Skip the newest <input type="number" min="0" data-rf="min_depth" value="${r.min_depth ?? ''}" placeholder="0"> messages</label>
          <label>Up to message <input type="number" min="0" data-rf="max_depth" value="${r.max_depth ?? ''}" placeholder="any"> back</label>
        </div>
        <label>Remove from what was found before inserting it (one per line)
          <textarea data-rf="trim" rows="2" class="mono">${esc((r.trim || []).join('\n'))}</textarea></label>
        <label class="check small"><input type="checkbox" data-rf="run_on_edit" ${r.run_on_edit ? 'checked' : ''}> Also run when I edit a message (Saved rules only)</label>
        <div class="rule-test">
          <label>Try it on <textarea class="test-input" rows="3" placeholder="Paste a message here"></textarea></label>
          <button type="button" class="secondary small" data-ract="test">Run</button>
          <pre class="test-output" hidden></pre>
        </div>
        <div class="rule-actions"><button type="button" class="danger small" data-ract="delete">Delete rule</button></div>
      </div>`;
}

function renderRules() {
    const q = ($('ruleSearch').value || '').toLowerCase();
    const onlyOn = $('rulesOnlyOn').checked;
    const list = ruleList().filter(r => (!onlyOn || r.enabled) &&
        (!q || r.name.toLowerCase().includes(q) || r.find.toLowerCase().includes(q)));
    const on = ruleList().filter(r => r.enabled).length;
    $('ruleCount').textContent = ruleList().length ? `${on} of ${ruleList().length} on` : '';
    $('ruleTabCount').textContent = preset.regex.length ? preset.regex.filter(r => r.enabled).length : '';
    document.querySelectorAll('#ruleScope [data-scope]').forEach(b => b.classList.toggle('active', b.dataset.scope === ruleScope));
    $('rules').innerHTML = list.length ? list.map(r => `
      <div class="rule ${r.enabled ? '' : 'off'}" data-rule="${esc(r.id)}">
        <div class="rule-row">
          <label class="switch" title="On or off"><input type="checkbox" data-ract="toggle" ${r.enabled ? 'checked' : ''}><span></span></label>
          <button type="button" class="rule-name" data-ract="open">${esc(r.name)}</button>
          <span class="chip mode-${r.mode}">${MODE_LABELS[r.mode]}</span>
          <span class="rule-where">${esc(ruleWhere(r))}</span>
        </div>
        ${openRules.has(r.id) ? ruleEditor(r) : ''}
      </div>`).join('')
      : `<p class="help">${ruleList().length ? 'No rules match.' : ruleScope === 'mine'
          ? 'You have no rules of your own. They run with every preset, before the preset\'s own.'
          : 'This preset has no text rules. Most presets don\'t need any.'}</p>`;
}

const ruleById = id => ruleList().find(r => r.id === id);

$('rules').addEventListener('click', async e => {
    const el = e.target.closest('[data-ract]');
    const box = e.target.closest('[data-rule]');
    if (!el || !box) return;
    const r = ruleById(box.dataset.rule);
    const a = el.dataset.ract;
    if (a === 'open') { openRules.has(r.id) ? openRules.delete(r.id) : openRules.add(r.id); renderRules(); }
    if (a === 'delete' && confirm(`Delete the rule “${r.name}”?`)) {
        setRuleList(ruleList().filter(x => x !== r)); renderRules(); rulesChanged();
    }
    if (a === 'test') {
        const out = box.querySelector('.test-output');
        out.hidden = false;
        try {
            const data = await act({ action: 'test_rule', id: preset.id, rule: r, text: box.querySelector('.test-input').value });
            out.textContent = data.problem || data.result || '(nothing left)';
        } catch (err) { out.textContent = err.message; }
    }
});

$('rules').addEventListener('change', e => {
    const box = e.target.closest('[data-rule]');
    if (!box) return;
    const r = ruleById(box.dataset.rule);
    const t = e.target;
    if (t.dataset.ract === 'toggle') { r.enabled = t.checked; renderRules(); rulesChanged(); return; }
    if (t.dataset.rp) {
        const p = Number(t.dataset.rp);
        r.placement = t.checked ? [...new Set([...r.placement, p])] : r.placement.filter(x => x !== p);
    } else if (t.dataset.rf) {
        const f = t.dataset.rf;
        if (f === 'run_on_edit') r[f] = t.checked;
        else if (f === 'min_depth' || f === 'max_depth') r[f] = t.value === '' ? null : Math.max(0, parseInt(t.value, 10) || 0);
        else if (f === 'trim') r.trim = t.value.split('\n').filter(Boolean);
        else r[f] = t.value;
    } else return;
    box.querySelector('.rule-name').textContent = r.name;
    box.querySelector('.rule-where').textContent = ruleWhere(r);
    const chip = box.querySelector('.chip');
    chip.className = `chip mode-${r.mode}`; chip.textContent = MODE_LABELS[r.mode];
    rulesChanged();
});

$('ruleSearch').addEventListener('input', renderRules);
$('rulesOnlyOn').addEventListener('change', renderRules);
$('addRule').onclick = () => {
    const r = { id: uid(), name: 'New rule', find: '', replace: '', trim: [], placement: [2], enabled: true,
                mode: 'display', macros_in_find: 0, min_depth: null, max_depth: null, run_on_edit: false };
    ruleList().push(r); openRules.add(r.id); renderRules();
};
$('importRules').onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const data = await act({ action: 'import_rules', id: preset.id, data: JSON.parse(await file.text()) });
        const known = new Set(ruleList().map(r => r.id));
        data.rules.forEach(r => { if (known.has(r.id)) r.id = uid(); ruleList().push(r); });
        $('ruleStatus').textContent = `Added ${data.rules.length} rule${data.rules.length === 1 ? '' : 's'}.`;
        renderRules(); rulesChanged();
    } catch (err) { $('ruleStatus').textContent = err.message; }
    e.target.value = '';
};

$('ruleScope').addEventListener('click', e => {
    const b = e.target.closest('[data-scope]');
    if (!b) return;
    ruleScope = b.dataset.scope;
    openRules.clear();
    renderRules();
});

// ------------------------------------------------------------------- Tabs
function showTab(tab) {
    document.querySelectorAll('[data-panel]').forEach(el => { el.hidden = el.dataset.panel !== tab; });
    document.querySelectorAll('#tabs [data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
    try { localStorage.setItem('presetTab', tab); } catch (e) { /* optional */ }
}
$('tabs').addEventListener('click', e => { const t = e.target.closest('[data-tab]'); if (t) showTab(t.dataset.tab); });
let startTab = 'blocks';
try { startTab = localStorage.getItem('presetTab') || 'blocks'; } catch (e) { /* optional */ }

renderList(); renderHead(); renderBlocks(); renderUtility(); renderRules(); showTab(startTab);

// Edit a short text in place: the element turns into a text box; Enter or clicking away saves, Esc cancels.
// Resolves to the new text, or null if nothing changed.
function editInPlace(el, value) {
    return new Promise(resolve => {
        const old = el.innerHTML;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.className = 'inline-edit';
        input.setAttribute('aria-label', 'New name');
        el.innerHTML = '';
        el.appendChild(input);
        input.focus();
        input.select();
        let done = false;
        const finish = keep => {
            if (done) return;
            done = true;
            const text = input.value.trim();
            el.innerHTML = old;
            resolve(keep && text && text !== value ? text : null);
        };
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); finish(true); }
            if (e.key === 'Escape') { e.preventDefault(); finish(false); }
        });
        input.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); });
        input.addEventListener('blur', () => finish(true));
    });
}
