// Weather and time of day over the scene, read from the World tracker's "time" and "weather" (no AI, free):
// a night tint, a dusk or dawn glow, rain (with lightning in a storm), snow or fog. Off with the switch in the
// pen menu (remembered in this browser), or when the system asks for reduced motion (tints only).
window.Atmosphere = (function () {
    const scene = document.querySelector('.character-background');
    if (!scene) return { update() {}, timeOfDay, weather };
    const layer = document.createElement('div');
    layer.className = 'atmosphere';
    layer.setAttribute('aria-hidden', 'true');
    scene.after(layer);
    // The weather again in front of the chat, only around the edges (the middle stays clear for reading): on a
    // phone the replies cover nearly all of the background, so the layer behind them alone was barely seen
    const front = document.createElement('div');
    front.className = 'atmosphere atmo-front';
    front.setAttribute('aria-hidden', 'true');
    document.body.appendChild(front);
    let last = null;

    const pick = (kind, v) => {  // the pen menu's fixed weather / time of day for this browser ('' = follow the scene)
        try {
            if (v === undefined) return localStorage.getItem('atmosphere-' + kind) || '';
            if (v) localStorage.setItem('atmosphere-' + kind, v); else localStorage.removeItem('atmosphere-' + kind);
        } catch (e) { return ''; }
        return v;
    };
    const store = (v) => { try { if (v === undefined) return localStorage.getItem('atmosphere'); localStorage.setItem('atmosphere', v); } catch (e) { return null; } };
    const isOn = () => store() !== 'off';

    function timeOfDay(text) {
        const t = String(text || '').toLowerCase();
        if (!t) return '';
        const m = t.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);
        if (m) {
            let h = Number(m[1]) % 24;
            if (m[3] === 'pm' && h < 12) h += 12;
            if (m[3] === 'am' && h === 12) h = 0;
            if (h >= 21 || h < 5) return 'night';
            if (h < 7) return 'dawn';
            if (h >= 18) return 'dusk';
            return 'day';
        }
        if (/midnight|night|late evening|small hours|pitch dark/.test(t)) return 'night';
        if (/dusk|sunset|twilight|evening|nightfall/.test(t)) return 'dusk';
        if (/dawn|sunrise|daybreak|first light/.test(t)) return 'dawn';
        return 'day';
    }

    function weather(text) {
        const w = String(text || '').toLowerCase();
        if (/thunder|storm|lightning|tempest/.test(w)) return 'storm';
        if (/rain|drizzl|shower|downpour|wet/.test(w)) return 'rain';
        if (/snow|blizzard|sleet|flurr/.test(w)) return 'snow';
        if (/fog|mist|haze|smog/.test(w)) return 'fog';
        if (/clear|sunny|cloudless|fair|bright sky|blue sky/.test(w)) return 'clear';
        return '';
    }

    function update(world) {
        world = world || {};
        // Until the World tracker says what the weather is, the character's theme does (Bulba's pick, or the
        // background's name): a rainy scene opens with rain
        // Weather it doesn't recognise ("cold, still air", "indoors") keeps the theme's; only a clear sky ends it
        const told = weather(world.weather);
        let seen = told === 'clear' ? '' : (told || window.THEME_WEATHER || '');
        let hour = timeOfDay(world.time);
        // A fixed pick in the pen menu wins over the scene ('' = follow the scene)
        const pickW = pick('weather'), pickT = pick('time');
        if (pickW) seen = pickW === 'clear' ? '' : pickW;
        if (pickT) hour = pickT === 'day' ? 'day' : pickT;
        const next = isOn() ? `${hour}|${seen}` : '|';
        if (next === last) return;
        last = next;
        const [time, sky] = next.split('|');
        layer.className = 'atmosphere' + (time ? ` time-${time}` : '') + (sky ? ` sky-${sky}` : '');
        layer.innerHTML = sky ? `<div class="sky"></div>${sky === 'storm' ? '<div class="flash"></div>' : ''}` : '';
        front.className = 'atmosphere atmo-front' + (sky ? ` sky-${sky}` : '');
        front.innerHTML = sky ? '<div class="sky"></div>' : '';
        const label = document.getElementById('atmosphereNow');
        if (label) label.textContent = [time, sky].filter(Boolean).join(', ') || 'nothing to show yet';
    }

    const toggle = document.getElementById('atmosphereToggle');
    if (toggle) {
        toggle.checked = isOn();
        toggle.addEventListener('change', () => { store(toggle.checked ? 'on' : 'off'); last = null; update(window.__lastWorld); });
    }
    document.querySelectorAll('#atmoPicks [data-atmo]').forEach(row => {
        const mark = () => row.querySelectorAll('[data-pick]').forEach(b => b.classList.toggle('on', b.dataset.pick === pick(row.dataset.atmo)));
        mark();
        row.addEventListener('click', (e) => {
            const b = e.target.closest('[data-pick]');
            if (!b) return;
            pick(row.dataset.atmo, b.dataset.pick);
            mark();
            if (toggle && !toggle.checked && b.dataset.pick) { toggle.checked = true; toggle.dispatchEvent(new Event('change')); }
            last = null;
            update(window.__lastWorld);
        });
    });
    update(window.__lastWorld || {});  // the theme's weather straight away, before any tracker has run
    return { refresh() { last = null; update(window.__lastWorld || {}); }, update(world) { window.__lastWorld = world; update(world); }, timeOfDay, weather };
})();
