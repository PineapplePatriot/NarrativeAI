const entriesEl = document.getElementById('entries');
const emptyMsg = document.getElementById('emptyMsg');
const statsEl = document.getElementById('stats');
const search = document.getElementById('search');
const scopeFilter = document.getElementById('scopeFilter');
const enabledFilter = document.getElementById('enabledFilter');

let entries = [];
let editing = null;

document.addEventListener('DOMContentLoaded', () => {
    const dataEl = document.getElementById('worldbook-json');
    if (dataEl) {
        try {
            const serverData = JSON.parse(dataEl.textContent);
            entries = (serverData.entries || []).map((e, i) => ({ ...e, id: i + 1 }));
        } catch (err) {
            console.error('Failed to parse worldbook JSON:', err);
        }
    }
    render();
});

function render() {
    entriesEl.innerHTML = '';
    const q = search.value.toLowerCase();
    const scope = scopeFilter.value;
    const enabled = enabledFilter.value;
    const filtered = entries.filter(e => {
        let ok = (e.key + ' ' + e.value + ' ' + (e.tags || []).join(' ')).toLowerCase().includes(q);
        if (scope) ok = ok && e.scope === scope;
        if (enabled) ok = ok && String(e.enabled) === enabled;
        return ok;
    });
    filtered.forEach(e => entriesEl.appendChild(entryRow(e)));
    emptyMsg.style.display = filtered.length ? 'none' : 'block';
    statsEl.textContent = `${filtered.length} entr${filtered.length === 1 ? 'y' : 'ies'} • scope: ${scope || 'all'}`;
}

function entryRow(e) {
    const div = document.createElement('div');
    div.className = 'entry';
    div.innerHTML = `
    <div class="entry-header">
      <div>
        <div class="entry-key">${e.key}</div>
        <div class="muted">${e.scope} • priority ${e.priority} • weight ${e.weight} ${e.enabled ? '' : '• disabled'}</div>
      </div>
      <div class="entry-actions">
        <button class="btn" title="Edit" onclick="openModal(${e.id})">Edit</button>
        <button class="btn" title="Delete" onclick="del(${e.id})">Delete</button>
      </div>
    </div>
    <div style="margin-bottom:8px">${escapeHtml(e.value).replace(/\n/g, '<br/>')}</div>
    <div>${(e.tags || []).map(t => `<span class="tag">${t}</span>`).join('')}</div>
  `;
    return div;
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])); }

// --- Modal ---
const modal = document.getElementById('modal');
const fKey = document.getElementById('fKey');
const fTags = document.getElementById('fTags');
const fScope = document.getElementById('fScope');
const fPriority = document.getElementById('fPriority');
const fWeight = document.getElementById('fWeight');
const fEnabled = document.getElementById('fEnabled');
const fValue = document.getElementById('fValue');
const modalTitle = document.getElementById('modalTitle');

document.getElementById('newEntryBtn').onclick = () => openModal();
document.getElementById('cancelBtn').onclick = () => closeModal();
document.getElementById('saveBtn').onclick = saveEntry;
document.getElementById('saveWorldbookBtn').onclick = saveWorldbook;

function openModal(id) {
    editing = id || null;
    if (editing) {
        const e = entries.find(x => x.id === id);
        modalTitle.textContent = 'Edit Entry';
        fKey.value = e.key; fTags.value = (e.tags || []).join(', '); fScope.value = e.scope;
        fPriority.value = e.priority; fWeight.value = e.weight; fEnabled.checked = e.enabled; fValue.value = e.value;
    } else {
        modalTitle.textContent = 'New Entry';
        fKey.value = ''; fTags.value = ''; fScope.value = 'global';
        fPriority.value = 50; fWeight.value = 1; fEnabled.checked = true; fValue.value = '';
    }
    modal.style.display = 'flex';
}

function closeModal() { modal.style.display = 'none'; }
window.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function saveEntry() {
    const obj = {
        key: fKey.value.trim(),
        tags: fTags.value.split(',').map(s => s.trim()).filter(Boolean),
        scope: fScope.value,
        priority: Number(fPriority.value) || 0,
        weight: Number(fWeight.value) || 0,
        enabled: !!fEnabled.checked,
        value: fValue.value
    };
    if (!obj.key) { alert('Key is required.'); return; }
    if (editing) {
        const i = entries.findIndex(x => x.id === editing);
        entries[i] = { ...entries[i], ...obj };
    } else {
        obj.id = (entries.at(-1)?.id || 0) + 1;
        entries.push(obj);
    }
    closeModal();
    render();
}

// --- Save Worldbook (з CSRF) ---
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');

async function saveWorldbook() {
    try {
        const resp = await fetch(window.location.pathname, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ entries })
        });
        const resJson = await resp.json();
        if (!resp.ok) alert('Error saving: ' + (resJson.error || 'Unknown'));
        else alert(`Saved ${resJson.count} entr${resJson.count === 1 ? 'y' : 'ies'} successfully.`);
    } catch (err) { alert('Network error: ' + err.message); }
}

// --- Delete Entry ---
function del(id) {
    if (!confirm('Delete this entry?')) return;
    entries = entries.filter(e => e.id !== id);
    render();
}


search.addEventListener('input', render);
scopeFilter.addEventListener('change', render);
enabledFilter.addEventListener('change', render);