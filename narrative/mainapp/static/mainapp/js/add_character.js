document.addEventListener("DOMContentLoaded", function () {
    // "3 of 9 added" on the folded Sprites section; open it when a sprite has an error
    const spriteCount = document.getElementById('spriteCount');
    function countSprites() {
        const groups = [...document.querySelectorAll('.file-group')].filter(g => g.style.display !== 'none');
        const added = groups.filter(g => g.querySelector('.file-preview img')).length;
        if (spriteCount) spriteCount.textContent = `${added} of ${groups.length} added`;
    }
    const sprites = document.getElementById('spritesSection');
    if (sprites && [...sprites.querySelectorAll('.form-error')].some(e => e.textContent.trim())) sprites.open = true;

    document.querySelectorAll('.file-group').forEach(group => {
        const input = group.querySelector('input[type="file"]');
        const preview = group.querySelector('.file-preview');

        input.addEventListener('change', function () {
            preview.innerHTML = '';
            if (this.files && this.files[0] && this.files[0].type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    preview.appendChild(img);
                    countSprites();
                };
                reader.readAsDataURL(this.files[0]);
            } else {
                preview.textContent = '📷';
            }
        });
    });
    const isMultCheckbox = document.getElementById('id_is_mult');
    const fileGroups = document.querySelectorAll('.file-group');
    const secondVoiceContainer = document.getElementById('second-char-voice-container');

    function toggleSecondCharFields() {
        if (!isMultCheckbox) return;

        const isChecked = isMultCheckbox.checked;

        fileGroups.forEach(group => {
            const fieldName = group.getAttribute('data-field-name');

            if (fieldName && fieldName.includes('second')) {
                if (isChecked) {
                    group.style.display = 'flex';
                } else {
                    group.style.display = 'none';
                }
            }
        });

        if (secondVoiceContainer) {
            secondVoiceContainer.style.display = isChecked ? 'block' : 'none';
        }
        countSprites();
    }

    if (isMultCheckbox) {
        toggleSecondCharFields();
        isMultCheckbox.addEventListener('change', toggleSecondCharFields);
    }
    countSprites();
});

// Arriving from "Add pictures" (…#spritesSection): open that section and bring it into view
if (location.hash === '#spritesSection') {
    const sprites = document.getElementById('spritesSection');
    if (sprites) { sprites.open = true; sprites.scrollIntoView({ block: 'start' }); }
}

// Nano Banana: the neutral picture from the description, then the missing moods from it, one request each
(function () {
    const box = document.getElementById('spriteMaker');
    if (!box) return;
    const MOODS = ['happy', 'sad', 'angry', 'surprised', 'scared', 'confused', 'calm', 'scheming'];
    // The image models OpenRouter offers right now (fetched once); the default is picked on the server
    fetch(box.dataset.models).then(r => r.json()).then(data => {
        const select = document.getElementById('spriteModel');
        (data.models || []).forEach(m => {
            const o = document.createElement('option');
            o.value = m.id; o.textContent = m.name;
            if (m.id === data.default) { o.selected = true; select.options[0].textContent = `Default (${m.name})`; }
            select.appendChild(o);
        });
    }).catch(() => { /* the default still works */ });
    const status = document.getElementById('spriteStatus');
    const cookie = name => (document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '=')) || '').split('=')[1];
    const group = field => document.querySelector(`[data-field-name="${field}"]`);
    const hasPicture = field => !!(group(field) && group(field).querySelector('.file-preview img'));
    const unsaved = field => !!(group(field) && group(field).querySelector('input[type=file]')?.files.length);
    // A second character: choose whose pictures to make
    const mult = document.getElementById('id_is_mult'), forWrap = document.getElementById('spriteForWrap');
    const secondName = document.getElementById('id_second_name'), nameWrap = document.getElementById('secondNameWrap');
    const showFor = () => {
        forWrap.hidden = !(mult && mult.checked);
        if (nameWrap) nameWrap.hidden = !(mult && mult.checked);
        const opt = document.querySelector('#spriteFor option[value="1"]');  // "make pictures for": their name
        if (opt) opt.textContent = (secondName && secondName.value.trim()) || 'The second character';
    };
    if (secondName) secondName.addEventListener('input', showFor);
    if (mult) { mult.addEventListener('change', showFor); showFor(); }
    const prefix = () => (!forWrap.hidden && document.getElementById('spriteFor').value) ? 'photo_second' : 'photo';

    async function make(mood, second = prefix() === 'photo_second') {
        const resp = await fetch(box.dataset.url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(cookie('csrftoken') || '') },
            body: JSON.stringify({ emotion: mood, second,
                                   model: document.getElementById('spriteModel').value || null }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Something went wrong.');
        const preview = group(data.field)?.querySelector('.file-preview');
        if (preview) preview.innerHTML = `<img src="${data.url}?v=${Date.now()}" alt="${mood}">`;
    }
    const busy = on => ['makeNeutral', 'makeSprites'].forEach(id => { document.getElementById(id).disabled = on; });

    document.getElementById('makeNeutral').onclick = async () => {
        const field = `${prefix()}_neutral`;
        if (unsaved(field)) { status.textContent = 'You picked a neutral picture: press Save to keep it (no need to make one).'; return; }
        if (hasPicture(field) && !document.getElementById('remakeSprites').checked) {
            status.textContent = 'There is a neutral picture already. Tick "also redo" to replace it.'; return;
        }
        busy(true);
        status.textContent = 'Drawing the neutral picture from the description… (about 15 seconds)';
        try {
            await make('neutral');
            status.textContent = "Done, and saved. Like it? Now make the moods from it (step 2).";
        } catch (err) { status.textContent = `Couldn't make it: ${err.message}`; }
        busy(false);
    };

    document.getElementById('makeSprites').onclick = async () => {
        const p = prefix();
        if (unsaved(`${p}_neutral`)) { status.textContent = 'Press Save first: the moods are made from the saved neutral picture.'; return; }
        if (!hasPicture(`${p}_neutral`)) { status.textContent = 'Step 1 first: the moods are made from the neutral picture.'; return; }
        const redo = document.getElementById('remakeSprites').checked;
        const todo = MOODS.filter(m => redo || !hasPicture(`${p}_${m}`));
        if (!todo.length) { status.textContent = 'Every mood already has a picture.'; return; }
        busy(true);
        let made = 0;
        for (const mood of todo) {
            status.textContent = `Making “${mood}” (${made + 1} of ${todo.length})…`;
            try { await make(mood); made++; }
            catch (err) { status.textContent = `Stopped at “${mood}”: ${err.message}`; busy(false); return; }
        }
        status.textContent = `Done: ${made} new picture${made === 1 ? '' : 's'}. They're saved already.`;
        busy(false);
    };

    // ↻ next to one mood picture: redraw just that one (a few cents), when only one came out wrong
    function addRedo(groupEl) {
        const name = groupEl.dataset.fieldName || '';
        const m = name.match(/^(photo|photo_second)_(\w+)$/);
        if (!m || !MOODS.includes(m[2]) || groupEl.querySelector('.sprite-redo')) return;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'sprite-redo'; b.textContent = '↻ Redo';
        b.title = `Draw “${m[2]}” again from the neutral picture (a few cents)`;
        b.onclick = async () => {
            if (!hasPicture(`${m[1]}_neutral`)) { status.textContent = 'The moods are made from the neutral picture: add that first.'; return; }
            b.disabled = true; busy(true);
            status.textContent = `Drawing “${m[2]}” again… (about 15 seconds)`;
            try { await make(m[2], m[1] === 'photo_second'); status.textContent = `“${m[2]}” redone and saved.`; }
            catch (err) { status.textContent = `Couldn't redo “${m[2]}”: ${err.message}`; }
            b.disabled = false; busy(false);
        };
        (groupEl.querySelector('.file-preview') || groupEl).after(b);
    }
    document.querySelectorAll('[data-field-name^="photo"]').forEach(addRedo);
})();

// The card's own text rules: switch each on or off right away
document.querySelectorAll('[data-card-rule]').forEach(box => box.addEventListener('change', async () => {
    const wrap = box.closest('.card-rules');
    const status = document.getElementById('cardRuleStatus');
    const cookie = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken='));
    try {
        const resp = await fetch(wrap.dataset.url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cookie ? decodeURIComponent(cookie.slice(10)) : '' },
            body: JSON.stringify({ id: box.dataset.cardRule, enabled: box.checked }),
        });
        if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).error || 'Could not save.');
        status.textContent = 'Saved.';
    } catch (err) { box.checked = !box.checked; status.textContent = err.message; }
}));

// 🗑 Delete this character (edit page): asks first, then back to the list
document.getElementById('deleteCharacterBtn')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget, chats = Number(btn.dataset.chats) || 0;
    const ok = await NADialog.confirm(`Delete ${btn.dataset.name}${chats ? ` and ${chats === 1 ? 'their chat' : `all ${chats} of their chats`}` : ''}? `
        + 'Their pictures go too. Their worldbook stays on the Worldbooks page. This can\'t be undone.',
        { title: '🗑 Delete character', ok: 'Delete', danger: true });
    if (!ok) return;
    const token = (document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken=')) || '').split('=')[1];
    const resp = await fetch(btn.dataset.deleteUrl, { method: 'POST', headers: { 'X-CSRFToken': decodeURIComponent(token || '') } });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) window.location.href = data.url;
    else NADialog.alert('Could not delete it. Try again.');
});
