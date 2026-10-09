// Bulba Watch on the chat page (mainapp/bulba/watch.py): a badge on the 🥔 button, a small note when a habit
// keeps repeating, and the first-time note that says it's on (with the off switch).
window.Watch = (function () {
    const dataEl = document.getElementById('watch-data');
    const btn = document.getElementById('bulbaBtn');
    if (!dataEl || !btn) return null;
    let state = JSON.parse(dataEl.textContent);
    let hiddenUntilNew = null;  // "Later": the note stays away until a newer one arrives
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    const card = document.createElement('div');
    card.className = 'watch-card';
    card.hidden = true;
    document.body.appendChild(card);
    const badge = document.createElement('span');
    badge.className = 'watch-badge';
    badge.hidden = true;
    btn.appendChild(badge);

    async function post(body) {
        const resp = await fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(() => ({}));
        if (data.watch) { state = data.watch; render(); }
        return data;
    }

    function render() {
        badge.hidden = !state.count;
        badge.textContent = state.count > 9 ? '9+' : String(state.count || '');
        btn.title = state.count ? 'Bulba noticed something' : 'Something off? Ask Bulba';
        if (state.intro) {
            card.hidden = false;
            card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>Bulba Watch is on</b></div>
                <p>Every ${state.every} replies I quietly read the latest ones for habits that keep repeating: the same
                sentence shapes, over-explaining, acting out of character. I also learn what you like from the replies you
                rewrite or edit. I only speak up when something keeps happening: you'll see a number on the 🥔 button.</p>
                <p class="watch-small">Each read costs a little on your key (usually under a cent). You can switch it off any
                time on the Extras page, or just for this chat.</p>
                <div class="watch-actions"><button type="button" data-w="keep">Keep it on</button>
                <button type="button" class="ghost" data-w="off">Turn it off</button>
                <button type="button" class="ghost" data-w="chat-off">Off in this chat</button></div>`;
            return;
        }
        const n = (state.notices || [])[0];
        if (!n || n.id === hiddenUntilNew) { card.hidden = true; return; }
        card.hidden = false;
        const quotes = (n.quotes || []).map(q => `<li>“${esc(q)}”</li>`).join('');
        card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>Bulba noticed something</b>
                <button type="button" class="watch-x" data-w="later" title="Later">✕</button></div>
            <p>${esc(n.text)}</p>
            ${quotes ? `<ul class="watch-quotes">${quotes}</ul>` : ''}
            <div class="watch-actions"><button type="button" data-w="open" data-id="${esc(n.id)}">${n.kind === 'pace' ? 'Get some help' : 'Look at it with Bulba'}</button>
            ${n.kind === 'pace' ? '' : `<button type="button" class="ghost" data-w="mute" data-id="${esc(n.id)}">I don't mind this</button>`}
            <button type="button" class="ghost" data-w="dismiss" data-id="${esc(n.id)}">Not now</button></div>`;
    }

    card.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-w]');
        if (!b) return;
        const what = b.dataset.w;
        if (what === 'keep') return post({ action: 'watch_settings', keep_on: true });
        if (what === 'off') { await post({ action: 'watch_settings', keep_on: false }); return showChatNotice('Bulba Watch is off. Turn it back on on the Extras page.'); }
        if (what === 'chat-off') { await post({ action: 'watch_settings', keep_on: true, chat_off: true }); return showChatNotice('Bulba Watch is off for this chat.'); }
        if (what === 'later') { hiddenUntilNew = (state.notices[0] || {}).id; return render(); }
        if (what === 'mute') { await post({ action: 'watch_note', id: b.dataset.id, status: 'muted' }); return showChatNotice("Got it: I won't bring that one up again."); }
        if (what === 'dismiss') return post({ action: 'watch_note', id: b.dataset.id, status: 'dismissed' });
        if (what === 'open') {
            card.hidden = true;
            if (window.openBulbaNote) window.openBulbaNote(b.dataset.id);  // Bulba marks it opened
        }
    });

    render();
    return {
        // After each reply: show what's new, and let Bulba read in the background when it's time
        afterReply(resp) {
            if (!resp) return;
            if (resp.watch) { state = resp.watch; render(); }
            if (resp.watch_due) post({ action: 'watch' }).catch(() => { /* it tries again after the next reply */ });
        },
        refresh(next) { state = next; render(); },
    };
})();
