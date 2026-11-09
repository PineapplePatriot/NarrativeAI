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
    function drawCard() {
        const d = T.data(), s = T.skin(), c = $('pitCard'), g = c.getContext('2d');
        const bg = g.createLinearGradient(0, 0, 1200, 630);
        bg.addColorStop(0, '#1a1027');
        bg.addColorStop(1, '#2b0f14');
        g.fillStyle = bg;
        g.fillRect(0, 0, 1200, 630);
        // splats in the skin's colour
        let seed = d.count + 7;
        const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
        g.globalAlpha = .22;
        g.fillStyle = s.color;
        for (let i = 0; i < 14; i++) {
            g.beginPath();
            g.arc(rnd() * 1200, rnd() * 630, 20 + rnd() * 60, 0, Math.PI * 2);
            g.fill();
        }
        g.globalAlpha = 1;
        g.font = '220px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
        g.textBaseline = 'middle';
        g.filter = s.filter || 'none';
        g.fillText(s.emoji, 80, 300);
        g.filter = 'none';
        g.fillStyle = '#ffffff';
        g.font = '800 96px system-ui, -apple-system, "Segoe UI", sans-serif';
        g.fillText(d.count.toLocaleString(), 400, 230);
        g.font = '600 40px system-ui, -apple-system, "Segoe UI", sans-serif';
        g.fillStyle = '#f1e4e4';
        g.fillText(`${(d.count === 1 ? s.name : many(s)).toLowerCase()} thrown at Narrative AI`, 400, 310);
        g.fillText('while waiting for a reply.', 400, 360);
        const best = [...T.ACHIEVEMENTS].reverse().find(a => d.ach[a.id] && a.id !== 'first' && a.id !== 'pit')
            || T.ACHIEVEMENTS.find(a => d.ach[a.id]);
        g.font = '500 32px system-ui, -apple-system, "Segoe UI", sans-serif';
        g.fillStyle = '#f2b72c';
        if (best) g.fillText(`🏅 ${best.name}: ${best.about}`.slice(0, 60), 400, 440);
        g.fillStyle = 'rgba(255,255,255,.55)';
        g.font = '500 28px system-ui, -apple-system, "Segoe UI", sans-serif';
        const open = T.SKINS.filter(T.unlocked).length;
        g.fillText(`${open}/${T.SKINS.length} skins · best ${d.best10 || 0} throws in 10 seconds · 🕳️ the Tomato Pit`, 80, 570);
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
