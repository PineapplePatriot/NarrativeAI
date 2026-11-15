/* 🧠 Story memory, in the Summary panel (mainapp/story_memory.py): a tab beside the manual summary.
   - Which one this chat uses: story memory or the manual summary (one switch; only one is sent to the AI).
   - Milestones (a scene each, written so a reader who never saw the chat follows it), arcs, who is who,
     who knows what, and where each relationship stands: all readable and editable.
   - Update now; for an older chat, "Build memory for this chat" works through it a chunk at a time.
   - After a reply the page runs the update when it's due (NAMemory.afterReply). */
window.NAMemory = (() => {
    const panel = document.getElementById('summaryPanel');
    if (!panel) return null;
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    let data = JSON.parse(document.getElementById('memory-data')?.textContent || 'null') || { mode: 'manual', memory: {} };
    let busy = false, tab = data.mode === 'memory' ? 'memory' : 'manual';

    // --- The tabs: built around the summary panel's own parts ---
    const head = panel.querySelector('.tp-head');
    const tabs = document.createElement('div');
    tabs.className = 'mem-tabs';
    head.after(tabs);
    const box = document.createElement('div');
    box.className = 'tp-body mem-body';
    box.id = 'memoryBody';
    const foot = document.createElement('div');
    foot.className = 'tp-foot mem-foot';
    panel.append(box, foot);
    const manualParts = [document.getElementById('summaryStatus'), document.getElementById('summaryBody'), panel.querySelector('.sum-foot')];

    async function post(body, label) {
        if (busy) return null;
        busy = true; paint(label);
        try {
            const resp = await fetch(window.location.href, { method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify(body) });
            const d = await resp.json().catch(() => ({}));
            if (!d.success) throw new Error(d.error || 'Something went wrong.');
            data = d;
            if (d.spending && typeof updateSpending === 'function') updateSpending(d.spending);
            return d;
        } finally { busy = false; paint(); }
    }

    function paintTabs() {
        const using = data.mode === 'memory';
        tabs.innerHTML = `
            <button type="button" class="mem-tab${tab === 'manual' ? ' on' : ''}" data-tab="manual">📜 Summary${!using ? ' <small>in use</small>' : ''}</button>
            <button type="button" class="mem-tab${tab === 'memory' ? ' on' : ''}" data-tab="memory">🧠 Story memory${using ? ' <small>in use</small>' : ''}</button>`;
        manualParts.forEach(el => { if (el) el.hidden = tab !== 'manual'; });
        box.hidden = foot.hidden = tab !== 'memory';
        if (tab === 'manual' && using) {
            let note = document.getElementById('memManualNote');
            if (!note) {
                note = document.createElement('div');
                note.id = 'memManualNote'; note.className = 'sum-status mem-note';
                manualParts[0]?.before(note);
            }
            note.hidden = false;
            note.innerHTML = '<span>This chat uses story memory, so the summary below isn’t sent to the AI.</span>' +
                '<button type="button" class="icon-btn" data-mem="use-manual">Use the summary instead</button>';
        } else document.getElementById('memManualNote')?.remove();
    }

    const routeName = k => (data.routes?.[k]?.title) || k;
    const range = (m) => m.to - m.from <= 1 ? `message ${m.from + 1}` : `messages ${m.from + 1}–${m.to}`;

    function paint(label) {
        paintTabs();
        if (tab !== 'memory') return;
        const mem = data.memory || {};
        const using = data.mode === 'memory';
        const left = data.left ?? Math.max(0, (data.total || 0) - (mem.upto || 0));
        const status = `<div class="sum-status"><span>${using
                ? (data.automatic ? `Updates every ${data.every} messages, on the background model.` : 'Updates when you press Update now.')
                : 'Not in use for this chat: the manual summary is.'}
              ${left ? ` ${left} message${left === 1 ? '' : 's'} not in memory yet.` : ''}</span>
            ${using ? '' : '<button type="button" class="icon-btn" data-mem="use-memory">Use story memory</button>'}</div>`;
        const milestones = (mem.milestones || []).filter(m => !m.arc);
        const arcs = (mem.arcs || []).map(a => `<div class="t-card mem-arc"><header><span>📖 Earlier (${esc(range(a))})</span>
              <span class="sum-actions"><button type="button" class="icon-btn small" data-mem="del" data-kind="arc" data-id="${a.id}" title="Undo this arc: its milestones come back">↩</button></span></header>
              <textarea class="sum-text" data-kind="arc" data-id="${a.id}" data-f="text">${esc(a.text)}</textarea></div>`).join('');
        const ms = milestones.map(m => `<div class="t-card mem-ms${m.open ? ' open' : ''}${m.stale ? ' stale' : ''}">
              <header><input class="mem-title" data-kind="milestone" data-id="${m.id}" data-f="title" value="${esc(m.title)}">
                <span class="sum-actions">
                  <button type="button" class="icon-btn small" data-mem="redo" data-id="${m.id}" title="Write it again from its messages">↻</button>
                  <button type="button" class="icon-btn small" data-mem="del" data-kind="milestone" data-id="${m.id}" title="Delete this milestone">🗑</button></span></header>
              <div class="sum-meta">${esc([m.where, m.when].filter(Boolean).join(' · '))}${m.who?.length ? ` · ${esc(m.who.join(', '))}` : ''} · ${esc(range(m))}${m.open ? ' · <b>still going</b>' : ''}${m.stale ? ' · <b>a message changed: ↻ to redo</b>' : ''}</div>
              <textarea class="sum-text" data-kind="milestone" data-id="${m.id}" data-f="summary">${esc(m.summary)}</textarea></div>`).join('');
        const people = (mem.people || []).map((p, i) => `<div class="mem-row">
              <input class="mem-name" data-kind="person" data-id="${i}" data-f="name" value="${esc(p.name)}">
              <input class="mem-line" data-kind="person" data-id="${i}" data-f="identity" value="${esc(p.identity)}">
              <button type="button" class="icon-btn small" data-mem="del" data-kind="person" data-id="${i}" title="Remove">✕</button></div>`).join('');
        const rels = (mem.relationships || []).map((r, i) => {
            const stages = data.routes?.[r.route]?.stages || [r.stage];
            return `<div class="t-card mem-rel"><header><span>${esc(r.from)} → ${esc(r.to)}</span>
                <span class="sum-actions"><button type="button" class="icon-btn small" data-mem="del" data-kind="relationship" data-id="${i}" title="Remove">🗑</button></span></header>
              <div class="mem-rel-row">
                <select data-kind="relationship" data-id="${i}" data-f="route">${Object.keys(data.routes || {}).map(k => `<option value="${k}" ${k === r.route ? 'selected' : ''}>${esc(routeName(k))}</option>`).join('')}</select>
                <select data-kind="relationship" data-id="${i}" data-f="stage">${stages.map(s => `<option ${s === r.stage ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select></div>
              <div class="mem-ladder">${stages.map(s => `<span class="${s === r.stage ? 'on' : ''}">${esc(s)}</span>`).join('')}</div>
              <div class="mem-dims">${['trust', 'warmth', 'tension'].map(d => `<label>${d} <input type="range" min="0" max="10" value="${r[d] ?? 5}" data-kind="relationship" data-id="${i}" data-f="${d}"><b>${r[d] ?? 5}</b></label>`).join('')}</div>
              ${(r.history || []).slice(-3).map(h => `<div class="sum-meta">${h.moved ? `⇢ ${esc(h.moved)}: ` : ''}${esc(h.why)}</div>`).join('')}</div>`;
        }).join('');
        const facts = (mem.facts || []).slice().reverse().map(f => `<div class="t-card mem-fact">
              <textarea class="sum-text" rows="2" data-kind="fact" data-id="${f.id}" data-f="text">${esc(f.text)}</textarea>
              <div class="mem-row"><small>Knows:</small><input class="mem-line" data-kind="fact" data-id="${f.id}" data-f="known_by" value="${esc((f.known_by || []).join(', '))}"></div>
              <div class="mem-row"><small>Hidden from:</small><input class="mem-line" data-kind="fact" data-id="${f.id}" data-f="hidden_from" value="${esc((f.hidden_from || []).join(', '))}">
                <button type="button" class="icon-btn small" data-mem="del" data-kind="fact" data-id="${f.id}" title="Remove">✕</button></div>
              ${(f.believed_by || []).map(b => `<div class="sum-meta">${esc(b.who)} believes: ${esc(b.belief)}</div>`).join('')}</div>`).join('');
        const nothing = !milestones.length && !(mem.arcs || []).length;
        box.innerHTML = status + (label ? `<p class="sum-busy">${esc(label)}</p>` : '') +
            (nothing ? `<p class="t-empty">${data.total > 1 ? 'Nothing in memory yet.' : 'Memory starts once the story does.'}</p>
                ${left > 0 ? `<button type="button" class="add-btn" data-mem="build">🧠 Build memory for this chat (${left} message${left === 1 ? '' : 's'}, ~${Math.max(1, Math.ceil(left / 16))} small call${left > 16 ? 's' : ''})</button>` : ''}` : '') +
            (arcs || ms ? `<h4 class="mem-h">Milestones</h4>${arcs}${ms}` : '') +
            (people ? `<h4 class="mem-h">Who and what is who</h4><div class="t-card">${people}</div>` : '') +
            (rels ? `<h4 class="mem-h">Relationships</h4>${rels}` : '') +
            (facts ? `<h4 class="mem-h">Who knows what</h4>${facts}` : '');
        fit();
        box.querySelectorAll('button, select, input, textarea').forEach(b => { b.disabled = busy; });
        foot.innerHTML = `<span>~${data.tokens || 0} tokens in the prompt</span>
            <span class="sum-actions">${left > 0 && !nothing ? `<button type="button" class="icon-btn" data-mem="${left > 16 ? 'build' : 'run'}">Update now</button>` : ''}
            <label class="mem-every">every <input type="number" min="1" max="100" value="${data.every || 4}" data-mem-every> msgs</label></span>`;
    }

    // Text boxes fit their text (only measurable while the panel shows: also when it opens)
    function fit() {
        box.querySelectorAll('.sum-text').forEach(el => {
            el.rows = Math.min(12, Math.max(2, Math.ceil(el.value.length / 46)));
            if (el.offsetParent) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight + 2, 320) + 'px'; }
        });
    }
    new MutationObserver(() => { if (!panel.hidden) fit(); }).observe(panel, { attributes: true, attributeFilter: ['hidden'] });

    async function build() {  // an older chat: chunk after chunk, until it has caught up
        try {
            let d = await post({ action: 'memory_run', catch_up: true }, 'Reading the chat…');
            while (d && d.left > 0) d = await post({ action: 'memory_run', catch_up: true }, `Reading the chat… ${d.left} messages to go`);
        } catch (e) { NADialog.alert(e.message); }
    }

    panel.addEventListener('click', async (e) => {
        const t = e.target.closest('[data-tab]');
        if (t) { tab = t.dataset.tab; paint(); return; }
        const b = e.target.closest('[data-mem]');
        if (!b || busy) return;
        const act = b.dataset.mem;
        try {
            if (act === 'use-memory' || act === 'use-manual') {
                const mode = act === 'use-memory' ? 'memory' : 'manual';
                await post({ action: 'memory_mode', mode });
                tab = mode;
                paint();
                if (mode === 'memory' && (data.left || 0) > 0 && !(data.memory?.milestones || []).length
                    && await NADialog.confirm(`Build story memory from the ${data.left} messages so far? About ${Math.max(1, Math.ceil(data.left / 16))} small call(s) on the background model.`, { ok: 'Build it' })) build();
            } else if (act === 'build') build();
            else if (act === 'run') await post({ action: 'memory_run' }, 'Updating…');
            else if (act === 'redo') await post({ action: 'memory_redo', id: b.dataset.id }, 'Writing it again…');
            else if (act === 'del') {
                if (b.dataset.kind !== 'arc' && !await NADialog.confirm('Remove it from memory?', { ok: 'Remove' })) return;
                await post({ action: 'memory_edit', kind: b.dataset.kind, id: b.dataset.id, delete: true });
            }
        } catch (err) { NADialog.alert(err.message); }
    });
    // Edits save when they leave the field
    panel.addEventListener('change', async (e) => {
        const el = e.target;
        if (el.matches('[data-mem-every]')) {
            try { await post({ action: 'memory_settings', every: Number(el.value) || 4 }); } catch (err) { NADialog.alert(err.message); }
            return;
        }
        if (!el.dataset.kind || !el.dataset.f || busy) return;
        const body = { action: 'memory_edit', kind: el.dataset.kind, id: el.dataset.id, [el.dataset.f]: el.type === 'range' ? Number(el.value) : el.value };
        if (el.dataset.kind === 'milestone') {  // title and text go together
            const card = el.closest('.mem-ms');
            body.title = card.querySelector('.mem-title').value;
            body.summary = card.querySelector('textarea').value;
        }
        try { await post(body); } catch (err) { NADialog.alert(err.message); }
    });
    panel.addEventListener('input', (e) => {
        if (e.target.type === 'range' && e.target.nextElementSibling) e.target.nextElementSibling.textContent = e.target.value;
    });

    paint();
    return {
        afterReply(d) {  // a reply came in: the update, quietly, when it's due
            if (d && d.memory_due) post({ action: 'memory_run', quiet: true }).catch(() => {});
        },
        refresh() { return post({ action: 'memory' }).catch(() => {}); },
        get mode() { return data.mode; },
    };
})();
