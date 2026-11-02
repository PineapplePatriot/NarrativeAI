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
    document.querySelector(`input[name=game][value=${state.game || 'off'}]`).checked = true;
    document.querySelectorAll('input[name=story_extras]').forEach(b => { b.checked = (state.story_extras || []).includes(b.value); });
    $('chatModel').textContent = state.chat_model || 'your chat model';
    $('background').innerHTML = `<option value="chat">Use my chat model for everything</option>` +
        state.cheap_models.map(m => `<option value="${esc(m.id)}">${esc(m.name)} (${esc(m.price)}): ${esc(m.best_for)}</option>`).join('');
    $('background').value = state.background;
    $('background').disabled = !state.openrouter;
    if (state.window) {
        $('memorySection').hidden = false;
        $('memoryModel').textContent = state.window.model || 'your chat model';
        const steps = NACosts.steps(state.window.max);
        $('chatContext').max = steps.length - 1;
        $('chatContext').value = NACosts.nearest(steps, state.window.value);
    }
    costs();
}

// What a message, a summary and a tracker update cost with these settings (static/js/costs.js)
function costs() {
    if (!state.window) return;
    const steps = NACosts.steps(state.window.max);
    const size = steps[Number($('chatContext').value)] || steps[0];
    const prices = state.prices || {};
    const bg = ($('background').value !== 'chat' ? (prices.bg || {})[$('background').value] : prices.chat) || null;
    $('memoryValue').textContent = NACosts.memory(size);
    $('memoryCost').textContent = NACosts.chat(prices.chat, size);
    for (const task of ['summary', 'trackers']) {
        const mode = (document.querySelector(`input[name=${task}]:checked`) || {}).value;
        $(`${task}Cost`).textContent = NACosts.job(task, bg, size, mode, Number($(`${task}Every`).value) || 1);
    }
}
['chatContext', 'summaryEvery', 'trackersEvery', 'background'].forEach(id => $(id).addEventListener('input', costs));
document.querySelectorAll('input[name=summary], input[name=trackers]').forEach(r => r.addEventListener('change', costs));

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
    if (state.window) body.chat_context = NACosts.steps(state.window.max)[Number($('chatContext').value)];
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
