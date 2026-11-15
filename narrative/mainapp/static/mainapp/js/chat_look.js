/* ✨ A custom chat look's moving parts (mainapp/chat_looks.py makes its styles): a light effect drifting over the
   page (sparkles, petals, snow...) and, if the look has one, a small sound when you send and when a reply lands.
   The effect follows the pen menu's "light effect" switch and the device's reduced-motion setting; the sound has
   its own switch there, kept in this browser. */
(function () {
    const data = (() => { try { return JSON.parse(document.getElementById('look-data').textContent); } catch (e) { return null; } })();
    if (!data || !document.body.classList.contains('skin-custom')) return;
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // --- The effect: a few drifting things, made once ---
    const GLYPHS = { sparkles: ['✦', '✧', '⋆', '✦'], stars: ['★', '☆', '✦'], hearts: ['♥', '♡'], snow: ['❄', '•', '❅'],
                     leaves: ['❦', '❧'], glitter: ['✧', '·', '✦', '˚'] };
    function effect() {
        const kind = data.effect;
        if (!kind || kind === 'none' || calm) return;
        const layer = document.createElement('div');
        layer.className = 'look-fx look-fx-' + kind;
        layer.setAttribute('aria-hidden', 'true');
        const n = { fireflies: 14, embers: 16, bubbles: 12, petals: 12, snow: 22, glitter: 26 }[kind] || 16;
        for (let i = 0; i < n; i++) {
            const s = document.createElement('i');
            const g = GLYPHS[kind];
            if (g) s.textContent = g[i % g.length];
            s.style.left = (Math.random() * 100).toFixed(1) + '%';
            s.style.top = (Math.random() * 100).toFixed(1) + '%';
            s.style.animationDelay = (-Math.random() * 20).toFixed(1) + 's';
            s.style.animationDuration = (10 + Math.random() * 14).toFixed(1) + 's';
            s.style.fontSize = (8 + Math.random() * 12).toFixed(0) + 'px';
            layer.append(s);
        }
        document.body.append(layer);
    }
    effect();

    // --- The sound: made by the browser (no files), quiet ---
    let ctx = null;
    const KEY = 'chat-look-sound';
    const on = () => { try { return localStorage.getItem(KEY) !== 'off'; } catch (e) { return true; } };
    function tone(freq, t, dur, type = 'sine', peak = 0.08, to = null) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = type; o.frequency.setValueAtTime(freq, t);
        if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + dur + 0.02);
    }
    const SOUNDS = {
        soft: { sent: t => tone(520, t, 0.12, 'sine', 0.05, 640), reply: t => { tone(660, t, 0.16, 'sine', 0.05); tone(880, t + 0.08, 0.2, 'sine', 0.04); } },
        chime: { sent: t => tone(1046, t, 0.25, 'triangle', 0.05), reply: t => { tone(784, t, 0.4, 'triangle', 0.05); tone(1175, t + 0.12, 0.5, 'triangle', 0.04); } },
        bubble: { sent: t => tone(300, t, 0.1, 'sine', 0.07, 700), reply: t => { tone(420, t, 0.09, 'sine', 0.06, 900); tone(520, t + 0.1, 0.09, 'sine', 0.05, 1000); } },
        typewriter: { sent: t => tone(1800, t, 0.03, 'square', 0.03), reply: t => { [0, 0.06, 0.13].forEach(d => tone(1600 + d * 900, t + d, 0.03, 'square', 0.025)); tone(2400, t + 0.24, 0.18, 'triangle', 0.03); } },
        retro: { sent: t => tone(440, t, 0.08, 'square', 0.03, 880), reply: t => { tone(523, t, 0.08, 'square', 0.03); tone(659, t + 0.08, 0.08, 'square', 0.03); tone(784, t + 0.16, 0.14, 'square', 0.03); } },
    };
    function play(which) {
        const set = SOUNDS[data.sound];
        if (!set || !on()) return;
        try {
            ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
            if (ctx.state === 'suspended') ctx.resume();
            set[which](ctx.currentTime + 0.01);
        } catch (e) { /* no sound here */ }
    }
    document.addEventListener('na-sent', () => play('sent'));
    document.addEventListener('na-replied', () => play('reply'));

    // The pen menu's switch for the sound (only shown when the look has one)
    const sw = document.getElementById('lookSoundToggle');
    if (sw) {
        sw.closest('label').hidden = !SOUNDS[data.sound];
        sw.checked = on();
        sw.addEventListener('change', () => {
            try { localStorage.setItem(KEY, sw.checked ? 'on' : 'off'); } catch (e) { /* this page only */ }
            if (sw.checked) play('reply');
        });
    }
    window.NALook = { play };
})();
