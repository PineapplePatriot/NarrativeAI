/* 🎶 Music that follows them around the app: the Pit radio or a chat's music keeps going on the other pages.
   - The Pit radio and a chat's music player write what's playing (track, where in it, volume) into this browser.
   - Any other page picks it up where it was (a short gap while the page loads) with a small ▶/❚❚ button in the
     top bar. The Pit picks a radio track back up in its own radio; a chat with music of its own plays its own
     (the carried one stops), a chat without music keeps the carried one going.
   - Browsers allow sound only after a click: when a page may not start it by itself, it starts on the first click.
   - Pausing it (on any page) means it stays paused on the next ones. */
(function () {
    if (window.NARadio) return;
    const KEY = 'na-radio-carry';
    const STALE = 30 * 60 * 1000;  // a state older than this (they left the app) isn't picked up
    const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } };
    const write = (s) => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private window */ } };

    let leaving = false;  // a page being left pauses its audio: that pause isn't theirs
    let heard = false;    // something played on this page; a page that never made a sound leaves the music as it was
    document.addEventListener('play', () => { heard = true; }, true);
    window.addEventListener('pagehide', () => { leaving = true; if (heard) save(); });
    window.addEventListener('pageshow', () => { leaving = false; });

    // --- What plays here: an owner (the Pit radio, a chat's music) or the carried player ---
    const owners = [];  // {player, info: () => ({list, i}) }
    let carried = null;

    function active() {
        const o = owners.find(o => o.player.src && !o.player.paused);
        if (o) return { player: o.player, info: o.info };
        if (carried && carried.player.src) return { player: carried.player, info: () => carried.state };
        const any = owners.find(o => o.player.src);
        return any ? { player: any.player, info: any.info } : null;
    }
    function save() {
        const a = active();
        if (!a) return;
        const info = a.info();
        if (!info || !info.list || !info.list.length) return;
        write({ list: info.list, i: info.i || 0, time: a.player.currentTime || 0, playing: !a.player.paused,
                vol: a.player.volume, at: Date.now() });
    }
    function watch(player, info) {
        owners.push({ player, info });
        let last = 0;
        player.addEventListener('play', () => { heard = true; stopCarried(); save(); });
        player.addEventListener('pause', () => { if (!leaving && document.visibilityState === 'visible') save(); });
        player.addEventListener('timeupdate', () => { const now = Date.now(); if (now - last > 2000) { last = now; save(); } });
        player.addEventListener('volumechange', () => { if (!player.paused) save(); });
    }
    function stopCarried() {
        if (!carried) return;
        carried.player.pause();
        carried.player.removeAttribute('src');
        carried = null;
        paint();
    }

    // Start sound now, or on their first click if the browser says no
    function start(player) {
        player.play().catch(() => {
            const go = () => { if (player.src && player.paused && !player.dataset.held) player.play().catch(() => {}); };
            document.addEventListener('pointerdown', go, { once: true, capture: true });
            document.addEventListener('keydown', go, { once: true, capture: true });
        });
    }
    function at(player, time) {
        const seek = () => { try { player.currentTime = time; } catch (e) { /* not seekable yet */ } };
        if (player.readyState >= 1) seek(); else player.addEventListener('loadedmetadata', seek, { once: true });
    }

    // --- The small button in the top bar (only while the carried music is the one here) ---
    let btn = null;
    function paint() {
        if (!btn) return;
        const on = carried && carried.player.src;
        btn.hidden = !on;
        if (!on) return;
        const t = carried.state.list[carried.state.i] || {};
        btn.textContent = carried.player.paused ? '▶ 🎶' : '❚❚ 🎶';
        btn.title = `${carried.player.paused ? 'Play' : 'Pause'}: ${t.name || 'music'}`;
        btn.classList.toggle('playing', !carried.player.paused);
    }

    function carry(state) {
        const player = new Audio();
        player.preload = 'auto';
        carried = { player, state };
        const load = () => {
            const t = state.list[state.i] || state.list[0];
            player.src = t.url;
        };
        load();
        player.volume = Math.min(1, Math.max(0, Number(state.vol ?? 0.4)));
        at(player, Number(state.time) || 0);
        player.addEventListener('ended', () => {  // the next one, the way it played where it started
            state.i = (state.i + 1) % state.list.length;
            load(); player.play().catch(() => {}); save();
        });
        ['play', 'pause'].forEach(ev => player.addEventListener(ev, () => {
            paint();
            if (!leaving && document.visibilityState === 'visible') save();
        }));
        let last = 0;
        player.addEventListener('timeupdate', () => { const now = Date.now(); if (now - last > 2000) { last = now; save(); } });
        start(player);
        paint();
    }

    function init() {
        // The owners on this page
        const pit = window.NAPitSound;
        if (pit && pit._player) {
            const radioList = () => {
                const cur = pit.current();
                const list = pit.prefs().loop ? cur.set.tracks : pit.SETS.flatMap(s => s.tracks);
                return { list: list.map(t => ({ url: t.url, name: t.title })), i: Math.max(0, list.findIndex(t => t.id === cur.id)) };
            };
            watch(pit._player, radioList);
        }
        const chatMusic = document.getElementById('bgMusicPlayer');
        if (chatMusic) {
            watch(chatMusic, () => chatMusic.src ? { list: [{ url: chatMusic.src,
                name: (document.getElementById('nowPlayingText') || {}).innerText || 'Chat music' }], i: 0 } : null);
        }

        const box = document.querySelector('.na-topbar .na-user');
        if (box) {
            btn = document.createElement('button');
            btn.type = 'button'; btn.className = 'na-radio-btn'; btn.hidden = true;
            btn.addEventListener('click', () => {
                if (!carried) return;
                if (carried.player.paused) { delete carried.player.dataset.held; carried.player.play().catch(() => {}); }
                else { carried.player.dataset.held = '1'; carried.player.pause(); }
            });
            box.prepend(btn);
        }

        // Pick up what was playing on the last page
        const s = read();
        if (!s || !s.playing || !Array.isArray(s.list) || !s.list.length || Date.now() - (s.at || 0) > STALE) return;
        if (chatMusic && (chatMusic.src || (window.SAVED_MUSIC && window.SAVED_MUSIC.url))) return;  // this chat has music of its own
        const url = (s.list[s.i] || {}).url;
        if (pit && pit._player) {
            const track = pit.SETS.flatMap(set => set.tracks).find(t => url && (t.url === url || url.endsWith(t.url)));
            if (track) {  // a radio track: the Pit's own radio carries on with it
                pit.pick(track.id);
                at(pit._player, Number(s.time) || 0);
                if (pit._player.paused) start(pit._player);
                return;
            }
        }
        carry(s);
    }

    window.NARadio = { save, _carried: () => carried };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
