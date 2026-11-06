/* Quick setup: a short form; every part can be handed to Bulba (a panel beside the form). */
const $ = id => document.getElementById(id);
const data = JSON.parse($('quick-data').textContent);
const cookie = name => decodeURIComponent((document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '=')) || '').split('=')[1] || '');

// Chat memory: the same slider and cost estimate as the Extras page (static/js/costs.js)
const steps = data.window ? NACosts.steps(data.window.max) : [];
function memory() {
    if (!data.window) return;
    const size = steps[Number($('chatContext').value)] || steps[0];
    $('memoryValue').textContent = NACosts.memory(size);
    $('memoryCost').textContent = NACosts.chat((data.prices || {}).chat, size);
}
if (data.window) {
    $('memoryModel').textContent = data.window.model || 'your chat model';
    $('chatContext').max = steps.length - 1;
    $('chatContext').value = NACosts.nearest(steps, data.window.value);
    $('chatContext').addEventListener('input', memory);
    memory();
} else {
    $('qMemory').hidden = true;
}

// Import a card: it becomes the picked character (a card without a picture opens its Sprites section instead)
const importForm = $('qImport');
importForm.querySelector('input[type=file]').addEventListener('change', async (e) => {
    const input = e.target, note = $('qImportNote');
    if (!input.files.length) return;
    note.hidden = false;
    note.textContent = 'Reading ' + input.files[0].name + '…';
    try {
        const resp = await fetch(importForm.action, { method: 'POST', body: new FormData(importForm) });
        const d = await resp.json();
        if (!resp.ok) throw new Error(d.error || 'Import failed.');
        note.textContent = 'Imported ' + d.name + (d.notes.length ? '. ' + d.notes.join(' ') : '.');
        const slug = (d.edit_url || '').split('/').filter(Boolean).pop();
        await save(false);  // keep what's filled in so far
        setTimeout(() => { window.location.href = QUICK.url + (slug ? '?character=' + encodeURIComponent(slug) : ''); }, 1200);
    } catch (err) { note.textContent = err.message; }
    input.value = '';
});

// Bulba beside the form, already asked about that part (nothing is sent until they press Send)
const drawer = $('qDrawer'), frame = $('qFrame');
document.querySelectorAll('[data-ask]').forEach(btn => btn.addEventListener('click', async () => {
    await save(false);  // Bulba sees what's already filled in
    const url = QUICK.bulba + '&draft=' + encodeURIComponent(btn.dataset.ask);
    if (!frame.src) frame.src = url;
    else frame.contentWindow.postMessage({ bulbaDraft: btn.dataset.ask }, window.location.origin);
    drawer.hidden = false;
}));
window.addEventListener('message', (e) => {
    if (e.origin !== window.location.origin || !e.data || e.data.quickBulba !== 'close') return;
    drawer.hidden = true;
    window.location.reload();  // shows what Bulba applied (persona, character, style)
});

async function save(go) {
    const body = {
        starter: (document.querySelector('input[name=starter]:checked') || {}).value || '',
        persona_name: $('personaName').value, persona_description: $('personaDescription').value,
        character: (document.querySelector('input[name=character]:checked') || {}).value || '',
        mature: $('qMature').checked,
    };
    if (data.window) body.chat_context = steps[Number($('chatContext').value)];
    $('qError').hidden = true;
    try {
        const resp = await fetch(QUICK.url, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const d = await resp.json();
        if (!resp.ok) throw new Error(d.error || 'Could not save.');
        if (go) {
            if (!d.url) throw new Error('Pick, make or import a character first (step 4).');
            window.location.href = d.url;
        }
    } catch (err) { $('qError').textContent = err.message; $('qError').hidden = false; }
}
$('qStart').addEventListener('click', () => save(true));

// 🔞: asks once that they're an adult
$('qMature').addEventListener('change', (e) => {
    if (e.target.checked && !confirm('Adult scenes are for adults only. Are you 18 or older?')) e.target.checked = false;
});
