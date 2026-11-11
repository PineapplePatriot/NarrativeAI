/* 🎰 The Sauce-o-Matic in the Tomato Pit: pull the lever, the machine shakes, capsules drop, and you open them.
   The draw itself happens on the server (mainapp/tomato_machine.py); this page only shows it.
   - One pull: a big capsule wobbles (harder for better tiers, sometimes starting a tier lower and turning), then
     cracks open with a flash and splash; a legendary gets rays and confetti.
   - Ten pulls: ten capsules drop into a grid and open one by one (Skip opens them all at once).
   - Reduced motion: no shaking, dropping or bursting, just the results fading in. */
(function () {
    const box = document.getElementById('machBox');
    if (!box) return;
    const URL = box.dataset.url;
    const T = window.NATomato;
    const $ = (id) => document.getElementById(id);
    const CSRF = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';
    const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
    const wait = (ms) => new Promise(r => setTimeout(r, calm() ? Math.min(ms, 60) : ms));
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const TIER = { common: 'Common', rare: 'Rare', legendary: 'Legendary' };
    const KINDS = { gardener: 'Gardeners', skin: 'Things to throw', hat: "Bulba's hats", trail: 'Cursor trails', badge: 'Badges',
                    decor: 'Garden decorations', seed: 'Seeds', oddity: 'Oddities' };
    const WEAR = { hat: 'Put it on Bulba', trail: 'Use it', badge: 'Wear it' };
    let state = null, busy = false;
    const prize = (id) => (state && state.prizes.find(p => p.id === id)) || { id, emoji: '❔', name: id, tier: 'common' };

    async function call(body) {
        const resp = await fetch(URL, body ? { method: 'POST', credentials: 'same-origin', body: JSON.stringify(body),
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() } } : { credentials: 'same-origin' });
        const out = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(out.error || 'The machine coughed. Try again in a moment.');
        return out;
    }
    const capsule = (tier, cls = '') => `<div class="cap ${tier} ${cls}"><div class="cap-t"></div><div class="cap-b"></div></div>`;

    // --- The side panel ---
    function paint() {
        const s = state;
        $('machCost').textContent = s.cost;
        $('machSpins').textContent = s.spins.toLocaleString();
        $('machSpinsWord').textContent = s.spins === 1 ? 'spin' : 'spins';
        $('machFill').style.width = `${Math.round(s.toward / s.cost * 100)}%`;
        $('machMeter').setAttribute('aria-valuemax', s.cost);
        $('machMeter').setAttribute('aria-valuenow', s.toward);
        $('machToward').textContent = `${s.toward} of ${s.cost} tomatoes towards the next spin`;
        $('machPull1').disabled = busy || s.spins < 1;
        $('machPull10').disabled = busy || s.spins < 10;
        const rare = s.pity.rare_at - s.pity.rare, legend = s.pity.legend_at - s.pity.legend;
        $('machPity').textContent = `A rare or better within ${rare} pull${rare === 1 ? '' : 's'} · a legendary within ${legend}`;
        $('machCompost').textContent = `♻ ${s.compost} compost`;
        $('machCompostBtn').disabled = busy || s.compost < s.compost_spin;
        $('machCompostBtn').title = `Turn ${s.compost_spin} compost into a spin`;
        // Bulba's Promise
        const sel = $('machPromise');
        if (sel.options.length === 1) {
            s.prizes.filter(p => p.tier === 'legendary').forEach(p => {
                const o = document.createElement('option');
                o.value = p.id;
                o.textContent = `${p.emoji} ${p.name}${p.now ? '' : ' (out of season)'}`;
                o.disabled = !p.now;
                sel.appendChild(o);
            });
        }
        sel.value = s.promise || '';
        const promised = s.promise && prize(s.promise);
        $('machPromiseNote').textContent = !promised ? 'Pick a legendary and Bulba promises you get it: a coin flip on your next legendary, and a sure thing on the one after if the flip goes wrong.'
            : s.promise_sure ? `Your next legendary is guaranteed to be ${promised.emoji} ${promised.name}.`
            : `Your next legendary is a 50/50 for ${promised.emoji} ${promised.name}. If it isn't, the one after is.`;
        paintOdds();
        paintShelf();
        paintHistory();
    }
    function paintOdds() {
        const s = state, season = s.prizes.find(p => p.season === s.season);
        $('machOdds').innerHTML = `<table>${Object.entries(s.odds).map(([t, n]) => `<tr><td><b>${TIER[t]}</b></td><td>${n}%</td>
            <td class="muted">${s.prizes.filter(p => p.tier === t && p.now).length} things</td></tr>`).join('')}</table>
            <ul><li>At least one rare (or better) every ${s.pity.rare_at} pulls, and a legendary by pull ${s.pity.legend_at} at the latest.</li>
            <li><b>Bulba's Promise</b>: choose a legendary. Each legendary is it half the time, and if it isn't, the next one is.</li>
            <li>Getting something you keep only one of again turns it into compost (♻ ${s.compost_spin} compost = 1 spin). Seeds and garden things stack.</li>
            <li>A golden splat (1 in 500) thrown at a chat or Bulba is a free spin.</li>
            <li>Seasonal: ${season ? `${season.emoji} ${esc(season.name)} is in the machine this ${s.season}` : 'nothing this season'}. The others wait for their season.</li></ul>`;
    }
    function paintShelf() {
        const s = state, mine = Object.keys(s.items).filter(k => s.items[k] > 0);
        $('machShelfCount').textContent = `${mine.length} of ${s.prizes.length} found`;
        const groups = Object.keys(KINDS).map(kind => {
            const got = s.prizes.filter(p => p.kind === kind && s.items[p.id]);
            if (!got.length) return '';
            return `<h3>${KINDS[kind]}</h3><div class="mach-shelf">${got.map(p => {
                const n = s.items[p.id], on = s.equipped[p.kind] === p.id;
                let act = '';
                if (WEAR[p.kind]) act = `<button type="button" class="na-btn${on ? ' on' : ''}" data-equip="${p.kind}" data-id="${on ? '' : p.id}">${on ? '✓ Wearing · take off' : WEAR[p.kind]}</button>`;
                else if (p.kind === 'skin') act = `<button type="button" class="na-btn" data-throw="${p.id}">Throw it</button>`;
                else if (p.kind === 'seed' || p.kind === 'decor' || p.kind === 'gardener') act = '<small class="muted">For your garden</small>';
                return `<div class="mach-item ${p.tier}" title="${esc(p.note)}"><span class="e">${p.emoji}</span><b>${esc(p.name)}${n > 1 ? ` ×${n}` : ''}</b>
                    <small class="muted">${esc(p.note)}</small>${act}</div>`;
            }).join('')}</div>`;
        }).join('');
        $('machShelf').innerHTML = groups || '<p class="muted">Nothing yet. The machine is waiting.</p>';
    }
    function paintHistory() {
        const h = state.history || [];
        $('machHistory').innerHTML = h.length ? h.map(r => {
            const p = prize(r.id);
            return `<li class="${r.tier}">${p.emoji} <b>${esc(p.name)}</b> <span class="muted">· ${TIER[r.tier]}${r.dup ? ` · ♻ +${r.compost}` : ''} ·
                ${new Date(r.at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span></li>`;
        }).join('') : '<li class="muted">No pulls yet.</li>';
    }
    function fillDome() {  // the capsules bobbing in the glass
        const balls = $('machBalls');
        const colors = ['var(--common)', 'var(--common)', 'var(--common)', 'var(--common)', 'var(--rare)', 'var(--common)', 'var(--rare)', 'var(--legendary)'];
        balls.innerHTML = Array.from({ length: 16 }, (_, i) => {
            const x = 6 + (i % 6) * 25 + (Math.floor(i / 6) % 2) * 12, y = 96 - Math.floor(i / 6) * 22;
            return `<span class="mach-ball" style="--c:${colors[i % colors.length]};left:${x}px;top:${y}px;animation-delay:${-(i * .37).toFixed(2)}s"></span>`;
        }).join('');
    }

    // --- Pulling ---
    async function pull(n) {
        if (busy) return;
        busy = true;
        paint();
        let out;
        try {
            out = await call({ action: 'spin', n });
        } catch (err) {
            busy = false; paint();
            if (window.NADialog) NADialog.alert(err.message, { title: 'The machine says no' }); return;
        }
        const stage = $('machStage');
        stage.classList.add('pulling');
        await wait(450);
        stage.classList.add('shaking', 'mixing');
        await wait(650);
        stage.classList.remove('pulling', 'shaking');
        const tray = $('machTray');
        tray.innerHTML = '';
        for (const r of out.results.slice(0, 5)) { tray.insertAdjacentHTML('beforeend', capsule(r.tier)); await wait(90); }
        await wait(650);
        stage.classList.remove('mixing');
        try {
            if (n === 1) await showOne(out.results[0]); else await showTen(out.results);
        } finally {
            tray.innerHTML = '';
            state = out;
            busy = false;
            paint();
            if (T && out.results.some(r => !r.dup && ['skin', 'hat', 'trail', 'badge'].includes(prize(r.id).kind))) T.refresh();
        }
    }

    // --- The reveal overlay ---
    const ov = $('machReveal'), inner = $('machRevealInner');
    let advance = null;  // what "Open it" / "Skip" / a tap does now
    function openOverlay(tier) {
        ov.className = 'mach-reveal t-' + tier;
        ov.hidden = false;
        document.body.classList.add('mach-open');
        $('machConfetti').innerHTML = '';
    }
    function closeOverlay() {
        ov.hidden = true;
        document.body.classList.remove('mach-open');
        inner.innerHTML = '';
        $('machConfetti').innerHTML = '';
    }
    const press = () => new Promise(res => { advance = res; });
    $('machNext').addEventListener('click', () => advance && advance('next'));
    $('machSkip').addEventListener('click', () => advance && advance('skip'));
    document.addEventListener('keydown', (e) => {
        if (ov.hidden || !advance) return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); advance('next'); }
        if (e.key === 'Escape') advance('skip');
    });
    function bar(next, skip) {
        $('machNext').textContent = next;
        $('machSkip').hidden = !skip;
        $('machNext').focus({ preventScroll: true });
    }
    function burst(at, tier) {  // flash and splash from the middle of `at`
        if (calm()) return;
        const host = at || inner;
        host.insertAdjacentHTML('beforeend', '<div class="mach-flash"></div>');
        const n = tier === 'legendary' ? 44 : tier === 'rare' ? 28 : 16;
        for (let i = 0; i < n; i++) {
            const a = Math.random() * Math.PI * 2, d = 90 + Math.random() * (tier === 'legendary' ? 260 : 160);
            const b = document.createElement('span');
            b.className = 'mach-bit';
            b.style.setProperty('--x', `${Math.cos(a) * d}px`);
            b.style.setProperty('--y', `${Math.sin(a) * d}px`);
            b.style.width = b.style.height = `${4 + Math.random() * 10}px`;
            host.appendChild(b);
        }
        setTimeout(() => host.querySelectorAll('.mach-flash, .mach-bit').forEach(x => x.remove()), 1000);
    }
    function confetti() {
        if (calm()) return;
        const c = $('machConfetti'), colors = ['#ffc531', '#ff8a3d', '#e0352b', '#fff1b8', '#7cc0ff', '#5aa83a'];
        for (let i = 0; i < 90; i++) {
            const s = document.createElement('span');
            s.style.left = `${Math.random() * 100}%`;
            s.style.background = colors[i % colors.length];
            s.style.setProperty('--dx', `${(Math.random() - .5) * 200}px`);
            s.style.setProperty('--r', `${Math.random() * 1080}deg`);
            s.style.animationDuration = `${2 + Math.random() * 2}s`;
            s.style.animationDelay = `${Math.random() * .6}s`;
            c.appendChild(s);
        }
    }
    function extra(r) {
        const p = prize(r.id), lines = [];
        if (r.promise === 'promise') lines.push('🤝 Bulba kept the promise.');
        if (r.promise === 'lost') lines.push('Not the promised one. Your next legendary will be.');
        if (r.dup) lines.push(`Already had it: ♻ +${r.compost} compost`);
        else if (['seed', 'decor'].includes(p.kind)) lines.push('Into the garden basket.');
        return lines.map(l => `<span class="extra">${esc(l)}</span>`).join('');
    }
    function card(r) {
        const p = prize(r.id);
        return `<div class="mach-card"><div class="e">${p.emoji}</div><div class="tier">${TIER[r.tier]}</div>
            <h3>${esc(p.name)}</h3><p>${esc(p.note)}</p>${extra(r)}</div>`;
    }
    // Sometimes a capsule starts a tier lower and turns while it wobbles
    const fakeFrom = (tier) => (tier === 'legendary' && Math.random() < .4) ? 'rare' : (tier === 'rare' && Math.random() < .2) ? 'common' : '';

    async function showOne(r) {
        openOverlay(r.tier === 'legendary' ? 'rare' : 'common');
        const from = calm() ? '' : fakeFrom(r.tier);
        inner.innerHTML = capsule(from || r.tier, 'big glow wobble' + (r.tier !== 'common' ? ' hard' : ''));
        const cap = inner.querySelector('.cap');
        cap.addEventListener('click', () => advance && advance('next'));
        bar('Open it', false);
        if (from) {  // the turn
            await wait(1100);
            cap.classList.remove(from); cap.classList.add(r.tier, 'hard');
            burst(null, r.tier);
            ov.classList.add('t-' + r.tier);
        }
        if (r.tier !== 'common') { ov.classList.remove('t-common', 't-rare'); ov.classList.add('t-' + r.tier, 'rays'); }
        await press();
        advance = null;
        cap.classList.remove('wobble');
        cap.classList.add('open');
        burst(null, r.tier);
        if (r.tier === 'legendary') confetti();
        await wait(380);
        inner.innerHTML = card(r);
        bar('Done', false);
        await press();
        advance = null;
        closeOverlay();
    }

    async function showTen(results) {
        const best = results.some(r => r.tier === 'legendary') ? 'legendary' : results.some(r => r.tier === 'rare') ? 'rare' : 'common';
        openOverlay(best);
        if (best !== 'common') ov.classList.add('rays');
        inner.innerHTML = `<div class="mach-ten">${results.map((r, i) =>
            `<div class="slot" data-i="${i}" style="animation-delay:${i * 70}ms">${capsule(r.tier, r.tier !== 'common' ? 'glow' : '')}</div>`).join('')}</div>
            <p class="muted" id="machTenSum"></p>`;
        inner.querySelectorAll('.slot .cap').forEach((c, i) => { c.style.animationDelay = `${i * 70}ms`; });
        bar('Open them', true);
        const how = await press();
        advance = null;
        const slots = [...inner.querySelectorAll('.slot')];
        let skip = how === 'skip';
        advance = () => { skip = true; };  // Faster or Skip: open the rest at once
        $('machSkip').hidden = false;
        $('machNext').textContent = 'Faster';
        for (let i = 0; i < results.length; i++) {
            const r = results[i], p = prize(r.id), slot = slots[i];
            if (!skip && r.tier === 'legendary') { slot.querySelector('.cap').classList.add('wobble'); await wait(700); }
            slot.className = `slot done ${r.tier}`;
            slot.innerHTML = `<span class="e">${p.emoji}</span><span class="n">${esc(p.name)}</span>${r.dup ? `<span class="dup">♻ +${r.compost}</span>` : ''}`;
            slot.title = `${p.name} (${TIER[r.tier]})${r.dup ? ': already had it' : ''}`;
            if (!skip) {
                if (r.tier !== 'common') burst(slot, r.tier);
                if (r.tier === 'legendary') confetti();
                await wait(r.tier === 'legendary' ? 700 : 260);
            }
        }
        const count = (t) => results.filter(r => r.tier === t).length;
        const compost = results.reduce((a, r) => a + (r.compost || 0), 0);
        const promise = results.find(r => r.promise);
        $('machTenSum').textContent = [count('legendary') && `${count('legendary')} legendary`, count('rare') && `${count('rare')} rare`,
            count('common') && `${count('common')} common`, compost && `♻ +${compost} compost`,
            promise && (promise.promise === 'promise' ? '🤝 Bulba kept the promise' : 'the promised one comes next time')].filter(Boolean).join(' · ');
        advance = null;
        bar('Done', false);
        await press();
        advance = null;
        closeOverlay();
    }

    // --- Buttons ---
    $('machPull1').addEventListener('click', () => pull(1));
    $('machPull10').addEventListener('click', () => pull(10));
    $('machLever').addEventListener('click', () => { if (state && state.spins >= 1) pull(1); });
    $('machOddsBtn').addEventListener('click', () => {
        const o = $('machOdds'); o.hidden = !o.hidden; $('machOddsBtn').setAttribute('aria-expanded', String(!o.hidden));
    });
    async function act(body) {
        try { state = await call(body); paint(); if (T) T.refresh(); }
        catch (err) { if (window.NADialog) NADialog.alert(err.message); paint(); }
    }
    $('machPromise').addEventListener('change', (e) => act({ action: 'promise', id: e.target.value || null }));
    $('machCompostBtn').addEventListener('click', () => act({ action: 'compost' }));
    $('machShelf').addEventListener('click', (e) => {
        const eq = e.target.closest('[data-equip]');
        if (eq) { act({ action: 'equip', slot: eq.dataset.equip, id: eq.dataset.id || null }); return; }
        const th = e.target.closest('[data-throw]');
        if (th && T) { T.pick(th.dataset.throw); T.toast('Loaded', `${prize(th.dataset.throw).name} is what you throw now.`); }
    });

    fillDome();
    call().then(s => { state = s; paint(); }).catch(() => { $('machToward').textContent = 'The machine is resting. Reload the page.'; });
    // Spins earned in another tab (or a golden splat) show up when you come back
    document.addEventListener('visibilitychange', () => { if (!document.hidden && !busy) call().then(s => { state = s; paint(); }).catch(() => {}); });
})();
