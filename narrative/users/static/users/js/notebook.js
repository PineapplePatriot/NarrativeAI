/* Bulba's notebook: what Watch looks for (switch habits off and on, add your own), what it learned about
   your taste, and what the account has spent. Every change saves at once. */
const $ = id => document.getElementById(id);
let state = JSON.parse($('notebook-data').textContent);
let editingLine = null;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : '';
}

function money(v) {
    v = Number(v) || 0;
    if (!v) return '$0';
    return v < 0.01 ? '< $0.01' : '$' + v.toFixed(v < 10 ? 2 : 0);
}

const toggle = (i, on, kind, title, about, extra = '') =>
    `<li class="${on ? '' : 'off'}"><label class="toggle-line"><input type="checkbox" data-${kind}="${i}" ${on ? 'checked' : ''}>
        <span>${esc(title)}${extra}${about ? `<small class="fix-about">${esc(about)}</small>` : ''}</span></label></li>`;

function fill() {
    $('spentTotal').textContent = money(state.spent);
    $('spentMonth').textContent = money(state.month);
    $('watchState').textContent = state.on ? 'on' : 'off';
    $('nbCommon').innerHTML = state.common.map((h, i) =>
        toggle(i, h.on, 'common', h.title, h.about, h.fixing ? ' <small class="in-preset" title="Rewritten out of new replies">🧹</small>' : '')).join('');
    $('nbModelName').textContent = state.model.name;
    $('nbModel').innerHTML = state.model.items.length
        ? state.model.items.map((h, i) => toggle(i, h.on, 'model', h.text, '')).join('')
        : '<li class="empty">Nothing special noted for this model; the common list covers it.</li>';
    $('nbOwn').innerHTML = state.own.length ? state.own.map((m, i) => `<li><span>${esc(m.title)}${m.about ? `<small class="fix-about">${esc(m.about)}</small>` : ''}</span>
        <span class="memory-btns"><button type="button" class="x" data-stopown="${i}" title="Remove">✕</button></span></li>`).join('')
        : '<li class="empty">Nothing yet. Add something below.</li>';
    $('nbFix').innerHTML = state.fix.length ? state.fix.map((m, i) => `<li><span>${esc(m.title)}</span><span class="memory-btns">
        <button type="button" class="x" data-stopfix="${i}" title="Stop fixing this">✕</button></span></li>`).join('')
        : '<li class="empty">Nothing yet. Press "Fix this automatically" on one of Bulba\'s notes in a chat, or add your own above.</li>';
    $('fixModel').value = state.fix_model || 'bulba';
    $('nbMutedBox').hidden = !state.muted_other.length;
    $('nbMuted').innerHTML = state.muted_other.map((m, i) => `<li><span>${esc(m.title)}</span><span class="memory-btns">
        <button type="button" class="x" data-unmute="${i}" title="Notice it again">✕</button></span></li>`).join('');
    $('watchTaste').innerHTML = state.taste.length ? state.taste.map((t, i) => editingLine === t
        ? `<li class="editing"><input type="text" id="memoryEdit" value="${esc(t)}" maxlength="200">
             <span class="memory-btns"><button type="button" data-save="${i}">Save</button>
             <button type="button" class="ghost" data-cancel>Cancel</button></span></li>`
        : `<li><span>${esc(t)}${(state.taste_in_preset || []).includes(t) ? ' <small class="in-preset">✓ in your preset</small>' : ''}</span><span class="memory-btns">
             <button type="button" class="x" data-edit="${i}" title="Reword">✎</button>
             <button type="button" class="x" data-forget="${i}" title="Remove">✕</button></span></li>`).join('')
        : '<li class="empty">Nothing yet. It learns as you rewrite or edit replies.</li>';
}

async function post(body) {
    $('memoryError').hidden = true;
    const resp = await fetch(NOTEBOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'watch_memory', ...body }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Could not save.');
    return data;
}

async function change(body) {
    try {
        const data = await post(body);
        state = data.state;
        editingLine = null;
    } catch (err) { $('memoryError').textContent = err.message; $('memoryError').hidden = false; }
    fill();
}

document.addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.common !== undefined) change({ op: t.checked ? 'unmute' : 'mute', old: state.common[t.dataset.common].label });
    else if (t.dataset.model !== undefined) change({ op: t.checked ? 'model_on' : 'model_off', old: state.model.items[t.dataset.model].text });
    else if (t.id === 'fixModel') change({ op: 'fix_model', new: t.value });
});

document.addEventListener('click', e => {
    const t = e.target.closest('[data-edit], [data-forget], [data-unmute], [data-stopfix], [data-stopown], [data-save], [data-cancel]');
    if (!t || !t.closest('.memory')) return;
    if (t.dataset.edit !== undefined) { editingLine = state.taste[t.dataset.edit]; fill(); $('memoryEdit').focus(); }
    else if (t.dataset.cancel !== undefined) { editingLine = null; fill(); }
    else if (t.dataset.save !== undefined) change({ op: 'edit', old: state.taste[t.dataset.save], new: $('memoryEdit').value });
    else if (t.dataset.forget !== undefined) change({ op: 'forget', old: state.taste[t.dataset.forget] });
    else if (t.dataset.unmute !== undefined) change({ op: 'unmute', old: state.muted_other[t.dataset.unmute].label });
    else if (t.dataset.stopfix !== undefined) change({ op: 'stop_fix', old: state.fix[t.dataset.stopfix].label });
    else if (t.dataset.stopown !== undefined) change({ op: 'stop_fix', old: state.own[t.dataset.stopown].label });
});

document.addEventListener('keydown', e => {
    if (e.target.id === 'memoryEdit' && e.key === 'Enter') { e.preventDefault(); document.querySelector('[data-save]').click(); }
});

// Something they dislike: Bulba words it (a short name and what to look for), they check it, then it's added
$('dislikeWord').addEventListener('click', async () => {
    const raw = $('dislikeRaw').value.trim();
    if (!raw) { $('dislikeRaw').focus(); return; }
    const btn = $('dislikeWord'); btn.disabled = true; btn.textContent = '🥔 Wording…';
    try {
        const data = await post({ op: 'word_dislike', new: raw });
        $('dislikeName').value = data.suggestion.name; $('dislikeAbout').value = data.suggestion.about;
        $('dislikeCheck').hidden = false; $('dislikeName').focus();
    } catch (err) { $('memoryError').textContent = err.message; $('memoryError').hidden = false; }
    finally { btn.disabled = false; btn.textContent = '🥔 Word it with Bulba'; }
});
$('dislikeAdd').addEventListener('click', async () => {
    await change({ op: 'add_dislike', name: $('dislikeName').value, about: $('dislikeAbout').value });
    if ($('memoryError').hidden) { $('dislikeRaw').value = ''; $('dislikeCheck').hidden = true; }
});
$('dislikeCancel').addEventListener('click', () => { $('dislikeCheck').hidden = true; });

fill();
