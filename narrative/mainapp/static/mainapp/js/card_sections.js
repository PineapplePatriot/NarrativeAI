/* 🧩 The card as sections (mainapp/card_sections.py), on the character's edit page.
   - An old card (one text box) gets "Upgrade this card": Bulba sorts it into sections, nothing lost; it changes
     only when they press Save. Or they start a fresh structured card of a kind: one person, several, a world.
   - Each section has an on/off switch and what it costs in tokens; the description box shows the text the AI
     reads, made from the switched-on sections (read-only while the card has sections).
   - Fill empty (Bulba drafts the blanks), Appearance from the picture, add people or their own sections. */
(function () {
    const box = document.getElementById('cardSections');
    if (!box) return;
    const url = box.dataset.url;
    const csrf = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
    const desc = document.getElementById('id_description');
    const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    const KIND = { character: '👤 One character', ensemble: '👥 Several people', simulation: '🌍 Simulation (a world that makes its own people)' };
    const PACE = { slow: 'Slow to warm up', steady: 'Ordinary pace', fast: 'Quick to warm up' };
    let LABELS = {}, ROUTES = {}, data = null, costs = null, dirty = false, busy = false;
    const PERSON_KEYS = ['identity', 'appearance', 'personality', 'temperament', 'goals', 'voice', 'background', 'relationships', 'knowledge'];
    const SHARED_KEYS = { character: [], ensemble: ['setting', 'between'], simulation: ['world', 'places', 'factions', 'tone', 'start', 'new_people'] };
    const tok = t => Math.ceil((t || '').length / 4);

    async function call(body) {
        const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
        const d = await resp.json().catch(() => ({ error: 'The app server didn’t answer.' }));
        if (!resp.ok || d.error) throw new Error(d.error || 'Something went wrong.');
        return d;
    }
    function status(text, bad) { const s = box.querySelector('.cs-status'); if (s) { s.textContent = text || ''; s.classList.toggle('bad', !!bad); } }
    async function run(body, label, after) {
        if (busy) return;
        busy = true; paintBusy(label);
        try { const d = await call(body); after(d); }
        catch (e) { status(e.message, true); }
        finally { busy = false; paintBusy(''); }
    }
    function paintBusy(label) {
        box.querySelectorAll('button').forEach(b => { b.disabled = busy; });
        if (label) status(label);
    }

    function lockDescription(on) {
        if (!desc) return;
        desc.readOnly = on;
        desc.classList.toggle('cs-composed', on);
        let note = document.getElementById('csDescNote');
        if (on && !note) {
            note = document.createElement('p');
            note.id = 'csDescNote'; note.className = 'section-help';
            note.textContent = 'Made from the switched-on sections above: this is what the AI reads. Edit the sections to change it.';
            desc.after(note);
        } else if (!on && note) note.remove();
    }

    // --- An old card: one text box ---
    function paintPlain() {
        lockDescription(false);
        box.innerHTML = `<div class="cs-upgrade">
            <b>🧩 This card is one text box.</b>
            <p class="section-help">Sections make it easier to read and to trim: who they are, appearance, personality in action,
            temperament, wants, voice, background, relationships, knowledge. Each one can be switched off, and you see what it costs.
            The text the AI reads stays the same kind of plain card, so exports to SillyTavern keep working.</p>
            <div class="cs-actions">
              <button type="button" class="btn-secondary" data-act="structure">✨ Upgrade this card</button>
              <span class="section-help">or start empty:</span>
              ${Object.entries(KIND).map(([k, v]) => `<button type="button" class="cs-chip" data-new="${k}">${esc(v)}</button>`).join('')}
            </div>
            <p class="cs-status section-help" aria-live="polite"></p></div>`;
    }

    // --- The sections editor ---
    function sectionRow(where, key, s, cost) {
        const [title, hint] = LABELS[key] || [key, ''];
        return `<div class="cs-sec${s.on ? '' : ' off'}" data-where="${where}" data-key="${key}">
            <div class="cs-sec-head"><label class="cs-switch"><input type="checkbox" data-f="on" ${s.on ? 'checked' : ''}> <b>${esc(title)}</b></label>
            <small class="cs-cost">${s.on && s.text ? `~${cost} tokens` : s.on ? 'empty' : 'off'}</small></div>
            <textarea data-f="text" rows="${Math.min(12, Math.max(2, Math.ceil((s.text || '').length / 90)))}" placeholder="${esc(hint)}">${esc(s.text)}</textarea></div>`;
    }
    function paint() {
        if (!data) return paintPlain();
        lockDescription(true);
        const shared = SHARED_KEYS[data.kind].map(k => sectionRow('shared', k, data.shared[k] || { text: '', on: true }, (costs?.shared || {})[k] || 0)).join('');
        const many = data.kind !== 'character';
        const people = data.people.map((p, i) => `<fieldset class="cs-person" data-person="${i}">
            <legend>${many ? `<input class="cs-name" data-f="name" value="${esc(p.name)}" placeholder="Their name">` : esc(p.name || 'The character')}</legend>
            <div class="cs-temper"><span>💗 Temperament</span>
              <select data-t="pace" title="How fast they warm up to someone">${Object.entries(PACE).map(([k, v]) => `<option value="${k}" ${p.temperament.pace === k ? 'selected' : ''}>${v}</option>`).join('')}</select>
              <select data-t="route" title="Which route a relationship with them leans to">${Object.entries(ROUTES).map(([k, v]) => `<option value="${k}" ${p.temperament.route === k ? 'selected' : ''}>Route: ${esc(v)}</option>`).join('')}</select>
              <input data-t="start" value="${esc(p.temperament.start)}" placeholder="Starts toward you as… (e.g. cold and suspicious)"></div>
            ${PERSON_KEYS.map(k => sectionRow('p' + i, k, p.sections[k], ((costs?.people || [])[i] || {})[k] || 0)).join('')}
            <div class="cs-actions"><button type="button" class="cs-chip" data-picture="${i}">🖼 Appearance from the picture</button>
              ${many ? `<button type="button" class="cs-chip danger" data-drop="${i}">Remove ${esc(p.name || 'this person')}</button>` : ''}</div>
          </fieldset>`).join('');
        const extra = data.extra.map((e, i) => `<div class="cs-sec${e.on ? '' : ' off'}" data-where="extra" data-key="${i}">
            <div class="cs-sec-head"><label class="cs-switch"><input type="checkbox" data-f="on" ${e.on ? 'checked' : ''}></label>
            <input class="cs-title" data-f="title" value="${esc(e.title)}"><small class="cs-cost">${e.on ? `~${tok(e.text)} tokens` : 'off'}</small>
            <button type="button" class="cs-x" data-unextra="${i}" title="Remove this section">✕</button></div>
            <textarea data-f="text" rows="${Math.min(12, Math.max(2, Math.ceil((e.text || '').length / 90)))}">${esc(e.text)}</textarea></div>`).join('');
        box.innerHTML = `<div class="cs-top"><b>🧩 Sections</b> <span class="cs-kind">${esc(KIND[data.kind])}</span>
              <span class="cs-total">~${costs ? costs.total : 0} tokens in all</span></div>
            ${shared ? `<fieldset class="cs-person cs-shared"><legend>${data.kind === 'simulation' ? 'The world' : 'What they share'}</legend>${shared}</fieldset>` : ''}
            ${people}
            ${many ? `<button type="button" class="cs-chip" data-act="person">+ Add ${data.kind === 'simulation' ? 'a recurring person' : 'a person'}</button>` : ''}
            ${extra}
            <button type="button" class="cs-chip" data-act="extra">+ Your own section</button>
            <div class="cs-actions cs-main">
              <button type="button" class="btn-secondary cs-save" data-act="save">💾 Save sections</button>
              <button type="button" class="cs-chip" data-act="fill" title="Bulba drafts the switched-on sections that are empty (costs a little)">✨ Fill empty ones</button>
              <button type="button" class="cs-chip" data-act="plain" title="Keep the text as it is now, as one box">Back to one box</button>
            </div>
            <p class="cs-status section-help" aria-live="polite">${dirty ? 'Not saved yet: press Save sections.' : ''}</p>`;
    }

    // Edits: kept in `data` as they type; the cost and the description preview follow
    function compose() {  // the same text the server makes (mainapp/card_sections.py compose), for the preview
        const parts = [];
        SHARED_KEYS[data.kind].forEach(k => { const s = data.shared[k]; if (s && s.on && s.text) parts.push(`[${LABELS[k][0]}]\n${s.text}`); });
        const several = data.people.length > 1 || data.kind === 'simulation';
        data.people.forEach(p => {
            const own = PERSON_KEYS.filter(k => p.sections[k].on && p.sections[k].text).map(k => `[${LABELS[k][0]}]\n${p.sections[k].text}`);
            if (own.length) parts.push(several ? `## ${p.name || 'Someone'}\n` + own.join('\n\n') : own.join('\n\n'));
        });
        data.extra.forEach(e => { if (e.on && e.text) parts.push(`[${e.title}]\n${e.text}`); });
        return parts.join('\n\n');
    }
    function changed(repaint) {
        dirty = true;
        if (desc) desc.value = compose();
        const total = box.querySelector('.cs-total');
        if (total) total.textContent = `~${tok(desc ? desc.value : compose())} tokens in all`;
        if (repaint) { costs = null; paint(); }
        else status('Not saved yet: press Save sections.');
    }
    function target(el) {
        const sec = el.closest('.cs-sec');
        if (!sec) return null;
        const where = sec.dataset.where, key = sec.dataset.key;
        if (where === 'shared') return data.shared[key] || (data.shared[key] = { text: '', on: true });
        if (where === 'extra') return data.extra[Number(key)];
        return data.people[Number(where.slice(1))].sections[key];
    }
    box.addEventListener('input', e => {
        if (!data) return;
        const el = e.target;
        if (el.dataset.f === 'text' || el.dataset.f === 'title') {
            const t = target(el); if (!t) return;
            t[el.dataset.f] = el.value;
            const cost = el.closest('.cs-sec').querySelector('.cs-cost');
            if (cost && el.dataset.f === 'text') cost.textContent = t.on ? (t.text ? `~${tok(t.text)} tokens` : 'empty') : 'off';
            changed(false);
        } else if (el.dataset.f === 'name') {
            data.people[Number(el.closest('.cs-person').dataset.person)].name = el.value; changed(false);
        } else if (el.dataset.t === 'start') {
            data.people[Number(el.closest('.cs-person').dataset.person)].temperament.start = el.value; changed(false);
        }
    });
    box.addEventListener('change', e => {
        if (!data) return;
        const el = e.target;
        if (el.dataset.f === 'on') {
            const t = target(el); if (!t) return;
            t.on = el.checked; el.closest('.cs-sec').classList.toggle('off', !el.checked);
            const cost = el.closest('.cs-sec').querySelector('.cs-cost');
            if (cost) cost.textContent = t.on ? (t.text ? `~${tok(t.text)} tokens` : 'empty') : 'off';
            changed(false);
        } else if (el.dataset.t === 'pace' || el.dataset.t === 'route') {
            data.people[Number(el.closest('.cs-person').dataset.person)].temperament[el.dataset.t] = el.value; changed(false);
        }
    });
    function got(d, note) {
        data = d.sections; costs = d.costs; paint();
        if (data && desc && d.description != null) desc.value = d.description;
        status(note);
    }
    box.addEventListener('click', e => {
        const b = e.target.closest('button');
        if (!b || busy) return;
        if (b.dataset.new) return run({ action: 'new', kind: b.dataset.new }, 'Setting it up…', d => { dirty = true; got(d, 'Fill in the sections and press Save sections. The old text is still in the description until you save.'); });
        if (b.dataset.picture != null) {
            return run({ action: 'picture', person: Number(b.dataset.picture), sections: data }, 'Bulba is looking at the picture…', d => {
                dirty = true; got(d, `Appearance written from the picture${d.looked ? ` (looked: ${d.looked})` : ''}. Check it, then Save sections.`);
            });
        }
        if (b.dataset.drop != null) { data.people.splice(Number(b.dataset.drop), 1); return changed(true); }
        if (b.dataset.unextra != null) { data.extra.splice(Number(b.dataset.unextra), 1); return changed(true); }
        const act = b.dataset.act;
        if (act === 'structure') return run({ action: 'structure' }, 'Sorting the card into sections… (Bulba reads it; a long card takes a minute)', d => {
            dirty = true;
            got(d, 'Sorted. Nothing has changed yet: check the sections and press Save sections. Anything that fit nowhere is under “More”.');
        });
        if (act === 'person') {
            data.people.push({ name: '', temperament: { pace: 'steady', route: 'basic', start: '' },
                               sections: Object.fromEntries(PERSON_KEYS.map(k => [k, { text: '', on: true }])) });
            return changed(true);
        }
        if (act === 'extra') { data.extra.push({ title: 'More', text: '', on: true }); return changed(true); }
        if (act === 'fill') return run({ action: 'fill', sections: data }, 'Bulba is drafting the empty sections…', d => { dirty = true; got(d, 'Drafted. Read them over, change what you like, then Save sections.'); });
        if (act === 'save') return run({ action: 'save', sections: data }, 'Saving…', d => { dirty = false; got(d, '✓ Saved. The description below is made from these sections.'); });
        if (act === 'plain') {
            if (!confirm('Go back to one text box? The text stays as it is now; the sections are dropped.')) return;
            return run({ action: 'plain' }, 'Saving…', d => { data = null; dirty = false; if (desc && d.description != null) desc.value = d.description; paintPlain(); status('Back to one text box.'); });
        }
    });
    // Leaving with unsaved sections: the main Save button saves them first
    const form = box.closest('form');
    if (form) form.addEventListener('submit', async (e) => {
        if (!data || !dirty) return;
        e.preventDefault();
        try { const d = await call({ action: 'save', sections: data }); dirty = false; if (desc && d.description != null) desc.value = d.description; form.submit(); }
        catch (err) { status(err.message, true); }
    });

    fetch(url).then(r => r.json()).then(d => {
        LABELS = d.labels || {}; ROUTES = d.routes || {};
        data = d.sections; costs = d.costs; paint();
    }).catch(() => { box.hidden = true; });
})();
