const photoInput = document.getElementById("id_photo");
const photoPreview = document.getElementById("photo-preview");

photoInput.addEventListener("change", function () {
    const file = this.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
            photoPreview.src = e.target.result;
            photoPreview.hidden = false;
            const initial = document.getElementById("photo-initial");
            if (initial) initial.remove();
        };
        reader.readAsDataURL(file);
    }
});
// Pictures of their persona: the neutral one from the description, the moods from it (mainapp views.persona_sprite)
(function () {
    const box = document.getElementById('personaPics');
    if (!box) return;
    const note = document.getElementById('personaPicNote');
    const csrf = (document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken=')) || '').split('=')[1];
    const has = mood => !!box.querySelector(`[data-mood="${mood}"] img`);
    async function make(mood) {
        const fig = box.querySelector(`[data-mood="${mood}"]`);
        fig.classList.add('working');
        try {
            const resp = await fetch(box.dataset.url, { method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ emotion: mood }) });
            const d = await resp.json();
            if (!resp.ok) throw new Error(d.error || 'Could not make it.');
            fig.querySelector('img, span').outerHTML = `<img src="${d.url}?t=${Date.now()}" alt="">`;
        } finally { fig.classList.remove('working'); }
    }
    async function run(btn, moods) {
        const buttons = document.querySelectorAll('.persona-pic-actions button');
        buttons.forEach(b => { b.disabled = true; });
        try {
            for (let i = 0; i < moods.length; i++) {
                note.textContent = `Making ${moods[i]} (${i + 1} of ${moods.length})… about 15 seconds each.`;
                await make(moods[i]);
            }
            note.textContent = moods.length ? '✓ Done. They show in your chats from the next reply.' : 'All moods are there already.';
        } catch (e) { note.textContent = e.message; }
        finally { buttons.forEach(b => { b.disabled = false; }); }
    }
    document.getElementById('personaMakeNeutral').addEventListener('click', e => {
        if (has('neutral') && !confirm('Replace your neutral picture with a new one?')) return;
        run(e.target, ['neutral']);
    });
    document.getElementById('personaMakeMoods').addEventListener('click', e => {
        if (!has('neutral')) { note.textContent = 'Add or make the neutral picture first: the moods are made from it.'; return; }
        run(e.target, ['happy', 'sad', 'angry', 'surprised', 'scared', 'confused', 'calm', 'scheming'].filter(m => !has(m)));
    });
})();
