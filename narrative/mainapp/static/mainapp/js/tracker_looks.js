/* ✨ Tracker looks: a picture of what each tracker holds, shown above its edit form (trackers.js trackerCard).
   Read-only and drawn from the same values; editing stays in the form under "✎ Edit". Every look is plain HTML and
   CSS (tracker_looks.css), escaped, no pictures loaded.
     World           a little sky: place, time of day and weather, temperature, who's there
     Plot threads    threads by status: brewing (dotted), imminent (pulsing), resolved (tied off)
     Quests          a quest log: objective, reward, done ones ticked
     Off-screen      "Meanwhile…" cards
     Characters      a card each: initial, a mood face, what they do, a thought bubble
     Clothing        a dressing list by body part, wounds in red
     Relationships   a heart, a shield and a spark per person, with the status as a ribbon
     Milestones      a little path to where it stands now
     Favours         IOU slips with a stamp
     Secrets         redacted until tapped, who knows and who doesn't
     Memories        sticky notes, resolved ones crossed out
     Scrapbook       polaroids
     Stats           game bars coloured by what they are (health, energy, hunger, mana…)
     Conditions      status-effect badges
     Inventory       item tiles with a guessed icon and a count, coins on their own line
     Reputation      a scale from hostile to revered with a marker
     Achievements    trophies */
(function () {
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
    const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
    const pct = (v, min, max) => clamp(Math.round((num(v) - min) / ((max - min) || 1) * 100), 0, 100);
    const hue = (s) => { let h = 0; for (const ch of String(s || '')) h = (h * 31 + ch.codePointAt(0)) % 360; return h; };
    const initial = (s) => esc(([...String(s || '?').trim()][0] || '?').toUpperCase());
    const has = (re, s) => re.test(String(s || '').toLowerCase());
    const pick = (table, s, fallback) => { const t = String(s || '').toLowerCase(); for (const [re, v] of table) if (re.test(t)) return v; return fallback; };

    const MOODS = [[/happ|joy|cheer|glad|delight|elat|excit/, '😄'], [/amus|playful|teas|smirk|grin/, '😏'], [/calm|relax|content|peace|serene/, '😌'],
        [/sad|grief|mourn|down|melanch|tear/, '😢'], [/ang|furious|rage|irritat|annoy|livid/, '😠'], [/fear|scared|afraid|terrif|anxious|nervous|panic/, '😨'],
        [/love|smitten|tender|affection|adoring|warm/, '🥰'], [/shock|surpris|stun|astonish/, '😲'], [/tired|exhaust|sleepy|weary|drained/, '🥱'],
        [/curious|intrigu|interest|fascinat/, '🧐'], [/embarrass|flustered|blush|shy/, '😳'], [/suspic|wary|guard|distrust/, '🤨'],
        [/bored|indifferent|cold|aloof|detached/, '😐'], [/determin|focus|resolute|serious/, '😤'], [/drunk|tipsy/, '🥴'], [/hurt|pain|injur/, '😣'],
        [/smug|proud|confident/, '😎'], [/confus|puzzl|lost/, '😕'], [/lust|aroused|heated/, '😳']];
    const ITEMS = [[/coin|\bmora\b|money|cash|dollar|credit|penn|euro|grivn|hryvn|gold pieces?|silver pieces?|\bgold\b$|^gold\b/, '🪙'], [/gem|jewel|diamond|ruby|emerald|sapphire/, '💎'], [/sword|blade|dagger|knife|katana|sabre|saber/, '🗡️'],
        [/bow|arrow/, '🏹'], [/gun|pistol|rifle|revolver/, '🔫'], [/shield/, '🛡️'], [/axe/, '🪓'], [/staff|wand|rod/, '🪄'], [/potion|elixir|vial|flask|tonic/, '🧪'],
        [/key/, '🗝️'], [/book|tome|journal|diary|notebook/, '📖'], [/map/, '🗺️'], [/letter|note|scroll|envelope|paper/, '📜'], [/ring/, '💍'],
        [/necklace|amulet|pendant|locket/, '📿'], [/bread|food|ration|apple|meat|cheese|snack|meal/, '🍞'], [/water|wine|ale|beer|drink|bottle/, '🍶'],
        [/phone|mobile/, '📱'], [/torch|lantern|lamp|candle/, '🕯️'], [/rope/, '🪢'], [/bag|pouch|sack|backpack/, '👝'], [/cloak|coat|jacket|armor|armour/, '🧥'],
        [/herb|flower|plant|leaf/, '🌿'], [/medic|bandage|kit|salve/, '🩹'], [/tool|wrench|hammer|lockpick/, '🔧'], [/card|ticket|pass|badge/, '🎫'], [/crystal|orb|stone/, '🔮']];
    const CONDITIONS = [[/injur|wound|bleed|cut|hurt|bruis/, '🩸'], [/drunk|tipsy|intoxic/, '🍺'], [/curse|hex|jinx/, '🧿'], [/poison|venom|toxic/, '☠️'],
        [/exhaust|tired|fatig|weary|sleep/, '😮‍💨'], [/sick|ill|fever|nause|flu/, '🤒'], [/burn|fire|scorch/, '🔥'], [/cold|freez|frost|chill/, '🥶'],
        [/stun|daze|dizz|concuss/, '💫'], [/bless|holy|protect|ward/, '✨'], [/hungr|starv/, '🍽️'], [/fear|terrif|panic/, '😱'], [/charm|enthrall|love/, '💘'],
        [/broken|fractur/, '🦴'], [/blind/, '🙈'], [/hidden|invisib|stealth/, '🫥'], [/wet|soak|drench/, '💧'], [/aroused|heat/, '🌡️']];
    const STATS = [[/health|hp|life|vital/, ['#e5484d', '❤️']], [/energy|stamina|fatigue/, ['#f5b82e', '⚡']], [/hunger|food|satiety/, ['#e8833a', '🍖']],
        [/thirst|water|hydrat/, ['#3aa0e8', '💧']], [/mana|mp|magic|power|chakra|qi/, ['#6d6cf0', '✨']], [/sanity|mind|stress|morale/, ['#b16ce8', '🧠']],
        [/money|gold|cash|coin|mora|credit|dollar/, ['#d4a72c', '🪙']], [/xp|exp|level|experience/, ['#2fbf8f', '⭐']], [/arous|lust|desire/, ['#ea5aa0', '💗']],
        [/sleep|rest/, ['#7c8cf5', '🌙']], [/hygien|clean/, ['#5ec2d6', '🫧']], [/heat|temper/, ['#ef6b3a', '🌡️']]];
    const SKY = [[/storm|thunder|lightning/, '⛈️'], [/rain|drizzle|shower/, '🌧️'], [/snow|blizzard|sleet/, '❄️'], [/fog|mist|haze/, '🌫️'],
        [/cloud|overcast|grey|gray/, '☁️'], [/wind|gust|breez/, '🌬️'], [/clear|sunny|bright|sun/, '☀️']];

    function timeOf(t) {
        const A = window.Atmosphere;
        if (A && A.timeOfDay) return A.timeOfDay(t || '') || 'day';
        return 'day';
    }
    const TIME_ICON = { night: '🌙', dusk: '🌇', dawn: '🌅', day: '☀️' };

    function empty(text) { return `<p class="tl-empty">${text}</p>`; }
    const listOf = (v) => (Array.isArray(v) ? v : []);

    const LOOKS = {
        world(v) {
            const t = timeOf(v.time), sky = pick(SKY, v.weather, '');
            const present = Array.isArray(v.present) ? v.present : String(v.present || '').split(',').map(s => s.trim()).filter(Boolean);
            const temp = String(v.temperature || ''), deg = parseFloat(temp);
            const warm = Number.isFinite(deg) ? clamp((deg + 10) / 50, 0, 1) : (has(/hot|warm|swelter/, temp) ? .85 : has(/cold|freez|chill|cool/, temp) ? .15 : .5);
            if (!v.location && !v.time && !v.weather && !present.length) return empty('Nothing about the world yet.');
            return `<div class="tl-world" data-time="${t}">
                <div class="tlw-sky"><span class="tlw-orb">${TIME_ICON[t]}</span>${sky ? `<span class="tlw-weather">${sky}</span>` : ''}</div>
                <div class="tlw-place">📍 <b>${esc(v.location || 'Somewhere')}</b></div>
                <div class="tlw-when">${esc([v.time, v.date].filter(Boolean).join(' · '))}${v.weather ? ` · ${esc(v.weather)}` : ''}</div>
                ${temp ? `<div class="tlw-temp"><span class="tlw-therm"><i style="height:${Math.round(warm * 100)}%"></i></span>${esc(temp)}</div>` : ''}
                ${present.length ? `<div class="tlw-present">${present.slice(0, 8).map(n => `<span class="tl-ava" style="--h:${hue(n)}" title="${esc(n)}">${initial(n)}</span>`).join('')}${present.length > 8 ? `<span class="tl-more">+${present.length - 8}</span>` : ''}</div>` : ''}
            </div>`;
        },
        events(v) {
            const items = listOf(v);
            if (!items.length) return empty('No loose threads yet.');
            return `<ul class="tl-threads">${items.map(x => {
                const s = String(x.status || '').toLowerCase();
                const cls = has(/resolv|done|closed|paid/, s) ? 'resolved' : has(/immin|now|urgent|soon|close/, s) ? 'imminent' : 'brewing';
                return `<li class="${cls}"><span class="tlt-knot"></span><div><b>${esc(x.title)}</b>${x.detail ? `<small>${esc(x.detail)}</small>` : ''}</div><em>${esc(x.status || 'brewing')}</em></li>`;
            }).join('')}</ul>`;
        },
        quests(v) {
            const items = listOf(v);
            if (!items.length) return empty('No quests yet.');
            const order = items.slice().sort((a, b) => (a.done ? 1 : 0) - (b.done ? 1 : 0));
            return `<ul class="tl-quests">${order.map(q => `<li class="${q.done ? 'done' : ''}"><span class="tlq-box">${q.done ? '✔' : ''}</span>
                <div><b>${esc(q.title)}</b>${q.objective ? `<small>➤ ${esc(q.objective)}</small>` : ''}${q.reward ? `<small class="tlq-reward">🎁 ${esc(q.reward)}</small>` : ''}</div></li>`).join('')}</ul>`;
        },
        offscreen(v) {
            const items = listOf(v);
            if (!items.length) return empty('Nobody busy off-screen yet.');
            return `<p class="tl-kicker">Meanwhile…</p><div class="tl-meanwhile">${items.map(x => `<div><span class="tl-ava" style="--h:${hue(x.name)}">${initial(x.name)}</span>
                <div><b>${esc(x.name)}</b>${x.location ? `<small>📍 ${esc(x.location)}</small>` : ''}${x.doing ? `<small>${esc(x.doing)}</small>` : ''}</div></div>`).join('')}</div>`;
        },
        characters(v) {
            const items = listOf(v);
            if (!items.length) return empty('Nobody here yet.');
            return `<div class="tl-people">${items.map(c => `<div class="tlp-card" style="--h:${hue(c.name)}">
                <div class="tlp-top"><span class="tl-ava big">${initial(c.name)}<i>${pick(MOODS, c.mood, '🙂')}</i></span>
                  <div><b>${esc(c.name)}</b>${c.mood ? `<small>${esc(c.mood)}</small>` : ''}</div></div>
                ${c.doing ? `<p class="tlp-doing">${esc(c.doing)}</p>` : ''}
                ${c.outfit || c.appearance ? `<p class="tlp-look">👗 ${esc(c.outfit || c.appearance)}</p>` : ''}
                ${c.thoughts ? `<p class="tlp-think">💭 ${esc(c.thoughts)}</p>` : ''}</div>`).join('')}</div>`;
        },
        clothing(v) {
            const items = listOf(v);
            if (!items.length) return empty('No outfits noted yet.');
            const parts = [['head', '🎩'], ['upper_body', '👕'], ['lower_body', '👖'], ['feet', '👟'], ['accessories', '💍'], ['held', '✋']];
            return items.map(c => `<div class="tl-dress"><b class="tl-name" style="--h:${hue(c.name)}">${esc(c.name)}</b>
                <ul>${parts.filter(([k]) => c[k]).map(([k, ico]) => `<li><span>${ico}</span>${esc(c[k])}</li>`).join('')}
                ${c.wounds ? `<li class="wound"><span>🩸</span>${esc(c.wounds)}</li>` : ''}</ul></div>`).join('');
        },
        relationships(v, spec) {
            const items = listOf(v);
            if (!items.length) return empty('No relationships yet.');
            const range = k => (spec.fields.find(f => f.key === k) || { min: 0, max: 100 });
            const ra = range('affection'), rt = range('trust'), rx = range('tension');
            return `<div class="tl-rel">${items.map(r => {
                const a = num(r.affection), ap = pct(a, ra.min, ra.max);
                const heart = a < -30 ? '💔' : a < 10 ? '🤍' : a < 50 ? '🩷' : a < 80 ? '❤️' : '💖';
                return `<div class="tlr-card" style="--h:${hue(r.name)}"><div class="tlr-head"><span class="tl-ava">${initial(r.name)}</span><b>${esc(r.name)}</b>
                    ${r.status ? `<span class="tlr-ribbon${String(r.status).length > 24 ? ' long' : ''}">${esc(r.status)}</span>` : ''}</div>
                    <div class="tlr-row"><span class="tlr-ico" style="--s:${0.8 + ap / 250}">${heart}</span><span class="tlr-bar aff"><i style="width:${ap}%"></i></span><small>${esc(a)}</small></div>
                    <div class="tlr-row"><span class="tlr-ico">🛡️</span><span class="tlr-bar trust"><i style="width:${pct(r.trust, rt.min, rt.max)}%"></i></span><small>${esc(r.trust ?? '–')}</small></div>
                    <div class="tlr-row"><span class="tlr-ico">⚡</span><span class="tlr-bar tension"><i style="width:${pct(r.tension, rx.min, rx.max)}%"></i></span><small>${esc(r.tension ?? '–')}</small></div>
                    ${r.last_change ? `<p class="tlr-why">↳ ${esc(r.last_change)}</p>` : ''}</div>`;
            }).join('')}</div>`;
        },
        milestones(v) {
            const items = listOf(v);
            if (!items.length) return empty('No milestones yet.');
            return items.map(m => `<div class="tl-path"><b>${esc(m.who)}</b>${m.toward ? ` <small>toward ${esc(m.toward)}</small>` : ''}
                <div class="tlpa-line"><span class="dot past"></span><span class="seg"></span><span class="dot past"></span><span class="seg"></span><span class="dot now">${esc(m.now || '…')}</span></div>
                ${m.because ? `<small class="tl-sub">after ${esc(m.because)}</small>` : ''}</div>`).join('');
        },
        favours(v) {
            const items = listOf(v);
            if (!items.length) return empty('Nobody owes anybody. Yet.');
            return `<div class="tl-iou">${items.map(f => {
                const s = String(f.status || 'promised').toLowerCase();
                const cls = has(/repaid|paid|settled|done/, s) ? 'paid' : has(/broken|refus/, s) ? 'broken' : has(/call/, s) ? 'called' : 'open';
                return `<div class="tli-slip ${cls}"><small>I.O.U.</small><b>${esc(f.favour)}</b>
                    <span>${esc(f.owed_by || '?')} → ${esc(f.owed_to || '?')}</span><em class="tli-stamp">${esc(f.status || 'promised')}</em></div>`;
            }).join('')}</div>`;
        },
        secrets(v) {
            const items = listOf(v);
            if (!items.length) return empty('No secrets. Suspicious.');
            return `<div class="tl-secrets">${items.map(x => `<div class="tls-card"><button type="button" class="tls-redacted" data-reveal title="Tap to reveal">${esc(x.secret)}</button>
                ${x.known_by ? `<small>👁 knows: ${esc(Array.isArray(x.known_by) ? x.known_by.join(', ') : x.known_by)}</small>` : ''}
                ${x.hidden_from ? `<small>🙈 kept from: ${esc(Array.isArray(x.hidden_from) ? x.hidden_from.join(', ') : x.hidden_from)}</small>` : ''}</div>`).join('')}</div>`;
        },
        memories(v) {
            const items = listOf(v);
            if (!items.length) return empty('Nothing pinned yet.');
            return `<div class="tl-notes">${items.map((m, i) => `<div class="tln-note ${m.resolved ? 'resolved' : ''}" style="--r:${(i % 3 - 1) * 1.6}deg;--h:${[48, 95, 190, 330][i % 4]}">📌 ${esc(m.memory)}</div>`).join('')}</div>`;
        },
        scrapbook(v) {
            const items = listOf(v);
            if (!items.length) return empty('No keepsakes yet.');
            return `<div class="tl-polaroids">${items.map((k, i) => `<figure style="--r:${(i % 3 - 1) * 2.5}deg;--h:${hue(k.title)}"><div class="tlpo-pic">${esc(([...String(k.title || '✦')][0]) || '✦')}</div>
                <figcaption><b>${esc(k.title)}</b>${k.detail ? `<small>${esc(k.detail)}</small>` : ''}</figcaption></figure>`).join('')}</div>`;
        },
        stats(v) {
            const items = listOf(v);
            if (!items.length) return empty('No stats yet.');
            return `<div class="tl-stats">${items.map(s => {
                const [color, ico] = pick(STATS, s.name, ['#a78bfa', '◆']);
                const max = num(s.max, 0), val = num(s.value, 0), p = max ? pct(val, 0, max) : 0;
                return `<div class="tls-row" style="--c:${color}"><span class="tls-ico">${ico}</span><span class="tls-name">${esc(s.name)}</span>
                    ${max ? `<span class="tls-bar ${p <= 20 ? 'low' : ''}"><i style="width:${p}%"></i></span><b>${esc(s.value)}<small>/${esc(s.max)}</small></b>` : `<b class="tls-solo">${esc(s.value)}</b>`}</div>`;
            }).join('')}</div>`;
        },
        conditions(v) {
            const items = listOf(v);
            if (!items.length) return empty('Fit as a fiddle.');
            return `<div class="tl-effects">${items.map(c => `<div class="tle-badge" style="--h:${hue(c.name)}"><span class="tle-ico">${pick(CONDITIONS, c.name + ' ' + (c.effect || ''), '🌀')}</span>
                <div><b>${esc(c.name)}</b>${c.effect ? `<small>${esc(c.effect)}</small>` : ''}</div>${c.duration ? `<em>⏳ ${esc(c.duration)}</em>` : ''}</div>`).join('')}</div>`;
        },
        inventory(v) {
            const items = listOf(v);
            if (!items.length) return empty('Empty pockets.');
            const coin = items.filter(x => has(/currenc|money|coin/, x.group) || pick(ITEMS, x.name, '') === '🪙');
            const rest = items.filter(x => !coin.includes(x));
            const groups = {};
            rest.forEach(x => { const g = String(x.group || 'carried').toLowerCase(); (groups[g] = groups[g] || []).push(x); });
            const order = Object.keys(groups).sort((a, b) => (a === 'equipped' ? -1 : b === 'equipped' ? 1 : 0));
            return `${coin.length ? `<div class="tl-coins">${coin.map(c => `<span>🪙 <b>${esc(c.qty ?? '')}</b> ${esc(c.name)}</span>`).join('')}</div>` : ''}
                ${order.map(g => `<p class="tl-kicker">${esc(g)}</p><div class="tl-items">${groups[g].map(x => `<div class="tlit ${g === 'equipped' ? 'eq' : ''}" title="${esc(x.name)}">
                    <span class="tlit-ico">${pick(ITEMS, x.name, '📦')}</span><small>${esc(x.name)}</small>${num(x.qty, 1) > 1 ? `<em>×${esc(x.qty)}</em>` : ''}</div>`).join('')}</div>`).join('')}`;
        },
        reputation(v, spec) {
            const items = listOf(v);
            if (!items.length) return empty('Nobody has an opinion of you yet.');
            const f = spec.fields.find(x => x.key === 'standing') || { min: -100, max: 100 };
            const word = (n) => n <= -60 ? 'Hostile' : n <= -20 ? 'Unfriendly' : n < 20 ? 'Neutral' : n < 60 ? 'Friendly' : 'Revered';
            return `<div class="tl-rep">${items.map(r => {
                const n = num(r.standing);
                return `<div class="tlre-row"><div class="tlre-top"><b>${esc(r.group)}</b><em class="w-${word(n).toLowerCase()}">${word(n)}</em></div>
                    <div class="tlre-scale"><i style="left:${pct(n, f.min, f.max)}%"></i></div>${r.note ? `<small>${esc(r.note)}</small>` : ''}</div>`;
            }).join('')}</div>`;
        },
        achievements(v) {
            const items = listOf(v);
            if (!items.length) return empty('No trophies yet. Go do something.');
            return `<div class="tl-trophies">${items.map(a => `<div><span class="tltr-cup">🏆</span><b>${esc(a.name)}</b>${a.detail ? `<small>${esc(a.detail)}</small>` : ''}</div>`).join('')}</div>`;
        },
    };

    window.TrackerLooks = {
        has: (id) => !!LOOKS[id],
        render(id, value, spec) {
            const fn = LOOKS[id];
            if (!fn) return '';
            try { return `<div class="tl tl-${id}">${fn(value || (spec.kind === 'list' ? [] : {}), spec)}</div>`; }
            catch (e) { return ''; }  // a value in an odd shape: the form below still shows it
        },
    };
    // Secrets: tap to reveal (and again to hide)
    document.addEventListener('click', (e) => {
        const b = e.target.closest('[data-reveal]');
        if (b) b.classList.toggle('shown');
    });
})();
