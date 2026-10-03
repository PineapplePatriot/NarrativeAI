const $ = id => document.getElementById(id);
const DATA = JSON.parse($('sampler-data').textContent);
let values = DATA.values;
let dirty = false;

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
function markDirty() { dirty = true; $('saveStatus').textContent = 'Unsaved changes'; $('saveStatus').className = 'status warn'; }
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

function renderBanner() {
    const b = $('modelBanner');
    if (!DATA.model) {
        b.innerHTML = 'No main chat connection yet. Set one up on the Connections page first.';
    } else if (DATA.locked.length) {
        b.innerHTML = `Your main chat model <b>${esc(DATA.model)}</b> rejects ${DATA.locked.map(k => `<b>${esc(k)}</b>`).join(', ')}.
            The app will skip them for this model even if they're switched on. Use <b>Reasoning effort</b> instead.`;
    } else {
        b.innerHTML = `Main chat model: <b>${esc(DATA.model)}</b>. Not every model supports every sampler;
            unsupported ones are usually ignored by OpenRouter.`;
    }
}

function control(spec, item) {
    const v = item.value;
    const dis = item.on ? '' : 'disabled';
    if (spec.kind === 'choice') {
        return `<select data-k="${spec.key}" ${dis}>${spec.choices.map(c => `<option ${c === v ? 'selected' : ''}>${c}</option>`).join('')}</select>`;
    }
    if (spec.kind === 'list') {
        const text = (v || []).map(s => s.replace(/\n/g, '\\n')).join(', ');
        return `<input data-k="${spec.key}" value="${esc(text)}" placeholder="e.g. \\nUser:, ###" ${dis}>`;
    }
    const isSlider = spec.max - spec.min <= 1000;  // big ranges (tokens) get a number box only
    return `${isSlider ? `<input type="range" data-k="${spec.key}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${v}" ${dis}>` : ''}
            <input type="number" class="num" data-k="${spec.key}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${v}" ${dis}>`;
}

function render() {
    $('samplers').innerHTML = DATA.specs.map(spec => {
        const item = values[spec.key];
        const skipped = item.on && DATA.locked.includes(spec.key);
        return `
        <div class="sampler ${item.on ? 'on' : ''}" data-row="${spec.key}">
          <label class="check title"><input type="checkbox" data-on="${spec.key}" ${item.on ? 'checked' : ''}>
            <span>${esc(spec.label)}</span>
            ${DATA.all_locked.includes(spec.key) ? '<span class="tag" title="Newest Claude models reject this">not for newest Claude</span>' : ''}
            ${skipped ? '<span class="tag warn">skipped for your model</span>' : ''}</label>
          <div class="control">${control(spec, item)}</div>
          <p class="help">${esc(spec.help)}</p>
        </div>`;
    }).join('');
}

$('samplers').addEventListener('input', e => {
    const t = e.target;
    if (t.dataset.on) {
        values[t.dataset.on].on = t.checked;
        markDirty(); render();
        return;
    }
    const key = t.dataset.k;
    if (!key) return;
    const spec = DATA.specs.find(s => s.key === key);
    let v = t.value;
    if (spec.kind === 'list') v = v.split(',').map(s => s.trim()).filter(Boolean).map(s => s.replace(/\\n/g, '\n'));
    else if (spec.kind !== 'choice') v = Number(v);
    values[key].value = v;
    // keep the slider and number box in sync
    t.closest('.control').querySelectorAll(`[data-k="${key}"]`).forEach(el => { if (el !== t) el.value = t.value; });
    markDirty();
});

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
            body: JSON.stringify(values),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        values = data.samplers;
        dirty = false;
        render();
        $('saveStatus').textContent = 'Saved'; $('saveStatus').className = 'status ok';
    } catch (err) {
        $('saveStatus').textContent = err.message; $('saveStatus').className = 'status bad';
    } finally {
        $('saveBtn').disabled = false;
    }
};

renderBanner();
render();
