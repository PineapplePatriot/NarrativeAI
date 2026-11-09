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
        $('pitAmmo').textContent = s.emoji;
        $('pitAmmo').style.filter = s.filter || '';
        const open = T.SKINS.filter(T.unlocked);
        $('pitSkinCount').textContent = `${open.length} of ${T.SKINS.length}`;
        const kinds = [...new Set(T.SKINS.map(x => x.kind))];
        $('pitSkins').innerHTML = kinds.map(kind => `<h3>${esc(kind)}</h3><div class="pit-skins">${T.SKINS.filter(x => x.kind === kind).map(x => {
            const ok = T.unlocked(x);
            const how = x.ach ? (T.ACHIEVEMENTS.find(a => a.id === x.ach) || {}).name : `${x.at.toLocaleString()} throws`;
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

/* 🎨 The splat wall: throws land where you tap and stay. Kept in this browser (a list of splats, so Undo works
   and the wall can change its background); every throw counts like any other (NATomato.tally). */
(function () {
    const T = window.NATomato, c = document.getElementById('wall');
    if (!T || !c) return;
    const g = c.getContext('2d'), W = c.width, H = c.height, KEY = 'na-tomato-wall', MAX = 4000;
    let wall = { bg: 'night', size: 38, emoji: true, splats: [] };
    try { wall = Object.assign(wall, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) { /* a fresh wall */ }
    const save = () => { try { localStorage.setItem(KEY, JSON.stringify(wall)); } catch (e) { wall.splats = wall.splats.slice(-1000); } };
    const EMOJI = '"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';

    function background() {
        const fills = { night: '#151826', plaster: '#e9e3d6', brick: '#8a3b2c', chalk: '#24372c' };
        g.fillStyle = fills[wall.bg] || fills.night;
        g.fillRect(0, 0, W, H);
        if (wall.bg === 'brick') {  // mortar lines
            g.fillStyle = 'rgba(230, 215, 200, .55)';
            for (let y = 0, row = 0; y < H; y += 50, row++) {
                g.fillRect(0, y, W, 5);
                for (let x = (row % 2) * 60; x < W; x += 120) g.fillRect(x, y, 5, 50);
            }
        } else if (wall.bg === 'plaster' || wall.bg === 'chalk') {  // a little texture
            let seed = 11;
            const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
            g.fillStyle = wall.bg === 'chalk' ? 'rgba(255, 255, 255, .035)' : 'rgba(120, 100, 70, .06)';
            for (let i = 0; i < 260; i++) g.fillRect(rnd() * W, rnd() * H, 2 + rnd() * 30, 1 + rnd() * 3);
        }
    }

    function draw(sp) {
        let seed = sp.seed;
        const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
        const r = sp.r;
        g.save();
        g.globalAlpha = .93;
        g.fillStyle = sp.c;
        // the blob: a wobbly circle
        g.beginPath();
        const n = 12, pts = [];
        for (let i = 0; i < n; i++) {
            const a = i / n * Math.PI * 2, d = r * (.72 + rnd() * .38);
            pts.push([sp.x + Math.cos(a) * d, sp.y + Math.sin(a) * d]);
        }
        g.moveTo((pts[0][0] + pts[n - 1][0]) / 2, (pts[0][1] + pts[n - 1][1]) / 2);
        for (let i = 0; i < n; i++) {
            const p = pts[i], q = pts[(i + 1) % n];
            g.quadraticCurveTo(p[0], p[1], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2);
        }
        g.fill();
        // droplets around it
        for (let i = 0, m = 6 + Math.floor(rnd() * 6); i < m; i++) {
            const a = rnd() * Math.PI * 2, d = r * (1.05 + rnd() * .9);
            g.beginPath();
            g.arc(sp.x + Math.cos(a) * d, sp.y + Math.sin(a) * d, r * (.06 + rnd() * .16), 0, Math.PI * 2);
            g.fill();
        }
        // drips running down
        for (let i = 0, m = 1 + Math.floor(rnd() * 3); i < m; i++) {
            const x = sp.x + (rnd() - .5) * r * 1.1, w = r * (.1 + rnd() * .1), len = r * (.5 + rnd() * 1.3);
            g.fillRect(x - w / 2, sp.y, w, r * .6 + len);
            g.beginPath();
            g.arc(x, sp.y + r * .6 + len, w * .75, 0, Math.PI * 2);
            g.fill();
        }
        if (sp.e) {
            g.globalAlpha = 1;
            g.translate(sp.x, sp.y);
            g.rotate(sp.rot);
            g.font = `${Math.round(r * 1.05)}px ${EMOJI}`;
            g.textAlign = 'center';
            g.textBaseline = 'middle';
            if (sp.f) g.filter = sp.f;
            g.fillText(sp.k, 0, 0);
        }
        g.restore();
    }

    function redraw() {
        background();
        wall.splats.forEach(draw);
        document.getElementById('wallCount').textContent = wall.splats.length ? `${wall.splats.length.toLocaleString()} splats` : '';
        document.querySelectorAll('#wallBg [data-bg]').forEach(b => b.classList.toggle('on', b.dataset.bg === wall.bg));
        document.querySelectorAll('#wallSize [data-size]').forEach(b => b.classList.toggle('on', Number(b.dataset.size) === wall.size));
        document.getElementById('wallEmoji').checked = wall.emoji;
        download();
    }
    let dlTimer = null;
    function download() {  // the picture behind "Download", with a small signature
        clearTimeout(dlTimer);
        dlTimer = setTimeout(() => {
            const out = document.createElement('canvas');
            out.width = W; out.height = H;
            const o = out.getContext('2d');
            o.drawImage(c, 0, 0);
            o.font = '600 20px system-ui, -apple-system, "Segoe UI", sans-serif';
            o.fillStyle = wall.bg === 'plaster' ? 'rgba(0, 0, 0, .45)' : 'rgba(255, 255, 255, .55)';
            o.textAlign = 'right';
            o.fillText('painted with vegetables · the Tomato Pit · Narrative AI', W - 18, H - 16);
            try { document.getElementById('wallDownload').href = out.toDataURL('image/png'); } catch (e) { /* no download here */ }
        }, 400);
    }

    function throwAt(e) {
        const rect = c.getBoundingClientRect();
        const s = T.skin(), lucky = T.tally(), lk = T.look(s, lucky);
        const sp = { x: Math.round((e.clientX - rect.left) / rect.width * W), y: Math.round((e.clientY - rect.top) / rect.height * H),
                     r: Math.round(wall.size * (.85 + Math.random() * .3)), c: lk.color, f: lk.filter || '', k: s.emoji,
                     e: wall.emoji, rot: Math.round(Math.random() * 628) / 100, seed: Math.floor(Math.random() * 233280) };
        wall.splats.push(sp);
        if (wall.splats.length > MAX) { wall.splats.shift(); redraw(); } else { draw(sp); download(); }
        document.getElementById('wallCount').textContent = `${wall.splats.length.toLocaleString()} splats`;
        saveSoon();
    }
    let saveTimer = null;
    const saveSoon = () => { clearTimeout(saveTimer); saveTimer = setTimeout(save, 600); };

    // Tap to throw; hold and drag to keep throwing (one every 90 ms)
    let down = false, lastAt = 0;
    c.addEventListener('pointerdown', (e) => { e.preventDefault(); down = true; c.setPointerCapture(e.pointerId); throwAt(e); lastAt = Date.now(); });
    c.addEventListener('pointermove', (e) => { if (down && Date.now() - lastAt > 90) { throwAt(e); lastAt = Date.now(); } });
    ['pointerup', 'pointercancel'].forEach(t => c.addEventListener(t, () => { down = false; }));

    document.getElementById('wallBg').addEventListener('click', (e) => {
        const b = e.target.closest('[data-bg]'); if (!b) return; wall.bg = b.dataset.bg; save(); redraw(); });
    document.getElementById('wallSize').addEventListener('click', (e) => {
        const b = e.target.closest('[data-size]'); if (!b) return; wall.size = Number(b.dataset.size); save(); redraw(); });
    document.getElementById('wallEmoji').addEventListener('change', (e) => { wall.emoji = e.target.checked; save(); });
    document.getElementById('wallUndo').addEventListener('click', () => { wall.splats.pop(); save(); redraw(); });
    document.getElementById('wallClear').addEventListener('click', async () => {
        if (!wall.splats.length) return;
        if (window.NADialog && !await NADialog.confirm('Wipe the whole wall clean? Your tomato count stays.',
                                                       { title: 'Clear the wall', ok: 'Clear it', danger: true })) return;
        wall.splats = []; save(); redraw();
    });
    redraw();
})();
