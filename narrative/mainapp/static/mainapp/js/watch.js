// Bulba Watch on the chat page (mainapp/bulba/watch.py): a number on the 🥔 button when a habit keeps repeating;
// pressing it shows the note (nothing pops up on its own). The chat tour explains what Watch is.
window.Watch = (function () {
    const dataEl = document.getElementById('watch-data');
    const btn = document.getElementById('bulbaBtn');
    if (!dataEl || !btn) return null;
    let state = JSON.parse(dataEl.textContent);
    let hiddenUntilNew = null;  // "Later": the note stays away until a newer one arrives
    let switched = null;  // the "Director mode?" note just used, for its Undo
    let selectedNotice = null;
    let opened = false;   // notes never pop up on their own: the 🥔 shows a number, a press opens the note
    let introDone = false;
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    // A quote as it looks in the chat: colour and simple formatting rendered, nothing else let through
    const shownQuote = q => window.DOMPurify
        ? DOMPurify.sanitize(String(q ?? ''), { ALLOWED_TAGS: ['font', 'span', 'b', 'i', 'em', 'strong', 'u', 's'],
                                                ALLOWED_ATTR: ['color', 'style'] })
        : esc(q);

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

    // 🧹 on replies shows while Bulba fixes some habit: it says what's on, and polishes that reply on request
    function polishButtons() {
        const fixing = state.fixing || [];
        document.body.classList.toggle('polish-on', fixing.length > 0);
        window.POLISH_TITLE = fixing.length ? `Bulba fixes: ${fixing.join(', ')}. Press to polish this reply now.` : '';
        document.querySelectorAll('.message-btn.polish-btn').forEach(b => { b.title = window.POLISH_TITLE; });
    }

    function render() {
        renderCard();
        if (!card.hidden && selectedNotice && (state.notices || []).length > 1 && !switched) {
            card.insertAdjacentHTML('afterbegin', '<button type="button" class="watch-back" data-w="list">← All findings</button>');
        }
    }

    function renderCard() {
        polishButtons();
        const toggle = document.getElementById('watchChatToggle');
        if (toggle) toggle.checked = !!(state.on && !state.chat_off);
        badge.hidden = !state.count;
        badge.textContent = state.count > 9 ? '9+' : String(state.count || '');
        btn.title = state.count ? 'Bulba noticed something' : 'Something off? Ask Bulba';
        if (state.intro && !introDone) {  // no card: the chat tour says what Watch is; mark it seen, keep it on
            introDone = true;
            post({ action: 'watch_settings', keep_on: true });
        }
        if (switched) {  // just switched to director mode from a note: a moment to undo it
            card.hidden = false;
            card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>Director mode is on</b></div>
                <p>Your messages are directions now, and replies read as chapters. The director's note in the pen menu
                can be sent on its own.</p>
                <div class="watch-actions"><button type="button" data-w="got-it">Got it</button>
                <button type="button" class="ghost" data-w="director-undo">Undo</button></div>`;
            return;
        }
        const notices = state.notices || [];
        if (selectedNotice && !notices.some(n => n.id === selectedNotice)) selectedNotice = null;
        if (opened && notices.length > 1 && !selectedNotice) {
            card.hidden = false;
            card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>${notices.length} findings</b>
                ${bulbaOpen() ? '' : '<button type="button" class="watch-talk" data-w="talk">💬 Talk to Bulba</button>'}
                <button type="button" class="watch-x" data-w="later" aria-label="Close findings">✕</button></div>
                <div class="watch-findings">${notices.map(n => `<button type="button" class="watch-finding" data-w="select" data-id="${esc(n.id)}">
                    <span>${esc(n.title)}</span>${n.count && n.of ? `<small>${esc(n.count)} of ${esc(n.of)} replies</small>` : ''}
                </button>`).join('')}</div>`;
            return;
        }
        const n = notices.find(n => n.id === selectedNotice) || notices[0];
        if (!n || n.id === hiddenUntilNew || !opened) { card.hidden = true; if (!n) opened = false; return; }
        card.hidden = false;
        if (n.kind === 'director') {
            card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>${esc(n.title)}</b>
                    <button type="button" class="watch-x" data-w="later" title="Later">✕</button></div>
                <p>${esc(n.text)}</p>
                <div class="watch-actions"><button type="button" data-w="director" data-id="${esc(n.id)}">Switch to director mode</button>
                <button type="button" class="ghost" data-w="dismiss" data-id="${esc(n.id)}">Not now</button></div>`;
            return;
        }
        if (n.kind === 'polish') {  // a polished reply was undone, edited, regenerated or got a 👎
            const fixes = (n.quotes || []).map(q => `<li>${shownQuote(q)}</li>`).join('');
            card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>${esc(n.title)}</b>
                    <button type="button" class="watch-x" data-w="later" title="Later">✕</button></div>
                <p>${esc(n.text)}</p>
                ${fixes ? `<ul class="watch-quotes">${fixes}</ul>` : ''}
                <div class="watch-actions"><button type="button" data-w="repolish" data-id="${esc(n.id)}" data-index="${esc(n.index)}">Rewrite it again</button>
                <button type="button" class="ghost" data-w="stop-fix" data-id="${esc(n.id)}">Stop fixing this</button>
                <button type="button" class="ghost" data-w="open" data-id="${esc(n.id)}">Tell me what's wrong</button></div>`;
            return;
        }
        const quotes = n.kind === 'taste'  // their taste, in their words: each line can be corrected or dropped first
            ? (n.quotes || []).map(q => `<li class="taste-line"><textarea rows="2" data-taste-old="${esc(q)}" aria-label="What Bulba learned">${esc(q)}</textarea>
                <button type="button" class="watch-x" data-w="taste-drop" title="Leave this one out">✕</button></li>`).join('')
            : (n.quotes || []).map(q => `<li>“${shownQuote(q)}”</li>`).join('');
        card.innerHTML = `<div class="watch-head"><span class="potato">🥔</span><b>${['taste', 'keeper', 'continuity'].includes(n.kind) ? esc(n.title) : 'Bulba noticed something'}</b>
                <button type="button" class="watch-x" data-w="later" title="Later">✕</button></div>
            <p>${esc(n.text)}${n.kind === 'taste' ? ' Change any line, or ✕ to leave it out.' : ''}</p>
            ${quotes ? `<ul class="watch-quotes${n.kind === 'taste' ? ' taste-edit' : ''}">${quotes}</ul>` : ''}
            <div class="watch-actions"><button type="button" data-w="open" data-id="${esc(n.id)}">${{ pace: 'Get some help', taste: 'Put them in my preset', keeper: 'Keep them (with Bulba)' }[n.kind] || 'Look at it with Bulba'}</button>
            ${['pace', 'taste', 'keeper', 'continuity'].includes(n.kind) || n.fixing || n.nofix ? '' : `<button type="button" class="ghost" data-w="fix" data-id="${esc(n.id)}" title="From now on, new replies get a quick polish that rewrites this habit (a small cost each time)">Fix this automatically</button>`}
            ${['pace', 'taste', 'keeper', 'continuity'].includes(n.kind) ? '' : `<button type="button" class="ghost" data-w="mute" data-id="${esc(n.id)}">I don't mind this</button>`}
            <button type="button" class="ghost" data-w="dismiss" data-id="${esc(n.id)}">Not now</button></div>`;
    }

    card.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-w]');
        if (!b) return;
        const what = b.dataset.w;
        if (what === 'select') { selectedNotice = b.dataset.id; return render(); }
        if (what === 'list') { selectedNotice = null; return render(); }
        if (what === 'keep') return post({ action: 'watch_settings', keep_on: true });
        if (what === 'off') { await post({ action: 'watch_settings', keep_on: false }); return showChatNotice('Bulba Watch is off. Turn it back on on the Extras page.'); }
        if (what === 'chat-off') { await post({ action: 'watch_settings', keep_on: true, chat_off: true }); return showChatNotice('Bulba Watch is off for this chat.'); }
        if (what === 'later') { selectedNotice = null; opened = false; return render(); }
        if (what === 'talk') { selectedNotice = null; opened = false; render(); bypass = true; return btn.click(); }
        if (what === 'mute') { await post({ action: 'watch_note', id: b.dataset.id, status: 'muted' }); return showChatNotice("Got it: I won't bring that one up again."); }
        if (what === 'dismiss') return post({ action: 'watch_note', id: b.dataset.id, status: 'dismissed' });
        if (what === 'director' || what === 'director-undo') {
            const undo = what === 'director-undo';
            const d = await post({ action: 'director_mode', id: undo ? switched : b.dataset.id, undo });
            if (!d.success) return showChatNotice(d.error || 'Could not switch.');
            document.body.classList.toggle('layout-book', d.layout === 'book');
            document.querySelectorAll('#layoutChoice [data-layout]').forEach(x => x.classList.toggle('on', x.dataset.layout === d.layout));
            switched = undo ? null : b.dataset.id;
            if (undo) showChatNotice('Back as it was.');
            return render();
        }
        if (what === 'got-it') { switched = null; return render(); }
        if (what === 'repolish') {
            await post({ action: 'watch_note', id: b.dataset.id, status: 'dismissed' });
            if (window.repolishMessage) window.repolishMessage(b.dataset.index);
            return;
        }
        if (what === 'stop-fix') {
            await post({ action: 'watch_note', id: b.dataset.id, status: 'stop_fix' });
            return showChatNotice("Okay: I'll stop fixing that. You can turn it back on from a habit note or the Extras page.");
        }
        if (what === 'fix') {
            await post({ action: 'watch_note', id: b.dataset.id, status: 'fix' });
            showChatNotice('Fixing it in the latest reply now, and in new replies from now on. See or stop it on the Extras page.');
            if (window.polishLatestNow) window.polishLatestNow();
            return;
        }
        if (what === 'taste-drop') {
            const li = b.closest('li');
            const area = li.querySelector('textarea');
            const dropped = li.classList.toggle('dropped');
            area.disabled = dropped;
            b.textContent = dropped ? '↺' : '✕';
            b.title = dropped ? 'Put it back' : 'Leave this one out';
            return;
        }
        if (what === 'open' && card.querySelector('.taste-edit')) {  // save their corrections first
            const lines = [...card.querySelectorAll('.taste-edit textarea')].map(t => ({
                old: t.dataset.tasteOld, new: t.closest('li').classList.contains('dropped') ? '' : t.value }));
            const d = await post({ action: 'watch_taste', id: b.dataset.id, lines });
            if (!d.success) return showChatNotice(d.error || 'Could not save those.');
        }
        if (what === 'open') {
            card.hidden = true;
            if (window.openBulbaNote) window.openBulbaNote(b.dataset.id);  // Bulba marks it opened
        }
    });

    // Pen menu → This chat: on/off for this chat (switching it on here also turns Watch back on overall)
    const chatToggle = document.getElementById('watchChatToggle');
    if (chatToggle) chatToggle.addEventListener('change', async () => {
        const on = chatToggle.checked;
        await post(on ? { action: 'watch_settings', chat_off: false, turn_on: true } : { action: 'watch_settings', chat_off: true });
        showChatNotice(on ? 'Bulba Watch is on in this chat.' : 'Bulba Watch is off in this chat. Other chats keep it.');
    });

    // The 🥔 with a number: the first press shows Bulba's note (with its buttons); without one it opens Bulba
    // One press always does something visible: on a wide screen Bulba opens with the findings beside it; on a
    // phone (the drawer would cover them) the findings show first, with "Talk to Bulba" right at the top
    let bypass = false;
    const wide = () => window.innerWidth >= 900;
    function bulbaOpen() { const d = document.querySelector('.bulba-drawer'); return !!(d && !d.hidden && wide()); }
    btn.addEventListener('click', (e) => {
        if (bypass) { bypass = false; return; }
        if ((state.notices || []).length && card.hidden) {
            if (!wide()) e.stopImmediatePropagation();
            opened = true;
            setTimeout(render, 0);  // after the drawer opened, so the card knows whether to offer "Talk to Bulba"
        }
    }, true);

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
