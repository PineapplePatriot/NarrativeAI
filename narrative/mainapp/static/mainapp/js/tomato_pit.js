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
        $('pitAch').innerHTML = T.ACHIEVEMENTS.map(a => `<li class="${d.ach[a.id] ? 'got' : ''}"><b>${d.ach[a.id] ? '🏅' : '🔒'} ${esc(a.name)}</b>
            <small>${esc(a.about)}</small></li>`).join('');
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
        glow.addColorStop(0, s.color + '55');
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
