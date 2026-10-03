const titleEl = document.getElementById('title');
const descEl = document.getElementById('desc');
const importFile = document.getElementById('importFile');
const importInfo = document.getElementById('importInfo');
const createBtn = document.getElementById('createBtn');

let imported = null;

function getCookie(name) {
    const match = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

importFile.addEventListener('change', async () => {
    imported = null;
    const file = importFile.files[0];
    if (!file) return;
    try {
        imported = JSON.parse(await file.text());
        // Prefill the title from the file if the user has not typed one
        const name = imported.title || imported.name || imported.data?.character_book?.name || imported.data?.name
            || file.name.replace(/\.json$/i, '');
        if (!titleEl.value.trim()) titleEl.value = name;
        const entries = imported.entries || imported.data?.character_book?.entries || imported.character_book?.entries || [];
        const count = Array.isArray(entries) ? entries.length : Object.keys(entries).length;
        importInfo.textContent = `Found ${count} entr${count === 1 ? 'y' : 'ies'} in “${file.name}”.`;
    } catch (err) {
        importInfo.textContent = `Could not read “${file.name}” as JSON: ${err.message}`;
    }
});

createBtn.onclick = async () => {
    const title = titleEl.value.trim();
    if (!title) { alert('Title is required'); return; }
    createBtn.disabled = true;
    try {
        const resp = await fetch('/main/worldbook_create/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ title, description: descEl.value.trim(), import: imported }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.message || `HTTP ${resp.status}`);
        window.location.href = data.url;
    } catch (err) {
        alert('Could not create the worldbook: ' + err.message);
        createBtn.disabled = false;
    }
};
