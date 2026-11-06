const $ = id => document.getElementById(id);

const DEFAULTS = JSON.parse($('lore-defaults').textContent);
let book = JSON.parse($('worldbook-json').textContent);
let editingUid = null;
let dirty = false;

function markDirty(on = true) {
    dirty = on;
    $('unsavedPill').hidden = !on;
}
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
function splitKeys(s) { return s.split(',').map(k => k.trim()).filter(Boolean); }
function approxTokens(s) { return Math.max(1, Math.floor((s || '').length / 4)); }
function label(e) { return e.comment || e.keys[0] || `Entry ${e.uid}`; }
function triState(v) { return v === '' ? null : v === 'true'; }

// --- Book header + settings ---
function fillHeaderAndSettings() {
    $('wbTitle').value = book.title;
    $('wbDesc').value = book.description;
    $('wbBasedOn').value = book.based_on || '';
    const s = book.settings;
    $('sScanDepth').value = s.scan_depth;
    $('sBudget').value = s.token_budget;
    $('sCase').checked = s.case_sensitive;
    $('sWhole').checked = s.match_whole_words;
    $('sRecursive').checked = s.recursive_scan;
    $('sCard').checked = !!s.scan_card;
    $('sFlex').value = String(s.flexible_endings ?? 'auto');
    $('sSemantic').checked = s.semantic_enabled;
    $('sThreshold').value = s.semantic_threshold;
    $('sTopK').value = s.semantic_top_k;
}

function readSettings() {
    book.title = $('wbTitle').value.trim();
    book.description = $('wbDesc').value.trim();
    book.based_on = $('wbBasedOn').value.trim();
    Object.assign(book.settings, {
        scan_depth: Number($('sScanDepth').value) || 0,
        token_budget: Number($('sBudget').value) || 0,
        case_sensitive: $('sCase').checked,
        match_whole_words: $('sWhole').checked,
        recursive_scan: $('sRecursive').checked,
        scan_card: $('sCard').checked,
        flexible_endings: $('sFlex').value === 'auto' ? 'auto' : $('sFlex').value === 'true',
        semantic_enabled: $('sSemantic').checked,
        semantic_threshold: Number($('sThreshold').value) || 0,
        semantic_top_k: Number($('sTopK').value) || 0,
    });
}

['wbTitle', 'wbDesc', 'wbBasedOn', 'sScanDepth', 'sBudget', 'sCase', 'sWhole', 'sRecursive', 'sCard', 'sFlex', 'sSemantic', 'sThreshold', 'sTopK']
    .forEach(id => $(id).addEventListener('input', () => { readSettings(); markDirty(); }));

// --- Entry list ---
function render() {
    const q = $('search').value.toLowerCase();
    const f = $('enabledFilter').value;
    const list = [...book.entries]
        .sort((a, b) => b.order - a.order)
        .filter(e => {
            const hay = [e.comment, e.content, ...e.keys, ...e.secondary_keys].join(' ').toLowerCase();
            if (q && !hay.includes(q)) return false;
            if (f === 'constant') return e.constant;
            if (f) return String(e.enabled) === f;
            return true;
        });

    $('entries').innerHTML = list.map(entryRow).join('');
    $('emptyMsg').style.display = list.length ? 'none' : 'block';
    const total = book.entries.length;
    $('stats').textContent = `${list.length} of ${total} entr${total === 1 ? 'y' : 'ies'}`;
}

function entryRow(e) {
    const badges = [];
    if (e.constant) badges.push('<span class="badge const">always on</span>');
    if (!e.enabled) badges.push('<span class="badge off">disabled</span>');
    if (e.secondary_keys.length) badges.push(`<span class="badge">${escapeHtml(e.selective_logic.replace('_', ' ').toLowerCase())}: ${e.secondary_keys.map(escapeHtml).join(', ')}</span>`);
    badges.push(`<span class="badge">order ${e.order}</span>`);
    badges.push(`<span class="badge">~${approxTokens(e.content)} tokens</span>`);

    const keys = e.keys.length
        ? e.keys.map(k => `<span class="tag">${escapeHtml(k)}</span>`).join('')
        : (e.constant ? '' : '<span class="warn">No keywords — this entry can only fire if it is always on or via semantic search.</span>');

    return `
    <div class="entry ${e.enabled ? '' : 'is-off'}">
      <div class="entry-header">
        <div class="entry-key">${escapeHtml(label(e))}</div>
        <div class="entry-actions">
          <button class="btn" onclick="openModal(${e.uid})">Edit</button>
          <button class="btn" onclick="duplicate(${e.uid})">Copy</button>
          <button class="btn" onclick="del(${e.uid})">Delete</button>
        </div>
      </div>
      <div class="keys">${keys}</div>
      <div class="preview">${escapeHtml(e.content)}</div>
      <div class="badges">${badges.join('')}</div>
    </div>`;
}

$('search').addEventListener('input', render);
$('enabledFilter').addEventListener('change', render);

// --- Entry editor ---
function nextUid() { return book.entries.reduce((m, e) => Math.max(m, e.uid), -1) + 1; }

function openModal(uid) {
    editingUid = uid ?? null;
    const e = editingUid === null ? { ...DEFAULTS.entry } : book.entries.find(x => x.uid === uid);
    $('modalTitle').textContent = editingUid === null ? 'New Entry' : 'Edit Entry';
    $('fComment').value = e.comment;
    $('fKeys').value = e.keys.join(', ');
    $('fSecondary').value = e.secondary_keys.join(', ');
    $('fLogic').value = e.selective_logic;
    $('fContent').value = e.content;
    $('fOrder').value = e.order;
    $('fEnabled').checked = e.enabled;
    $('fConstant').checked = e.constant;
    $('fSemantic').checked = e.semantic;
    $('fCase').value = e.case_sensitive === null ? '' : String(e.case_sensitive);
    $('fWhole').value = e.match_whole_words === null ? '' : String(e.match_whole_words);
    $('fDepth').value = e.scan_depth ?? '';
    $('fExcludeRec').checked = e.exclude_recursion;
    $('fPreventRec').checked = e.prevent_recursion;
    updateTokenHint();
    $('entryExpandResult').innerHTML = '';
    $('modal').style.display = 'flex';
    $('fComment').focus();
}

function closeModal() { $('modal').style.display = 'none'; }
function updateTokenHint() { $('fTokens').textContent = `~${approxTokens($('fContent').value)} tokens`; }
$('fContent').addEventListener('input', updateTokenHint);

function saveEntry() {
    const obj = {
        comment: $('fComment').value.trim(),
        keys: splitKeys($('fKeys').value),
        secondary_keys: splitKeys($('fSecondary').value),
        selective_logic: $('fLogic').value,
        content: $('fContent').value,
        order: Number($('fOrder').value) || 0,
        enabled: $('fEnabled').checked,
        constant: $('fConstant').checked,
        semantic: $('fSemantic').checked,
        case_sensitive: triState($('fCase').value),
        match_whole_words: triState($('fWhole').value),
        scan_depth: $('fDepth').value === '' ? null : Number($('fDepth').value),
        exclude_recursion: $('fExcludeRec').checked,
        prevent_recursion: $('fPreventRec').checked,
    };
    if (!obj.content.trim()) { alert('Content is required.'); return; }
    if (!obj.keys.length && !obj.constant &&
        !confirm('This entry has no keywords and is not "always on", so it will only fire through semantic search. Save anyway?')) return;

    if (editingUid === null) {
        book.entries.push({ ...DEFAULTS.entry, ...obj, uid: nextUid() });
    } else {
        const i = book.entries.findIndex(x => x.uid === editingUid);
        book.entries[i] = { ...book.entries[i], ...obj };
    }
    closeModal();
    markDirty();
    render();
}

function duplicate(uid) {
    const e = book.entries.find(x => x.uid === uid);
    book.entries.push({ ...e, uid: nextUid(), comment: (e.comment || label(e)) + ' (copy)' });
    markDirty();
    render();
}

function del(uid) {
    if (!confirm('Delete this entry?')) return;
    book.entries = book.entries.filter(e => e.uid !== uid);
    markDirty();
    render();
}

$('newEntryBtn').onclick = () => openModal();
$('cancelBtn').onclick = closeModal;
$('saveBtn').onclick = saveEntry;
window.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// --- Server calls ---
function getCookie(name) {
    const match = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function postJson(url, body) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
}

$('saveWorldbookBtn').onclick = async () => {
    readSettings();
    if (!book.title) { alert('Title is required.'); return; }
    try {
        const data = await postJson(URLS.save, book);
        book = data.book;
        markDirty(false);
        fillHeaderAndSettings();
        render();
        flash(`Saved ${data.count} entr${data.count === 1 ? 'y' : 'ies'}.`);
    } catch (err) { alert('Error saving: ' + err.message); }
};

function flash(text) {
    const el = document.createElement('div');
    el.className = 'flash';
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2200);
}

// --- Test panel ---
const STATUS_TEXT = { included: 'added', over_budget: 'over budget', disabled: 'disabled' };

$('testBtn').onclick = async () => {
    readSettings();
    const messages = $('testInput').value.split('\n').map(s => s.trim()).filter(Boolean);
    const note = $('testNote').value.trim();
    if (!messages.length && !note) { $('testResults').innerHTML = '<p class="muted">Type at least one message or a note.</p>'; return; }
    $('testResults').innerHTML = '<p class="muted">Testing…</p>';
    try {
        const data = await postJson(URLS.test, { book, messages, note });
        const rows = data.report.map(r => `
          <div class="result ${r.status}">
            <div class="result-head"><b>${escapeHtml(r.label)}</b><span class="status">${STATUS_TEXT[r.status] || r.status}</span></div>
            <div class="muted">${escapeHtml(r.reason)}${r.tokens ? ` · ~${r.tokens} tokens` : ''}</div>
          </div>`).join('');
        const notes = data.notes.map(n => `<p class="warn">${escapeHtml(n)}</p>`).join('');
        $('testResults').innerHTML = notes + (rows || '<p class="muted">Nothing fired. Check the keywords and the scan depth.</p>')
            + (data.prompt ? `<details class="advanced"><summary>Text sent to the AI (~${data.tokens_used} tokens)</summary><pre>${escapeHtml(data.prompt)}</pre></details>` : '');
    } catch (err) {
        $('testResults').innerHTML = `<p class="warn">Test failed: ${escapeHtml(err.message)}</p>`;
    }
};

// --- 🥔 Word forms: Bulba suggests the forms a word takes inside (Київ → Києві); nothing is saved until they add them ---
let proposedForms = null;
$('formsBtn').onclick = async () => {
    readSettings();
    const btn = $('formsBtn'), out = $('formsResult');
    btn.disabled = true;
    out.innerHTML = '<p class="muted">Bulba is going through the keywords…</p>';
    try {
        const data = await postJson(URLS.forms, { book });
        proposedForms = data.forms || {};
        const rows = book.entries.filter(e => (proposedForms[e.uid] || []).length).map(e => `
          <div class="result included"><div class="result-head"><b>${escapeHtml(label(e))}</b></div>
            <div class="muted">+ ${proposedForms[e.uid].map(escapeHtml).join(', ')}</div></div>`).join('');
        out.innerHTML = rows
            ? rows + `<button class="btn primary full" id="formsApply" type="button">Add these to the keywords</button>`
            : `<p class="muted">${escapeHtml(data.note || 'Nothing to add: the keywords already cover their forms.')}</p>`;
        if (rows) $('formsApply').onclick = () => {
            book.entries.forEach(e => {
                const extra = (proposedForms[e.uid] || []).filter(k => !e.keys.some(x => x.toLowerCase() === k.toLowerCase()));
                e.keys = [...e.keys, ...extra];
            });
            proposedForms = null;
            out.innerHTML = '<p class="muted">Added. Press Save to keep them (or reload the page to drop them).</p>';
            markDirty();
            render();
        };
    } catch (err) {
        out.innerHTML = `<p class="warn">${escapeHtml(err.message)}</p>`;
    } finally { btn.disabled = false; }
};

// --- 🥔 Expand: more keywords, more lore, missing entries; they tick what to add, then Save ---
const ORIGIN = { web: '🌐 from the web', memory: '🧠 from what Bulba knows', invented: '✨ invented' };
function sourcesHtml(data) {
    return data.sources && data.sources.length ? `<details class="advanced"><summary>Sources</summary>${data.sources.map(u =>
        `<div><a href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u.replace(/^https?:\/\//, '').slice(0, 60))}</a></div>`).join('')}</details>` : '';
}
function tick(id, html) { return `<label class="check x-pick"><input type="checkbox" data-pick="${id}" checked/> <span>${html}</span></label>`; }

$('expandBtn').onclick = async () => {
    readSettings();
    const what = [['xKeys', 'keys'], ['xLore', 'lore'], ['xNew', 'new']].filter(([id]) => $(id).checked).map(([, w]) => w);
    const out = $('expandResult'), btn = $('expandBtn');
    if (!what.length) { out.innerHTML = '<p class="muted">Tick at least one.</p>'; return; }
    btn.disabled = true;
    out.innerHTML = '<p class="muted">Bulba is ' + (book.based_on ? 'looking it up and ' : '') + 'going through the book… (up to a few minutes)</p>';
    try {
        const data = await postJson(URLS.expand, { book, what });
        const rows = [];
        book.entries.forEach(e => {
            const s = data.entries[e.uid];
            if (!s) return;
            if (s.keys.length) rows.push(tick(`k${e.uid}`, `<b>${escapeHtml(label(e))}</b>: + ${s.keys.map(escapeHtml).join(', ')}`));
            if (s.add) rows.push(tick(`a${e.uid}`, `<b>${escapeHtml(label(e))}</b>, more lore: <i>${escapeHtml(s.add)}</i>`));
        });
        data.new.forEach((n, i) => rows.push(tick(`n${i}`, `<b>New: ${escapeHtml(n.title)}</b> (${n.keys.map(escapeHtml).join(', ')})<br><i>${escapeHtml(n.content)}</i>`)));
        out.innerHTML = `<p class="x-origin">${ORIGIN[data.origin] || ''}</p>` + (data.note ? `<p class="muted">${escapeHtml(data.note)}</p>` : '')
            + rows.join('') + sourcesHtml(data)
            + (rows.length ? '<button class="btn primary full" id="expandApply" type="button">Add the ticked ones</button>' : '');
        if (!rows.length) return;
        $('expandApply').onclick = () => {
            const picked = id => out.querySelector(`[data-pick="${id}"]`)?.checked;
            const tag = data.origin === 'invented' ? ' (invented)' : '';
            book.entries.forEach(e => {
                const s = data.entries[e.uid];
                if (!s) return;
                if (picked(`k${e.uid}`)) e.keys = [...e.keys, ...s.keys.filter(k => !e.keys.some(x => x.toLowerCase() === k.toLowerCase()))];
                if (picked(`a${e.uid}`)) e.content = e.content.trim() + '\n' + s.add;
            });
            data.new.forEach((n, i) => {
                if (picked(`n${i}`)) book.entries.push({ ...DEFAULTS.entry, uid: nextUid(), comment: n.title + tag, keys: n.keys, content: n.content });
            });
            out.innerHTML = '<p class="muted">Added. Press Save to keep them (or reload the page to drop them).</p>';
            markDirty();
            render();
        };
    } catch (err) {
        out.innerHTML = `<p class="warn">${escapeHtml(err.message)}</p>`;
    } finally { btn.disabled = false; }
};

// The same for the entry being edited: the suggestions go into the editor's fields, then Save Entry
$('entryExpandBtn').onclick = async () => {
    readSettings();
    const out = $('entryExpandResult'), btn = $('entryExpandBtn');
    const entry = { ...DEFAULTS.entry, uid: 0, comment: $('fComment').value.trim(), keys: splitKeys($('fKeys').value),
                    content: $('fContent').value };
    if (!entry.content.trim() && !entry.keys.length) { out.innerHTML = '<p class="muted">Write a title or keywords first.</p>'; return; }
    if (!entry.content.trim()) entry.content = entry.comment || entry.keys[0];
    btn.disabled = true;
    out.innerHTML = '<p class="muted">Bulba is on it…</p>';
    try {
        const data = await postJson(URLS.expand, { book: { title: book.title, description: book.description,
            based_on: book.based_on, entries: [entry] }, what: ['keys', 'lore'], uid: 0 });
        const s = data.entries[0];
        if (!s) { out.innerHTML = `<p class="muted">${escapeHtml(data.note || 'Nothing to add.')}</p>`; return; }
        out.innerHTML = `<p class="x-origin">${ORIGIN[data.origin] || ''}</p>`
            + (s.keys.length ? tick('k', `+ ${s.keys.map(escapeHtml).join(', ')}`) : '')
            + (s.add ? tick('a', `<i>${escapeHtml(s.add)}</i>`) : '') + sourcesHtml(data)
            + '<button class="btn primary" id="entryExpandApply" type="button">Put them in</button>';
        $('entryExpandApply').onclick = () => {
            if (out.querySelector('[data-pick="k"]')?.checked) $('fKeys').value = [...splitKeys($('fKeys').value), ...s.keys].join(', ');
            if (out.querySelector('[data-pick="a"]')?.checked) $('fContent').value = ($('fContent').value.trim() + '\n' + s.add).trim();
            updateTokenHint();
            out.innerHTML = '<p class="muted">In the fields above. Press Save Entry to keep them.</p>';
        };
    } catch (err) {
        out.innerHTML = `<p class="warn">${escapeHtml(err.message)}</p>`;
    } finally { btn.disabled = false; }
};

fillHeaderAndSettings();
render();
