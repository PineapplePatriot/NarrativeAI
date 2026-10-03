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
const approxTokens = s => Math.floor((s || '').length / 3) + 4;
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
    $('postProcessing').innerHTML = Object.entries(DATA.post_processing)
        .map(([k, label]) => `<option value="${k}" ${k === preset.options.post_processing ? 'selected' : ''}>${esc(label)}</option>`).join('');

    const extras = [];
    const regex = (preset.extras.extensions || {}).regex_scripts || [];
    if (regex.length) extras.push(`${regex.length} regex scripts`);
    if (preset.extras.function_calling) extras.push('function calling');
    if ((preset.extras.unused_prompts || []).length) extras.push(`${preset.extras.unused_prompts.length} unused prompts`);
    $('extrasNote').textContent = extras.length
        ? `Kept from SillyTavern for export, but not used here yet: ${extras.join(', ')}.` : '';
}

document.querySelector('.toolbar').addEventListener('click', async e => {
    const action = e.target.dataset.act;
    if (!action) return;
    try {
        if (action === 'rename') {
            const name = prompt('New name', preset.name);
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

// ------------------------------------------------------------------ Blocks
function groupOf(headerId) {
    // [start, end) indexes of a header and the blocks under it
    const start = preset.blocks.findIndex(b => b.id === headerId);
    let end = start + 1;
    while (end < preset.blocks.length && preset.blocks[end].kind !== 'header') end++;
    return [start, end];
}

function badges(b) {
    const out = [];
    if (b.kind === 'marker') out.push('<span class="tag slot" title="Filled in by the app">slot</span>');
    if (b.role !== 'system') out.push(`<span class="tag">${b.role}</span>`);
    if (b.position === 'in_chat') out.push(`<span class="tag" title="Inside the chat, ${b.depth} message(s) from the end">in chat @${b.depth}</span>`);
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
    const tokens = b.kind === 'prompt' ? `<span class="tokens" data-row-tokens>~${approxTokens(b.content)}</span>` : '';
    return `
      <div class="block ${b.enabled ? 'on' : ''} ${open.has(b.id) ? 'editing' : ''}" draggable="true" data-id="${esc(b.id)}">
        <span class="handle" title="Drag to move">⠿</span>
        <input type="checkbox" data-toggle="${esc(b.id)}" ${b.enabled ? 'checked' : ''} title="On / off">
        <button type="button" class="block-name" data-open="${esc(b.id)}">${esc(b.name)}</button>
        ${badges(b)}${tokens}
        <span class="moves">
          <button type="button" class="icon" data-move="-1" title="Move up">↑</button>
          <button type="button" class="icon" data-move="1" title="Move down">↓</button>
        </span>
      </div>
      ${open.has(b.id) ? editor(b) : ''}`;
}

function renderBlocks() {
    const all = preset.blocks.filter(b => b.kind !== 'header');
    $('blockCount').textContent = `${all.filter(b => b.enabled).length} of ${all.length} on`;
    let html = '';
    let hidden = false;
    preset.blocks.forEach((b, i) => {
        if (b.kind === 'header') {
            const [start, end] = groupOf(b.id);
            const inGroup = preset.blocks.slice(start + 1, end);
            const on = inGroup.filter(x => x.enabled).length;
            hidden = collapsed.has(b.id);
            html += `<div class="group-head ${open.has(b.id) ? 'editing' : ''}" draggable="true" data-id="${esc(b.id)}">
                <span class="handle" title="Drag to move the whole group">⠿</span>
                <button type="button" class="fold" data-fold="${esc(b.id)}">${hidden ? '▸' : '▾'}</button>
                <button type="button" class="block-name" data-open="${esc(b.id)}">${esc(b.name)}</button>
                <span class="count">${on}/${inGroup.length}</span></div>
                ${open.has(b.id) ? editor(b) : ''}`;
        } else if (!hidden) {
            html += blockRow(b);
        }
    });
    $('blocks').innerHTML = html || '<p class="help">No blocks yet. Add one below.</p>';
    renderSlotPicker();
}

function renderSlotPicker() {
    const present = new Set(preset.blocks.filter(b => b.kind === 'marker').map(b => b.marker));
    const missing = Object.entries(DATA.markers).filter(([k]) => !present.has(k));
    $('addSlot').innerHTML = `<option value="">+ Slot…</option>` +
        missing.map(([k, label]) => `<option value="${k}">${esc(label)}</option>`).join('');
    $('addSlot').disabled = !missing.length;
}

// Clicks: open editor, fold group, move, delete, duplicate
$('blocks').addEventListener('click', e => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.open) {
        open.has(t.dataset.open) ? open.delete(t.dataset.open) : open.add(t.dataset.open);
        renderBlocks();
    } else if (t.dataset.fold) {
        collapsed.has(t.dataset.fold) ? collapsed.delete(t.dataset.fold) : collapsed.add(t.dataset.fold);
        renderBlocks();
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
    }
    if (f === 'depth') {
        const row = $('blocks').querySelector(`[data-id="${CSS.escape(b.id)}"]`);
        row.querySelectorAll('.tag').forEach(t => { if (t.textContent.startsWith('in chat')) t.textContent = `in chat @${b.depth}`; });
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
                                 utility: preset.utility, options: preset.options });
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

renderList(); renderHead(); renderBlocks(); renderUtility();
