/* 🍅 The tomato: a long wait (a slow reply, a long Bulba turn, a book job) shows a tomato to throw at the screen.
   Each throw lands on a random spot and splats for a moment. Throw enough and the secret Tomato Pit opens: a page
   for throwing as many as you like, with achievements and skins (colours, vegetables, objects) and a share card.
   Progress is kept on the account (tomatoes/state/): this browser keeps a copy and sends what it threw since the
   last sync every few seconds, so two devices add up instead of overwriting each other.
   Pages say when they're waiting: NATomato.watch(() => isWaiting). */
(function () {
    if (window.NATomato) return;
    const PIT = (document.currentScript && document.currentScript.dataset.pit) || '';
    const SHOW_AFTER = 10;   // seconds of waiting before the tomato shows up
    const LINGER = 5;        // seconds it stays after the wait ends (so it doesn't vanish under the cursor)
    const KEY = 'na-tomatoes';
    const PENDING = 'na-tomatoes-pending';  // thrown here, not yet on the account
    const STATE = (document.currentScript && document.currentScript.dataset.state) || '';
    const CSRF = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';

    // --- Skins: colours, vegetables, objects. `at`: total throws to unlock; `ach`: an achievement unlocks it ---
    const SKINS = [
        { id: 'tomato', name: 'Tomato', emoji: '🍅', color: '#e0352b', at: 0, kind: 'Colours' },
        { id: 'green', name: 'Green tomato', emoji: '🍅', filter: 'hue-rotate(95deg) saturate(1.2)', color: '#5aa83a', at: 25, kind: 'Colours' },
        { id: 'golden', name: 'Golden tomato', emoji: '🍅', filter: 'hue-rotate(38deg) saturate(1.6) brightness(1.15)', color: '#f2b72c', at: 75, kind: 'Colours' },
        { id: 'heirloom', name: 'Purple heirloom', emoji: '🍅', filter: 'hue-rotate(275deg) saturate(1.1)', color: '#8e3fb8', at: 150, kind: 'Colours' },
        { id: 'ghost', name: 'Ghost tomato', emoji: '🍅', filter: 'grayscale(1) brightness(1.6) opacity(.75)', color: '#dfe6ee', at: 400, kind: 'Colours' },
        { id: 'carrot', name: 'Carrot', emoji: '🥕', color: '#f07b1d', at: 50, kind: 'Vegetables' },
        { id: 'eggplant', name: 'Eggplant', emoji: '🍆', color: '#6b2f87', at: 100, kind: 'Vegetables' },
        { id: 'broccoli', name: 'Broccoli', many: 'Broccoli', emoji: '🥦', color: '#3f9b3a', at: 200, kind: 'Vegetables' },
        { id: 'corn', name: 'Corn', many: 'Corncobs', emoji: '🌽', color: '#f5cf3a', at: 300, kind: 'Vegetables' },
        { id: 'pepper', name: 'Chili', many: 'Chilies', emoji: '🌶️', color: '#d4231c', at: 500, kind: 'Vegetables' },
        { id: 'onion', name: 'Onion', emoji: '🧅', color: '#e9c9a8', at: 750, kind: 'Vegetables' },
        { id: 'potato', name: 'Potato', emoji: '🥔', color: '#b98a4e', at: 1000, kind: 'Vegetables', note: "Bulba's cousin. Bulba is not amused." },
        { id: 'egg', name: 'Egg', emoji: '🥚', color: '#f7e27a', ach: 'patient', kind: 'Objects' },
        { id: 'pie', name: 'Cream pie', emoji: '🥧', color: '#f6ecd2', ach: 'night', kind: 'Objects' },
        { id: 'balloon', name: 'Water balloon', emoji: '🎈', color: '#4aa8e8', ach: 'rage', kind: 'Objects' },
        { id: 'sock', name: 'Old sock', emoji: '🧦', color: '#9aa3ad', at: 1500, kind: 'Objects' },
        { id: 'fish', name: 'Fish', many: 'Fish', emoji: '🐟', color: '#6f9fc2', at: 2500, kind: 'Objects' },
        { id: 'floppy', name: 'Floppy disk', emoji: '💾', color: '#3a4250', at: 5000, kind: 'Objects' },
        { id: 'trophy', name: 'Trophy', emoji: '🏆', color: '#e8b923', at: 10000, kind: 'Objects' },
        { id: 'star', name: 'Lucky star', emoji: '🌟', color: '#ffe066', ach: 'lucky', kind: 'Objects' },
    ];

    const ACHIEVEMENTS = [
        { id: 'first', name: 'First blood', about: 'Threw your first tomato.' },
        { id: 'pit', name: 'Down the pit', about: 'Found the Tomato Pit.' },
        { id: 'hundred', name: 'Sauce', about: '100 tomatoes.' },
        { id: 'thousand', name: 'Passata', about: '1,000 tomatoes.' },
        { id: 'tenk', name: 'Salad bar', about: '10,000 tomatoes. Please go outside.' },
        { id: 'patient', name: 'Patient critic', about: 'Threw something during 10 real waits.', unlocks: 'egg' },
        { id: 'long', name: 'Long haul', about: 'Kept throwing through a wait over a minute.' },
        { id: 'rage', name: 'Rage', about: '30 throws in 10 seconds.', unlocks: 'balloon' },
        { id: 'berserk', name: 'Berserk', about: '60 throws in 10 seconds. Is your hand okay?' },
        { id: 'night', name: 'Night owl', about: 'Threw between 2 and 5 in the morning.', unlocks: 'pie' },
        { id: 'regular', name: 'Regular', about: 'Threw on 7 different days.' },
        { id: 'collector', name: 'Collector', about: 'Unlocked 10 skins.' },
        { id: 'lucky', name: 'Lucky splat', about: 'A one-in-500 golden splat.', unlocks: 'star' },
    ];

    const css = `
.na-tom-btn { position: fixed; right: 12px; top: 42%; z-index: 9000; display: flex; align-items: center; gap: 8px;
    background: rgba(20, 22, 34, .92); color: #f1f5f9; border: 1px solid rgba(255,255,255,.15); border-radius: 999px;
    padding: 6px 14px 6px 6px; box-shadow: 0 8px 24px rgba(0,0,0,.4); font: inherit; font-size: .85rem; cursor: pointer;
    animation: naTomIn .35s cubic-bezier(.2,1.6,.4,1); transition: opacity .4s; }
.na-tom-btn .na-tom-face { font-size: 1.9rem; line-height: 1; display: inline-block; transition: transform .1s; }
.na-tom-btn:active .na-tom-face { transform: scale(.85) rotate(-15deg); }
.na-tom-btn small { opacity: .7; display: block; font-size: .72rem; }
.na-tom-btn.thrown .na-tom-line { display: none; }  /* after the first throw: just the tomato and the count */
@media (max-width: 600px) { .na-tom-btn { max-width: 58vw; } .na-tom-btn .na-tom-line { font-size: .78rem; } }
.na-tom-btn.fading { opacity: 0; pointer-events: none; }
.na-tom-pit-link { position: fixed; right: 12px; top: calc(42% - 54px); z-index: 9000; background: #7c3aed; color: #fff; padding: 8px 14px;
    border-radius: 12px; text-decoration: none; font-size: .85rem; box-shadow: 0 8px 24px rgba(0,0,0,.4); animation: naTomIn .4s ease-out; }
.na-tom-fly { position: fixed; z-index: 9001; pointer-events: none; font-size: 2rem; line-height: 1; will-change: transform;
    transition: transform .32s cubic-bezier(.3,.1,.6,1); }
.na-tom-splat { position: fixed; z-index: 8999; pointer-events: none; width: 120px; height: 120px; margin: -60px 0 0 -60px;
    animation: naTomSplat 1.5s ease-out forwards; }
.na-tom-splat .na-tom-bit { position: absolute; left: 50%; top: 50%; font-size: 1.6rem; transform: translate(-50%,-50%) rotate(var(--r)); opacity: .85; }
.na-tom-toasts { position: fixed; left: 50%; top: 18px; transform: translateX(-50%); z-index: 9002; display: flex;
    flex-direction: column; align-items: center; gap: 8px; pointer-events: none; width: max-content; max-width: calc(100vw - 32px); }
.na-tom-toast { background: rgba(20,22,34,.95);
    color: #f8fafc; border: 1px solid rgba(255,255,255,.18); border-radius: 12px; padding: 10px 16px; font-size: .9rem;
    box-shadow: 0 10px 30px rgba(0,0,0,.45); animation: naTomToast 3.2s ease-in-out forwards; pointer-events: none; text-align: center; }
.na-tom-toast b { display: block; }
@keyframes naTomIn { from { transform: scale(.4) translateY(30px); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes naTomSplat { 0% { transform: scale(.3); opacity: 1; } 12% { transform: scale(1.08); } 20% { transform: scale(1); opacity: 1; }
    100% { transform: scale(1.04) translateY(14px); opacity: 0; } }
@keyframes naTomToast { 0% { opacity: 0; transform: translateY(-10px); } 10%, 85% { opacity: 1; transform: none; }
    100% { opacity: 0; transform: translateY(-6px); } }
@media (prefers-reduced-motion: reduce) { .na-tom-btn, .na-tom-pit-link { animation: none; } .na-tom-fly { transition: none; }
    .na-tom-splat { animation: naTomFade .9s linear forwards; } }
@keyframes naTomFade { from { opacity: 1; } to { opacity: 0; } }`;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    // --- What's kept: the account's state, a copy here, and the throws not yet sent ---
    const read = (k) => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } };
    const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private window */ } };
    const blank = () => ({ count: 0, skin: 'tomato', ach: {}, days: [], waits: 0, found: false, best10: 0 });
    let data = Object.assign(blank(), read(KEY) || {});
    let pending = Object.assign({ add: 0, add_waits: 0 }, read(PENDING) || {});
    if (STATE && !data.synced && data.count) {  // kept only in this browser before: it goes to the account once
        pending.add += data.count;
        pending.add_waits += data.waits || 0;
    }
    function save() { write(KEY, data); write(PENDING, pending); }

    function merge(server) {  // the account's state plus what's still on its way there
        const ach = Object.assign({}, data.ach, server.ach || {});
        data = Object.assign(blank(), server, {
            count: (server.count || 0) + pending.add, waits: (server.waits || 0) + pending.add_waits,
            ach, days: [...new Set([...(server.days || []), ...data.days])].slice(-30),
            best10: Math.max(server.best10 || 0, data.best10 || 0), found: !!(server.found || data.found),
            skin: pending.skin || server.skin || data.skin, synced: true,
        });
        save();
        changed();
    }
    let syncTimer = null, syncing = false;
    function later() { clearTimeout(syncTimer); syncTimer = setTimeout(sync, 3000); }
    async function sync(leaving = false) {
        if (!STATE || syncing) return;
        clearTimeout(syncTimer);
        const sent = pending;
        pending = { add: 0, add_waits: 0 };
        save();
        const body = { add: sent.add, add_waits: sent.add_waits, ach: data.ach, days: data.days, best10: data.best10,
                       found: data.found, ...(sent.skin ? { skin: sent.skin } : {}) };
        syncing = true;
        try {
            const resp = await fetch(STATE, { method: 'POST', keepalive: leaving, credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() }, body: JSON.stringify(body) });
            if (!resp.ok) throw new Error('not saved');
            if (!leaving) merge(await resp.json());
        } catch (e) {  // not saved: it goes with the next sync
            pending = { add: pending.add + sent.add, add_waits: pending.add_waits + sent.add_waits,
                        ...(pending.skin || sent.skin ? { skin: pending.skin || sent.skin } : {}) };
            save();
        } finally { syncing = false; }
    }
    addEventListener('pagehide', () => { if (pending.add || pending.add_waits || pending.skin) sync(true); });
    document.addEventListener('visibilitychange', () => { if (document.hidden && (pending.add || pending.skin)) sync(true); });

    const skin = (id = data.skin) => SKINS.find(s => s.id === id) || SKINS[0];
    const unlocked = s => (s.ach ? !!data.ach[s.ach] : data.count >= s.at);
    const listeners = [];
    const changed = () => listeners.forEach(fn => { try { fn(data); } catch (e) { /* a page's own problem */ } });

    function toast(title, text) {
        const t = document.createElement('div');
        t.className = 'na-tom-toast';
        t.innerHTML = `<b></b><span></span>`;
        t.querySelector('b').textContent = title;
        t.querySelector('span').textContent = text || '';
        let stack = document.querySelector('.na-tom-toasts');  // several at once (an achievement and a skin) stack up
        if (!stack) { stack = document.createElement('div'); stack.className = 'na-tom-toasts'; document.body.appendChild(stack); }
        stack.appendChild(t);
        setTimeout(() => t.remove(), 3300);
    }

    function award(id) {
        if (data.ach[id]) return;
        const a = ACHIEVEMENTS.find(x => x.id === id);
        data.ach[id] = Date.now();
        const s = a.unlocks && SKINS.find(x => x.id === a.unlocks);
        toast('🏅 ' + a.name, a.about + (s ? ` Unlocked: ${s.emoji} ${s.name}.` : ''));
    }

    // --- One throw: a flight from `from` (or nowhere) to a random spot, then a splat that fades fast ---
    const recent = [];
    let waitThrows = 0;
    function spot() {
        const m = 50;
        return { x: m + Math.random() * Math.max(1, innerWidth - 2 * m), y: m + Math.random() * Math.max(1, innerHeight - 2 * m) };
    }
    function splat(x, y, s, lucky) {
        const el = document.createElement('div');
        el.className = 'na-tom-splat';
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        const color = lucky ? '#ffd23f' : s.color;
        const drops = Array.from({ length: 7 }, () => {
            const a = Math.random() * Math.PI * 2, r = 30 + Math.random() * 26, size = 4 + Math.random() * 9;
            return `<circle cx="${60 + Math.cos(a) * r}" cy="${60 + Math.sin(a) * r}" r="${size}"/>`;
        }).join('');
        const blob = Array.from({ length: 10 }, (_, i) => {
            const a = i / 10 * Math.PI * 2, r = 22 + Math.random() * 14;
            return `${60 + Math.cos(a) * r},${60 + Math.sin(a) * r}`;
        }).join(' ');
        el.innerHTML = `<svg viewBox="0 0 120 120" width="120" height="120" aria-hidden="true"><g fill="${color}" opacity=".9">
            <polygon points="${blob}" stroke="${color}" stroke-width="10" stroke-linejoin="round"/>${drops}</g></svg>
            <span class="na-tom-bit" style="--r:${Math.round(Math.random() * 360)}deg;${s.filter ? 'filter:' + s.filter : ''}">${s.emoji}</span>`;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 1600);
    }
    function throwOne(from) {
        const s = skin();
        const to = spot();
        const lucky = Math.random() < 1 / 500;
        const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (from && !reduce) {
            const fly = document.createElement('div');
            fly.className = 'na-tom-fly';
            fly.textContent = s.emoji;
            if (s.filter) fly.style.filter = s.filter;
            fly.style.left = (from.x - 16) + 'px';
            fly.style.top = (from.y - 16) + 'px';
            document.body.appendChild(fly);
            requestAnimationFrame(() => requestAnimationFrame(() => {
                fly.style.transform = `translate(${to.x - from.x}px, ${to.y - from.y}px) rotate(${Math.random() > .5 ? '' : '-'}540deg)`;
            }));
            setTimeout(() => { fly.remove(); splat(to.x, to.y, s, lucky); }, 330);
        } else {
            splat(to.x, to.y, s, lucky);
        }
        count(lucky);
    }

    function count(lucky) {
        const before = SKINS.filter(unlocked).length;
        data.count++;
        pending.add++;
        const now = Date.now();
        recent.push(now);
        while (recent.length && now - recent[0] > 10000) recent.shift();
        data.best10 = Math.max(data.best10 || 0, recent.length);
        const day = new Date().toISOString().slice(0, 10);
        if (!data.days.includes(day)) data.days = [...data.days, day].slice(-30);
        if (waiting) {
            if (!waitThrows) { data.waits++; pending.add_waits++; }
            waitThrows++;
        }
        award('first');
        if (data.count >= 100) award('hundred');
        if (data.count >= 1000) award('thousand');
        if (data.count >= 10000) award('tenk');
        if (data.waits >= 10) award('patient');
        if (waiting && waited >= 60) award('long');
        if (recent.length >= 30) award('rage');
        if (recent.length >= 60) award('berserk');
        const h = new Date().getHours();
        if (h >= 2 && h < 5) award('night');
        if (data.days.length >= 7) award('regular');
        if (lucky) award('lucky');
        const after = SKINS.filter(unlocked);
        if (after.length >= 10) award('collector');
        if (after.length > before) {
            const fresh = after.filter(s => !s.ach && s.at === data.count)[0];
            if (fresh) toast('New skin: ' + fresh.emoji + ' ' + fresh.name, PIT ? 'Pick it in the Tomato Pit.' : '');
        }
        if (!data.found && PIT && data.count >= 10) showPitLink();
        save();
        changed();
        later();
    }

    // --- The tomato that shows up during a long wait ---
    const LINES = ['Slow, huh? Throw a tomato.', 'Go on. Nobody is watching.', "Bulba won't take it personally.",
                   'Waiting builds character. Tomatoes help.', 'Express your feedback. Visually.'];
    const watchers = [];
    let waiting = false, waited = 0, idle = 0, btn = null, pitLink = null;
    function showButton() {
        if (btn) { btn.classList.remove('fading'); return; }
        btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'na-tom-btn';
        btn.setAttribute('aria-label', 'Throw a tomato');
        btn.innerHTML = `<span class="na-tom-face"></span><span><span class="na-tom-line"></span><small></small></span>`;
        btn.querySelector('.na-tom-line').textContent = LINES[Math.floor(Math.random() * LINES.length)];
        paintButton();
        btn.addEventListener('click', () => {
            const r = btn.querySelector('.na-tom-face').getBoundingClientRect();
            throwOne({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
            btn.classList.add('thrown');
            paintButton();
        });
        document.body.appendChild(btn);
    }
    function paintButton() {
        if (!btn) return;
        const s = skin(), face = btn.querySelector('.na-tom-face');
        face.textContent = s.emoji;
        face.style.filter = s.filter || '';
        btn.querySelector('small').textContent = data.count ? `${data.count.toLocaleString()} thrown` : 'Click to throw';
    }
    function hideButton() {
        if (!btn) return;
        btn.classList.add('fading');
        const gone = btn;
        btn = null;
        setTimeout(() => gone.remove(), 450);
        if (pitLink) { pitLink.remove(); pitLink = null; }
    }
    function showPitLink() {
        if (pitLink || !btn) return;
        pitLink = document.createElement('a');
        pitLink.className = 'na-tom-pit-link';
        pitLink.href = PIT;
        pitLink.target = '_top';
        pitLink.textContent = '🕳️ You found something: the Tomato Pit →';
        document.body.appendChild(pitLink);
    }
    setInterval(() => {
        const now = watchers.some(fn => { try { return !!fn(); } catch (e) { return false; } });
        if (now) {
            if (!waiting) { waiting = true; waited = 0; waitThrows = 0; }
            waited++;
            idle = 0;
            if (waited >= SHOW_AFTER) showButton();
        } else if (waiting || btn) {
            waiting = false;
            if (++idle >= LINGER) hideButton();
        }
    }, 1000);

    // The account's state when a page opens (the pit always; elsewhere only once tomatoes have been thrown here)
    function fetchState() {
        if (!STATE) return;
        fetch(STATE, { credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)).then(st => {
            if (!st) return;
            if (pending.add || pending.add_waits || pending.skin) sync(); else merge(st);
        }).catch(() => { /* offline: the copy here will do */ });
    }
    if (PIT && location.pathname === PIT) fetchState();
    else if (data.count || pending.add) setTimeout(fetchState, 1500);

    window.NATomato = {
        SKINS, ACHIEVEMENTS,
        watch(fn) { watchers.push(fn); },
        throwOne, toast, unlocked,
        data: () => data,
        skin,
        pick(id) { const s = SKINS.find(x => x.id === id); if (s && unlocked(s)) { data.skin = pending.skin = id; save(); changed(); paintButton(); sync(); } },
        found() { if (!data.found) { data.found = true; award('pit'); save(); changed(); sync(); } },
        onChange(fn) { listeners.push(fn); },
    };
})();
