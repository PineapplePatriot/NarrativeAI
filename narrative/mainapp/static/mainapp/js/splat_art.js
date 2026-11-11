/* 🎨 Drawing a splat wall: the backgrounds and the four splat shapes. Shared by the wall in the Tomato Pit
   (tomato_pit.js) and the gallery (tomato_gallery.js). A wall is 1200×750; a splat is
   {x, y, r, c: colour, f: CSS filter for the thrown thing, k: the emoji, e: show it, rot, seed, t: shape}.
   The server checks every splat (mainapp/tomatoes.py clean_splat), so a shared piece is only ever this. */
(function () {
    if (window.NASplat) return;
    const W = 1200, H = 750;
    const EMOJI = '"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
    const SCENES = (document.currentScript && document.currentScript.dataset.scenes) || '';
    const TEXTURES = [
        { id: 'night', name: 'Night' }, { id: 'plaster', name: 'Plaster', light: true }, { id: 'brick', name: 'Brick' },
        { id: 'chalk', name: 'Chalkboard' }, { id: 'sky', name: 'Sky', light: true }, { id: 'grass', name: 'Lawn' },
        { id: 'wood', name: 'Fence' }, { id: 'paper', name: 'Newspaper', light: true }, { id: 'tiles', name: 'Kitchen tiles', light: true },
        { id: 'canvas', name: 'Art canvas', light: true },
    ];
    const SHAPES = [
        { id: 'splat', name: 'Splat' }, { id: 'drip', name: 'Drip' }, { id: 'spray', name: 'Spray' }, { id: 'stamp', name: 'Stamp' },
    ];
    const images = {};
    function scene(file, done) {  // a story background, loaded once; `done` redraws when it arrives
        if (!images[file]) {
            const img = new Image();
            images[file] = img;
            img.onload = () => { const w = img._waiting || []; img._waiting = []; w.forEach(fn => fn()); };
            img.src = SCENES + file;
        }
        const img = images[file];
        if (img.complete && img.naturalWidth) return img;
        (img._waiting = img._waiting || []).push(done);
        return null;
    }
    const rng = (seed) => () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);

    function background(g, bg, done) {
        const fills = { night: '#151826', plaster: '#e9e3d6', brick: '#8a3b2c', chalk: '#24372c', grass: '#4f8a3a',
                        wood: '#9a6b3f', paper: '#efeadc', tiles: '#f3f5f7', canvas: '#fbf8f1' };
        if (String(bg).startsWith('scene:')) {
            g.fillStyle = '#151826'; g.fillRect(0, 0, W, H);
            const img = scene(bg.slice(6), done || (() => {}));
            if (img) {  // cover the wall, centred
                const k = Math.max(W / img.naturalWidth, H / img.naturalHeight), w = img.naturalWidth * k, h = img.naturalHeight * k;
                g.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
            }
            return;
        }
        if (bg === 'sky') {
            const grad = g.createLinearGradient(0, 0, 0, H);
            grad.addColorStop(0, '#6fb6f2'); grad.addColorStop(1, '#d9efff');
            g.fillStyle = grad; g.fillRect(0, 0, W, H);
            const rnd = rng(5);
            g.fillStyle = 'rgba(255,255,255,.85)';
            for (let i = 0; i < 7; i++) {  // a few clouds
                const cx = rnd() * W, cy = 60 + rnd() * H * .5, s = 30 + rnd() * 40;
                for (let j = 0; j < 5; j++) { g.beginPath(); g.arc(cx + (j - 2) * s * .7, cy + Math.sin(j * 1.7) * s * .25, s * (.6 + rnd() * .4), 0, Math.PI * 2); g.fill(); }
            }
            return;
        }
        g.fillStyle = fills[bg] || fills.night;
        g.fillRect(0, 0, W, H);
        const rnd = rng(11);
        if (bg === 'brick') {  // mortar lines
            g.fillStyle = 'rgba(230, 215, 200, .55)';
            for (let y = 0, row = 0; y < H; y += 50, row++) {
                g.fillRect(0, y, W, 5);
                for (let x = (row % 2) * 60; x < W; x += 120) g.fillRect(x, y, 5, 50);
            }
        } else if (bg === 'plaster' || bg === 'chalk' || bg === 'canvas') {  // a little texture
            g.fillStyle = bg === 'chalk' ? 'rgba(255, 255, 255, .035)' : 'rgba(120, 100, 70, .06)';
            for (let i = 0; i < 260; i++) g.fillRect(rnd() * W, rnd() * H, 2 + rnd() * 30, 1 + rnd() * 3);
        } else if (bg === 'grass') {  // blades
            for (let i = 0; i < 1400; i++) {
                g.strokeStyle = rnd() > .5 ? 'rgba(30, 80, 25, .45)' : 'rgba(140, 200, 90, .35)';
                const x = rnd() * W, y = rnd() * H;
                g.beginPath(); g.moveTo(x, y); g.lineTo(x + (rnd() - .5) * 8, y - 8 - rnd() * 14); g.stroke();
            }
        } else if (bg === 'wood') {  // fence planks
            for (let x = 0; x < W; x += 100) {
                g.fillStyle = `rgba(60, 35, 15, ${.15 + rnd() * .15})`; g.fillRect(x, 0, 100, H);
                g.fillStyle = 'rgba(40, 22, 8, .7)'; g.fillRect(x, 0, 6, H);
                g.strokeStyle = 'rgba(70, 40, 15, .25)';
                for (let j = 0; j < 6; j++) { const gx = x + 15 + rnd() * 75; g.beginPath(); g.moveTo(gx, 0); g.bezierCurveTo(gx + 8, H * .3, gx - 8, H * .6, gx + 4, H); g.stroke(); }
            }
        } else if (bg === 'paper') {  // columns of "print"
            g.fillStyle = '#2a2a2a'; g.fillRect(40, 30, W - 80, 54);
            g.fillStyle = 'rgba(40, 40, 40, .28)';
            for (let col = 0; col < 4; col++) {
                for (let y = 110; y < H - 30; y += 14) { const w = 230 - rnd() * (rnd() > .9 ? 120 : 20); g.fillRect(50 + col * 280, y, w, 5); }
            }
        } else if (bg === 'tiles') {
            g.fillStyle = 'rgba(160, 175, 190, .6)';
            for (let x = 0; x < W; x += 75) g.fillRect(x, 0, 3, H);
            for (let y = 0; y < H; y += 75) g.fillRect(0, y, W, 3);
        }
    }

    function blob(g, x, y, r, rnd) {  // a wobbly circle
        const n = 12, pts = [];
        for (let i = 0; i < n; i++) { const a = i / n * Math.PI * 2, d = r * (.72 + rnd() * .38); pts.push([x + Math.cos(a) * d, y + Math.sin(a) * d]); }
        g.beginPath();
        g.moveTo((pts[0][0] + pts[n - 1][0]) / 2, (pts[0][1] + pts[n - 1][1]) / 2);
        for (let i = 0; i < n; i++) { const p = pts[i], q = pts[(i + 1) % n]; g.quadraticCurveTo(p[0], p[1], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2); }
        g.fill();
    }
    function dot(g, x, y, r) { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
    function drips(g, sp, rnd, m, long) {
        const r = sp.r;
        for (let i = 0; i < m; i++) {
            const x = sp.x + (rnd() - .5) * r * 1.1, w = r * (.1 + rnd() * .1), len = r * (long ? 1.5 + rnd() * 3 : .5 + rnd() * 1.3);
            g.fillRect(x - w / 2, sp.y, w, r * .6 + len);
            dot(g, x, sp.y + r * .6 + len, w * .75);
        }
    }

    function draw(g, sp) {
        const rnd = rng(sp.seed || 1), r = sp.r, t = sp.t || 'splat';
        g.save();
        g.globalAlpha = .93;
        g.fillStyle = sp.c;
        if (t === 'splat') {
            blob(g, sp.x, sp.y, r, rnd);
            for (let i = 0, m = 6 + Math.floor(rnd() * 6); i < m; i++) {
                const a = rnd() * Math.PI * 2, d = r * (1.05 + rnd() * .9);
                dot(g, sp.x + Math.cos(a) * d, sp.y + Math.sin(a) * d, r * (.06 + rnd() * .16));
            }
            drips(g, sp, rnd, 1 + Math.floor(rnd() * 3), false);
        } else if (t === 'drip') {  // a smaller blob that runs down the wall
            blob(g, sp.x, sp.y, r * .7, rnd);
            drips(g, sp, rnd, 3 + Math.floor(rnd() * 3), true);
        } else if (t === 'spray') {  // a mist of droplets, thicker in the middle
            g.globalAlpha = .8;
            for (let i = 0, m = 40 + Math.floor(r * 1.2); i < m; i++) {
                const a = rnd() * Math.PI * 2, d = r * 1.3 * Math.sqrt(rnd()) * (rnd() > .85 ? 1.4 : 1);
                dot(g, sp.x + Math.cos(a) * d, sp.y + Math.sin(a) * d, 1 + rnd() * r * .07);
            }
        }
        if (sp.e || t === 'stamp') {  // the thing itself, on top (a stamp is only that)
            g.globalAlpha = 1;
            g.translate(sp.x, sp.y);
            g.rotate(sp.rot || 0);
            g.font = `${Math.round(r * (t === 'stamp' ? 1.6 : 1.05))}px ${EMOJI}`;
            g.textAlign = 'center';
            g.textBaseline = 'middle';
            if (sp.f) g.filter = sp.f;
            g.fillText(sp.k, 0, 0);
        }
        g.restore();
    }

    function paint(g, art, done) {  // a whole piece, at any canvas size
        const k = g.canvas.width / W;
        g.save();
        g.setTransform(k, 0, 0, k, 0, 0);
        background(g, art.bg, done);
        (art.splats || []).forEach(sp => draw(g, sp));
        g.restore();
    }
    const light = (bg) => !!(TEXTURES.find(t => t.id === bg) || {}).light;
    function signed(canvas, bg) {  // a copy with a small signature, for downloads
        const out = document.createElement('canvas');
        out.width = canvas.width; out.height = canvas.height;
        const o = out.getContext('2d'), k = canvas.width / W;
        o.drawImage(canvas, 0, 0);
        o.font = `600 ${Math.round(20 * k)}px system-ui, -apple-system, "Segoe UI", sans-serif`;
        o.fillStyle = light(bg) ? 'rgba(0, 0, 0, .45)' : 'rgba(255, 255, 255, .6)';
        o.textAlign = 'right';
        o.fillText('painted with vegetables · the Tomato Pit · Narrative AI', out.width - 18 * k, out.height - 16 * k);
        return out;
    }
    window.NASplat = { W, H, TEXTURES, SHAPES, background, draw, paint, signed, light };
})();
