const $ = id => document.getElementById(id);
let state = JSON.parse($('extras-data').textContent);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function fill() {
    $('removeEleven').hidden = !state.has_eleven_key;
    $('elevenKey').placeholder = state.has_eleven_key ? 'A key is saved. Paste a new one to replace it.' : 'ElevenLabs API key (leave empty for no voices)';
    for (const task of ['summary', 'trackers']) {
        document.querySelector(`input[name=${task}][value=${state[task].mode}]`).checked = true;
        $(`${task}Every`).value = state[task].interval;
    }
    $('sprites').checked = state.sprites;
    $('ideas').checked = !!state.ideas;
    $('watch').checked = !!state.watch;
    fillMemory();
    document.querySelector(`input[name=game][value=${state.game || 'off'}]`).checked = true;
    document.querySelectorAll('input[name=story_extras]').forEach(b => { b.checked = (state.story_extras || []).includes(b.value); });
    $('chatModel').textContent = state.chat_model || 'your chat model';
    $('background').innerHTML = `<option value="chat">Use my chat model for everything</option>` +
        state.cheap_models.map(m => `<option value="${esc(m.id)}">${esc(m.name)} (${esc(m.price)}): ${esc(m.best_for)}</option>`).join('');
    $('background').value = state.background;
    $('background').disabled = !state.openrouter;
}

function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

$('saveBtn').onclick = async () => {
    $('error').hidden = true; $('saved').hidden = true;
    $('saveBtn').disabled = true;
    const body = {
        summary: { mode: document.querySelector('input[name=summary]:checked').value, interval: Number($('summaryEvery').value) },
        trackers: { mode: document.querySelector('input[name=trackers]:checked').value, interval: Number($('trackersEvery').value) },
        sprites: $('sprites').checked,
        ideas: $('ideas').checked,
        watch: $('watch').checked,
        game: document.querySelector('input[name=game]:checked').value,
        story_extras: [...document.querySelectorAll('input[name=story_extras]:checked')].map(b => b.value),
        eleven_key: $('elevenKey').value,
        remove_eleven_key: $('removeElevenBox').checked,
    };
    if (state.openrouter) body.background = $('background').value;
    try {
        const resp = await fetch(EXTRAS_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Could not save.');
        state = data.state;
        $('elevenKey').value = ''; $('removeElevenBox').checked = false;
        fill();
        $('saved').hidden = false;
    } catch (e) {
        $('error').textContent = e.message; $('error').hidden = false;
    } finally {
        $('saveBtn').disabled = false;
    }
};
fill();

// --------------------------------------------------------------- what Bulba Watch learned
var editingLine = null;  // var: fill() runs before this line
function fillMemory() {
    const mem = state.watch_memory || { taste: [], muted: [] };
    $('watchTaste').innerHTML = mem.taste.length ? mem.taste.map((t, i) => editingLine === t
        ? `<li class="editing"><input type="text" id="memoryEdit" value="${esc(t)}" maxlength="200">
             <span class="memory-btns"><button type="button" data-save="${i}">Save</button>
             <button type="button" class="ghost" data-cancel>Cancel</button></span></li>`
        : `<li><span>${esc(t)}</span><span class="memory-btns">
             <button type="button" class="x" data-edit="${i}" title="Reword">✎</button>
             <button type="button" class="x" data-forget="${i}" title="Remove">✕</button></span></li>`).join('')
        : '<li class="empty">Nothing yet. It learns as you rewrite or edit replies.</li>';
    $('watchMutedBox').hidden = !mem.muted.length;
    $('watchMuted').innerHTML = mem.muted.map((m, i) => `<li><span>${esc(m.title)}</span><span class="memory-btns">
        <button type="button" class="x" data-unmute="${i}" title="Notice it again">✕</button></span></li>`).join('');
}

async function changeMemory(body) {
    $('memoryError').hidden = true;
    try {
        const resp = await fetch(EXTRAS_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'watch_memory', ...body }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Could not save.');
        state.watch_memory = data.state.watch_memory;
        editingLine = null;
        fillMemory();
    } catch (err) { $('memoryError').textContent = err.message; $('memoryError').hidden = false; }
}

document.addEventListener('click', e => {
    const mem = state.watch_memory || { taste: [], muted: [] };
    const t = e.target.closest('[data-edit], [data-forget], [data-unmute], [data-save], [data-cancel]');
    if (!t || !t.closest('.memory')) return;
    if (t.dataset.edit !== undefined) { editingLine = mem.taste[t.dataset.edit]; fillMemory(); $('memoryEdit').focus(); }
    else if (t.dataset.cancel !== undefined) { editingLine = null; fillMemory(); }
    else if (t.dataset.save !== undefined) changeMemory({ op: 'edit', old: mem.taste[t.dataset.save], new: $('memoryEdit').value });
    else if (t.dataset.forget !== undefined) changeMemory({ op: 'forget', old: mem.taste[t.dataset.forget] });
    else if (t.dataset.unmute !== undefined) changeMemory({ op: 'unmute', old: mem.muted[t.dataset.unmute].label });
});
document.addEventListener('keydown', e => {
    if (e.target.id === 'memoryEdit' && e.key === 'Enter') { e.preventDefault(); document.querySelector('[data-save]').click(); }
});
