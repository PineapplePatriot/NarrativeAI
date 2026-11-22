/* 🧩 The persona in parts: the seven core elements (mainapp/card_sections.py PERSONA), each its own box. They're
   written into the persona's text as "[Appearance]"-style parts, which is what the AI reads; text that isn't in a
   part stays at the end as it was. Used on the profile page (their usual persona) and wherever a chat's own persona
   is written (the chat page, the Screen): PersonaParts.attach(textarea). */
(function () {
    const DEFAULT_PARTS = [
        { key: 'pronouns', title: 'Name & pronouns', hint: 'Their name, and how others refer to them (she/he/they...).' },
        { key: 'appearance', title: 'Appearance', hint: 'Build, face, hair, eyes, what they usually wear, how they move.' },
        { key: 'background', title: 'Background & lore', hint: "Where they come from and what shaped them, in this story's world." },
        { key: 'connection', title: 'Connection to the story', hint: "How they're tied to the card's characters (or to its world): history, debts, roles." },
        { key: 'traits', title: 'Core traits', hint: 'How they behave: what they do, not adjectives.' },
        { key: 'likes', title: 'Likes & dislikes', hint: "What draws them in and what they can't stand." },
        { key: 'temperament', title: 'Temperament', hint: 'A line per situation: in danger, when flirted with, when lied to, as trust grows, at a low point; and how they change.' },
    ];
    const fromPage = JSON.parse(document.getElementById('persona-parts')?.textContent || '[]');
    const PARTS = fromPage.length ? fromPage : DEFAULT_PARTS;
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const titles = Object.fromEntries(PARTS.map(p => [p.title.toLowerCase(), p.key]));
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
        const out = PARTS.map(p => [p.title, box.querySelector(`[data-part="${p.key}"]`).value.trim()]).filter(([, v]) => v)
            .map(([t, v]) => `[${t}]\n${v}`);
        const rest = box.querySelector('[data-part="rest"]').value.trim();
        if (rest) out.push(rest);
        return out.join('\n\n');
    }

    function attach(area, { remember = 'na-persona-parts', inputClass = 'form-input' } = {}) {
        if (!area || area.dataset.personaParts) return;
        area.dataset.personaParts = '1';
        const toggle = document.createElement('button');
        toggle.type = 'button'; toggle.className = 'secondary persona-parts-toggle';
        area.before(toggle);
        let box = null;
        function show(on) {
            toggle.textContent = on ? '📝 One text box' : '🧩 Write it in parts (seven core elements)';
            area.hidden = on;
            try { localStorage.setItem(remember, on ? '1' : ''); } catch (e) { /* private window */ }
            if (!on) { if (box) box.remove(); box = null; return; }
            const { found, rest } = split(area.value);
            box = document.createElement('div');
            box.className = 'persona-parts';
            box.innerHTML = PARTS.map(p => `<label class="persona-part"><b>${esc(p.title)}</b><small>${esc(p.hint)}</small>
                  <textarea class="${inputClass}" rows="2" data-part="${p.key}"></textarea></label>`).join('') +
                `<label class="persona-part"><b>Anything else</b><small>Kept as it is, after the parts.</small>
                  <textarea class="${inputClass}" rows="2" data-part="rest"></textarea></label>`;
            area.after(box);
            PARTS.forEach(p => { box.querySelector(`[data-part="${p.key}"]`).value = found[p.key] || ''; });
            box.querySelector('[data-part="rest"]').value = rest;
            box.querySelectorAll('textarea').forEach(t => { t.rows = Math.min(8, Math.max(2, Math.ceil(t.value.length / 70))); });
            box.addEventListener('input', () => { area.value = compose(box); area.dispatchEvent(new Event('input', { bubbles: true })); });
        }
        toggle.addEventListener('click', () => show(area.hidden === false));
        let start = false;
        try { start = localStorage.getItem(remember) === '1'; } catch (e) { /* private window */ }
        show(start || /^\s*\[(Name & pronouns|Appearance|Who they are)\]/.test(area.value));
    }

    window.PersonaParts = { attach };
    attach(document.getElementById('id_persona_description'));  // the profile page
})();
