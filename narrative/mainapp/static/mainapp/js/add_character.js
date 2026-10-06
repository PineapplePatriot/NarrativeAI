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

// Nano Banana: make the missing mood pictures from the neutral one, one request per mood
(function () {
    const box = document.getElementById('spriteMaker');
    if (!box) return;
    const MOODS = ['happy', 'sad', 'angry', 'surprised', 'scared', 'confused', 'calm', 'scheming'];
    // The image models OpenRouter offers right now (fetched once); the default is picked on the server
    fetch(box.dataset.models).then(r => r.json()).then(data => {
        const select = document.getElementById('spriteModel');
        const label = m => m.name;
        (data.models || []).forEach(m => {
            const o = document.createElement('option');
            o.value = m.id; o.textContent = label(m);
            if (m.id === data.default) { o.selected = true; select.options[0].textContent = `Default (${m.name})`; }
            select.appendChild(o);
        });
    }).catch(() => { /* the default still works */ });
    const status = document.getElementById('spriteStatus');
    const cookie = name => (document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '=')) || '').split('=')[1];
    const hasPicture = field => !!document.querySelector(`[data-field-name="${field}"] .file-preview img`);
    document.getElementById('makeSprites').onclick = async (e) => {
        const btn = e.currentTarget;
        const second = false;
        if (!hasPicture('photo_neutral')) { status.textContent = 'Add and save a neutral picture first.'; return; }
        const redo = document.getElementById('remakeSprites').checked;
        const todo = MOODS.filter(m => redo || !hasPicture(`photo_${m}`));
        if (!todo.length) { status.textContent = 'Every mood already has a picture.'; return; }
        btn.disabled = true;
        let made = 0;
        for (const mood of todo) {
            status.textContent = `Making “${mood}” (${made + 1} of ${todo.length})…`;
            try {
                const resp = await fetch(box.dataset.url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(cookie('csrftoken') || '') },
                    body: JSON.stringify({ emotion: mood, second, model: document.getElementById('spriteModel').value || null }),
                });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'Something went wrong.');
                const preview = document.querySelector(`[data-field-name="${data.field}"] .file-preview`);
                if (preview) preview.innerHTML = `<img src="${data.url}?v=${Date.now()}" alt="${mood}">`;
                made++;
            } catch (err) {
                status.textContent = `Stopped at “${mood}”: ${err.message}`;
                btn.disabled = false;
                return;
            }
        }
        status.textContent = `Done: ${made} new picture${made === 1 ? '' : 's'}. They're saved already.`;
        btn.disabled = false;
    };
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
