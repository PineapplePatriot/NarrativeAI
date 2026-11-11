/* 🌻 The garden, live: a pixel-art plot (192×128 pixels, drawn 4× bigger) with plants that grow and sway,
   decorations, gardeners who wander about and work, Bulba in the corner (wearing the hat they won), butterflies by
   day and fireflies by night. Day and night follow this device's clock.
   The server keeps the truth (mainapp/tomato_garden.py); between visits this page grows the plants itself from
   the rate it was told, and asks again every minute. Reduced motion: everything stands still, redrawn once a second. */
(function () {
    const root = document.getElementById('garden');
    const cv = document.getElementById('gCanvas');
    if (!root || !cv) return;
    const URL = root.dataset.state;
    const $ = (id) => document.getElementById(id);
    const CSRF = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
    const W = 192, H = 128, S = 4, T = 16, GX = 32, GY = 40;
    const g = cv.getContext('2d');
    g.imageSmoothingEnabled = false;

    // --- Pixel art: rows of letters, one letter per pixel (palette below), '.' is see-through ---
    const PAL = { k: '#1d1b26', g: '#3f9b3a', G: '#2b6b27', l: '#86cf5e', b: '#7a5232', B: '#4f341f', r: '#e0352b', R: '#9e1f17',
        o: '#f07b1d', O: '#b4550f', y: '#f5cf3a', Y: '#c9971a', w: '#ffffff', c: '#efe9dc', s: '#f1c27d', S: '#c98e5a', u: '#4aa8e8',
        U: '#2a6aa3', n: '#a3acb8', N: '#646d7a', p: '#8e3fb8', P: '#5a2577', t: '#c49155', T: '#8f6331', h: '#e8d28a', H: '#b89a4a', m: '#ff7aa8' };
    const cache = new Map();
    function sprite(name, rows, swap = {}) {
        const key = name + JSON.stringify(swap);
        if (cache.has(key)) return cache.get(key);
        const w = Math.max(...rows.map(r => r.length)), h = rows.length;
        const c = document.createElement('canvas');
        c.width = w; c.height = h;
        const x = c.getContext('2d');
        rows.forEach((row, j) => [...row].forEach((ch, i) => {
            const col = PAL[swap[ch] || ch];
            if (col) { x.fillStyle = col; x.fillRect(i, j, 1, 1); }
        }));
        cache.set(key, c);
        return c;
    }
    const ART = {
        seed: ['.......l........', '......lgl.......', '.....BBBBBB.....', '....BBkBBkBB....'],
        sprout: ['......l...l.....', '.....lgl.lgl....', '......lgggl.....', '........g.......', '.......bgb......'],
        leafy: ['......l.l.......', '.....lglgl......', '..l...lgl...l...', '.lgl...g...lgl..', '..lgl..g..lgl...', '...lgggggggl....',
                '.......g........', '.....lgggl......', '......lgl.......', '.......g........', '......bgb.......'],
        bloom: ['......F.F.......', '.....lgFgl......', '..F...lgl...F...', '.lgl...g...lgl..', '..lgl..g..lgF...', '...lgggggggl....',
                '.......g........', '.....lgggl......', '......lgl.......', '.......g........', '......bgb.......'],
        ripe_seed_tomato: ['......l.l.......', '.....lglgl......', '..l..rrlgl..l...', '.lgl.rRg...lgl..', '..lgl..g.rr.l...',
                '...lgggggrRl....', '.rr....g........', '.rR..lgggl......', '......lgl.......', '.......g........', '......bgb.......'],
        ripe_seed_carrot: ['....l..l..l.....', '...lgl.gl.gl....', '....lglglgl.....', '.....lgggl......', '......ggg.......',
                '.....ooooo......', '.....oOooo......', '......ooo.......', '......bob.......'],
        ripe_seed_sunflower: ['.....yyyyy......', '....yyYYYyy.....', '...yyYBBBYyy....', '...yyYBBBYyy....', '....yyYYYyy.....',
                '.....yyyyy......', '.......g........', '....lg.g........', '.....lgg..gl....', '.......ggl......', '.......g........',
                '.......g........', '......bgb.......'],
        ripe_seed_pumpkin: ['........G.......', '.......Gg..l....', '...ooooGooo.gl..', '..oOooOoooOo....', '.ooOooOoooOoo...',
                '.ooOooOoooOoo...', '..oOooOoooOo....', '...ooooooooo....'],
        gnome: ['....r.....', '...rr.....', '...rrr....', '..rrrrr...', '..sssss...', '..skssk...', '.wwwwwww..', '..wwwww...',
                '..uuuuu...', '.suuuuus..', '..uuuuu...', '..k...k...'],
        bench: ['.SSSSSSSSSSSSSS.', '.bbbbbbbbbbbbbb.', '.SSSSSSSSSSSSSS.', '.bbbbbbbbbbbbbb.', '................', '.SSSSSSSSSSSSSS.',
                '.bbbbbbbbbbbbbb.', '..B..........B..', '..B..........B..'],
        scarecrow: ['......hh......', '.....hHHh.....', '....hhhhhh....', '.....ssss.....', '.....kssk.....', '.....ssss.....',
                '.b.uuuuuuuu.b.', 'bbbbuuuuuubbbb', '.h..uuuuuu..h.', '....uuuuuu....', '......bb......', '......bb......', '......bb......'],
        pond: ['...uuuuuuuuu....', '.uuuUuuuuuuuuu..', 'uuuuuuwwuuuuuUuu', 'uuUuuuuuuuuwuuuu', '.uuuuuuuUuuuuuu.', '...uuuuuuuuuu...'],
        pond2: ['...uuuuuuuuu....', '.uuuuuuuUuuuuu..', 'uuuUuuuuuwwuuuuu', 'uuuuuwuuuuuuuUuu', '.uuuuUuuuuuuuuu.', '...uuuuuuuuuu...'],
        lantern: ['..k...', '.RRRR.', 'RrrrrR', 'RryyrR', 'RrrrrR', '.RRRR.', '..k...'],
        gardener_farmer: ['..hhhhhh..', '.hhhhhhhh.', 'hhHHHHHHhh', '..ssssss..', '..skssks..', '..ssssss..', '..wwwwww..', '...wwww...',
                '.uuUuuUuu.', 'suuuuuuuus', '.uuuuuuuu.'],
        gardener_frog: ['..gg..gg..', '.gwkggwkg.', '.gggggggg.', 'gggggggggg', 'glrrrrrrlg', '.gggggggg.', '.uUuuuuUu.', 'guuuuuuuug', '.uuuuuuuu.'],
        gardener_robot: ['....k.....', '....r.....', '..nnnnnn..', '..nuunun..', '..nnnnnn..', '..nNNNNn..', '...nnnn...', '.nnnnnnnn.',
                'Nn.nyyn.nN', '...nnnn...'],
        gardener_witch: ['....P.....', '...PP.....', '...PPP....', '..PPPPP...', 'PPPPPPPPPP', '..ssssss..', '..skssks..', '..ssssss..',
                '.ppppppp..', 'sppppppps.', '.ppppppp..'],
        bulba: ['...tttttt...', '..tttttttt..', '.ttTtttttTt.', 'tttktttkttt.', 'tttttttttttt', 'ttTttkkkttTt', 'tttttttttttt',
                '.ttttTttttt.', '..tttttttt..', '...tttttt...'],
        bulba_blink: ['...tttttt...', '..tttttttt..', '.ttTtttttTt.', 'tttTtttTttt.', 'tttttttttttt', 'ttTttkkkttTt', 'tttttttttttt',
                '.ttttTttttt.', '..tttttttt..', '...tttttt...'],
        hat_crown: ['y.y.y.y', 'yyyyyyy', 'yryuyry'],
        hat_straw: ['..hhhh..', '..HHHH..', 'hhhhhhhh'],
        hat_top: ['.kkkk.', '.kkkk.', '.rrrr.', 'kkkkkk'],
    };
    const LEGS = {  // two walking frames under each gardener
        gardener_farmer: [['..uu..uu..', '..BB..BB..'], ['...uu.uu..', '...BB.BB..']],
        gardener_frog: [['..uu..uu..', '.gg....gg.'], ['...uu.uu..', '..gg..gg..']],
        gardener_robot: [['...n..n...', '..NN..NN..'], ['...n.n....', '..NN.NN...']],
        gardener_witch: [['..pp..pp..', '..kk..kk..'], ['...pp.pp..', '...kk.kk..']],
    };
    const FLOWER = { seed_tomato: 'y', seed_carrot: 'w', seed_sunflower: 'y', seed_pumpkin: 'y' };
    const HATS = { '👑': 'hat_crown', '👒': 'hat_straw', '🎩': 'hat_top' };
    const LINES = {
        gardener_farmer: ['Back in my day, tomatoes were thrown uphill.', 'Needs more water. Everything needs more water.', 'Good soil, this.'],
        gardener_frog: ['Ribbit. (Professionally.)', 'Basket is ready.', 'This is my job and I love it.'],
        gardener_robot: ['BEEP. WEED DETECTED. (It was a flower.)', 'HARVEST SCHEDULE: OPTIMAL.', 'BOOP.'],
        gardener_witch: ['♪ hmm hmm hmmm ♪', 'Sunflowers gossip, you know.', 'Grow, little one.'],
        bulba: ["I'm not a gardener. I'm a vegetable with opinions.", 'Plant something. I’m bored.', 'Those are my cousins. Be nice.',
                'The pumpkin is judging you. So am I.', 'Throw tomatoes at slow replies. It waters this place.'],
    };

    // --- State from the server, grown on the page between visits ---
    let st = null, gotAt = 0, sel = null, hover = null;
    async function call(body) {
        const resp = await fetch(URL, body ? { method: 'POST', credentials: 'same-origin', body: JSON.stringify(body),
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() } } : { credentials: 'same-origin' });
        const out = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(out.error || 'The garden did not answer. Try again in a moment.');
        return out;
    }
    function take(s) {
        const fresh = !st;
        st = s; gotAt = Date.now();
        syncGardeners();
        paintSide();
        if (fresh) loop();
    }
    const load = () => call().then(take).catch(err => { $('gTile').innerHTML = `<p class="muted">${esc(err.message)}</p>`; });
    function tileAt(x, y) { return st && st.tiles.find(t => t.x === x && t.y === y); }
    function grown(t) {  // progress now, from the server's figure and the time since
        if (t.kind !== 'plant') return 0;
        return Math.min(1, t.progress + t.rate * (Date.now() - gotAt) / 1000);
    }
    const STAGES = [[0.15, 'seed'], [0.4, 'sprout'], [0.7, 'leafy'], [1, 'bloom']];
    const stageOf = (p) => (STAGES.find(([lim]) => p < lim) || [0, 'ripe'])[1];
    const STAGE_WORD = { seed: 'Just planted', sprout: 'Sprouting', leafy: 'Growing', bloom: 'Blooming', ripe: 'Ripe!' };
    const dur = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.ceil((s % 3600) / 60);
        return h ? `${h} h ${m} min` : `${m} min`; };

    // --- Gardeners and critters ---
    const walkers = new Map();
    function syncGardeners() {
        const ids = new Set(st.gardeners.map(x => x.id));
        st.gardeners.forEach((x, i) => { if (!walkers.has(x.id)) walkers.set(x.id, { id: x.id, x: 40 + i * 30, y: 100, tx: 0, ty: 0, wait: 1 + i, frame: 0, flip: false, say: '', sayFor: 0, act: 0 }); });
        [...walkers.keys()].forEach(k => { if (!ids.has(k)) walkers.delete(k); });
    }
    function pickTarget(w) {
        const plants = st.tiles.filter(t => t.kind === 'plant');
        if (plants.length && Math.random() < .55) {
            const t = plants[Math.floor(Math.random() * plants.length)];
            w.tx = GX + t.x * T + 8 + (Math.random() < .5 ? -9 : 9); w.ty = GY + t.y * T + 15; w.goal = 'tend';
        } else { w.tx = 10 + Math.random() * 172; w.ty = 36 + Math.random() * 86; w.goal = 'stroll'; }
    }
    const bits = [];  // droplets, notes, sparks
    function act(w) {
        const n = { gardener_farmer: 5, gardener_witch: 2, gardener_robot: 3, gardener_frog: 0 }[w.id] || 0;
        for (let i = 0; i < n; i++) bits.push({ x: w.x + (w.flip ? -6 : 6), y: w.y - 10, vx: (Math.random() - .5) * 8 + (w.flip ? -8 : 8),
            vy: -10 - Math.random() * 8, life: 1, kind: w.id === 'gardener_farmer' ? 'drop' : w.id === 'gardener_witch' ? 'note' : 'spark' });
        if (w.id === 'gardener_frog') w.hop = 1;
        if (Math.random() < .3) { w.say = LINES[w.id][Math.floor(Math.random() * LINES[w.id].length)]; w.sayFor = 3.2; }
    }
    function step(w, dt) {
        if (w.sayFor > 0) w.sayFor -= dt;
        if (w.hop > 0) w.hop = Math.max(0, w.hop - dt * 2.5);
        if (w.wait > 0) { w.wait -= dt; if (w.wait <= 0) pickTarget(w); return; }
        const dx = w.tx - w.x, dy = w.ty - w.y, d = Math.hypot(dx, dy);
        if (d < 1) { if (w.goal === 'tend') act(w); w.wait = 1.5 + Math.random() * 3; return; }
        const sp = 14 * dt;
        w.x += dx / d * Math.min(sp, d); w.y += dy / d * Math.min(sp, d);
        w.flip = dx < 0;
        w.frame += dt * 6;
    }
    const butterflies = Array.from({ length: 3 }, (_, i) => ({ x: 30 + i * 60, y: 50 + i * 15, ph: i * 2 }));
    const flies = Array.from({ length: 10 }, (_, i) => ({ x: Math.random() * W, y: 40 + Math.random() * 80, ph: i }));
    const STARS = Array.from({ length: 24 }, (_, i) => ({ x: (i * 53) % W, y: 2 + (i * 29) % 22, ph: i }));
    const bulba = { x: 6, y: 104, blink: 0, say: '', sayFor: 0 };

    // --- Time of day ---
    function sky(h) {
        if (h < 5 || h >= 21) return ['#0b1030', '#1c2350', .45];
        if (h < 7) return ['#f6a77a', '#8fb8e8', .12];
        if (h < 18) return ['#6fb6f2', '#cfeaff', 0];
        return ['#f08a5d', '#4b3b78', .2];
    }
    let bg = null, bgHour = -1;
    function background(h) {  // sky, fence, lawn and soil, redrawn when the hour changes
        if (bg && bgHour === h) return bg;
        bgHour = h;
        bg = document.createElement('canvas'); bg.width = W; bg.height = H;
        const b = bg.getContext('2d'), [top, low] = sky(h);
        const grad = b.createLinearGradient(0, 0, 0, 30); grad.addColorStop(0, top); grad.addColorStop(1, low);
        b.fillStyle = grad; b.fillRect(0, 0, W, 30);
        b.fillStyle = '#5aa83a'; b.fillRect(0, 30, W, H - 30);
        let seed = 3; const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
        for (let i = 0; i < 420; i++) { b.fillStyle = rnd() < .5 ? '#4c9431' : '#6cbb47'; b.fillRect(Math.floor(rnd() * W), 30 + Math.floor(rnd() * (H - 30)), 1, 1 + Math.floor(rnd() * 2)); }
        b.fillStyle = '#9a6b3f';  // fence
        for (let x = 2; x < W; x += 10) b.fillRect(x, 20, 3, 13);
        b.fillRect(0, 23, W, 2); b.fillRect(0, 29, W, 2);
        b.fillStyle = '#6e4a2a'; for (let x = 2; x < W; x += 10) b.fillRect(x + 2, 20, 1, 13);
        for (let y = 0; y < (st ? st.rows : 5); y++) for (let x = 0; x < (st ? st.cols : 8); x++) {  // soil patches
            const px = GX + x * T, py = GY + y * T;
            b.fillStyle = '#6b4a2b'; b.fillRect(px + 1, py + 1, 14, 14);
            b.fillStyle = '#5a3d22'; b.fillRect(px + 1, py + 1, 14, 2);
            b.fillStyle = '#7d5834'; for (let r = 5; r < 15; r += 4) b.fillRect(px + 3, py + r, 10, 1);
        }
        return bg;
    }
    function sunMoon(h, m) {
        const day = h >= 6 && h < 20, t = day ? ((h - 6) + m / 60) / 14 : (((h + 4) % 24) + m / 60) / 10;
        const x = 8 + t * 176, y = 18 - Math.sin(t * Math.PI) * 13;
        g.fillStyle = day ? '#ffe680' : '#eef2ff';
        g.beginPath(); g.arc(x, y, day ? 5 : 4, 0, Math.PI * 2); g.fill();
        if (!day) { g.fillStyle = sky(h)[0]; g.beginPath(); g.arc(x + 2, y - 1, 3.4, 0, Math.PI * 2); g.fill(); }
    }

    // --- Drawing ---
    const put = (img, x, y) => g.drawImage(img, Math.round(x), Math.round(y));
    function plantSprite(t, p) {
        const stg = stageOf(p);
        if (stg === 'ripe') return sprite('ripe_' + t.seed, ART['ripe_' + t.seed]);
        if (stg === 'bloom') return sprite('bloom', ART.bloom, { F: FLOWER[t.seed] || 'y' });
        return sprite(stg, ART[stg]);
    }
    function draw(time) {
        const now = new Date(), h = now.getHours(), mi = now.getMinutes(), sec = time / 1000;
        const moving = !calm();
        g.setTransform(S, 0, 0, S, 0, 0);
        g.imageSmoothingEnabled = false;
        g.drawImage(background(h), 0, 0);
        const night = sky(h)[2];
        if (night > .3) STARS.forEach(s => { g.fillStyle = `rgba(255,255,255,${.4 + .5 * Math.abs(Math.sin(sec + s.ph))})`; g.fillRect(s.x, s.y, 1, 1); });
        sunMoon(h, mi);
        // things on the plot, back to front
        const things = [];
        st.tiles.forEach(t => {
            const px = GX + t.x * T, py = GY + t.y * T;
            if (t.kind === 'plant') {
                const p = grown(t), img = plantSprite(t, p);
                const sway = moving && stageOf(p) !== 'seed' && Math.sin(sec * 1.7 + t.x * .9 + t.y) > .55 ? 1 : 0;
                things.push({ y: py + 16, f: () => {
                    put(img, px + (16 - img.width) / 2 + sway, py + 16 - img.height);
                    if (stageOf(p) === 'ripe' && moving && Math.sin(sec * 3 + t.x * 2) > .92) { g.fillStyle = '#fff'; g.fillRect(px + 4 + (t.x * 5) % 8, py + 4, 1, 1); }
                } });
            } else {
                // a decoration stands on grass, not on dug soil
                g.fillStyle = '#5aa83a'; g.fillRect(px + 1, py + 1, 14, 14);
                g.fillStyle = '#6cbb47'; g.fillRect(px + 3, py + 4, 1, 2); g.fillRect(px + 11, py + 9, 1, 2); g.fillRect(px + 6, py + 12, 1, 1);
                const name = t.id === 'pond' && moving && Math.floor(sec) % 2 ? 'pond2' : t.id, img = sprite(name, ART[name] || ART.gnome);
                things.push({ y: py + 16, f: () => put(img, px + (16 - img.width) / 2, py + 15 - img.height) });
            }
        });
        walkers.forEach(w => {
            const body = sprite(w.id, ART[w.id]), legs = LEGS[w.id][moving && w.wait <= 0 ? Math.floor(w.frame) % 2 : 0];
            const leg = sprite(w.id + '_l' + legs[0], legs), hop = Math.sin((w.hop || 0) * Math.PI) * 5;
            things.push({ y: w.y, f: () => {
                g.save();
                const x = Math.round(w.x - 5), y = Math.round(w.y - body.height - leg.height - hop);
                if (w.flip) { g.translate(x * 2 + 10, 0); g.scale(-1, 1); }
                put(body, x, y); put(leg, x, y + body.height);
                g.restore();
            } });
        });
        things.sort((a, b) => a.y - b.y).forEach(t => t.f());
        // Bulba in the corner, in their hat
        const blink = moving && (sec % 4.2) < .15;
        const bimg = sprite(blink ? 'bulba_blink' : 'bulba', blink ? ART.bulba_blink : ART.bulba);
        put(bimg, bulba.x, bulba.y);
        const hat = HATS[st.hat];
        if (hat) { const himg = sprite(hat, ART[hat]); put(himg, bulba.x + (12 - himg.width) / 2 + 1, bulba.y - himg.height + 1); }
        // selection
        [[hover, 'rgba(255,255,255,.55)'], [sel, '#ffe066']].forEach(([s, c]) => {
            if (!s) return; g.strokeStyle = c; g.lineWidth = 1; g.strokeRect(GX + s.x * T + .5, GY + s.y * T + .5, 15, 15);
        });
        // little lives: butterflies by day, fireflies and lantern light by night
        if (moving && night < .3) butterflies.forEach(bf => {
            const x = bf.x + Math.sin(sec * .4 + bf.ph) * 40, y = bf.y + Math.sin(sec * 1.3 + bf.ph) * 8, up = Math.sin(sec * 12 + bf.ph) > 0;
            g.fillStyle = '#ff7aa8'; g.fillRect(x - 1, y - (up ? 1 : 0), 1, up ? 2 : 1); g.fillRect(x + 1, y - (up ? 1 : 0), 1, up ? 2 : 1);
            g.fillStyle = '#1d1b26'; g.fillRect(x, y, 1, 1);
        });
        if (night) { g.fillStyle = `rgba(10, 15, 45, ${night})`; g.fillRect(0, 0, W, H); }
        if (night > .1) {
            g.globalCompositeOperation = 'lighter';
            st.tiles.filter(t => t.id === 'lantern').forEach(t => {
                const cx = GX + t.x * T + 8, cy = GY + t.y * T + 8, rg = g.createRadialGradient(cx, cy, 1, cx, cy, 22);
                rg.addColorStop(0, 'rgba(255,190,90,.55)'); rg.addColorStop(1, 'rgba(255,190,90,0)');
                g.fillStyle = rg; g.fillRect(cx - 22, cy - 22, 44, 44);
            });
            if (moving) flies.forEach(f => {
                const x = (f.x + Math.sin(sec * .3 + f.ph) * 20 + W) % W, y = f.y + Math.cos(sec * .5 + f.ph) * 6, a = .3 + .7 * Math.abs(Math.sin(sec * 2 + f.ph));
                g.fillStyle = `rgba(220, 255, 120, ${a})`; g.fillRect(x, y, 1, 1);
            });
            g.globalCompositeOperation = 'source-over';
        }
        bits.forEach(b => {
            g.fillStyle = b.kind === 'drop' ? '#7cc0ff' : b.kind === 'note' ? '#d7b4ff' : '#ffe066';
            if (b.kind === 'note') { g.fillRect(b.x, b.y, 1, 3); g.fillRect(b.x - 1, b.y + 2, 1, 1); } else g.fillRect(b.x, b.y, 1, b.kind === 'drop' ? 2 : 1);
        });
        // speech bubbles, in normal-size text
        g.setTransform(1, 0, 0, 1, 0, 0);
        walkers.forEach(w => { if (w.sayFor > 0) bubble(w.say, w.x * S, (w.y - 30) * S); });
        if (bulba.sayFor > 0) bubble(bulba.say, (bulba.x + 6) * S + 60, (bulba.y - 4) * S);
        $('gClock').textContent = `${night > .3 ? '🌙' : h < 7 ? '🌅' : h >= 18 ? '🌇' : '☀️'} ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    function bubble(text, x, y) {
        g.font = '600 22px system-ui, -apple-system, "Segoe UI", sans-serif';
        const w = Math.min(g.measureText(text).width, 420) + 24, bx = Math.max(6, Math.min(cv.width - w - 6, x - w / 2)), by = Math.max(6, y - 44);
        g.fillStyle = 'rgba(255,255,255,.95)'; g.strokeStyle = '#1d1b26'; g.lineWidth = 3;
        g.beginPath(); g.roundRect(bx, by, w, 40, 10); g.fill(); g.stroke();
        g.fillStyle = '#1d1b26'; g.textBaseline = 'middle'; g.fillText(text, bx + 12, by + 21, 420);
    }

    let last = 0, raf = 0;
    function loop() {
        cancelAnimationFrame(raf);
        const tick = (time) => {
            if (document.hidden) { raf = requestAnimationFrame(tick); return; }
            const dt = Math.min(.1, (time - last) / 1000 || 0);
            if (calm() && time - last < 1000) { raf = requestAnimationFrame(tick); return; }
            last = time;
            if (!calm()) {
                walkers.forEach(w => step(w, dt));
                for (let i = bits.length - 1; i >= 0; i--) { const b = bits[i]; b.x += b.vx * dt; b.y += b.vy * dt; b.vy += 30 * dt; b.life -= dt; if (b.life <= 0) bits.splice(i, 1); }
                if (bulba.sayFor > 0) bulba.sayFor -= dt;
            }
            draw(time);
            if (sel) paintTileLive();
            raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
    }

    // --- Pointing ---
    function at(e) { const r = cv.getBoundingClientRect(); return { x: (e.clientX - r.left) / r.width * W, y: (e.clientY - r.top) / r.height * H }; }
    function cell(p) { const x = Math.floor((p.x - GX) / T), y = Math.floor((p.y - GY) / T); return st && x >= 0 && y >= 0 && x < st.cols && y < st.rows ? { x, y } : null; }
    cv.addEventListener('pointermove', (e) => { hover = cell(at(e)); });
    cv.addEventListener('pointerleave', () => { hover = null; });
    cv.addEventListener('click', (e) => {
        if (!st) return;
        const p = at(e);
        if (p.x < bulba.x + 14 && p.y > bulba.y - 4) { bulba.say = LINES.bulba[Math.floor(Math.random() * LINES.bulba.length)]; bulba.sayFor = 3.5; return; }
        const w = [...walkers.values()].find(w => Math.abs(w.x - p.x) < 7 && p.y < w.y + 2 && p.y > w.y - 26);
        if (w) { w.say = LINES[w.id][Math.floor(Math.random() * LINES[w.id].length)]; w.sayFor = 3.2; return; }
        sel = cell(p);
        paintTile();
    });

    // --- The side panel ---
    const prizeOf = (id) => (st.prizes[id] || { name: id, emoji: '❔' });
    let tileKey = '';
    function paintTile() {
        const box = $('gTile');
        tileKey = '';
        if (!sel) { box.innerHTML = '<p class="muted">Tap a patch of soil to plant something, or a plant to see how it\'s doing.</p>'; return; }
        const t = tileAt(sel.x, sel.y);
        if (!t) {
            const seeds = Object.keys(st.basket).filter(k => st.crops[k]), decor = Object.keys(st.basket).filter(k => !st.crops[k]);
            box.innerHTML = `<h3>An empty patch</h3>${seeds.length ? `<div class="g-small muted">Plant</div><div class="g-row">${seeds.map(k =>
                `<button type="button" class="na-btn" data-do="plant" data-id="${k}">${prizeOf(k).emoji} ${esc(st.crops[k].name)} ×${st.basket[k]}</button>`).join('')}</div>` : ''}
                ${decor.length ? `<div class="g-small muted">Place</div><div class="g-row">${decor.map(k =>
                `<button type="button" class="na-btn" data-do="place" data-id="${k}">${prizeOf(k).emoji} ${esc(prizeOf(k).name)}</button>`).join('')}</div>` : ''}
                ${!seeds.length && !decor.length ? '<p class="muted">Your basket is empty. The Sauce-o-Matic gives out seeds and decorations.</p>' : ''}`;
            return;
        }
        if (t.kind === 'decor') {
            box.innerHTML = `<h3>${prizeOf(t.id).emoji} ${esc(prizeOf(t.id).name)}</h3><div class="g-row">
                <button type="button" class="na-btn" data-do="remove">Back to the basket</button></div>`;
            return;
        }
        box.innerHTML = `<h3>${prizeOf(t.seed).emoji} ${esc(t.name)}</h3><div id="gLive"></div>`;
        paintTileLive();
    }
    function paintTileLive() {
        const t = sel && tileAt(sel.x, sel.y), live = $('gLive');
        if (!t || t.kind !== 'plant' || !live) return;
        const p = grown(t), stg = stageOf(p), key = `${stg}|${Math.floor(p * 1000)}`;
        if (key === tileKey) return;
        tileKey = key;
        const left = (1 - p) / t.rate, yieldN = st.crops[t.seed].compost + (st.gardeners.some(x => x.id === 'gardener_frog') ? 1 : 0);
        live.innerHTML = `<div>${STAGE_WORD[stg]} · ${Math.floor(p * 100)}%</div><div class="g-bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div>
            <div class="g-small muted">${stg === 'ripe' ? 'Ready to pick.' : `Ripe in about ${dur(left)}, sooner while you chat.`}</div>
            <div class="g-row">${stg === 'ripe' ? `<button type="button" class="na-btn na-primary" data-do="harvest">🧺 Harvest: ♻ +${yieldN} compost</button>` : ''}
            <button type="button" class="na-btn" data-do="dig">Dig it up</button></div>`;
    }
    $('gTile').addEventListener('click', async (e) => {
        const b = e.target.closest('[data-do]');
        if (!b || !sel) return;
        const action = b.dataset.do;
        if (action === 'dig' && window.NADialog && !await NADialog.confirm('Dig it up? The seed is lost.', { title: 'Dig it up', ok: 'Dig it up', danger: true })) return;
        b.disabled = true;
        try {
            take(await call({ action, x: sel.x, y: sel.y, id: b.dataset.id || undefined }));
            if (action === 'harvest') burstAt(sel);
            paintTile();
        } catch (err) { if (window.NADialog) NADialog.alert(err.message); b.disabled = false; }
    });
    function burstAt(c) {
        for (let i = 0; i < 14; i++) bits.push({ x: GX + c.x * T + 8, y: GY + c.y * T + 6, vx: (Math.random() - .5) * 30, vy: -15 - Math.random() * 20, life: 1, kind: 'spark' });
    }
    function paintSide() {
        $('gCompost').textContent = `♻ ${st.compost} compost`;
        const items = Object.entries(st.basket);
        $('gBasket').innerHTML = items.length ? `<div class="g-basket">${items.map(([k, n]) => `<div>${prizeOf(k).emoji} ${esc(st.crops[k] ? st.crops[k].name + ' seeds' : prizeOf(k).name)} <b>×${n}</b></div>`).join('')}</div>`
            : '<p class="muted g-small">Empty. Seeds and decorations come from the Sauce-o-Matic.</p>';
        $('gBasket').insertAdjacentHTML('beforeend', `<p class="muted g-small">Each tomato you throw at a chat or Bulba waters every plant: ${Math.round(st.water / 60)} minutes of growth.</p>`);
        $('gGardeners').innerHTML = st.gardeners.length ? st.gardeners.map(x => `<div class="g-gard"><span class="e">${prizeOf(x.id).emoji}</span><div><b>${esc(prizeOf(x.id).name)}</b><br><span class="muted">${esc(x.about)}</span></div></div>`).join('')
            : '<p class="muted g-small">None yet. Gardeners are the Sauce-o-Matic\'s legendaries: each one moves in and helps.</p>';
        $('gLog').innerHTML = st.log.length ? st.log.map(l => `<li>${esc(l.text)} <span class="muted">${new Date(l.at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></li>`).join('')
            : '<li class="muted">Nothing yet.</li>';
        if (sel) paintTile();
    }

    load();
    setInterval(() => { if (!document.hidden) load(); }, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && st) load(); });
})();
