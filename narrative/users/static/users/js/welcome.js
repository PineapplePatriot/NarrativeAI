const $ = id => document.getElementById(id);
const DATA = JSON.parse($('welcome-data').textContent);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let picked = (DATA.models.find(m => m.openrouter === DATA.current_model) || {}).id || null;

$('keyNote').hidden = !DATA.has_key;

function renderModels() {
    $('models').innerHTML = DATA.models.map(m => `
        <label class="model ${m.id === picked ? 'picked' : ''} ${m.recommended ? 'recommended' : ''}">
          <input type="radio" name="model" value="${esc(m.id)}" ${m.id === picked ? 'checked' : ''}>
          <span class="model-head"><b>${esc(m.name)}</b>
            ${m.recommended ? '<span class="tag rec">Popular right now</span>' : ''}
            <span class="tag price" title="Rough price guide">${esc(m.price)}</span></span>
          <span class="best">${esc(m.best_for)}</span>
          <span class="watch">${esc(m.watch_out)}</span>
        </label>`).join('');
}
$('models').addEventListener('change', e => { picked = e.target.value; renderModels(); });

function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

async function save(skipCheck = false) {
    const err = $('error');
    err.hidden = true;
    if (!picked) { err.textContent = 'Pick a model first.'; err.hidden = false; return; }
    $('saveBtn').disabled = true;
    $('saveBtn').textContent = 'Checking your key…';
    try {
        const resp = await fetch(WELCOME_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ api_key: $('apiKey').value, model: picked, skip_check: skipCheck }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            err.innerHTML = esc(data.error) + (data.can_skip ? ' <button type="button" class="link" id="skipBtn">Save anyway</button>' : '');
            err.hidden = false;
            const skip = $('skipBtn');
            if (skip) skip.onclick = () => save(true);
            return;
        }
        $('pickedModel').textContent = data.model;
        document.querySelectorAll('.step, .actions').forEach(el => el.hidden = true);
        $('done').hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
        err.textContent = 'Could not reach the app server.'; err.hidden = false;
    } finally {
        $('saveBtn').disabled = false;
        $('saveBtn').textContent = 'Save and continue';
    }
}
$('saveBtn').onclick = () => save();
renderModels();
