/* 🖼 The Splat Gallery: your saved walls (rename, share, delete, keep painting, download) and everyone's shared
   ones (like, download). Each piece is drawn here from its splats (splat_art.js), fetched when its card scrolls
   into view. The server: mainapp/tomatoes.py and views.tomato_art*. */
(function () {
    const S = window.NASplat, root = document.getElementById('gallery');
    if (!S || !root) return;
    const $ = (id) => document.getElementById(id);
    const CSRF = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';
    const urlOne = (id) => root.dataset.one.replace(/0\/$/, `${id}/`);
    const urlLike = (id) => root.dataset.like.replace(/0\/like\/$/, `${id}/like/`);
    const send = (url, method, body) => fetch(url, { method, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() }, body: body ? JSON.stringify(body) : undefined })
        .then(async r => { const out = await r.json().catch(() => ({})); if (!r.ok) throw new Error(out.error || 'That did not work. Try again.'); return out; });
    let scope = 'mine', sort = 'new', page = 1;
    const full = {};  // id → the piece with its splats

    async function piece(id) {
        if (!full[id]) full[id] = await send(urlOne(id), 'GET');
        return full[id];
    }
    const seen = new IntersectionObserver((entries) => entries.forEach(async (en) => {
        if (!en.isIntersecting) return;
        seen.unobserve(en.target);
        const cv = en.target, art = await piece(cv.dataset.id).catch(() => null);
        if (art) { const draw = () => S.paint(cv.getContext('2d'), art, draw); draw(); }
    }), { rootMargin: '200px' });

    function card(item) {
        const el = document.createElement('article');
        el.className = 'gal-card';
        el.innerHTML = `<canvas width="600" height="375" aria-label="The piece"></canvas>
            <div class="gal-body"><div class="gal-title"></div><div class="gal-meta"></div><div class="gal-actions"></div></div>`;
        const cv = el.querySelector('canvas');
        cv.dataset.id = item.id;
        seen.observe(cv);
        cv.addEventListener('click', () => view(item));
        el.querySelector('.gal-title').textContent = item.title || 'Untitled';
        const when = new Date(item.created).toLocaleDateString();
        el.querySelector('.gal-meta').textContent = `${item.mine ? '' : 'by ' + item.artist + ' · '}${when} · ${item.count.toLocaleString()} splats`;
        const acts = el.querySelector('.gal-actions');
        const btn = (label, fn, cls = '') => { const b = document.createElement('button'); b.type = 'button'; b.className = 'na-btn ' + cls; b.textContent = label; b.addEventListener('click', fn); acts.appendChild(b); return b; };
        if (item.mine) {
            const lab = document.createElement('label');
            lab.className = 'gal-share';
            lab.innerHTML = '<input type="checkbox"> <span>Shared</span>';
            const box = lab.querySelector('input');
            box.checked = item.shared;
            box.addEventListener('change', async () => {
                try { const out = await send(urlOne(item.id), 'POST', { shared: box.checked }); item.shared = out.shared; }
                catch (err) { box.checked = !box.checked; NADialog.alert(err.message); }
            });
            acts.appendChild(lab);
            if (item.shared) lab.title = `${item.likes} ❤`;
            btn('✎', async () => {
                const t = await NADialog.prompt('A new name:', item.title, { title: 'Rename', ok: 'Save' });
                if (t === null) return;
                try { const out = await send(urlOne(item.id), 'POST', { title: t }); item.title = out.title; el.querySelector('.gal-title').textContent = out.title || 'Untitled'; }
                catch (err) { NADialog.alert(err.message); }
            }).title = 'Rename';
            btn('🎨', () => keepPainting(item)).title = 'Keep painting it on the wall';
        } else {
            const like = btn(`❤ ${item.likes}`, async () => {
                try { const out = await send(urlLike(item.id), 'POST'); item.likes = out.likes; item.liked = out.liked; paintLike(); }
                catch (err) { NADialog.alert(err.message); }
            }, 'gal-like');
            const paintLike = () => { like.textContent = `❤ ${item.likes}`; like.classList.toggle('on', !!item.liked); like.setAttribute('aria-pressed', String(!!item.liked)); };
            paintLike();
        }
        btn('⬇', () => downloadOf(item)).title = 'Download';
        if (item.mine) btn('🗑', async () => {
            if (!await NADialog.confirm(`Delete “${item.title || 'Untitled'}” for good?`, { title: 'Delete', ok: 'Delete it', danger: true })) return;
            try { await send(urlOne(item.id), 'DELETE'); el.remove(); if (!$('galGrid').children.length) empty(); }
            catch (err) { NADialog.alert(err.message); }
        }).title = 'Delete';
        return el;
    }

    async function downloadOf(item) {
        const art = await piece(item.id);
        const cv = document.createElement('canvas');
        cv.width = S.W; cv.height = S.H;
        const go = () => {
            S.paint(cv.getContext('2d'), art, go);
            const a = document.createElement('a');
            a.download = `${(item.title || 'splat-wall').replace(/[^\w\- ]+/g, '').trim() || 'splat-wall'}.png`;
            a.href = S.signed(cv, art.bg).toDataURL('image/png');
            a.click();
        };
        go();
    }
    async function keepPainting(item) {
        let current = {};
        try { current = JSON.parse(localStorage.getItem('na-tomato-wall') || '{}'); } catch (e) { /* none */ }
        if ((current.splats || []).length && !await NADialog.confirm(
            'This replaces what is on your wall in the Pit right now. Save that first if you want to keep it.',
            { title: 'Keep painting', ok: 'Replace the wall' })) return;
        const art = await piece(item.id);
        try { localStorage.setItem('na-tomato-wall', JSON.stringify(Object.assign(current, { bg: art.bg, splats: art.splats }))); }
        catch (e) { NADialog.alert('This browser would not keep it (private window?).'); return; }
        location.href = root.dataset.wall;
    }
    async function view(item) {
        const art = await piece(item.id);
        const big = $('galBig');
        const draw = () => S.paint(big.getContext('2d'), art, draw);
        draw();
        $('galBigTitle').textContent = item.title || 'Untitled';
        $('galBigBy').textContent = item.mine ? '' : `by ${item.artist}`;
        $('galView').hidden = false;
        $('galClose').focus();
    }
    const close = () => { $('galView').hidden = true; };
    $('galClose').addEventListener('click', close);
    $('galView').addEventListener('click', (e) => { if (e.target === $('galView')) close(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

    function empty() {
        $('galEmpty').hidden = false;
        $('galEmpty').textContent = scope === 'mine'
            ? 'Nothing saved yet. Paint a wall in the Pit and press “Save to gallery”.'
            : 'Nobody has shared anything yet. Be the first.';
    }
    async function load(more = false) {
        page = more ? page + 1 : 1;
        if (!more) { $('galGrid').innerHTML = ''; $('galEmpty').hidden = true; }
        $('galMore').hidden = true;
        try {
            const out = await send(`${root.dataset.list}?scope=${scope}&sort=${sort}&page=${page}`, 'GET');
            out.items.forEach(it => $('galGrid').appendChild(card(it)));
            $('galMore').hidden = !out.more;
            if (!$('galGrid').children.length) empty();
        } catch (err) { $('galEmpty').hidden = false; $('galEmpty').textContent = err.message; }
    }
    function paintTabs() {
        document.querySelectorAll('#galScope [data-scope]').forEach(b => { b.classList.toggle('on', b.dataset.scope === scope); b.setAttribute('aria-selected', String(b.dataset.scope === scope)); });
        document.querySelectorAll('#galSort [data-sort]').forEach(b => b.classList.toggle('on', b.dataset.sort === sort));
        $('galSort').hidden = scope !== 'all';
    }
    $('galScope').addEventListener('click', (e) => { const b = e.target.closest('[data-scope]'); if (!b) return; scope = b.dataset.scope; paintTabs(); load(); });
    $('galSort').addEventListener('click', (e) => { const b = e.target.closest('[data-sort]'); if (!b) return; sort = b.dataset.sort; paintTabs(); load(); });
    $('galMore').addEventListener('click', () => load(true));
    if (location.hash === '#everyone') scope = 'all';
    paintTabs();
    load();
})();
