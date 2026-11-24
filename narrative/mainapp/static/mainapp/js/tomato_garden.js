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
    const W = 256, H = 144, S = 4, T = 16, GX = 32, GY = 40;  // the plot on the left, the cottage on the right
    const g = cv.getContext('2d');
    g.imageSmoothingEnabled = false;

    // --- Pixel art: rows of letters, one letter per pixel (palette below), '.' is see-through ---
    const PAL = { k: '#1d1b26', g: '#3f9b3a', G: '#2b6b27', l: '#86cf5e', b: '#7a5232', B: '#4f341f', r: '#e0352b', R: '#9e1f17',
        o: '#f07b1d', O: '#b4550f', y: '#f5cf3a', Y: '#c9971a', w: '#ffffff', c: '#efe9dc', s: '#f1c27d', S: '#c98e5a', u: '#4aa8e8',
        q: '#8fe3dc', Q: '#3f9fa6', U: '#2a6aa3', n: '#a3acb8', N: '#646d7a', p: '#8e3fb8', P: '#5a2577', t: '#c49155', T: '#8f6331', h: '#e8d28a', H: '#b89a4a', m: '#ff7aa8' };
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
        // Mr. Death (Lantern Night): a black hood, a polite skull, a little lantern; the scythe leans on his shoulder
        gardener_death: ['.n.kkkkk..', 'nnkkkkkkk.', '.nkkcccck.', '.nkckcckk.', '.nkccccck.', '.nkkcwcck.', 'n.kkkkkkk.',
                'n.kkkkkkkk', 'nkkkkkkkky', 'n.kkkkkkk.', 'n.kkkkkkk.'],
        // First Snow: a snowman (coal smile, carrot nose, a red scarf) and Babbo Natale (red cap with a white bobble,
        // a big white beard, a red coat and a black belt)
        snowman: ['....kkkk....', '....kkkk....', '...kkkkkk...', '....wwww....', '...wkwwkw...', '...wwwoow...', '...wkkkkw...',
                '..rrrrrrrr..', '....wwwwRr..', '.b.wwwwwwwb.', '..bwwkwwwb..', '..wwwwwwww..', '..wwwkwwww..', '...wwwwww...'],
        gardener_babbo: ['.......w..', '....rrrr..', '...rrrrr..', '..rrrrrr..', '.wwwwwwww.', '..ssssss..', '..skssks..', '.wwssssww.',
                '.wwwwwwww.', '..wwwwww..', '.rrwwwwrr.', 'srrrrrrrrs', '.kkkyykkk.', '.rrrrrrrr.'],
        // 🏡 The cottage's visitors: Il Dattore (pale teal hair, a dark mask across the eyes, a long white coat with dark
        // feathers at the collar) and Pantaleone (black hair with a violet streak, little glasses, a fur collar, a
        // black coat lined in violet, a gold coin pin)
        visitor_dattore: ['...qqqq...', '..qqqqqq..', '.qqQqqqQq.', '.qkkrrkkq.', '.qssssssq.', '..ssssss..', '.kkUUUUkk.',
                'kwwwUUwwwk', '.wwwyywww.', 'swwwUUwwws', '.wwwwwwww.', '.wwkwwkww.'],
        visitor_pantaleone: ['...kkkk...', '..kkkkkk..', '.kkpkkkkk.', '.kssssssk.', '.knnssnnk.', '..ssssss..', '.NNNNNNNN.',
                'kPpkkkkpPk', 'kPpkyykpPk', 'sPpkkkkpPs', '.Ppkkkkpp.', '.PP.kk.PP.'],
        ripe_seed_monster: ['..p.....p.......', '.pPp...pPp......', 'pPmPp.pPmPp.....', '.pPPPpPPPp......', '..pPwkwkPp......',
                '..pPkkkkPp......', '..pPwkwkPp......', '...pPPPPp.......', '....g..g........', '..lgg..gg.l.....', '.lgl..g..lgl....',
                '..l...g...l.....', '......g.........', '.....bgb........'],
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
        gardener_death: [['.n.k..k...', '.n.k..k...'], ['.n..k.k...', '.n..k.k...']],
        gardener_babbo: [['..rr..rr..', '..kk..kk..'], ['...rr.rr..', '...kk.kk..']],
        visitor_dattore: [['..kk..kk..', '..kk..kk..'], ['...kk.kk..', '...kk.kk..']],
        visitor_pantaleone: [['..kk..kk..', '..PP..PP..'], ['...kk.kk..', '...PP.PP..']],
    };
    const FLOWER = { seed_tomato: 'y', seed_carrot: 'w', seed_sunflower: 'y', seed_pumpkin: 'y', seed_monster: 'm' };
    // 🧬 A mutation looks like one from the sprout on: its leaves tinted (leaf), its ripe crop recoloured (ripe), its
    // flower (flower), a little effect (fx: glow, sparkle, stripes, legs, wink, face, zz, hat, twin) and a size (scale)
    const VARIANT = {
        heart_tomato: { leaf: { g: 'G' }, flower: 'm', ripe: { r: 'm', R: 'r' }, fx: 'hearts' },
        stripy_tomato: { leaf: { l: 'h' }, flower: 'y', ripe: { R: 'y' }, fx: 'stripes' },
        golden_tomato: { leaf: { l: 'y', g: 'Y' }, flower: 'y', ripe: { r: 'y', R: 'Y' }, fx: 'glow', glow: '255,214,90' },
        twin_carrot: { leaf: { l: 'g' }, flower: 'w', ripe: {}, fx: 'twin' },
        purple_carrot: { leaf: { l: 'm' }, flower: 'p', ripe: { o: 'p', O: 'P' } },
        legs_carrot: { leaf: { g: 'G' }, flower: 'w', ripe: {}, fx: 'legs' },
        giant_sunflower: { leaf: {}, flower: 'y', ripe: {}, scale: 1.35 },
        night_sunflower: { leaf: { l: 'q', g: 'Q' }, flower: 'q', ripe: { y: 'q', Y: 'Q', B: 'U' }, fx: 'glow', glow: '143,227,220', night: true },
        winking_sunflower: { leaf: {}, flower: 'y', ripe: {}, fx: 'wink' },
        giant_pumpkin: { leaf: {}, flower: 'y', ripe: {}, scale: 1.4 },
        smiling_pumpkin: { leaf: {}, flower: 'o', ripe: {}, fx: 'face' },
        glass_pumpkin: { leaf: { l: 'q', g: 'Q' }, flower: 'q', ripe: { o: 'q', O: 'Q' }, fx: 'sparkle', alpha: .75 },
        glowing_monster: { leaf: { l: 'q' }, flower: 'm', ripe: {}, fx: 'glow', glow: '255,122,168' },
        sleepy_monster: { leaf: { l: 'n', g: 'N' }, flower: 'p', ripe: { m: 'n' }, fx: 'zz' },
        polite_monster: { leaf: {}, flower: 'm', ripe: {}, fx: 'hat' },
    };
    const HATS = { '👑': 'hat_crown', '👒': 'hat_straw', '🎩': 'hat_top' };
    const LINES = {
        gardener_farmer: ['Back in my day, tomatoes were thrown uphill.', 'Needs more water. Everything needs more water.', 'Good soil, this.'],
        gardener_frog: ['Ribbit. (Professionally.)', 'Basket is ready.', 'This is my job and I love it.'],
        gardener_robot: ['BEEP. WEED DETECTED. (It was a flower.)', 'HARVEST SCHEDULE: OPTIMAL.', 'BOOP.'],
        gardener_witch: ['♪ hmm hmm hmmm ♪', 'Sunflowers gossip, you know.', 'Grow, little one.'],
        gardener_death: ['Everything ripens in its time. I simply wait.', 'Lovely evening for it.', 'No, the flower bites. That is normal.',
                         'I collect only what is due. Compost, mostly.'],
        gardener_babbo: ['Ho ho... no. Buon Natale!', 'Not that one. The other one. The better-dressed one.',
                         'A present for the shed. Do not shake it.', 'Mamma mia, this soil is frozen.', 'Panettone after the harvest, sì?'],
        visitor_dattore: ['Hm. This wall would be improved by a small reactor.', 'Do not touch the lightning rod. It bites.',
                          'Measure twice, cut once, electrify thrice.', 'Pantaleone calls it “a cottage”. I call it “phase one”.',
                          'Hand me the screwdriver. No, the other screwdriver. The one that hums.'],
        visitor_pantaleone: ['Every brick has a receipt. Every receipt has a brick.', 'Is that… a second lightning rod?',
                             'Lovely. Expensive, but lovely.', 'I am not here. I am auditing.', 'Bulba, stop eating the invoices.'],
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
    const dur = (s) => { const all = Math.max(1, Math.ceil(Math.max(0, s) / 60)), h = Math.floor(all / 60), m = all % 60;
        return h ? (m ? `${h} h ${m} min` : `${h} h`) : `${m} min`; };

    // --- Gardeners and critters ---
    const walkers = new Map();
    function syncGardeners() {
        // the cottage's visitors: Il Dattore while he's building it (and on the porch after); Pantaleone for a day after a scene
        const hs = st.house || {}, recent = hs.scene && hs.scene.at && (Date.now() / 1000 - hs.scene.at) < 86400;
        const people = [...st.gardeners, ...(hs.stage !== undefined ? [{ id: 'visitor_dattore', visitor: true }] : []),
                        ...(recent ? [{ id: 'visitor_pantaleone', visitor: true }] : [])];
        const ids = new Set(people.map(x => x.id));
        people.forEach((x, i) => { if (!walkers.has(x.id)) walkers.set(x.id, { id: x.id, visitor: !!x.visitor, x: x.visitor ? 200 + i * 6 : 40 + i * 30, y: x.visitor ? 118 : 100, tx: 0, ty: 0, wait: 1 + i, frame: 0, flip: false, say: '', sayFor: 0, act: 0 }); });
        [...walkers.keys()].forEach(k => { if (!ids.has(k)) walkers.delete(k); });
    }
    function pickTarget(w) {
        if (w.visitor) { w.tx = 176 + Math.random() * 72; w.ty = 112 + Math.random() * 24; w.goal = Math.random() < .4 ? 'tend' : 'stroll'; return; }
        const plants = st.tiles.filter(t => t.kind === 'plant');
        if (plants.length && Math.random() < .55) {
            const t = plants[Math.floor(Math.random() * plants.length)];
            w.tx = GX + t.x * T + 8 + (Math.random() < .5 ? -9 : 9); w.ty = GY + t.y * T + 15; w.goal = 'tend';
        } else { w.tx = 10 + Math.random() * (W - 20); w.ty = 36 + Math.random() * (H - 42); w.goal = 'stroll'; }
    }
    const bits = [];  // droplets, notes, sparks
    function act(w) {
        const n = { gardener_farmer: 5, gardener_witch: 2, gardener_robot: 3, gardener_frog: 0, gardener_death: 2, gardener_babbo: 4, visitor_dattore: 3 }[w.id] || 0;
        for (let i = 0; i < n; i++) bits.push({ x: w.x + (w.flip ? -6 : 6), y: w.y - 10, vx: (Math.random() - .5) * 8 + (w.flip ? -8 : 8),
            vy: -10 - Math.random() * 8, life: 1, kind: w.id === 'gardener_farmer' ? 'drop' : w.id === 'gardener_witch' ? 'note' : w.id === 'gardener_death' ? 'wisp' : w.id === 'gardener_babbo' ? 'snow' : 'spark' });
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
    const bulba = { x: 6, y: H - 24, blink: 0, say: '', sayFor: 0 };

    // --- Time of day ---
    function sky(h) {
        if (h < 5 || h >= 21) return ['#0b1030', '#1c2350', .45];
        if (h < 7) return ['#f6a77a', '#8fb8e8', .12];
        if (h < 18) return ['#6fb6f2', '#cfeaff', 0];
        return ['#f08a5d', '#4b3b78', .2];
    }
    let bg = null, bgHour = -1;
    function background(h) {  // sky, fence, lawn and soil, redrawn when the hour changes
        const key = h + '|' + (st ? st.rows : 5);  // (the plot grows a row with the cottage's walls)
        if (bg && bgHour === key) return bg;
        bgHour = key;
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
        const x = 8 + t * (W - 16), y = 18 - Math.sin(t * Math.PI) * 13;
        g.fillStyle = day ? '#ffe680' : '#eef2ff';
        g.beginPath(); g.arc(x, y, day ? 5 : 4, 0, Math.PI * 2); g.fill();
        if (!day) { g.fillStyle = sky(h)[0]; g.beginPath(); g.arc(x + 2, y - 1, 3.4, 0, Math.PI * 2); g.fill(); }
    }

    // --- Drawing ---
    const put = (img, x, y) => g.drawImage(img, Math.round(x), Math.round(y));
    function plantSprite(t, p) {
        const stg = stageOf(p);
        const kind = t.look || t.seed;  // a mutation's seed grows like its crop, but looks like the mutation (VARIANT)
        const v = VARIANT[t.variant] || null;
        if (stg === 'ripe') return sprite('ripe_' + kind + (v ? '_' + t.variant : ''), ART['ripe_' + kind], v ? v.ripe : {});
        if (stg === 'bloom') return sprite('bloom' + (v ? '_' + t.variant : ''), ART.bloom, { ...(v ? v.leaf : {}), F: (v && v.flower) || FLOWER[kind] || 'y' });
        return sprite(stg + (v && stg !== 'seed' ? '_' + t.variant : ''), ART[stg], v && stg !== 'seed' ? v.leaf : {});
    }
    // 🧬 The mutation's little effect, drawn over (or around) its plant
    function variantFx(v, img, x, y, p, sec, moving, night) {
        if (!v) return;
        const stg = stageOf(p), w = img.width, h = img.height, cx = x + w / 2;
        if (v.glow && stg !== 'seed' && (!v.night || night > .3 || stg === 'ripe')) {
            const a = .18 + (moving ? .1 * Math.sin(sec * 2 + x) : 0);
            const grd = g.createRadialGradient(cx, y + h / 2, 1, cx, y + h / 2, Math.max(w, h) * .7);
            grd.addColorStop(0, `rgba(${v.glow},${a + .15})`); grd.addColorStop(1, `rgba(${v.glow},0)`);
            g.fillStyle = grd; g.fillRect(x - 6, y - 6, w + 12, h + 12);
        }
        if (stg !== 'ripe') {  // while growing: a hint (a sparkle now and then) that it isn't an ordinary plant
            if (moving && Math.sin(sec * 2.3 + x) > .8) { g.fillStyle = '#fff6b0'; g.fillRect(x + (x * 7) % w, y + 1, 1, 1); }
            return;
        }
        const P = (c, px, py, pw = 1, ph = 1) => { g.fillStyle = PAL[c] || c; g.fillRect(x + px, y + py, pw, ph); };
        if (v.fx === 'hearts' && moving) { const k = (sec * .8 + x) % 3; P('m', 3, -k * 2, 1, 1); P('m', 5, -k * 2, 1, 1); P('m', 4, -k * 2 + 1, 1, 1); }
        if (v.fx === 'stripes') for (let i = 1; i < w - 1; i += 3) P('y', i, Math.floor(h / 2), 1, 2);
        if (v.fx === 'sparkle' && moving && Math.sin(sec * 4 + x) > .6) P('w', (Math.floor(sec * 3) * 5) % w, 2 + (Math.floor(sec * 3) * 3) % (h - 4));
        if (v.fx === 'legs') { P('o', w / 2 - 2, h, 1, 3); P('o', w / 2 + 1, h, 1, 3); if (moving && Math.floor(sec * 2) % 2) P('o', w / 2 + 2, h + 2); }
        if (v.fx === 'wink') { P('k', 6, 2, 1, 1); P('k', 8, 2, 2, 1); P('k', 6, 4, 4, 1); }
        if (v.fx === 'face') { P('k', 5, 3, 1, 1); P('k', 9, 3, 1, 1); P('k', 5, 5, 6, 1); P('k', 6, 6, 4, 1); }
        if (v.fx === 'zz' && moving) { const k = (sec * .7) % 3; P('w', w - 3, -k * 2, 2, 1); P('w', w - 2, -k * 2 + 1); P('w', w - 3, -k * 2 + 2, 2, 1); }
        if (v.fx === 'hat') { P('k', 2, -3, 5, 3); P('k', 1, 0, 7, 1); P('r', 2, -1, 5, 1); }
        if (v.fx === 'twin') put(img, x + 4, y + 1);
    }
    // 🏡 The cottage, drawn in the stages built so far (mainapp/tomato_house.py); scaffolding while one is being built
    function cottage(sec, h, moving, night) {
        const hs = st.house;
        if (!hs) return;
        const n = hs.stage, X = 182, F = 104, R = (x, y, w, hh, c) => { g.fillStyle = c; g.fillRect(x, y, w, hh); };
        const month = new Date().getMonth();
        if (n < 1) {  // a sign on a stake: something is coming
            R(206, F - 22, 2, 22, '#7a5232'); R(197, F - 26, 20, 10, '#c49155'); R(197, F - 26, 20, 1, '#8f6331');
            R(201, F - 23, 12, 1, '#4f341f'); R(203, F - 20, 8, 1, '#4f341f');
        }
        if (n >= 1) {  // foundation, and the mailbox beside it
            R(X - 4, F - 6, 64, 6, '#8e939c'); for (let x = X - 2; x < X + 58; x += 8) R(x, F - 6, 1, 6, '#6d727b'); R(X - 4, F - 6, 64, 1, '#b5bac2');
            R(X - 12, F - 18, 2, 18, '#7a5232'); R(X - 16, F - 24, 10, 7, '#2a6aa3'); R(X - 16, F - 24, 10, 1, '#4aa8e8'); R(X - 7, F - 27, 1, 4, '#e0352b');
        }
        if (n >= 2) {  // walls with a door and two windows (warm light at night)
            R(X, F - 34, 56, 28, '#efe9dc'); R(X, F - 34, 56, 2, '#c49155'); R(X, F - 22, 56, 1, '#c49155'); R(X, F - 34, 2, 28, '#8f6331'); R(X + 54, F - 34, 2, 28, '#8f6331');
            R(X + 23, F - 22, 10, 16, '#7a5232'); R(X + 30, F - 15, 1, 2, '#f5cf3a');
            const lit = night > .1 ? '#ffd36b' : '#9fd3ff';
            [[X + 7, F - 30], [X + 40, F - 30]].forEach(([x, y]) => { R(x, y, 9, 8, '#7a5232'); R(x + 1, y + 1, 7, 6, lit); R(x + 4, y + 1, 1, 6, '#7a5232'); R(x + 1, y + 4, 7, 1, '#7a5232'); });
            if (n >= 5) {  // window boxes on the finished cottage
                [[X + 6, F - 22], [X + 39, F - 22]].forEach(([x, y]) => { R(x, y, 11, 2, '#8f6331'); R(x + 1, y - 1, 2, 1, '#ff7aa8'); R(x + 5, y - 1, 2, 1, '#f5cf3a'); R(x + 8, y - 1, 2, 1, '#ff7aa8'); });
            }
        }
        if (n >= 3) {  // a red roof, the lightning rod Pantaleone didn't approve, and the rain barrel
            for (let i = 0; i < 16; i++) R(X - 4 + i * 2, F - 35 - i, 64 - i * 4, 1, i % 4 === 0 ? '#9e1f17' : '#e0352b');
            R(X + 27, F - 58, 1, 8, '#646d7a'); if (moving && Math.sin(sec * 2.3) > .9) R(X + 26, F - 60, 3, 2, '#fff7a8'); else R(X + 27, F - 59, 1, 1, '#f5cf3a');
            R(X + 60, F - 14, 9, 14, '#6d5a44'); R(X + 60, F - 12, 9, 1, '#3d3a3a'); R(X + 60, F - 5, 9, 1, '#3d3a3a'); R(X + 61, F - 14, 7, 1, '#4aa8e8');
        }
        if (n >= 4) {  // the chimney, and smoke from the kitchen
            R(X + 42, F - 54, 7, 14, '#a8442c'); R(X + 41, F - 55, 9, 2, '#7a2f1f');
            if (moving) for (let i = 0; i < 4; i++) {
                const k = (sec * .5 + i / 4) % 1;
                g.fillStyle = `rgba(230, 230, 235, ${.6 * (1 - k)})`;
                g.beginPath(); g.arc(X + 45 + Math.sin(k * 6 + i) * 3 + k * 6, F - 58 - k * 22, 1.5 + k * 3, 0, Math.PI * 2); g.fill();
            }
        }
        if (n >= 5) {  // the porch, a rocking chair that rocks by itself, and the season on the door
            R(X - 4, F - 3, 64, 3, '#c49155'); R(X - 4, F - 3, 64, 1, '#e8d28a'); R(X + 2, F - 20, 2, 17, '#8f6331'); R(X + 52, F - 20, 2, 17, '#8f6331');
            const rock = moving ? Math.round(Math.sin(sec * 1.6) * 1) : 0;
            R(X + 8 + rock, F - 13, 2, 9, '#7a5232'); R(X + 8 + rock, F - 7, 8, 2, '#7a5232'); R(X + 7, F - 4, 10, 1, '#4f341f');
            if (month === 11 || month === 0) { R(X + 25, F - 20, 6, 6, '#2b6b27'); R(X + 26, F - 19, 4, 4, '#7a5232'); R(X + 27, F - 21, 2, 2, '#e0352b'); }  // a wreath
            else if (month >= 8) { R(X + 35, F - 8, 6, 5, '#f07b1d'); R(X + 37, F - 9, 2, 1, '#2b6b27'); }  // a pumpkin
            else if (month >= 5) { R(X + 36, F - 12, 1, 8, '#3f9b3a'); R(X + 34, F - 15, 5, 4, '#f5cf3a'); R(X + 36, F - 14, 1, 2, '#4f341f'); }  // a sunflower
            else { R(X + 35, F - 7, 2, 2, '#ff7aa8'); R(X + 38, F - 6, 2, 2, '#f7a8c8'); R(X + 36, F - 5, 3, 1, '#3f9b3a'); }  // spring flowers
        }
        if (hs.building) {  // scaffolding over what's going up
            const top = [F - 12, F - 38, F - 54, F - 60, F - 24][Math.min(n, 4)];
            g.fillStyle = '#b07a3e';
            for (let x = X - 6; x <= X + 60; x += 22) g.fillRect(x, top, 2, F - top);
            for (let y = top + 4; y < F; y += 10) g.fillRect(X - 6, y, 68, 1);
            if (moving && Math.sin(sec * 5) > .8) bits.push({ x: X + Math.random() * 56, y: top + Math.random() * 10, vx: (Math.random() - .5) * 10, vy: -8, life: .6, kind: 'spark' });
        }
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
                const p = grown(t), img = plantSprite(t, p), v = VARIANT[t.variant] || null;
                const sway = moving && stageOf(p) !== 'seed' && Math.sin(sec * 1.7 + t.x * .9 + t.y) > .55 ? 1 : 0;
                const big = v && v.scale && stageOf(p) !== 'seed' ? 1 + (v.scale - 1) * Math.min(1, p) : 1;
                things.push({ y: py + 16, f: () => {
                    const w = Math.round(img.width * big), hh = Math.round(img.height * big);
                    const ix = px + (16 - w) / 2 + sway, iy = py + 16 - hh;
                    if (v && v.alpha && stageOf(p) === 'ripe') g.globalAlpha = v.alpha;
                    if (big !== 1) g.drawImage(img, Math.round(ix), Math.round(iy), w, hh); else put(img, ix, iy);
                    g.globalAlpha = 1;
                    variantFx(v, img, Math.round(ix), Math.round(iy), p, sec, moving, night);
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
        things.push({ y: 104, f: () => cottage(sec, h, moving, sky(h)[2]) });  // the cottage sorts with the walkers
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
            g.fillStyle = b.kind === 'drop' ? '#7cc0ff' : b.kind === 'note' ? '#d7b4ff' : b.kind === 'wisp' ? '#7ef0e6' : b.kind === 'snow' ? '#ffffff' : '#ffe066';
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
        if (armed && sel && !tileAt(sel.x, sel.y) && st.basket[armed]) { putDown(armed, sel); return; }
        paintTile();
    });

    // --- From the basket to the soil: drag an item onto a patch, or tap it (armed) and then a patch ---
    let armed = null;
    async function putDown(id, c) {
        if (!c || tileAt(c.x, c.y)) { if (window.NADialog && c) NADialog.alert('Something is already there. Pick a free patch.'); return; }
        try {
            take(await call({ action: st.crops[id] ? 'plant' : 'place', x: c.x, y: c.y, id }));
            sel = c; armed = null; burstAt(c); paintSide(); paintTile();
        } catch (err) { if (window.NADialog) NADialog.alert(err.message); }
    }
    $('gBasket').addEventListener('click', (e) => {
        const b = e.target.closest('[data-item]');
        if (!b) return;
        armed = armed === b.dataset.item ? null : b.dataset.item;
        paintSide();
    });
    $('gBasket').addEventListener('dragstart', (e) => {
        const b = e.target.closest('[data-item]');
        if (!b) return;
        e.dataTransfer.setData('text/plain', b.dataset.item);
        e.dataTransfer.effectAllowed = 'move';
    });
    cv.addEventListener('dragover', (e) => { e.preventDefault(); hover = cell(at(e)); });
    cv.addEventListener('drop', (e) => {
        e.preventDefault();
        const id = e.dataTransfer.getData('text/plain');
        if (id && st && st.basket[id]) putDown(id, cell(at(e)));
    });

    // Gardeners: three at work, the others in the shed
    $('gGardeners').addEventListener('click', async (e) => {
        const b = e.target.closest('[data-crew]');
        if (!b) return;
        b.disabled = true;
        try { take(await call({ action: 'crew', id: b.dataset.crew, on: !!b.dataset.on })); paintSide(); }
        catch (err) { if (window.NADialog) NADialog.alert(err.message); b.disabled = false; }
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
        box.innerHTML = `<h3>${prizeOf(t.seed).emoji} ${esc(t.name)}</h3>${t.variant ? `<p class="muted g-small">A mutation's seed: it comes out as itself
            ${Math.round(st.keep[st.almanac.find(a => a.id === t.variant)?.rare ? 'rare' : 'common'] * 100)}% of the time (with its seed back), otherwise as an ordinary ${esc(prizeOf(st.crops[t.seed].base).name.replace(/ seeds$/, '').toLowerCase())}.</p>` : ''}<div id="gLive"></div>`;
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
        $('gBasket').innerHTML = items.length ? `<div class="g-basket">${items.map(([k, n]) => `<button type="button" class="g-bitem${armed === k ? ' armed' : ''}"
                draggable="true" data-item="${k}" title="Drag it onto a patch, or tap it and then a patch">
                <span class="e">${prizeOf(k).emoji}</span><span>${esc(st.crops[k] ? st.crops[k].name + ' seeds' : prizeOf(k).name)}</span><b>×${n}</b></button>`).join('')}</div>`
            : '<p class="muted g-small">Empty. Seeds and decorations come from the Sauce-o-Matic.</p>';
        $('gBasket').insertAdjacentHTML('beforeend', `<p class="muted g-small">${items.length ? (armed ? `Now tap a free patch for the ${esc(prizeOf(armed).name.toLowerCase())}. ` : 'Drag a seed or a decoration onto a patch, or tap it and then a patch. ') : ''}Each tomato you throw at a chat or Bulba waters every plant: ${Math.round(st.water / 60)} minutes of growth.</p>`);
        const gard = (x, on) => `<div class="g-gard${on ? '' : ' resting'}"><span class="e">${prizeOf(x.id).emoji}</span><div><b>${esc(prizeOf(x.id).name)}</b><br>
            <span class="muted">${esc(x.about)}</span><br><button type="button" class="na-btn g-crew" data-crew="${x.id}" data-on="${on ? '' : '1'}">
            ${on ? '🛖 Send to the shed' : '🌱 Bring to work'}</button>${!on && st.gardeners.length >= st.crew_max ? '<span class="muted g-crew-why">The crew is full: send one to the shed first.</span>' : ''}</div></div>`;
        const shed = st.shed || [];
        $('gGardeners').innerHTML = st.gardeners.length || shed.length
            ? `<p class="muted g-small">${st.crew_max} at work at a time; the rest rest in the shed.</p>`
              + st.gardeners.map(x => gard(x, true)).join('')
              + (shed.length ? `<div class="g-small muted g-shed-head">🛖 In the shed</div>` + shed.map(x => gard(x, false)).join('') : '')
            : '<p class="muted g-small">None yet. Gardeners are the Sauce-o-Matic\'s legendaries: each one moves in and helps.</p>';
        $('gLog').innerHTML = st.log.length ? st.log.map(l => `<li>${esc(l.text)} <span class="muted">${new Date(l.at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></li>`).join('')
            : '<li class="muted">Nothing yet.</li>';
        paintBoard();
        paintCottage();
        paintKitchen();
        if (sel) paintTile();
    }
    // 🏡 The cottage: the stage being built, its builder's order, the last scene between Il Dattore and Pantaleone
    const WHO = { 'Il Dattore': '🔬', 'Pantaleone': '💰' };
    function paintCottage() {
        const hs = st.house, box = $('gCottage');
        if (!hs || !box) return;
        // One line for the progress (the stage names are in the tooltips), then only the next thing to do
        const dots = hs.stages.map((s, i) => `<i class="${i < hs.stage ? 'done' : i === hs.stage ? 'now' : ''}" title="${esc(s.emoji + ' ' + s.name + ': ' + s.about)}"></i>`).join('');
        const c = hs.current;
        const head = `<div class="g-progress"><span class="g-dots">${dots}</span>
            <span>${c ? `Stage ${hs.stage + 1} of ${hs.stages.length} · <b>${c.emoji} ${esc(c.name)}</b>` : '<b>All built</b>'}</span></div>`;
        let body = '';
        if (!c) body = `<p>${esc(hs.builder)} is already sketching a mill. ${esc(hs.banker)} is already sketching an audit.</p>`;
        else if (hs.building) body = `<p class="g-next">🔨 ${esc(hs.builder)} is building. Ready in about <b>${dur(hs.building)}</b>.</p>`;
        else {
            const missing = c.needs.some(x => x.have < x.n) || (c.mutations && c.found < c.mutations);
            const chips = c.needs.map(x => `<span class="g-chip${x.have >= x.n ? ' full' : ''}">${x.seed === 'seed_tomato' ? '🍅' : prizeOf(x.seed).emoji} ${x.have}/${x.n}</span>`).join('')
                + (c.mutations ? `<span class="g-chip${c.found >= c.mutations ? ' full' : ''}" title="Different mutations found">🧬 ${Math.min(c.found, c.mutations)}/${c.mutations}</span>` : '');
            const canGive = c.needs.some(x => x.have < x.n && (st.shelf || {})[x.seed]);
            body = missing
                ? `<div class="g-next"><span>1. Give him:</span> ${chips}
                    ${c.needs.length ? `<button type="button" class="na-btn${canGive ? ' na-primary' : ''}" data-give="house" ${canGive ? '' : 'disabled'}
                       title="${canGive ? 'From your shelf' : 'Harvest these first: they land on the shelf'}">🧺 Give</button>` : ''}</div>
                   <p class="muted g-small">2. Then build it for ♻ ${c.compost} compost (about ${c.hours} h).</p>`
                : `<div class="g-next"><span>${chips}</span>
                    <button type="button" class="na-btn${hs.ready ? ' na-primary' : ''}" data-build ${hs.ready ? '' : 'disabled'}>🔨 Build it: ♻ ${c.compost}</button>
                    ${hs.ready ? '' : `<span class="muted g-small">${esc(hs.why)}</span>`}</div>`;
            body += `<p class="muted g-small">Unlocks ${esc(c.about)}${c.budget_left ? ` · 💰 within ${dur(c.budget_left)}: ${esc(hs.banker)} tips 🍅 100` : ''}</p>`;
        }
        const sc = hs.scene || {}, lines = sc.lines || [];
        let seen = null;
        try { seen = localStorage.getItem('na-cottage-scene'); } catch (e) { /* private window */ }
        const fresh = lines.length && String(sc.at) !== seen;
        box.innerHTML = `${head}${body}
            ${lines.length ? `<details class="g-scene"${fresh ? ' open' : ''}><summary>💬 ${esc(hs.builder)} and ${esc(hs.banker)}${fresh ? ' <span class="g-new">new</span>' : ''}</summary>
                <div>${lines.map(l => `<p><span class="who">${WHO[l.who] || '🗨️'} ${esc(l.who)}</span> ${esc(l.text)}</p>`).join('')}</div></details>` : ''}`;
        const d = box.querySelector('.g-scene');
        if (d) d.addEventListener('toggle', () => { try { localStorage.setItem('na-cottage-scene', String(sc.at)); } catch (e) { /* this page only */ } });
    }
    // 🧺 handing crops over from the shelf (to the cottage or to an order)
    document.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-give]');
        if (!b) return;
        b.disabled = true;
        try { take(await call({ action: 'give', to: b.dataset.give })); } catch (err) { if (window.NADialog) NADialog.alert(err.message); b.disabled = false; }
    });
    $('gCottage') && $('gCottage').addEventListener('click', async (e) => {
        const b = e.target.closest('[data-build]');
        if (!b) return;
        b.disabled = true;
        try { take(await call({ action: 'build' })); } catch (err) { if (window.NADialog) NADialog.alert(err.message); b.disabled = false; }
    });
    // 🍲 The kitchen (mainapp/tomato_kitchen.py): crops from the shelf into the pot, the pantry, the recipe book
    const potPick = {};
    function paintKitchen() {
        const box = $('gKitchen'), k = st.kitchen;
        if (!box || !k) return;
        const cropIcon = (seed) => seed === 'seed_tomato' ? '🍅' : prizeOf(seed).emoji;
        $('gBoosts').textContent = (k.boosts || []).map(b => ({ compost: `🍞 +${b.n} compost a harvest`, luck: `🍰 mutations ×${b.n}`,
            water: `🥫 watering ×${b.n}` })[b.kind] + ` · ${dur(b.left)}`).join(' · ');
        if (!k.open) {
            box.innerHTML = '<p class="muted g-small">Opens when the cottage gets its chimney and kitchen (stage 4). Then: two to four crops in the pot, and a dish comes out. Some recipes are secret.</p>';
            return;
        }
        let html = '';
        if (k.pot) {
            html += k.pot.left > 0
                ? `<div class="g-pot cooking"><span class="e">🍲</span><div><b>Cooking:</b> ${esc(k.pot.what)}<small class="muted">Ready in ${dur(k.pot.left)}.</small></div></div>`
                : `<div class="g-pot ready"><span class="e">🍲</span><div><b>Ready!</b> ${esc(k.pot.what)}</div><button type="button" class="na-btn na-primary" data-kitchen="collect">Take it out</button></div>`;
        } else {
            const shelf = Object.entries(st.shelf || {});
            Object.keys(potPick).forEach(s => { if (!(st.shelf || {})[s]) delete potPick[s]; });
            const total = Object.values(potPick).reduce((a, b) => a + b, 0);
            html += shelf.length ? `<p class="muted g-small">Put ${k.min} to ${k.max} crops from the shelf in the pot (${k.minutes} minutes each). Known recipes are in the book; others are for finding.</p>
                <div class="g-potpick">${shelf.map(([s, n]) => `<div class="g-potrow"><span class="e">${cropIcon(s)}</span><span>${esc(prizeOf(s).name.replace(/ seeds$/, ''))} <small class="muted">(${n})</small></span>
                    <button type="button" class="na-btn" data-pot="${s}" data-d="-1" ${potPick[s] ? '' : 'disabled'}>−</button><b>${potPick[s] || 0}</b>
                    <button type="button" class="na-btn" data-pot="${s}" data-d="1" ${(potPick[s] || 0) < n && total < k.max ? '' : 'disabled'}>+</button></div>`).join('')}</div>
                <button type="button" class="na-btn na-primary" data-kitchen="cook" ${total >= k.min && total <= k.max ? '' : 'disabled'}>🍲 Cook (${total})</button>`
                : '<p class="muted g-small">The shelf is empty: harvest something first.</p>';
        }
        html += (k.pantry || []).length ? `<h3 class="g-sub">Pantry</h3><div class="g-pantry">${k.pantry.map(d => `<div class="g-dish"><span class="e">${d.emoji}</span>
                <div><b>${esc(d.name)}</b> ×${d.n}<small class="muted">Eat: ${esc(d.boost)}. Or give it to a dish order.</small></div>
                <button type="button" class="na-btn" data-kitchen="eat" data-id="${d.id}">Eat</button></div>`).join('')}</div>` : '';
        const found = (k.book || []).filter(r => r.known).length;
        html += `<details class="g-book"><summary>📖 Recipe book (${found} of ${(k.book || []).length})</summary>
            ${(k.book || []).map(r => `<div class="g-recipe${r.known ? '' : ' unknown'}"><span class="e">${r.emoji}</span><div><b>${esc(r.name)}</b>
                <small class="muted">${esc(r.needs)}${r.boost ? ' · ' + esc(r.boost) : ''}${r.cooked ? ` · cooked ${r.cooked}×` : ''}</small></div></div>`).join('')}</details>`;
        box.innerHTML = html;
    }
    $('gKitchen')?.addEventListener('click', async (e) => {
        const p = e.target.closest('[data-pot]');
        if (p) { potPick[p.dataset.pot] = Math.max(0, (potPick[p.dataset.pot] || 0) + Number(p.dataset.d)); paintKitchen(); return; }
        const b = e.target.closest('[data-kitchen]');
        if (!b) return;
        b.disabled = true;
        const body = { action: b.dataset.kitchen };
        if (body.action === 'cook') body.needs = Object.fromEntries(Object.entries(potPick).filter(([, n]) => n > 0));
        if (body.action === 'eat') body.id = b.dataset.id;
        try {
            take(await call(body));
            if (body.action === 'cook') Object.keys(potPick).forEach(s => delete potPick[s]);
        } catch (err) { if (window.NADialog) NADialog.alert(err.message); b.disabled = false; }
    });

    // 📋 The order board and 🧬 the almanac
    function paintBoard() {
        const orders = st.orders || [], days = (s) => s >= 86400 ? `${Math.ceil(s / 86400)} days left` : `${Math.max(1, Math.round(s / 3600))} h left`;
        $('gFilled').textContent = st.filled ? `${st.filled} filled` : '';
        const icon = (seed) => seed === 'seed_tomato' ? '🍅' : prizeOf(seed).emoji;
        const total = (o) => Object.values(o.needs).reduce((a, b) => a + b, 0), have = (o) => Object.values(o.have).reduce((a, b) => a + b, 0);
        $('gOrders').innerHTML = (orders.length ? `<div class="g-orders">${orders.map(o => `<div class="g-order${o.dish ? ' dish' : ''}">
                <span class="e">${o.dish ? o.emoji : icon(Object.keys(o.needs)[0])}</span>
                <div><b>${o.dish ? esc(o.dish) : esc(o.what)}</b> <small>for ${esc(o.from)} · ${days(o.left)}</small>
                ${o.dish || Object.keys(o.needs).length > 1 ? `<small class="g-parts">${Object.entries(o.needs).map(([k, n]) => `${icon(k)} ${o.have[k] || 0}/${n}`).join(' · ')}</small>` : ''}</div>
                <span class="pay">🍅 ${o.reward}</span>
                ${Object.keys(o.needs).some(k => (o.have[k] || 0) < o.needs[k] && (st.shelf || {})[k])
                    || (o.dish && ((st.kitchen || {}).pantry || []).some(d => d.name === o.dish))
                    ? `<button type="button" class="na-btn na-primary g-give" data-give="${o.id}">${o.dish && ((st.kitchen || {}).pantry || []).some(d => d.name === o.dish) ? '🍲 Give the dish' : '🧺 Give'}</button>` : ''}
                <div class="g-bar"><i style="width:${Math.round(have(o) / total(o) * 100)}%"></i></div></div>`).join('')}</div>`
            : '<p class="muted g-small">No orders right now. A new one goes up each day.</p>')
            + `<p class="muted g-small">Up to ${st.orders_max} at a time, a new one each day. Give them crops from your shelf (🧺); tomatoes from orders count toward your next spin.</p>`;
        // 🧺 the shelf: what's been harvested and not given yet
        const shelf = Object.entries(st.shelf || {});
        if ($('gShelf')) $('gShelf').innerHTML = shelf.length
            ? `<div class="g-shelf">${shelf.map(([k, n]) => `<div class="g-jar" title="${esc(prizeOf(k).name.replace(/ seeds$/, ''))}"><span class="e">${icon(k)}</span><b>×${n}</b></div>`).join('')}</div>
               <p class="muted g-small">Harvests land here (up to ${st.shelf_max} of each; more goes to the compost). Hand them to an order or to the cottage.</p>`
            : '<p class="muted g-small">Empty. Harvest something ripe and it lands here, ready to give to an order.</p>';
        const al = st.almanac || [], found = al.filter(a => a.got);
        $('gAlmanacCount').textContent = `${found.length} of ${al.length}`;
        $('gAlmanac').innerHTML = `<p class="muted g-small">About 1 harvest in ${st.mutation_odds} comes out strange. Most give triple compost; the gold-edged ones give a free spin. Each one also gives its seed: plant it to try for another.</p>
            <div class="g-almanac">${al.map(a => a.got ? `<div class="g-mut${a.rare ? ' rare' : ''}" title="${a.rare ? 'A free spin' : 'Triple compost'}"><span class="e">${a.emoji}</span>
                <div>${esc(a.name)}<small>${a.rare ? 'rare · a spin' : 'triple compost'}${a.got > 1 ? ` · ×${a.got}` : ''}</small></div></div>`
                : `<div class="g-mut unknown${a.rare ? ' rare' : ''}"><span class="e">❔</span><div>???<small>${esc(prizeOf(a.crop).name.replace(/ seeds$/, ''))}${a.rare ? ' · rare' : ''}</small></div></div>`).join('')}</div>`;
        // A new mutation since they last looked: say so once
        const m = st.mutation;
        let seen = null;
        try { seen = localStorage.getItem('na-garden-mutation'); } catch (e) { /* private window */ }
        if (seen === null) { try { localStorage.setItem('na-garden-mutation', m ? m.at : 1); } catch (e) { /* no memory here */ } }
        else if (m && m.at > +seen) {
            try { localStorage.setItem('na-garden-mutation', m.at); } catch (e) { /* this page only */ }
            const a = al.find(x => x.id === m.id);
            if (a && window.NATomato) NATomato.toast(`🧬 A mutation! ${a.emoji} ${a.name}`, a.rare ? 'A free spin is waiting at the Sauce-o-Matic.' : 'Triple compost. It went into the almanac.');
        }
    }

    load();
    setInterval(() => { if (!document.hidden) load(); }, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && st) load(); });
})();
