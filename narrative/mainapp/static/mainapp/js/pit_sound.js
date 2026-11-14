/* 🔊 The Tomato Pit's sounds: effects drawn with the Web Audio API (no files), and the Pit radio.
   - Effects: a whoosh and a splat per throw (a sparkle for a golden one), the machine's lever, rattle, capsules
     landing, a pop when one opens and a chime by tier (a fanfare for a legendary), compost squelching into a spin.
     Pages call NAPitSound.play(name); throws arrive as 'na-tomato-throw' events from tomato.js.
   - The radio: AI-made tracks (no rights needed) named only by emoji, grouped in sets that share a theme. When a
     track ends, the next one from its set plays, so a set mixes on its own. Nothing plays until it's pressed.
   - On/off and volumes are kept in this browser. Effects are on by default, quieter than the music. */
(function () {
    if (window.NAPitSound) return;
    const BASE = (document.currentScript && document.currentScript.dataset.music) || '/static/defaults/music/pit/';
    const SETS = [
        { name: 'Circus', tracks: [{ id: 'moonlit-big-top', title: '🔮🎭💫' }, { id: 'moonlit-circus', title: '🎠🎪👻' }] },
        { name: 'Witchy woods', tracks: [{ id: 'birch-moon-rite', title: '🌿🪈🧙‍♂️' }, { id: 'black-birch-sabbath', title: '💃🕯🪄' }] },
        { name: 'Mornings', tracks: [{ id: 'alba-fiorita', title: '😇💐💫' }, { id: 'luce-del-mattino', title: '💅👸🌹' }] },
        { name: 'Merchant', tracks: [{ id: 'obsidian-merchant', title: '🤵‍♀️💳💸' }] },
    ];
    const KEY = 'na-pit-sound';
    const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } };
    const prefs = Object.assign({ sfx: true, sfxVol: 0.5, musicVol: 0.45, track: 'moonlit-big-top' }, read());
    const save = () => { try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) { /* private window */ } };

    // --- Effects ---
    let ctx = null, master = null, noiseBuf = null;
    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
            master = ctx.createGain();
            master.connect(ctx.destination);
            noiseBuf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
            const d = noiseBuf.getChannelData(0);
            for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
        }
        if (ctx.state === 'suspended') ctx.resume();
        master.gain.value = prefs.sfxVol;
        return ctx;
    }
    function env(g, t, a, peak, d) {  // attack to peak, then decay to silence
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(peak, t + a);
        g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
    }
    function tone(freq, t, dur, { type = 'sine', peak = 0.3, attack = 0.005, to = null } = {}) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = type;
        o.frequency.setValueAtTime(freq, t);
        if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
        env(g, t, attack, peak, dur);
        o.connect(g).connect(master);
        o.start(t); o.stop(t + attack + dur + 0.05);
    }
    function noise(t, dur, { type = 'lowpass', freq = 1200, to = null, q = 1, peak = 0.4, attack = 0.003 } = {}) {
        const s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
        s.buffer = noiseBuf;
        f.type = type; f.Q.value = q;
        f.frequency.setValueAtTime(freq, t);
        if (to) f.frequency.exponentialRampToValueAtTime(to, t + dur);
        env(g, t, attack, peak, dur);
        s.connect(f).connect(g).connect(master);
        s.start(t, Math.random() * 0.5); s.stop(t + attack + dur + 0.05);
    }
    const SOUNDS = {
        whoosh: (t) => noise(t, 0.16, { type: 'bandpass', freq: 600, to: 2400, q: 1.2, peak: 0.18, attack: 0.04 }),
        splat: (t) => {
            noise(t, 0.18, { freq: 900 + Math.random() * 500, to: 180, peak: 0.55 });
            tone(140 + Math.random() * 40, t, 0.12, { type: 'sine', peak: 0.35, to: 60 });
        },
        golden: (t) => [1319, 1568, 2093, 2637].forEach((f, i) => tone(f, t + i * 0.06, 0.25, { type: 'triangle', peak: 0.16 })),
        lever: (t) => {
            noise(t, 0.05, { type: 'highpass', freq: 2500, peak: 0.25 });
            tone(110, t + 0.02, 0.18, { type: 'square', peak: 0.12, to: 70 });
            tone(220, t + 0.3, 0.12, { type: 'square', peak: 0.08, to: 160 });
        },
        rattle: (t) => { for (let i = 0; i < 12; i++) noise(t + i * 0.05, 0.03, { type: 'bandpass', freq: 1800 + Math.random() * 1500, q: 6, peak: 0.25 }); },
        drop: (t) => { tone(520, t, 0.06, { peak: 0.2, to: 300 }); tone(420, t + 0.16, 0.05, { peak: 0.12, to: 260 }); },
        pop: (t) => { tone(300, t, 0.09, { peak: 0.35, to: 1100 }); noise(t, 0.06, { type: 'highpass', freq: 3000, peak: 0.2 }); },
        common: (t) => tone(880, t, 0.35, { type: 'sine', peak: 0.2 }),
        rare: (t) => { tone(988, t, 0.3, { type: 'triangle', peak: 0.2 }); tone(1319, t + 0.1, 0.45, { type: 'triangle', peak: 0.2 }); },
        legendary: (t) => {
            [523, 659, 784, 1047].forEach((f, i) => tone(f, t + i * 0.11, 0.3, { type: 'sawtooth', peak: 0.09 }));
            [1047, 1319, 1568].forEach(f => tone(f, t + 0.48, 1.1, { type: 'triangle', peak: 0.12, attack: 0.02 }));
            for (let i = 0; i < 8; i++) tone(2093 + i * 150, t + 0.5 + i * 0.07, 0.2, { peak: 0.05 });
        },
        turn: (t) => [660, 880, 1175].forEach((f, i) => tone(f, t + i * 0.05, 0.12, { type: 'triangle', peak: 0.12 })),
        compost: (t) => {
            noise(t, 0.3, { freq: 400, to: 120, peak: 0.4, attack: 0.02 });
            tone(1047, t + 0.3, 0.3, { type: 'triangle', peak: 0.15 }); tone(1568, t + 0.4, 0.4, { type: 'triangle', peak: 0.15 });
        },
        click: (t) => tone(1200, t, 0.03, { type: 'square', peak: 0.05 }),
    };
    let lastSplat = 0;
    function play(name) {
        if (!prefs.sfx || !SOUNDS[name] || !audio()) return;
        if (name === 'splat' || name === 'whoosh') {  // dragging on the wall: not a machine gun
            const now = performance.now();
            if (name === 'splat' && now - lastSplat < 60) return;
            if (name === 'splat') lastSplat = now;
        }
        SOUNDS[name](ctx.currentTime + 0.01);
    }
    document.addEventListener('na-tomato-throw', (e) => {
        if (!(e.detail && e.detail.wall)) play('whoosh');  // painting the wall: just the splats
        setTimeout(() => play(e.detail && e.detail.lucky ? 'golden' : 'splat'), e.detail && e.detail.flight ? 300 : 0);
    });

    // --- The radio ---
    const player = new Audio();
    player.preload = 'none';
    const all = SETS.flatMap(s => s.tracks.map(t => ({ ...t, set: s })));
    const find = (id) => all.find(t => t.id === id) || all[0];
    let current = find(prefs.track);
    function load(track) {
        current = track;
        prefs.track = track.id; save();
        player.src = BASE + track.id + '.mp3';
        player.volume = prefs.musicVol;
    }
    player.addEventListener('ended', () => {  // the next track from the same set (a set of one loops)
        const list = current.set.tracks;
        load(find(list[(list.findIndex(t => t.id === current.id) + 1) % list.length].id));
        player.play().catch(() => {});
    });
    const listeners = [];
    const changed = () => listeners.forEach(fn => fn());
    ['play', 'pause', 'ended'].forEach(ev => player.addEventListener(ev, changed));

    window.NAPitSound = {
        SETS, play,
        prefs: () => ({ ...prefs }),
        setSfx(on) { prefs.sfx = !!on; save(); if (on) play('click'); changed(); },
        setSfxVolume(v) { prefs.sfxVol = v; save(); if (master) master.gain.value = v; },
        setMusicVolume(v) { prefs.musicVol = v; save(); player.volume = v; },
        playing: () => !player.paused,
        current: () => current,
        pick(id) { load(find(id)); player.play().catch(() => {}); changed(); },
        toggle() {
            if (!player.src) load(current);
            if (player.paused) player.play().catch(() => {}); else player.pause();
            changed();
        },
        onChange(fn) { listeners.push(fn); },
        _player: player,  // for checks
    };
})();

/* The radio's panel in the Pit: a button in the jump row, opening tracks by set, music and effects volume. */
(function () {
    const S = window.NAPitSound, btn = document.getElementById('radioBtn'), panel = document.getElementById('radioPanel');
    if (!S || !btn || !panel) return;
    const p = S.prefs();
    panel.innerHTML = `<div class="radio-top"><button type="button" class="na-btn radio-play" id="radioPlay">▶</button>
        <span class="radio-now" id="radioNow"></span></div>
        ${S.SETS.map(set => `<div class="radio-set"><small class="muted">${set.name}</small><div class="radio-tracks">${set.tracks.map(t =>
            `<button type="button" class="radio-track" data-track="${t.id}" title="${set.name}">${t.title}</button>`).join('')}</div></div>`).join('')}
        <label class="radio-vol">🎶 <input type="range" id="radioMusicVol" min="0" max="1" step="0.05" value="${p.musicVol}" aria-label="Music volume"></label>
        <label class="radio-vol">💥 <input type="range" id="radioSfxVol" min="0" max="1" step="0.05" value="${p.sfxVol}" aria-label="Sound effects volume">
          <input type="checkbox" id="radioSfx" ${p.sfx ? 'checked' : ''}> <span>Sound effects</span></label>`;
    const $ = (id) => document.getElementById(id);
    function paint() {
        const playing = S.playing(), cur = S.current();
        $('radioPlay').textContent = playing ? '❚❚' : '▶';
        $('radioNow').textContent = cur.title;
        btn.textContent = playing ? `🎶 ${cur.title}` : '🎶 Radio';
        btn.classList.toggle('on', playing);
        panel.querySelectorAll('[data-track]').forEach(b => b.classList.toggle('on', b.dataset.track === cur.id));
    }
    S.onChange(paint);
    btn.addEventListener('click', () => { panel.hidden = !panel.hidden; btn.setAttribute('aria-expanded', String(!panel.hidden)); });
    document.addEventListener('click', (e) => { if (!panel.hidden && !panel.contains(e.target) && e.target !== btn) panel.hidden = true; });
    $('radioPlay').addEventListener('click', () => S.toggle());
    panel.addEventListener('click', (e) => { const b = e.target.closest('[data-track]'); if (b) S.pick(b.dataset.track); });
    $('radioMusicVol').addEventListener('input', (e) => S.setMusicVolume(Number(e.target.value)));
    $('radioSfxVol').addEventListener('input', (e) => S.setSfxVolume(Number(e.target.value)));
    $('radioSfxVol').addEventListener('change', () => S.play('pop'));
    $('radioSfx').addEventListener('change', (e) => S.setSfx(e.target.checked));
    paint();
})();
