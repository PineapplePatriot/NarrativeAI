/* 🎭 More moods on the character's page (mainapp/sprites.py): pictures for moods beyond the nine built in, uploaded
   or drawn from the neutral picture by the image model; ✕ takes one away. */
(function () {
    const box = document.getElementById('moreMoods');
    if (!box) return;
    const $ = (id) => document.getElementById(id);
    const csrf = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
    const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    const status = (t, bad) => { $('mmStatus').textContent = t; $('mmStatus').classList.toggle('bad', !!bad); };
    function paint(d) {
        const moods = Object.entries(d.first || {});
        $('mmGrid').innerHTML = moods.length ? moods.map(([m, url]) => `<figure class="mm-item"><img src="${esc(url)}" alt="">
            <figcaption>${esc(m)}</figcaption><button type="button" class="mm-x" data-remove="${esc(m)}" title="Take it away">✕</button>
            ${window.Cutout ? `<button type="button" class="mm-cut" data-cut="${esc(m)}" data-url="${esc(url)}" title="Cut out the background (free, in your browser)">✂️</button>` : ''}</figure>`).join('')
            : '<p class="section-help">None yet.</p>';
        $('mmSuggest').innerHTML = (d.suggested || []).filter(m => !(m in (d.first || {}))).map(m => `<option value="${esc(m)}">`).join('');
    }
    async function load(init) {
        const resp = await fetch(box.dataset.url, init);
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.error || 'Something went wrong.');
        paint(d);
        return d;
    }
    $('mmFile').addEventListener('change', async () => {
        const file = $('mmFile').files[0], name = $('mmName').value.trim();
        $('mmFile').value = '';
        if (!file) return;
        if (!name) { status('Name the mood first, then upload.', true); return; }
        const body = new FormData();
        body.append('picture', file); body.append('emotion', name);
        status('Uploading…');
        try { await load({ method: 'POST', headers: { 'X-CSRFToken': csrf }, body }); $('mmName').value = ''; status(`✓ “${name}” added.`); }
        catch (e) { status(e.message, true); }
    });
    $('mmMake').addEventListener('click', async () => {
        const name = $('mmName').value.trim();
        if (!name) { status('Name the mood first.', true); return; }
        $('mmMake').disabled = true;
        status(`Drawing “${name}” from the neutral picture… (a few cents, on your key)`);
        try {
            const resp = await fetch(box.dataset.make, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                body: JSON.stringify({ emotion: name, note: document.getElementById('spriteNote')?.value || '',
                                       plain: !!document.getElementById('spritePlain')?.checked }) });
            const d = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(d.error || 'The picture maker failed.');
            if (d.cut && window.Cutout) await sendCut(d.name, await Cutout.cutUrl(d.url)).catch((err) => status(`Made, but the cut-out failed: ${err.message}`, true));
            await load(); $('mmName').value = ''; status(`✓ “${name}” made.`);
        } catch (e) { status(e.message, true); }
        finally { $('mmMake').disabled = false; }
    });
    // ✂️ an extra mood's cut-out, kept in its place (the original is remembered on the server)
    async function sendCut(name, blob) {
        const maker = document.getElementById('spriteMaker');
        const form = new FormData();
        form.append('target', 'character'); form.append('slug', maker.dataset.slug); form.append('name', name);
        form.append('file', blob, 'cut.png');
        const resp = await fetch(maker.dataset.cut, { method: 'POST', headers: { 'X-CSRFToken': csrf }, body: form });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.error || 'Could not save the cut-out.');
    }
    $('mmGrid').addEventListener('click', async (e) => {
        const c = e.target.closest('[data-cut]');
        if (c) {
            const blob = await Cutout.review(c.dataset.url.split('?')[0], { title: `Cut out “${c.dataset.cut}”` });
            if (!blob) return;
            try { await sendCut(`extra:${c.dataset.cut}`, blob); await load(); status(`✓ “${c.dataset.cut}” cut out.`); }
            catch (err) { status(err.message, true); }
            return;
        }
        const b = e.target.closest('[data-remove]');
        if (!b || !confirm(`Take away the “${b.dataset.remove}” picture?`)) return;
        try { await load({ method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ remove: b.dataset.remove }) }); }
        catch (err) { status(err.message, true); }
    });
    load().catch(() => { box.hidden = true; });
})();
