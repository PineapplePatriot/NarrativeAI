/* 📇 The quick view: tap the character's picture or name in a chat for their card at a glance, without leaving
   the story. Who they are, how they look, their temperament, and from this chat's story memory: where the
   relationship stands, who they've met, the scene now. Edit and Story memory are a tap away. */
(function () {
    const me = document.currentScript;
    const url = me && me.dataset.url;
    if (!url) return;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));
    let shade = null, cache = null, opener = null;

    function close() {
        if (!shade) return;
        shade.classList.remove('open');
        const s = shade; shade = null;
        setTimeout(() => s.remove(), 220);
        document.removeEventListener('keydown', onKey);
        if (opener) opener.focus();
    }
    function onKey(e) { if (e.key === 'Escape') close(); }

    const bar = (label, v) => `<div class="qc-bar"><span>${label}</span><i><b style="width:${(Number(v) || 0) * 10}%"></b></i><em>${v ?? '–'}</em></div>`;
    const section = (title, text) => text ? `<div class="qc-sec"><h5>${esc(title)}</h5><p>${esc(text)}</p></div>` : '';

    function render(d) {
        const many = d.people.length > 1;
        const people = d.people.map(p => `
            ${many ? `<h4 class="qc-person">${esc(p.name)}</h4>` : ''}
            <div class="qc-chips"><span>💗 ${esc(p.pace)}</span>${p.route !== 'Basic' ? `<span>🧭 ${esc(p.route)}</span>` : ''}${p.start ? `<span>Starts: ${esc(p.start)}</span>` : ''}</div>
            ${section('Who they are', p.identity)}${section('Appearance', p.appearance)}
            <details class="qc-more"><summary>More: personality, voice, wants</summary>
              ${section('Personality in action', p.personality)}${section('Temperament', p.temperament)}${section('Voice', p.voice)}${section('Wants', p.goals)}</details>`).join('');
        const shared = Object.entries(d.shared).map(([t, v]) => section(t, v)).join('');
        const rels = d.relationships.map(r => `<div class="qc-rel">
              <div class="qc-rel-head"><b>${esc(r.from)}</b> → <b>${esc(r.to)}</b> <small>${esc(r.route)}</small></div>
              <div class="qc-ladder">${r.ladder.map(s => `<span class="${s === r.stage ? 'on' : ''}">${esc(s)}</span>`).join('')}</div>
              ${bar('Trust', r.trust)}${bar('Warmth', r.warmth)}${bar('Tension', r.tension)}
              ${r.last ? `<p class="qc-last">Last: ${esc(r.last)}</p>` : ''}</div>`).join('');
        const met = d.met.map(p => `<li><b>${esc(p.name)}</b>${p.identity ? `: ${esc(p.identity)}` : ''}</li>`).join('');
        const story = d.memory_on
            ? (rels || met || d.now
                ? `${d.now ? `<div class="qc-sec"><h5>Now</h5><p><b>${esc(d.now.title)}</b>${d.now.where ? ` · ${esc(d.now.where)}` : ''}<br>${esc(d.now.summary)}</p></div>` : ''}
                   ${rels}${met ? `<div class="qc-sec"><h5>Met so far</h5><ul>${met}</ul></div>` : ''}`
                : '<p class="qc-empty">Story memory fills this in as the story goes (every few messages).</p>')
            : '<p class="qc-empty">This chat uses the manual summary. Switch to story memory (📚 Summary → 🧠 Story memory) to follow relationships here.</p>';
        const portrait = d.photo
            ? `<img class="qc-pic" src="${esc(d.photo)}" alt="">${d.second_photo ? `<img class="qc-pic qc-pic2" src="${esc(d.second_photo)}" alt="">` : ''}`
            : `<span class="qc-initial">${esc(d.name.slice(0, 1).toUpperCase())}</span>`;
        return `<div class="qc-card" role="dialog" aria-modal="true" aria-label="${esc(d.name)}" style="--card-accent:${esc(d.look.color)}">
            <div class="qc-portrait">${d.look.bg ? `<span class="qc-scene" style="background-image:url('${esc(d.look.bg)}')"></span>` : ''}${portrait}
              <span class="qc-badges">${d.look.badge ? `<span>${esc(d.look.badge)}</span>` : ''}${d.look.route ? `<span>${esc(d.look.route)}</span>` : ''}</span>
              <button type="button" class="qc-x" aria-label="Close">✕</button>
              <div class="qc-title"><h3>${esc(d.name)}</h3>${d.tagline ? `<p>${esc(d.tagline)}</p>` : ''}</div></div>
            <div class="qc-tabs" role="tablist"><button type="button" class="on" data-qc="card">The card</button><button type="button" data-qc="story">In this story</button></div>
            <div class="qc-body" data-pane="card">${shared}${people || section('About', d.about) +
                '<p class="qc-empty">A one-box card: “✨ Upgrade this card” on its page sorts it into sections.</p>'}</div>
            <div class="qc-body" data-pane="story" hidden>${story}</div>
            <div class="qc-foot"><a class="qc-btn" href="${esc(d.edit_url)}">✏️ Edit card</a>
              <button type="button" class="qc-btn" data-qc-memory>🧠 Story memory</button></div></div>`;
    }

    async function open(from) {
        if (shade) return;
        opener = from || null;
        shade = document.createElement('div');
        shade.className = 'qc-shade';
        shade.innerHTML = '<div class="qc-card qc-loading">…</div>';
        document.body.append(shade);
        requestAnimationFrame(() => shade && shade.classList.add('open'));
        document.addEventListener('keydown', onKey);
        try {
            if (!cache) {
                const resp = await fetch(url, { headers: { Accept: 'application/json' } });
                if (!resp.ok) throw new Error();
                cache = await resp.json();
            }
            if (!shade) return;
            shade.innerHTML = render(cache);
            shade.querySelector('.qc-x').focus();
        } catch (e) {
            if (shade) shade.innerHTML = '<div class="qc-card"><p class="qc-empty">Couldn’t load the card. Try again in a moment.</p></div>';
        }
    }

    document.addEventListener('click', (e) => {
        if (shade) {
            if (e.target === shade || e.target.closest('.qc-x')) return close();
            const tab = e.target.closest('[data-qc]');
            if (tab) {
                shade.querySelectorAll('[data-qc]').forEach(b => b.classList.toggle('on', b === tab));
                shade.querySelectorAll('[data-pane]').forEach(p => { p.hidden = p.dataset.pane !== tab.dataset.qc; });
                return;
            }
            if (e.target.closest('[data-qc-memory]')) {
                close();
                if (window.Summary) Summary.toggle(true);
                document.querySelector('.mem-tab[data-tab="memory"]')?.click();
            }
            return;
        }
        const hit = e.target.closest('.chat-header .character-avatar:not(.add-picture), .chat-header .character-details h3, .character-info-panel .character-name, [data-quick-card]');
        if (hit) { e.preventDefault(); open(hit); }
    });
    window.NAQuickCard = { open, forget: () => { cache = null; } };

    // Make the picture and name read as something to tap
    document.querySelectorAll('.chat-header .character-avatar:not(.add-picture), .chat-header .character-details h3, .character-info-panel .character-name').forEach(el => {
        el.classList.add('qc-hit');
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.title = 'Quick look at the card';
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(el); } });
    });
})();
