/* The Tomato Pit (the secret page): throw as many as you like, pick a skin, see achievements, share a card.
   The throwing, skins and achievements live in static/js/tomato.js (loaded by the top bar). */
(function () {
    const T = window.NATomato;
    const $ = id => document.getElementById(id);
    const many = (s) => s.many || (/o$/.test(s.name) ? s.name + 'es' : s.name + 's');
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    if (!T) return;
    T.found();

    // Throwing: a click or tap throws from where it happened; holding Space keeps throwing
    const field = $('pitField');
    field.addEventListener('pointerdown', (e) => { e.preventDefault(); T.throwOne({ x: e.clientX, y: e.clientY }); });
    function throwFromField() {
        const r = $('pitAmmo').getBoundingClientRect();
        T.throwOne({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    }
    const typing = e => e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
    document.addEventListener('keydown', (e) => {
        if (typing(e) || !(e.code === 'Space' || (e.key === 'Enter' && e.target === field))) return;
        e.preventDefault();
        throwFromField();  // held down, the key repeats: so does the throwing
    });
    document.addEventListener('keyup', (e) => { if (e.code === 'Space' && !typing(e)) e.preventDefault(); });  // no extra click

    // Throws per second, for the bragging
    const stamps = [];
    let lastCount = T.data().count;
    T.onChange((d) => { if (d.count > lastCount) stamps.push(Date.now()); lastCount = d.count; });  // throws, not syncs
    setInterval(() => {
        const now = Date.now();
        while (stamps.length && now - stamps[0] > 3000) stamps.shift();
        $('pitRate').textContent = stamps.length ? `${(stamps.length / 3).toFixed(1)} per second` : '';
    }, 500);

    function paint() {
        const d = T.data(), s = T.skin();
        $('pitCount').textContent = d.count.toLocaleString();
        if ($('sumTotal')) $('sumTotal').textContent = d.count.toLocaleString();
        $('pitAmmo').textContent = s.emoji;
        $('pitAmmo').style.filter = s.filter || '';
        const open = T.SKINS.filter(T.unlocked);
        $('pitSkinCount').textContent = `${open.length} of ${T.SKINS.length}`;
        const kinds = [...new Set(T.SKINS.map(x => x.kind))];
        $('pitSkins').innerHTML = kinds.map(kind => `<h3>${esc(kind)}</h3><div class="pit-skins">${T.SKINS.filter(x => x.kind === kind).map(x => {
            const ok = T.unlocked(x);
            const how = x.prize ? 'Win it from the Sauce-o-Matic' : x.ach ? (T.ACHIEVEMENTS.find(a => a.id === x.ach) || {}).name : `${x.at.toLocaleString()} throws`;
            return `<button type="button" class="pit-skin${x.id === s.id ? ' on' : ''}" data-skin="${x.id}" ${ok ? '' : 'disabled'}
                title="${esc(ok ? (x.note || x.name) : 'Locked: ' + how)}"><span class="e" style="${x.filter ? 'filter:' + x.filter : ''}">${ok ? x.emoji : '❔'}</span>
                ${esc(ok ? x.name : '???')}<small>${esc(ok ? (x.note ? x.note : '') : how)}</small></button>`;
        }).join('')}</div>`).join('');
        const got = T.ACHIEVEMENTS.filter(a => d.ach[a.id]);
        $('pitAchCount').textContent = `${got.length} of ${T.ACHIEVEMENTS.length}`;
        $('pitAch').innerHTML = T.ACHIEVEMENTS.map(a => {
            const got = d.ach[a.id];
            if (a.secret && !got) return '<li class="secret"><b>👻 Secret</b><small>Keep throwing.</small></li>';
            return `<li class="${got ? 'got' : ''}"><b>${got ? (a.secret ? '👻' : '🏅') : '🔒'} ${esc(a.name)}</b>
                <small>${esc(a.about)}</small></li>`;
        }).join('');
        card();
    }
    $('pitSkins').addEventListener('click', (e) => {
        const b = e.target.closest('[data-skin]');
        if (b && !b.disabled) T.pick(b.dataset.skin);
    });

    // The share card: count, skin, best achievement, the app's name
    let cardTimer = null;
    function card() {
        clearTimeout(cardTimer);
        cardTimer = setTimeout(drawCard, 250);  // not on every single throw
    }
    // Text that wraps inside `maxW`, at most `lines` lines (the last one ends in … if it had to be cut)
    function wrap(g, text, x, y, maxW, lineH, lines) {
        const words = String(text).split(/\s+/);
        let line = '', n = 0;
        for (let i = 0; i < words.length; i++) {
            const next = line ? line + ' ' + words[i] : words[i];
            if (g.measureText(next).width <= maxW || !line) { line = next; continue; }
            if (n === lines - 1) { line += '…'; break; }
            g.fillText(line, x, y + n * lineH);
            n++;
            line = words[i];
        }
        if (line) g.fillText(line, x, y + n * lineH);
        return y + (n + 1) * lineH;
    }
    const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    const EMOJI = '"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
    function drawCard() {
        const d = T.data(), s = T.skin(), c = $('pitCard'), g = c.getContext('2d');
        const W = 1200, H = 630, X = 430, MAXW = W - X - 70;
        const bg = g.createLinearGradient(0, 0, W, H);
        bg.addColorStop(0, '#1a1027');
        bg.addColorStop(1, '#2b0f14');
        g.fillStyle = bg;
        g.fillRect(0, 0, W, H);
        // a few soft splats in the skin's colour, kept faint so the text stays readable
        let seed = d.count + 7;
        const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
        g.globalAlpha = .1;
        g.fillStyle = s.color;
        for (let i = 0; i < 12; i++) {
            g.beginPath();
            g.arc(rnd() * W, rnd() * H, 20 + rnd() * 70, 0, Math.PI * 2);
            g.fill();
        }
        g.globalAlpha = 1;
        // the skin, big, on a glow
        const glow = g.createRadialGradient(215, 300, 10, 215, 300, 190);
        glow.addColorStop(0, /^#[0-9a-f]{6}$/i.test(s.color) ? s.color + '55' : 'rgba(255, 255, 255, .12)');
        glow.addColorStop(1, 'transparent');
        g.fillStyle = glow;
        g.fillRect(0, 80, 430, 440);
        g.textBaseline = 'middle';
        g.textAlign = 'center';
        g.font = `210px ${EMOJI}`;
        g.filter = s.filter || 'none';
        g.fillText(s.emoji, 215, 300);
        g.filter = 'none';
        g.textAlign = 'left';
        g.textBaseline = 'alphabetic';
        g.shadowColor = 'rgba(0, 0, 0, .45)';
        g.shadowBlur = 10;
        g.fillStyle = '#f2b72c';
        g.font = `700 26px ${FONT}`;
        g.fillText('THE TOMATO PIT', X, 130);
        g.fillStyle = '#ffffff';
        g.font = `800 112px ${FONT}`;
        g.fillText(d.count.toLocaleString(), X, 240);
        g.fillStyle = '#f3e8e8';
        g.font = `600 38px ${FONT}`;
        let y = wrap(g, `${(d.count === 1 ? s.name : many(s)).toLowerCase()} thrown at Narrative AI while waiting for a reply.`,
                     X, 300, MAXW, 48, 2);
        const best = [...T.ACHIEVEMENTS].reverse().find(a => d.ach[a.id] && a.id !== 'first' && a.id !== 'pit')
            || T.ACHIEVEMENTS.find(a => d.ach[a.id]);
        if (best) {
            y += 22;
            g.fillStyle = '#f2b72c';
            g.font = `700 32px ${FONT}`;
            g.fillText(`🏅 ${best.name}`, X, y);
            g.fillStyle = 'rgba(255, 255, 255, .72)';
            g.font = `500 26px ${FONT}`;
            wrap(g, best.about, X, y + 38, MAXW, 34, 2);
        }
        g.shadowBlur = 0;
        g.fillStyle = 'rgba(255, 255, 255, .5)';
        g.font = `500 24px ${FONT}`;
        const open = T.SKINS.filter(T.unlocked).length;
        g.fillText(`${open}/${T.SKINS.length} skins  ·  best ${d.best10 || 0} throws in 10 seconds`, 70, H - 48);
        try { $('pitDownload').href = c.toDataURL('image/png'); } catch (e) { /* a locked-down browser: no download */ }
    }
    $('pitShare').addEventListener('click', async () => {
        drawCard();
        const c = $('pitCard');
        const text = `I've thrown ${T.data().count.toLocaleString()} ${many(T.skin()).toLowerCase()} at Narrative AI while waiting. 🍅`;
        try {
            const blob = await new Promise(r => c.toBlob(r, 'image/png'));
            const file = new File([blob], 'tomato-pit.png', { type: 'image/png' });
            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                await navigator.share({ files: [file], text });
                return;
            }
        } catch (e) { if (e && e.name === 'AbortError') return; }
        try { await navigator.clipboard.writeText(text); T.toast('Text copied', 'Download the picture and post it with it.'); }
        catch (e) { $('pitDownload').click(); }
    });

    T.onChange(paint);
    paint();
})();

/* 🎨 The splat wall: throws land where you tap and stay; dragging paints a line of them, with no gaps. Kept in
   this browser (a list of splats, drawn by splat_art.js), and saved to the gallery on request (mainapp/tomatoes.py).
   Painting counts nowhere: not the total, not the leaderboard (a golden splat can still show up, just for looks). Undo and Redo
   take back a whole stroke (or a whole wipe). */
(function () {
    const T = window.NATomato, S = window.NASplat, c = document.getElementById('wall');
    if (!T || !S || !c) return;
    const $ = (id) => document.getElementById(id);
    const g = c.getContext('2d'), W = S.W, H = S.H, KEY = 'na-tomato-wall', MAX = 4000, PER_MOVE = 8;
    let wall = { bg: 'night', size: 38, emoji: true, shape: 'splat', splats: [] };
    try { wall = Object.assign(wall, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) { /* a fresh wall */ }
    if (!Array.isArray(wall.splats)) wall.splats = [];
    const save = () => { try { localStorage.setItem(KEY, JSON.stringify(wall)); } catch (e) { wall.splats = wall.splats.slice(-1000); } };
    let saveTimer = null;
    const saveSoon = () => { clearTimeout(saveTimer); saveTimer = setTimeout(save, 600); };
    const undo = [], redo = [];  // actions: {add: [splats]} or {wipe: [[index, splat]...]}

    // --- Controls ---
    const tex = $('wallBgTextures');
    S.TEXTURES.forEach(t => { const o = document.createElement('option'); o.value = t.id; o.textContent = t.name; tex.appendChild(o); });
    S.SHAPES.forEach(sh => {
        const b = document.createElement('button');
        b.type = 'button'; b.dataset.shape = sh.id; b.textContent = sh.name;
        $('wallShape').appendChild(b);
    });
    let ammoKey = '';
    function paintAmmo() {  // the unlocked skins, to pick what to throw without leaving the wall
        const open = T.SKINS.filter(T.unlocked), key = open.map(x => x.id).join() + '|' + T.data().skin;
        if (key === ammoKey) return;
        ammoKey = key;
        const box = $('wallAmmo');
        box.innerHTML = '';
        open.forEach(sk => {
            const b = document.createElement('button');
            b.type = 'button'; b.title = sk.name; b.textContent = sk.emoji;
            if (sk.filter) b.style.filter = sk.filter;
            b.classList.toggle('on', sk.id === T.data().skin);
            b.addEventListener('click', () => T.pick(sk.id));
            box.appendChild(b);
        });
    }
    T.onChange(paintAmmo);
    function paintControls() {
        $('wallBg').value = wall.bg;
        if ($('wallBg').value !== wall.bg) { wall.bg = 'night'; $('wallBg').value = 'night'; }
        $('wallSize').value = wall.size;
        $('wallEmoji').checked = wall.emoji;
        document.querySelectorAll('#wallShape [data-shape]').forEach(b => b.classList.toggle('on', b.dataset.shape === wall.shape));
        $('wallUndo').disabled = !undo.length && !wall.splats.length;
        $('wallRedo').disabled = !redo.length;
        $('wallCount').textContent = wall.splats.length ? `${wall.splats.length.toLocaleString()} splats` : '';
    }

    // --- Drawing ---
    let frame = 0;
    function redraw() {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
            S.background(g, wall.bg, redraw);
            wall.splats.forEach(sp => S.draw(g, sp));
            paintControls();
            download();
        });
    }
    let dlTimer = null;
    function download() {
        clearTimeout(dlTimer);
        dlTimer = setTimeout(() => {
            try { $('wallDownload').href = S.signed(c, wall.bg).toDataURL('image/png'); } catch (e) { /* no download here */ }
        }, 500);
    }
    const at = (e) => { const r = c.getBoundingClientRect(); return { x: (e.clientX - r.left) / r.width * W, y: (e.clientY - r.top) / r.height * H }; };

    function throwAt(p, stroke) {
        const s = T.skin(), lucky = Math.random() < 1 / 500, lk = T.look(s, lucky);  // paint only: counts nowhere
        const sp = { x: Math.round(p.x), y: Math.round(p.y), r: Math.round(wall.size * (.85 + Math.random() * .3)), c: lk.color,
                     f: lk.filter || '', k: s.emoji, e: wall.emoji, rot: Math.round(Math.random() * 628) / 100,
                     seed: Math.floor(Math.random() * 233280), t: wall.shape };
        wall.splats.push(sp);
        stroke.push(sp);
        if (wall.splats.length > MAX) { wall.splats.shift(); redraw(); } else { S.draw(g, sp); download(); }
    }
    function wipeAt(p, removed) {
        const reach = wall.size * 1.1;
        for (let i = wall.splats.length - 1; i >= 0; i--) {
            const sp = wall.splats[i];
            if (Math.hypot(sp.x - p.x, sp.y - p.y) <= reach + sp.r * .5) removed.push([i, wall.splats.splice(i, 1)[0]]);
        }
    }
    const spacing = () => Math.max(6, wall.size * ({ splat: .7, drip: .6, spray: .9, stamp: 1.3 }[wall.shape] || .7));

    // Tap to throw; drag to paint a line of throws (or to wipe)
    let down = null;  // {last, stroke | removed}
    let wiping = false;
    c.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        c.setPointerCapture(e.pointerId);
        const p = at(e);
        if (wiping) { down = { last: p, removed: [] }; wipeAt(p, down.removed); redraw(); return; }
        down = { last: p, stroke: [] };
        throwAt(p, down.stroke);
    });
    c.addEventListener('pointermove', (e) => {
        if (!down) return;
        const p = at(e);
        if (wiping) { wipeAt(p, down.removed); down.last = p; redraw(); return; }
        const d = Math.hypot(p.x - down.last.x, p.y - down.last.y), step = spacing();
        if (d < step) return;
        const n = Math.min(PER_MOVE, Math.floor(d / step));
        for (let i = 1; i <= n; i++) {
            const k = i * step / d;
            throwAt({ x: down.last.x + (p.x - down.last.x) * k, y: down.last.y + (p.y - down.last.y) * k }, down.stroke);
        }
        down.last = n === PER_MOVE ? p : { x: down.last.x + (p.x - down.last.x) * n * step / d, y: down.last.y + (p.y - down.last.y) * n * step / d };
        paintControls();
    });
    ['pointerup', 'pointercancel'].forEach(t => c.addEventListener(t, () => {
        if (!down) return;
        if (down.stroke && down.stroke.length) { undo.push({ add: down.stroke }); redo.length = 0; }
        if (down.removed && down.removed.length) { undo.push({ wipe: down.removed }); redo.length = 0; }
        down = null;
        saveSoon();
        paintControls();
    }));

    function takeBack() {
        const act = undo.pop();
        if (!act) { if (wall.splats.length) { wall.splats.pop(); } }  // after a reload: one splat at a time
        else if (act.add) { const gone = new Set(act.add); wall.splats = wall.splats.filter(sp => !gone.has(sp)); redo.push(act); }
        else if (act.wipe) { act.wipe.slice().reverse().forEach(([i, sp]) => wall.splats.splice(i, 0, sp)); redo.push(act); }
        save(); redraw();
    }
    function putBack() {
        const act = redo.pop();
        if (!act) return;
        if (act.add) wall.splats.push(...act.add);
        else if (act.wipe) { const gone = new Set(act.wipe.map(x => x[1])); wall.splats = wall.splats.filter(sp => !gone.has(sp)); }
        undo.push(act);
        save(); redraw();
    }
    $('wallUndo').addEventListener('click', takeBack);
    $('wallRedo').addEventListener('click', putBack);
    document.addEventListener('keydown', (e) => {
        if (!(e.ctrlKey || e.metaKey) || e.target.closest('input, textarea, select')) return;
        if (e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); takeBack(); }
        else if (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey)) { e.preventDefault(); putBack(); }
    });
    $('wallBg').addEventListener('change', (e) => { wall.bg = e.target.value; save(); redraw(); });
    $('wallSize').addEventListener('input', (e) => { wall.size = Number(e.target.value); saveSoon(); });
    $('wallShape').addEventListener('click', (e) => {
        const b = e.target.closest('[data-shape]'); if (!b) return; wall.shape = b.dataset.shape; save(); paintControls(); });
    $('wallEmoji').addEventListener('change', (e) => { wall.emoji = e.target.checked; save(); });
    $('wallWipe').addEventListener('click', () => {
        wiping = !wiping;
        $('wallWipe').setAttribute('aria-pressed', String(wiping));
        $('wallWipe').classList.toggle('on', wiping);
        c.classList.toggle('wiping', wiping);
    });
    $('wallClear').addEventListener('click', async () => {
        if (!wall.splats.length) return;
        if (window.NADialog && !await NADialog.confirm('Wipe the whole wall clean? Your tomato count stays, and Undo brings it back.',
                                                       { title: 'Clear the wall', ok: 'Clear it', danger: true })) return;
        undo.push({ wipe: wall.splats.map((sp, i) => [i, sp]).reverse() }); redo.length = 0;  // removed from the end, in order
        wall.splats = []; save(); redraw();
    });
    // Full screen: the wall fills the window (a CSS mode, so it works on phones too); Esc leaves it
    function full(on) {
        $('wallBox').classList.toggle('wall-full', on);
        document.body.classList.toggle('wall-full-open', on);
        $('wallFull').setAttribute('aria-pressed', String(on));
        $('wallFull').textContent = on ? '✕ Leave full screen' : '⛶ Full screen';
    }
    $('wallFull').addEventListener('click', () => full(!$('wallBox').classList.contains('wall-full')));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('wallBox').classList.contains('wall-full')) full(false); });

    // 💾 Save to the gallery
    $('wallSave').addEventListener('click', async () => {
        const btn = $('wallSave');
        if (!wall.splats.length) { NADialog.alert('Throw something at the wall first.', { title: 'Nothing to save' }); return; }
        const title = await NADialog.prompt('What is it called?', '', { title: 'Save to the gallery', ok: 'Next' });
        if (title === null) return;
        const shared = await NADialog.confirm("Show it in everyone's gallery too? You can change this later.",
                                              { title: 'Share it?', ok: 'Share it', cancel: 'Just for me' });
        btn.disabled = true;
        try {
            const resp = await fetch(btn.dataset.url, { method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '' },
                body: JSON.stringify({ title, bg: wall.bg, splats: wall.splats, shared }) });
            const out = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(out.error || 'It did not save. Try again in a moment.');
            T.toast('🖼 Saved to the gallery', shared ? 'Everyone can see it now.' : 'Only you can see it.');
        } catch (err) {
            NADialog.alert(err.message, { title: 'Not saved' });
        } finally { btn.disabled = false; }
    });

    // A piece opened from the gallery ("Keep painting") arrives in this browser's wall: show it
    if (location.hash === '#wallBox') setTimeout(() => $('wallBox').scrollIntoView({ behavior: 'smooth' }), 300);
    paintAmmo();
    redraw();
})();

/* 🏆 The leaderboard: chat + Bulba tomatoes of everyone who chose to be on it (mainapp/tomatoes.py). */
(function () {
    const box = document.getElementById('boardBox');
    if (!box) return;
    const URL = box.dataset.url;
    const CSRF = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';
    const $ = (id) => document.getElementById(id);
    const fmt = (n) => Number(n || 0).toLocaleString();
    function paint(b) {
        if (!b || !b.me) return;
        $('boardMine').textContent = fmt(b.me.wild);
        if ($('sumWild')) {
            $('sumWild').textContent = fmt(b.me.wild);
            $('sumRank').textContent = b.me.wild ? (b.me.on_board ? `at chats · #${b.me.rank}` : `at chats · you'd be #${b.me.rank}`) : 'at chats and Bulba';
        }
        $('boardJoin').checked = !!b.me.on_board;
        $('boardRank').textContent = !b.me.wild ? 'Throw at a slow reply to get on the board.'
            : b.me.on_board ? `You're #${b.me.rank}.` : `You'd be #${b.me.rank}.`;
        $('boardPlayers').textContent = b.players ? `${fmt(b.players)} on the board` : '';
        const list = $('boardList');
        list.innerHTML = '';
        b.top.forEach((row) => {
            const li = document.createElement('li');
            li.className = row.me ? 'me' : '';
            li.innerHTML = '<span class="n"></span><span class="w"></span>';
            li.querySelector('.n').textContent = row.name;
            if (row.badge) {  // won at the Sauce-o-Matic, worn by the name
                const badge = document.createElement('span');
                badge.className = 'board-badge';
                badge.textContent = row.badge;
                li.querySelector('.n').prepend(badge);
            }
            li.querySelector('.w').textContent = fmt(row.wild);
            list.appendChild(li);
        });
        $('boardEmpty').hidden = b.top.length > 0;
    }
    async function load(body) {
        try {
            const resp = await fetch(URL, body ? { method: 'POST', credentials: 'same-origin', body: JSON.stringify(body),
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() } } : { credentials: 'same-origin' });
            if (resp.ok) paint(await resp.json());
        } catch (e) { /* offline: try again later */ }
    }
    $('boardJoin').addEventListener('change', (e) => load({ on_board: e.target.checked }));
    document.addEventListener('na-board-refresh', () => load());  // a badge just put on at the machine
    load();
    setInterval(() => { if (!document.hidden) load(); }, 30000);
})();
