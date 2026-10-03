const $ = id => document.getElementById(id);
const CUSTOM = 'openai_compatible';
const OPENROUTER = 'openrouter';

let state = JSON.parse($('connections-state').textContent);
let newCounter = 0;
let dirty = false;

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}
function markDirty() { dirty = true; $('saveStatus').textContent = 'Unsaved changes'; $('saveStatus').className = 'status warn'; }
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

function newProfile(name) {
    return { id: `new-${++newCounter}`, name, provider: OPENROUTER, base_url: '', model: '', key_hint: '', has_key: false, api_key: '' };
}

// --- Connections ---
function renderProfiles() {
    $('startBanner').hidden = state.profiles.some(p => p.has_key || p.api_key);
    $('profiles').innerHTML = state.profiles.map(p => `
      <div class="profile" data-id="${esc(p.id)}">
        <div class="grid">
          <label>Name<input data-f="name" value="${esc(p.name)}" placeholder="e.g. Main"></label>
          <label>Provider
            <select data-f="provider">
              ${state.providers.map(o => `<option value="${o.value}" ${o.value === p.provider ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}
            </select>
          </label>
          <label class="wide" ${p.provider === CUSTOM ? '' : 'hidden'}>API base URL
            <input data-f="base_url" value="${esc(p.base_url)}" placeholder="https://api.example.com/v1">
          </label>
          <label>API key
            <input data-f="api_key" type="password" autocomplete="off" value="${esc(p.api_key || '')}"
                   placeholder="${p.has_key ? `Saved (${esc(p.key_hint)}), leave empty to keep` : (p.provider === OPENROUTER ? 'sk-or-v1-...' : 'Optional for local servers')}">
          </label>
          <label>Model
            <input data-f="model" value="${esc(p.model)}" ${p.provider === OPENROUTER ? 'list="openrouterModels"' : ''}
                   placeholder="${p.provider === OPENROUTER ? 'Start typing, e.g. anthropic/' : 'Model name'}">
          </label>
        </div>
        <div class="row">
          <button type="button" class="secondary small" data-act="test">Test</button>
          <span class="status" data-role="test"></span>
          <button type="button" class="danger small" data-act="remove">Remove</button>
        </div>
      </div>`).join('') || '<p class="help">No connections yet.</p>';
}

$('profiles').addEventListener('input', e => {
    const card = e.target.closest('.profile');
    if (!card || !e.target.dataset.f) return;
    const p = state.profiles.find(x => String(x.id) === card.dataset.id);
    p[e.target.dataset.f] = e.target.value;
    markDirty();
    if (e.target.dataset.f === 'provider') { renderProfiles(); renderTasks(); }
    if (e.target.dataset.f === 'name') renderTasks();
});

$('profiles').addEventListener('click', async e => {
    const act = e.target.dataset.act;
    if (!act) return;
    const card = e.target.closest('.profile');
    const p = state.profiles.find(x => String(x.id) === card.dataset.id);
    if (act === 'remove') {
        const used = state.tasks.filter(t => String(t.profile_id) === String(p.id)).map(t => t.label);
        if (!confirm(`Remove “${p.name || 'this connection'}”?` + (used.length ? `\n${used.join(', ')} will switch to the main chat connection.` : ''))) return;
        state.profiles = state.profiles.filter(x => x !== p);
        state.tasks.forEach(t => { if (String(t.profile_id) === String(p.id)) t.profile_id = null; });
        markDirty(); renderProfiles(); renderTasks();
    }
    if (act === 'test') {
        const out = card.querySelector('[data-role=test]');
        out.textContent = 'Testing…'; out.className = 'status';
        try {
            const data = await postJson(URLS.test, { ...p, id: typeof p.id === 'number' ? p.id : null });
            out.textContent = data.message; out.className = 'status ' + (data.ok ? 'ok' : 'bad');
        } catch (err) { out.textContent = err.message; out.className = 'status bad'; }
    }
});

$('addProfileBtn').onclick = () => {
    state.profiles.push(newProfile(state.profiles.length ? `Connection ${state.profiles.length + 1}` : 'Main'));
    markDirty(); renderProfiles(); renderTasks();
};

// --- Tasks ---
function profileOptions(selected, allowDefault) {
    const opts = allowDefault ? [`<option value="">Same as main chat</option>`] : [];
    state.profiles.forEach(p => opts.push(
        `<option value="${esc(p.id)}" ${String(p.id) === String(selected) ? 'selected' : ''}>${esc(p.name || 'Unnamed')}</option>`));
    return opts.join('');
}

function renderTasks() {
    $('tasks').innerHTML = state.tasks.map(t => {
        const isChat = t.task === 'chat';
        const off = t.toggleable && !t.enabled;
        return `
        <div class="task ${off ? 'is-off' : ''}" data-task="${t.task}">
          <div class="task-info">
            <b>${esc(t.label)}</b>
            <p class="help">${esc(t.help)}</p>
            ${t.toggleable ? `<label class="check"><input type="checkbox" data-f="enabled" ${t.enabled ? 'checked' : ''}> On</label>` : ''}
          </div>
          <div class="task-fields">
            <label>Connection
              <select data-f="profile_id" ${off ? 'disabled' : ''}>${profileOptions(t.profile_id, !isChat)}</select>
            </label>
            <label>Model override
              <input data-f="model" list="openrouterModels" value="${esc(t.model)}" ${off ? 'disabled' : ''}
                     placeholder="${isChat || t.profile_id ? "Connection's model" : 'Same as main chat'}">
            </label>
            ${t.schedulable ? `
            <label>When
              <select data-f="mode">
                <option value="manual" ${t.mode === 'manual' ? 'selected' : ''}>Only when I press the button</option>
                <option value="auto" ${t.mode === 'auto' ? 'selected' : ''}>Automatically</option>
              </select>
            </label>
            <label ${t.mode === 'auto' ? '' : 'hidden'}>Every N messages
              <input data-f="interval" type="number" min="1" value="${t.interval}">
            </label>` : ''}
          </div>
        </div>`;
    }).join('');
}

$('tasks').addEventListener('input', e => {
    const row = e.target.closest('.task');
    const f = e.target.dataset.f;
    if (!row || !f) return;
    const t = state.tasks.find(x => x.task === row.dataset.task);
    if (f === 'enabled') t.enabled = e.target.checked;
    else if (f === 'profile_id') {
        const v = e.target.value;
        t.profile_id = v === '' ? null : (/^\d+$/.test(v) ? Number(v) : v);
    } else if (f === 'interval') t.interval = Number(e.target.value) || 1;
    else t[f] = e.target.value;
    markDirty();
    if (f === 'enabled' || f === 'mode' || f === 'profile_id') renderTasks();
});

// --- ElevenLabs ---
function renderVoice() {
    $('elevenKey').value = '';
    $('elevenKey').placeholder = state.eleven_key_hint ? `Saved (${state.eleven_key_hint}), leave empty to keep` : 'sk_...';
    $('clearElevenRow').hidden = !state.eleven_key_hint;
    $('clearEleven').checked = false;
}
$('elevenKey').addEventListener('input', markDirty);
$('clearEleven').addEventListener('change', markDirty);

// --- Save ---
function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
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

$('saveBtn').onclick = async () => {
    $('saveBtn').disabled = true;
    try {
        const data = await postJson(URLS.save, {
            profiles: state.profiles,
            tasks: state.tasks,
            eleven_key: $('elevenKey').value,
            clear_eleven_key: $('clearEleven').checked,
        });
        state = data.state;
        dirty = false;
        renderAll();
        $('saveStatus').textContent = 'Saved'; $('saveStatus').className = 'status ok';
        if (URLS.next && state.profiles.length) window.location.href = URLS.next;
    } catch (err) {
        $('saveStatus').textContent = err.message; $('saveStatus').className = 'status bad';
    } finally {
        $('saveBtn').disabled = false;
    }
};

// --- OpenRouter model list (public, no key needed) ---
fetch('https://openrouter.ai/api/v1/models')
    .then(r => r.json())
    .then(d => {
        $('openrouterModels').innerHTML = (d.data || [])
            .sort((a, b) => a.id.localeCompare(b.id))
            .map(m => `<option value="${esc(m.id)}">${esc(m.name || m.id)}</option>`).join('');
    })
    .catch(() => { /* model list is only a convenience */ });

function renderAll() { renderProfiles(); renderTasks(); renderVoice(); }

if (!state.profiles.length) state.profiles.push(newProfile('Main'));
renderAll();
