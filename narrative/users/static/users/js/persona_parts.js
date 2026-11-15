/* 🧩 The persona in parts, on the profile page: the seven core elements (mainapp/card_sections.py PERSONA),
   each its own box. They're written into "About you in stories" as "[Appearance]"-style parts, which is what the
   AI reads; text that isn't in a part stays at the end as it was. */
(function () {
    const area = document.getElementById('id_persona_description');
    const parts = JSON.parse(document.getElementById('persona-parts')?.textContent || '[]');
    if (!area || !parts.length) return;
    const titles = Object.fromEntries(parts.map(p => [p.title.toLowerCase(), p.key]));
    Object.assign(titles, { 'who they are': 'pronouns', 'personality in action': 'traits', 'voice': 'traits', 'what they want here': 'connection' });

    function split(text) {
        const found = {}, rest = [];
        let current = null;
        for (const line of (text || '').split('\n')) {
            const m = line.match(/^\s*\[([^\]\n]{2,40})\]\s*$/);
            if (m && titles[m[1].trim().toLowerCase()]) { current = titles[m[1].trim().toLowerCase()]; continue; }
            (current ? (found[current] = found[current] || []) : rest).push(line);
        }
        return { found: Object.fromEntries(Object.entries(found).map(([k, v]) => [k, v.join('\n').trim()])), rest: rest.join('\n').trim() };
    }
    function compose(box) {
        const out = parts.map(p => [p.title, box.querySelector(`[data-part="${p.key}"]`).value.trim()]).filter(([, v]) => v)
            .map(([t, v]) => `[${t}]\n${v}`);
        const rest = box.querySelector('[data-part="rest"]').value.trim();
        if (rest) out.push(rest);
        return out.join('\n\n');
    }

    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.className = 'secondary persona-parts-toggle';
    area.before(toggle);
    let box = null;
    function show(on) {
        toggle.textContent = on ? '📝 One text box' : '🧩 Write it in parts (seven core elements)';
        area.hidden = on;
        try { localStorage.setItem('na-persona-parts', on ? '1' : ''); } catch (e) { /* private window */ }
        if (!on) { if (box) box.remove(); box = null; return; }
        const { found, rest } = split(area.value);
        box = document.createElement('div');
        box.className = 'persona-parts';
        box.innerHTML = parts.map(p => `<label class="persona-part"><b>${p.title}</b><small>${p.hint}</small>
              <textarea class="form-input" rows="2" data-part="${p.key}"></textarea></label>`).join('') +
            `<label class="persona-part"><b>Anything else</b><small>Kept as it is, after the parts.</small>
              <textarea class="form-input" rows="2" data-part="rest"></textarea></label>`;
        area.after(box);
        parts.forEach(p => { box.querySelector(`[data-part="${p.key}"]`).value = found[p.key] || ''; });
        box.querySelector('[data-part="rest"]').value = rest;
        box.querySelectorAll('textarea').forEach(t => { t.rows = Math.min(8, Math.max(2, Math.ceil(t.value.length / 70))); });
        box.addEventListener('input', () => { area.value = compose(box); });
    }
    toggle.addEventListener('click', () => show(area.hidden === false));
    let start = false;
    try { start = localStorage.getItem('na-persona-parts') === '1'; } catch (e) { /* private window */ }
    show(start || /^\s*\[(Name & pronouns|Appearance|Who they are)\]/.test(area.value));
})();
