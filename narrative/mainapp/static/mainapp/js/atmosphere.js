// Weather and time of day over the scene, read from the World tracker's "time" and "weather" (no AI, free):
// a night tint, a dusk or dawn glow, rain (with lightning in a storm), snow or fog. Off with the switch in the
// pen menu (remembered in this browser), or when the system asks for reduced motion (tints only).
window.Atmosphere = (function () {
    const scene = document.querySelector('.character-background');
    if (!scene) return null;
    const layer = document.createElement('div');
    layer.className = 'atmosphere';
    layer.setAttribute('aria-hidden', 'true');
    scene.after(layer);
    let last = null;

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
        return '';
    }

    function update(world) {
        world = world || {};
        const next = isOn() ? `${timeOfDay(world.time)}|${weather(world.weather)}` : '|';
        if (next === last) return;
        last = next;
        const [time, sky] = next.split('|');
        layer.className = 'atmosphere' + (time ? ` time-${time}` : '') + (sky ? ` sky-${sky}` : '');
        layer.innerHTML = sky ? `<div class="sky"></div>${sky === 'storm' ? '<div class="flash"></div>' : ''}` : '';
        const label = document.getElementById('atmosphereNow');
        if (label) label.textContent = [time, sky].filter(Boolean).join(', ') || 'nothing to show yet';
    }

    const toggle = document.getElementById('atmosphereToggle');
    if (toggle) {
        toggle.checked = isOn();
        toggle.addEventListener('change', () => { store(toggle.checked ? 'on' : 'off'); last = null; update(window.__lastWorld); });
    }
    return { update(world) { window.__lastWorld = world; update(world); } };
})();
