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
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ emotion: mood, note: document.getElementById('personaPicHint')?.value || '',
                    plain: !!document.getElementById('personaPlain')?.checked }) });
            const d = await resp.json();
            if (!resp.ok) throw new Error(d.error || 'Could not make it.');
            let url = d.url;
            if (d.cut && window.Cutout) {  // ✂️ drawn on a plain colour: cut out here, the transparent one kept
                try { url = await sendCut(d.name, await Cutout.cutUrl(d.url)); }
                catch (err) { note.textContent = `Made, but the cut-out failed: ${err.message}`; }
            }
            fig.querySelector('img, span').outerHTML = `<img src="${url}?t=${Date.now()}" alt="">`;
            paintCuts();
        } finally { fig.classList.remove('working'); }
    }
    // ✂️ cut-outs of the persona's pictures (the original is kept on the server, so ↺ brings it back)
    let cutNames = [];
    async function sendCut(name, blob) {
        const fd = new FormData(); fd.append('target', 'persona'); fd.append('name', name); fd.append('file', blob, 'cut.png');
        const resp = await fetch(box.dataset.cut, { method: 'POST', headers: { 'X-CSRFToken': csrf }, body: fd });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.error || 'Could not save the cut-out.');
        cutNames = d.cut || cutNames;
        return d.url;
    }
    function paintCuts() {
        box.querySelectorAll('figure[data-mood]').forEach(fig => {
            const undo = fig.querySelector('.persona-uncut');
            if (undo) undo.hidden = !cutNames.includes(`persona_photo_${fig.dataset.mood}`);
        });
    }
    if (window.Cutout) fetch(`${box.dataset.cut}?target=persona`).then(r => r.json()).then(d => { cutNames = d.cut || []; paintCuts(); }).catch(() => {});
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
    // Each mood on its own: 📤 upload your own picture, ✨ make just this one (or ↻ redo it)
    box.querySelectorAll('figure[data-mood]').forEach(fig => {
        const mood = fig.dataset.mood, bar = document.createElement('div');
        bar.className = 'persona-pic-one';
        const label = () => has(mood) ? '↻' : '✨';
        bar.innerHTML = `<label title="Upload your own ${mood} picture">📤<input type="file" accept="image/png,image/jpeg,image/webp" hidden></label>` +
                        `<button type="button" title="Make just this one from the neutral picture">${label()}</button>` +
                        (window.Cutout ? `<button type="button" class="persona-cut" title="Cut out the background (free, in your browser)">✂️</button>` +
                                         `<button type="button" class="persona-uncut" title="Undo the cut-out" hidden>↺</button>` : '');
        fig.appendChild(bar);
        bar.querySelector('.persona-cut')?.addEventListener('click', async () => {
            const img = fig.querySelector('img');
            if (!img) { note.textContent = 'There is no picture there to cut out yet.'; return; }
            const blob = await Cutout.review(img.src.split('?')[0], { title: `Cut out your ${mood} picture` });
            if (!blob) return;
            try { img.src = `${await sendCut(`persona_photo_${mood}`, blob)}?t=${Date.now()}`; note.textContent = `✓ ${mood}: cut out.`; }
            catch (err) { note.textContent = err.message; }
            paintCuts();
        });
        bar.querySelector('.persona-uncut')?.addEventListener('click', async () => {
            const resp = await fetch(box.dataset.cut, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                body: JSON.stringify({ target: 'persona', name: `persona_photo_${mood}`, undo: true }) });
            const d = await resp.json().catch(() => ({}));
            if (!resp.ok) { note.textContent = d.error || 'Could not undo it.'; return; }
            cutNames = d.cut || [];
            const img = fig.querySelector('img');
            if (img) img.src = `${d.url}?t=${Date.now()}`;
            note.textContent = `✓ ${mood}: the original is back.`;
            paintCuts();
        });
        bar.querySelector('input').addEventListener('change', async (e) => {
            const file = e.target.files[0]; if (!file) return;
            const fd = new FormData(); fd.append('emotion', mood); fd.append('file', file);
            fig.classList.add('working');
            try {
                const resp = await fetch(box.dataset.url, { method: 'POST', headers: { 'X-CSRFToken': csrf }, body: fd });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || 'Could not upload it.');
                fig.querySelector('img, span').outerHTML = `<img src="${d.url}?t=${Date.now()}" alt="">`;
                note.textContent = `✓ Your ${mood} picture is saved.`;
                bar.querySelector('button').textContent = label();
            } catch (err) { note.textContent = err.message; }
            finally { fig.classList.remove('working'); }
        });
        bar.querySelector('button').addEventListener('click', async () => {
            if (mood !== 'neutral' && !has('neutral')) { note.textContent = 'Add or make the neutral picture first: the moods are made from it.'; return; }
            await run(null, [mood]);
            bar.querySelector('button').textContent = label();
        });
    });

    document.getElementById('personaMakeNeutral').addEventListener('click', e => {
        if (has('neutral') && !confirm('Replace your neutral picture with a new one?')) return;
        run(e.target, ['neutral']);
    });
    document.getElementById('personaMakeMoods').addEventListener('click', e => {
        if (!has('neutral')) { note.textContent = 'Add or make the neutral picture first: the moods are made from it.'; return; }
        run(e.target, ['happy', 'sad', 'angry', 'surprised', 'scared', 'confused', 'calm', 'scheming'].filter(m => !has(m)));
    });
})();
