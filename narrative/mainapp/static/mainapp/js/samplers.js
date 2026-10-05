const $ = id => document.getElementById(id);
const DATA = JSON.parse($('sampler-data').textContent);
let values = DATA.values;
let dirty = false;

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
function markDirty() { dirty = true; $('saveStatus').textContent = 'Unsaved changes'; $('saveStatus').className = 'status warn'; }
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

const PROFILE = DATA.profile;  // null when the model isn't in our list

// Mirrors model_profiles.sampler_status, so switching thinking off updates the page at once
function thinkingOn() {
    const info = (PROFILE && PROFILE.reasoning) || {};
    if (info.always_on) return true;
    const r = values.reasoning_effort;
    if (r && r.on) return r.value !== 'off';
    return (info.default || 'off') !== 'off';
}
function statusOf(key) {
    if (key === 'context_size') return { status: 'supported', why: '' };  // an app setting, never sent
    if (!PROFILE) return DATA.status[key] || { status: 'unverified', why: '' };
    const rule = (PROFILE.samplers || {})[key] || { status: 'unverified' };
    let status = rule.status || 'unverified';
    if (thinkingOn() && rule.when_reasoning) status = rule.when_reasoning;
    return { status, why: rule.why || '' };
}

function renderBanner() {
    const b = $('modelBanner');
    if (!DATA.model) {
        b.innerHTML = 'No main chat connection yet. Set one up on the Connections page first.';
    } else if (PROFILE) {
        const r = PROFILE.reasoning || {};
        b.innerHTML = `Main chat model: <b>${esc(PROFILE.name)}</b> <span class="muted">(${esc(DATA.model)})</span>.
            The settings below are matched to it: ones it fixes or doesn't have are never sent.
            ${r.note ? `<br>${esc(r.note)}` : ''}
            <br><span class="muted">Checked ${esc(PROFILE.verified)} against
            ${(PROFILE.sources || []).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">source ${i + 1}</a>`).join(', ')}.</span>`;
    } else {
        b.innerHTML = `Main chat model: <b>${esc(DATA.model)}</b>. It isn't in our model list yet
            (we know ${DATA.known_models.map(esc).join(', ')}), so every switched-on setting is sent as it is
            and the model may ignore some.`;
    }
}

const STATUS_TAG = {
    unverified: '<span class="tag" title="No source confirms this model uses it">not confirmed for this model</span>',
    fixed: '<span class="tag warn">fixed by the model · not sent</span>',
    unused: '<span class="tag">not used by this model</span>',
};

function control(spec, item) {
    const v = item.value;
    const dis = item.on ? '' : 'disabled';
    if (spec.kind === 'choice') {
        let choices = spec.choices.map(c => [c, c]);
        if (spec.key === 'reasoning_effort' && PROFILE && PROFILE.reasoning && PROFILE.reasoning.choices) {
            choices = Object.entries(PROFILE.reasoning.choices);
        }
        const known = choices.some(([c]) => c === v);
        return `<select data-k="${spec.key}" ${dis}>
            ${known ? '' : `<option value="${esc(v)}" selected>${esc(v)} (not available)</option>`}
            ${choices.map(([c, label]) => `<option value="${esc(c)}" ${c === v ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select>`;
    }
    if (spec.kind === 'list') {
        const text = (v || []).map(s => s.replace(/\n/g, '\\n')).join(', ');
        return `<input data-k="${spec.key}" value="${esc(text)}" placeholder="e.g. \\nUser:, ###" ${dis}>`;
    }
    const isSlider = spec.max - spec.min <= 1000;  // big ranges (tokens) get a number box only
    return `${isSlider ? `<input type="range" data-k="${spec.key}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${v}" ${dis}>` : ''}
            <input type="number" class="num" data-k="${spec.key}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${v}" ${dis}>`;
}

function row(spec) {
    const item = values[spec.key];
    const st = statusOf(spec.key);
    const tag = STATUS_TAG[st.status] && (PROFILE || st.status === 'fixed') ? STATUS_TAG[st.status] : '';
    return `
    <div class="sampler ${item.on ? 'on' : ''} st-${st.status}" data-row="${spec.key}">
      <label class="check title"><input type="checkbox" data-on="${spec.key}" ${item.on ? 'checked' : ''}>
        <span>${esc(spec.label)}</span> ${tag}</label>
      <div class="control">${control(spec, item)}</div>
      <p class="help">${esc(spec.help)}${st.why ? `<br><span class="why">${esc(st.why)}</span>` : ''}</p>
    </div>`;
}

let unusedOpen = false;
function render() {
    const used = DATA.specs.filter(s => statusOf(s.key).status !== 'unused');
    const unused = DATA.specs.filter(s => statusOf(s.key).status === 'unused');
    $('samplers').innerHTML = used.map(row).join('') + (unused.length ? `
        <details class="unused" ${unusedOpen ? 'open' : ''}>
          <summary>Not used by ${esc(PROFILE ? PROFILE.name : 'this model')} (${unused.length})</summary>
          ${unused.map(row).join('')}
        </details>` : '');
    const d = $('samplers').querySelector('details.unused');
    if (d) d.addEventListener('toggle', () => { unusedOpen = d.open; });
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
    if (key === 'reasoning_effort') render();  // thinking on/off can lock or unlock other settings
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
