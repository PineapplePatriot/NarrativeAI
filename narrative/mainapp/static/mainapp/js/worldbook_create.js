const STORE_KEY = 'worldbooks';
function loadStore() { try { return JSON.parse(localStorage.getItem(STORE_KEY) || '[]'); } catch { return [] } }
function saveStore(arr) { localStorage.setItem(STORE_KEY, JSON.stringify(arr)); }
function slug(s) { return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''); }

const seedList = document.getElementById('seedList');
const addSeedBtn = document.getElementById('addSeedBtn');
const seedTpl = document.getElementById('seedTpl');
const createBtn = document.getElementById('createBtn');

addSeedBtn.onclick = () => { seedList.appendChild(seedTpl.content.cloneNode(true)); };

// === Збір даних Seed Entries ===
function gatherEntries() {
    const entries = [];
    seedList.querySelectorAll('.entry').forEach((el, i) => {
        const key = el.querySelector('input[placeholder="npc.dottore"]');
        const tags = el.querySelector('input[placeholder="character, science"]');
        const scope = el.querySelector('select');
        const prio = el.querySelector('input[type="number"][min="0"][max="100"]');
        const weight = el.querySelector('input[type="number"][min="0"][max="1"]');
        const enabled = el.querySelector('input[type="checkbox"]');
        const val = el.querySelector('textarea.valueField');

        entries.push({
            id: i + 1,
            key: key.value.trim(),
            tags: tags.value.split(',').map(s => s.trim()).filter(Boolean),
            scope: scope.value,
            priority: Number(prio.value) || 0,
            weight: Number(weight.value) || 0,
            enabled: Boolean(enabled.checked),
            value: val.value
        });
    });
    return entries;
}

// === CSRF ===
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

// === Створення worldbook ===
createBtn.onclick = () => {
    const title = document.getElementById('title').value.trim();
    const desc = document.getElementById('desc').value.trim();
    if (!title) { alert('Title is required'); return; }
    const id = slug(title);
    const payload = { id, title, description: desc, entries: gatherEntries(), updatedAt: Date.now() };

    fetch("/main/worldbook_create/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken
        },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(data => {
            console.log("Response from server:", data);
            alert("Worldbook successfully created!");
            window.location.href = '/main/worldbook_list/';
        })
        .catch(err => { console.error("Помилка при відправці:", err); });
};