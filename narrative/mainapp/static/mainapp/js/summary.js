// Summary panel: the summary is kept in pieces, each covering a range of messages.
// Pieces can be edited, re-run or deleted; uncovered messages can be summarized (up to a chosen message).
window.Summary = (() => {
    const panel = document.getElementById('summaryPanel');
    const body = document.getElementById('summaryBody');
    const statusEl = document.getElementById('summaryStatus');
    let data = JSON.parse(document.getElementById('summary-data').textContent || 'null') || { parts: [], total: 0 };
    let busy = false;

    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const range = (from, to) => to - from === 1 ? `Message ${from + 1}` : `Messages ${from + 1}–${to}`;
    const tokens = (text) => Math.round((text || '').length / 4);

    async function post(body) {
        const resp = await fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const d = await resp.json().catch(() => ({}));
        if (!d.success) throw new Error(d.error || 'Something went wrong.');
        set(d);
        return d;
    }

    // Pieces, gaps between them and the uncovered tail, in message order
    function rows() {
        const out = [];
        let at = 0;
        data.parts.forEach((p, i) => {
            if (p.from > at) out.push({ kind: 'gap', from: at, to: p.from });
            out.push({ kind: 'piece', index: i, ...p });
            at = Math.max(at, p.to);
        });
        if (at < data.total) out.push({ kind: 'tail', from: at, to: data.total });
        return out;
    }

    function renderStatus() {
        let text;
        if (!data.auto) text = 'Runs only when you ask. Automatic summaries can be turned on in Connections.';
        else if (data.paused) text = `Automatic summaries are paused for this chat (normally every ${data.interval} messages).`;
        else text = `Runs automatically every ${data.interval} new messages.`;
        statusEl.innerHTML = `
            <span>${esc(text)}${data.model ? ` <span class="sum-model">Model: ${esc(data.model)}</span>` : ''}</span>
            ${data.auto ? `<button type="button" class="icon-btn" data-sum="pause">${data.paused ? '▶ Resume' : '⏸ Pause'}</button>` : ''}`;
    }

    function render() {
        renderStatus();
        if (!data.total) { body.innerHTML = '<p class="t-empty">No messages yet.</p>'; return; }
        body.innerHTML = rows().map(r => {
            if (r.kind === 'piece') return `
                <div class="t-card sum-piece" data-piece="${r.index}">
                    <header><span>${range(r.from, r.to)}</span>
                        <span class="sum-actions">
                            <button type="button" class="icon-btn small" data-sum="rerun" title="Summarize these messages again">↻</button>
                            <button type="button" class="icon-btn small" data-sum="delete" title="Delete this piece">🗑</button>
                        </span></header>
                    <textarea class="sum-text" rows="3">${esc(r.text)}</textarea>
                    <div class="sum-meta">~${tokens(r.text)} tokens <span class="sum-saved"></span></div>
                </div>`;
            if (r.kind === 'gap') return `
                <div class="t-card sum-gap">
                    <header><span>${range(r.from, r.to)}</span></header>
                    <p class="t-empty">Not in the summary (a piece was deleted).</p>
                    <button type="button" class="add-btn" data-sum="run" data-from="${r.from}" data-to="${r.to}">Summarize ${range(r.from, r.to).toLowerCase()}</button>
                </div>`;
            return `
                <div class="t-card sum-gap">
                    <header><span>${range(r.from, r.to)}</span></header>
                    <p class="t-empty">Not summarized yet. Recent messages are sent to the AI as they are, so there's no rush.</p>
                    <div class="sum-run">
                        <label>Summarize up to message
                            <input type="number" class="sum-upto" min="${r.from + 1}" max="${r.to}" value="${r.to}"></label>
                        <button type="button" class="icon-btn" data-sum="run" data-from="${r.from}">Summarize</button>
                    </div>
                </div>`;
        }).join('') + (busy ? '<p class="sum-busy">Summarizing…</p>' : '');
        body.querySelectorAll('.sum-text').forEach(autosize);
        body.querySelectorAll('button').forEach(b => b.disabled = busy);
        document.getElementById('summaryTotal').textContent =
            data.parts.length ? `${data.parts.length} piece${data.parts.length === 1 ? '' : 's'} · ~${tokens(data.summary)} tokens in the prompt` : 'No summary yet.';
    }

    function autosize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight + 2, 320) + 'px'; }

    // The marker in the chat after the last summarized message, and the box in Narrative Controls
    function renderMarker() {
        document.querySelectorAll('.summary-marker').forEach(m => m.remove());
        const upto = data.summary_upto || 0;
        const msgs = document.querySelectorAll('.message:not(#typingMessage)');
        if (!upto || upto > msgs.length) return;
        const marker = document.createElement('button');
        marker.type = 'button';
        marker.className = 'summary-marker';
        marker.title = 'Open the summary';
        marker.textContent = upto === msgs.length ? '📚 Summarized up to here' : `📚 Summarized up to here · ${msgs.length - upto} newer message${msgs.length - upto === 1 ? '' : 's'} below`;
        marker.addEventListener('click', () => toggle(true));
        msgs[upto - 1].after(marker);
    }

    function set(d) {
        if (!d) return;
        data = { ...data, ...d };
        const box = document.getElementById('summaryDisplay');
        if (box) box.innerText = data.summary || 'No summary yet.';
        const cov = document.getElementById('summaryCoverage');
        if (cov) cov.textContent = data.summary_upto ? `Covers messages 1–${data.summary_upto}` : '';
        renderMarker();
        if (!panel.hidden) render();
    }

    async function run(body, { quiet = false } = {}) {
        if (busy) return;
        busy = true;
        if (!panel.hidden) render();
        try {
            await post({ action: 'summarize', ...body });
        } catch (err) {
            if (quiet) console.warn('Automatic summary failed:', err.message); else alert(err.message);
        } finally {
            busy = false;
            if (!panel.hidden) render();
        }
    }

    body.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-sum]');
        if (!btn || busy) return;
        const card = btn.closest('[data-piece]');
        const piece = card ? Number(card.dataset.piece) : null;
        const act = btn.dataset.sum;
        try {
            if (act === 'run') {
                const from = Number(btn.dataset.from);
                const input = btn.closest('.t-card').querySelector('.sum-upto');
                const to = input ? Number(input.value) : Number(btn.dataset.to);
                await run({ from, to });
            } else if (act === 'rerun') {
                busy = true; render();
                try { await post({ action: 'summary_rerun', piece }); } finally { busy = false; render(); }
            } else if (act === 'delete') {
                if (confirm('Delete this summary piece? Its messages will be left out of the summary until you summarize them again.')) {
                    await post({ action: 'summary_delete', piece });
                }
            }
        } catch (err) { alert(err.message); }
    });

    body.addEventListener('input', (e) => { if (e.target.classList.contains('sum-text')) autosize(e.target); });
    body.addEventListener('change', async (e) => {
        if (!e.target.classList.contains('sum-text')) return;
        const card = e.target.closest('[data-piece]');
        const piece = Number(card.dataset.piece);
        try {
            await post({ action: 'summary_edit', piece, text: e.target.value });
            const saved = panel.querySelector(`[data-piece="${piece}"] .sum-saved`);
            if (saved) { saved.textContent = '· saved'; setTimeout(() => saved.textContent = '', 1500); }
        } catch (err) { alert(err.message); render(); }
    });

    statusEl.addEventListener('click', async (e) => {
        if (!e.target.closest('[data-sum="pause"]')) return;
        try { await post({ action: 'summary_pause', paused: !data.paused }); } catch (err) { alert(err.message); }
    });

    document.getElementById('summaryRedo').addEventListener('click', () => {
        if (busy) return;
        if (confirm(`Summarize all ${data.total} messages again as one piece? This replaces every piece and costs tokens (more for long chats).`)) {
            run({ mode: 'regen' });
        }
    });

    function toggle(force) {
        const show = force ?? panel.hidden;
        panel.hidden = !show;
        if (show) {
            document.getElementById('chatsPanel').hidden = true;
            render();
        }
    }

    // Messages were added or removed on the page: keep the counts and marker right
    function messagesChanged(total) {
        data.total = total ?? document.querySelectorAll('.message:not(#typingMessage)').length;
        renderMarker();
        if (!panel.hidden) render();
    }

    renderMarker();
    return { toggle, run, set, messagesChanged, get paused() { return data.paused; } };
})();
