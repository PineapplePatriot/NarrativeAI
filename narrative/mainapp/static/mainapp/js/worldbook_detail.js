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
    const s = book.settings;
    $('sScanDepth').value = s.scan_depth;
    $('sBudget').value = s.token_budget;
    $('sCase').checked = s.case_sensitive;
    $('sWhole').checked = s.match_whole_words;
    $('sRecursive').checked = s.recursive_scan;
    $('sSemantic').checked = s.semantic_enabled;
    $('sThreshold').value = s.semantic_threshold;
    $('sTopK').value = s.semantic_top_k;
}

function readSettings() {
    book.title = $('wbTitle').value.trim();
    book.description = $('wbDesc').value.trim();
    Object.assign(book.settings, {
        scan_depth: Number($('sScanDepth').value) || 0,
        token_budget: Number($('sBudget').value) || 0,
        case_sensitive: $('sCase').checked,
        match_whole_words: $('sWhole').checked,
        recursive_scan: $('sRecursive').checked,
        semantic_enabled: $('sSemantic').checked,
        semantic_threshold: Number($('sThreshold').value) || 0,
        semantic_top_k: Number($('sTopK').value) || 0,
    });
}

['wbTitle', 'wbDesc', 'sScanDepth', 'sBudget', 'sCase', 'sWhole', 'sRecursive', 'sSemantic', 'sThreshold', 'sTopK']
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
    if (!messages.length) { $('testResults').innerHTML = '<p class="muted">Type at least one message.</p>'; return; }
    $('testResults').innerHTML = '<p class="muted">Testing…</p>';
    try {
        const data = await postJson(URLS.test, { book, messages });
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

fillHeaderAndSettings();
render();
