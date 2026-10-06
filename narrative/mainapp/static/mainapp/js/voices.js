// Voice pickers on the character page: your ElevenLabs voices instead of pasted IDs, and a list of other
// people in the story with a voice of their own (saved in the hidden voice_cast field as {"Name": "voice id"}).
(function () {
    const castBox = document.getElementById('voiceCast');
    const castField = document.querySelector('input[name=voice_cast]');
    const note = document.getElementById('voiceListNote');
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    let voices = [];
    let preview = null;

    function label(v) {
        const bits = [v.gender, v.age && v.age.replace('_', ' '), v.accent].filter(Boolean).join(', ');
        return v.name + (bits ? ` (${bits})` : '');
    }

    function options(selected, emptyLabel) {
        const known = voices.some(v => v.id === selected);
        return `<option value="">${esc(emptyLabel)}</option>` +
            (selected && !known ? `<option value="${esc(selected)}" selected>${esc(selected)} (not in your list)</option>` : '') +
            voices.map(v => `<option value="${esc(v.id)}" ${v.id === selected ? 'selected' : ''}>${esc(label(v))}</option>`).join('');
    }

    function playPreview(id) {
        const v = voices.find(x => x.id === id);
        if (preview) preview.pause();
        if (v && v.preview) { preview = new Audio(v.preview); preview.play().catch(() => {}); }
    }

    // The three fields of the form become dropdowns (the text input stays, hidden, and is what gets saved)
    function upgrade(input) {
        if (!input || input.dataset.upgraded) return;
        input.dataset.upgraded = '1';
        input.type = 'hidden';
        const wrap = document.createElement('div');
        wrap.className = 'voice-pick';
        wrap.innerHTML = `<select>${options(input.value, '— Pick one for me —')}</select>
            <button type="button" class="voice-preview" title="Hear a sample">▶</button>`;
        input.after(wrap);
        const select = wrap.querySelector('select');
        select.onchange = () => { input.value = select.value; };
        wrap.querySelector('.voice-preview').onclick = () => playPreview(select.value);
    }

    // --- The cast ---
    function readCast() {
        try { return JSON.parse(castField.value || '{}') || {}; } catch (e) { return {}; }
    }

    function writeCast() {
        const cast = {};
        castBox.querySelectorAll('.cast-row').forEach(row => {
            const name = row.querySelector('input').value.trim();
            const id = row.querySelector('select').value;
            if (name && id) cast[name] = id;
        });
        castField.value = JSON.stringify(cast);
    }

    function addRow(name = '', id = '') {
        const row = document.createElement('div');
        row.className = 'cast-row';
        row.innerHTML = `<input type="text" placeholder="Name, as the story says it" value="${esc(name)}" maxlength="60">
            <select>${options(id, '— Pick a voice —')}</select>
            <button type="button" class="voice-preview" title="Hear a sample">▶</button>
            <button type="button" class="cast-remove" title="Remove">✕</button>`;
        castBox.appendChild(row);
        row.querySelector('input').oninput = writeCast;
        row.querySelector('select').onchange = writeCast;
        row.querySelector('.voice-preview').onclick = () => playPreview(row.querySelector('select').value);
        row.querySelector('.cast-remove').onclick = () => { row.remove(); writeCast(); };
    }

    async function start() {
        try {
            const resp = await fetch(window.ELEVEN_VOICES_URL);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Could not load your voices.');
            voices = data.voices || [];
            if (note) note.textContent = `${voices.length} voices from your ElevenLabs account. Add more in ElevenLabs' Voice Library and reload.`;
        } catch (err) {
            if (note) note.textContent = err.message + ' You can still paste voice IDs.';
            return;  // keep the plain text fields
        }
        ['eleven_voice_char_id', 'eleven_voice_narr_id', 'eleven_voice_second_id']
            .forEach(n => upgrade(document.querySelector(`input[name=${n}]`)));
        Object.entries(readCast()).forEach(([n, id]) => addRow(n, id));
        document.getElementById('addCastBtn').onclick = () => addRow();
    }

    if (castBox && castField) start();
})();
