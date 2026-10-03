const $ = id => document.getElementById(id);
const DATA = JSON.parse($('preset-data').textContent);
let presets = DATA.presets;
let preset = DATA.preset;
let saveTimer = null;
const collapsed = new Set();

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
const approxTokens = s => Math.floor((s || '').length / 3) + 4;

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
    if (data.presets) { presets = data.presets; preset = data.preset; }
    return data;
}

// --- Preset list ---
function renderList() {
    $('presetList').innerHTML = presets.map(p => `
      <button type="button" class="preset-item ${p.id === preset.id ? 'selected' : ''}" data-id="${p.id}">
        <span class="name">${esc(p.name)}</span>
        <span class="meta">${p.active ? '<b class="active">● active</b> · ' : ''}${p.enabled}/${p.blocks} blocks on</span>
      </button>`).join('');
}

$('presetList').addEventListener('click', e => {
    const item = e.target.closest('.preset-item');
    if (!item) return;
    window.location.href = `${URLS.page}?id=${item.dataset.id}`;
});

// --- Selected preset ---
function renderHead() {
    const summary = presets.find(p => p.id === preset.id);
    $('presetName').textContent = preset.name;
    $('activeBadge').innerHTML = summary && summary.active
        ? '<span class="badge-active">Active for all chats</span>'
        : '<button type="button" id="activateBtn">Use this preset</button>';
    const btn = $('activateBtn');
    if (btn) btn.onclick = () => act({ action: 'activate', id: preset.id }).then(renderAll).catch(err => alert(err.message));
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
            await act({ action, id: preset.id, name });
        } else if (action === 'delete') {
            if (!confirm(`Delete “${preset.name}”? This cannot be undone.`)) return;
            const data = await act({ action, id: preset.id });
            window.location.href = `${URLS.page}?id=${data.selected}`;
            return;
        } else {
            const data = await act({ action, id: preset.id });
            window.location.href = `${URLS.page}?id=${data.selected}`;
            return;
        }
        renderAll();
    } catch (err) { alert(err.message); }
});

$('postProcessing').onchange = e => { preset.options.post_processing = e.target.value; scheduleSave(); };

// --- Blocks, grouped under their headers ---
function groups() {
    const out = [];
    let current = { header: null, blocks: [] };
    for (const b of preset.blocks) {
        if (b.kind === 'header') {
            if (current.header || current.blocks.length) out.push(current);
            current = { header: b, blocks: [] };
        } else current.blocks.push(b);
    }
    if (current.header || current.blocks.length) out.push(current);
    return out;
}

function blockRow(b) {
    const badges = [];
    if (b.kind === 'marker') badges.push('<span class="tag slot" title="Filled in by the app">slot</span>');
    if (b.role !== 'system') badges.push(`<span class="tag">${b.role}</span>`);
    if (b.position === 'in_chat') badges.push(`<span class="tag" title="Placed inside the chat, ${b.depth} message(s) from the end">in chat @${b.depth}</span>`);
    const tokens = b.kind === 'prompt' ? `<span class="tokens">~${approxTokens(b.content)}</span>` : '';
    return `
      <div class="block ${b.enabled ? 'on' : ''}" data-id="${esc(b.id)}">
        <label class="switch-row"><input type="checkbox" data-toggle="${esc(b.id)}" ${b.enabled ? 'checked' : ''}></label>
        <button type="button" class="block-name" data-open="${esc(b.id)}">${esc(b.name)}</button>
        ${badges.join('')}${tokens}
      </div>
      <pre class="block-content" data-content="${esc(b.id)}" hidden>${esc(b.kind === 'marker'
        ? 'Filled in by the app: ' + (DATA.markers[b.marker] || b.marker) : b.content)}</pre>`;
}

function renderBlocks() {
    const all = preset.blocks.filter(b => b.kind !== 'header');
    $('blockCount').textContent = `${all.filter(b => b.enabled).length} of ${all.length} on`;
    $('blocks').innerHTML = groups().map((g, i) => {
        const key = g.header ? g.header.id : `top-${i}`;
        const on = g.blocks.filter(b => b.enabled).length;
        const head = g.header
            ? `<button type="button" class="group-head" data-group="${esc(key)}">
                 <span>${collapsed.has(key) ? '▸' : '▾'} ${esc(g.header.name)}</span><span class="count">${on}/${g.blocks.length}</span></button>`
            : '';
        return `<div class="group">${head}<div class="group-body" ${collapsed.has(key) ? 'hidden' : ''}>${g.blocks.map(blockRow).join('')}</div></div>`;
    }).join('');
}

$('blocks').addEventListener('click', e => {
    const t = e.target;
    if (t.dataset.open) {
        const pre = $('blocks').querySelector(`[data-content="${CSS.escape(t.dataset.open)}"]`);
        pre.hidden = !pre.hidden;
    }
    const g = t.closest('.group-head');
    if (g) {
        collapsed.has(g.dataset.group) ? collapsed.delete(g.dataset.group) : collapsed.add(g.dataset.group);
        renderBlocks();
    }
});

$('blocks').addEventListener('change', e => {
    const id = e.target.dataset.toggle;
    if (!id) return;
    preset.blocks.find(b => b.id === id).enabled = e.target.checked;
    e.target.closest('.block').classList.toggle('on', e.target.checked);
    scheduleSave();
});

function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
        const enabled = Object.fromEntries(preset.blocks.map(b => [b.id, b.enabled]));
        try {
            await act({ action: 'save', id: preset.id, enabled, post_processing: preset.options.post_processing });
            renderList(); renderBlocks();
        } catch (err) { alert('Could not save: ' + err.message); }
    }, 500);
}

// --- Import / new default ---
$('importFile').addEventListener('change', async () => {
    const file = $('importFile').files[0];
    if (!file) return;
    $('importStatus').textContent = 'Importing…';
    try {
        const data = await act({ action: 'import', data: JSON.parse(await file.text()), name: file.name.replace(/\.json$/i, '') });
        window.location.href = `${URLS.page}?id=${data.selected}`;
    } catch (err) {
        $('importStatus').textContent = `Could not import “${file.name}”: ${err.message}`;
    }
});

$('newDefaultBtn').onclick = async () => {
    try {
        const data = await act({ action: 'new_default' });
        window.location.href = `${URLS.page}?id=${data.selected}`;
    } catch (err) { alert(err.message); }
};

// --- Preview ---
$('previewCharacter').innerHTML = DATA.characters.length
    ? DATA.characters.map(c => `<option value="${esc(c.slug)}">${esc(c.name)}</option>`).join('')
    : '<option value="">No characters yet</option>';

$('previewBtn').onclick = async () => {
    $('preview').innerHTML = '<p class="help">Building…</p>';
    try {
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

function renderAll() { renderList(); renderHead(); renderBlocks(); }
renderAll();
