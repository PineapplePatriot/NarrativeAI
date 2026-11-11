// Chats drawer: several conversations per character. The open chat is the ?chat=<id> in the address.
window.Chats = (() => {
    const panel = document.getElementById('chatsPanel');
    const list = document.getElementById('chatsList');
    let chats = JSON.parse(document.getElementById('chats-data').textContent || '[]');

    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    function urlFor(id) {
        const url = new URL(window.location.href);
        url.searchParams.set('chat', id);
        return url.toString();
    }

    async function post(body) {
        const resp = await fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.success) throw new Error(data.error || 'Something went wrong.');
        if (data.go_to) { window.location.href = urlFor(data.go_to); return data; }
        chats = data.chats || chats;
        render();
        return data;
    }

    function render() {
        list.innerHTML = chats.map(c => `
            <div class="t-card chat-card${c.current ? ' current' : ''}" data-id="${c.id}">
                <header>
                    <a class="chat-name" href="${esc(urlFor(c.id))}">${esc(c.title)}</a>
                    <span>
                        <button class="icon-btn small" data-chat-act="rename" title="Rename">✎</button>
                        <button class="icon-btn small" data-chat-act="delete" title="Delete">🗑</button>
                    </span>
                </header>
                ${c.parent ? `<div class="chat-meta">⑂ from “${esc(c.parent)}” at message ${esc(c.branch_point)}</div>` : ''}
                <div class="chat-preview">${esc(c.preview) || '<em>No messages yet</em>'}</div>
                <div class="chat-meta">${c.count} message${c.count === 1 ? '' : 's'} · started ${esc(c.created)} · last ${esc(c.updated)}${c.current ? ' · <strong>open</strong>' : ''}</div>
            </div>`).join('');
    }

    list.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-chat-act]');
        if (!btn) return;
        const id = Number(btn.closest('.chat-card').dataset.id);
        const chat = chats.find(c => c.id === id);
        try {
            if (btn.dataset.chatAct === 'rename') {
                const title = await NADialog.prompt('Chat name:', chat.title, { ok: 'Rename' });
                if (title && title.trim()) {
                    await post({ action: 'rename_chat', id, title });
                    if (chat.current) document.getElementById('chatTitle').textContent = title.trim();
                }
            } else if (await NADialog.confirm(`Delete “${chat.title}” and all its messages? This can't be undone.`,
                                              { ok: 'Delete', danger: true })) {
                await post({ action: 'delete_chat', id });
            }
        } catch (err) { alert(err.message); }
    });

    function toggle(force) {
        const show = force ?? panel.hidden;
        panel.hidden = !show;
        document.getElementById('chatsBtn')?.classList.toggle('active', show);
        if (show) {
            render();
            post({ action: 'list_chats' }).catch(() => {});  // counts may have changed since the page loaded
        }
    }

    async function create() {
        try { await post({ action: 'new_chat' }); } catch (err) { alert(err.message); }
    }

    // A chat file becomes a new chat: this app's own (or a rescued one), or SillyTavern's .jsonl
    function importFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json,.jsonl,application/json';
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            try {
                const text = await file.text();
                let chat;
                try { chat = JSON.parse(text); }
                catch (e) {  // .jsonl: one JSON object per line
                    chat = text.split('\n').filter(l => l.trim()).map(l => JSON.parse(l));
                }
                const title = file.name.replace(/\.(jsonl?|txt)$/i, '').slice(0, 200);
                await post({ action: 'import_chat', chat, title });
            } catch (err) { alert('Could not import that file: ' + err.message); }
        };
        input.click();
    }

    // Keep the address pointing at the open chat, so reloading or bookmarking opens the same one
    const open = chats.find(c => c.current);
    if (open && new URL(window.location.href).searchParams.get('chat') !== String(open.id)) {
        history.replaceState(null, '', urlFor(open.id));
    }

    return { toggle, create, render, importFile };
})();
