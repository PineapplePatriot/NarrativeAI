let currentAudio = null;

// A new mood picture fades in over the old one instead of jumping (instant with reduced motion, or the first time)
function swapSprite(img, url) {
    if (!url || img.getAttribute('src') === url) return;
    if (!img.getAttribute('src') || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { img.src = url; return; }
    const ready = new Image();
    ready.onload = () => {
        img.parentNode.querySelectorAll('.sprite-incoming').forEach(old => old.remove());  // a newer one wins
        const layer = img.cloneNode();
        const look = getComputedStyle(img);
        layer.classList.add('sprite-incoming');
        layer.style.objectFit = look.objectFit;
        layer.style.objectPosition = look.objectPosition;
        layer.src = url;
        img.parentNode.appendChild(layer);
        requestAnimationFrame(() => requestAnimationFrame(() => layer.classList.add('in')));
        setTimeout(() => { img.src = url; layer.remove(); }, 560);
    };
    ready.src = url;
}

function updateCharacterImages(photoUrl, photoSecond, charCount) {
    const c1 = document.getElementById('char1Container');
    const c2 = document.getElementById('char2Container');

    // charCount = 2;
    const count = Number(charCount) || 1;

    // Helper to update src
    const setImg = (container, url) => {
        let img = container.querySelector('img.character-sprite:not(.sprite-incoming)');
        if (!img) {
            img = document.createElement('img');
            img.className = 'character-sprite';
            container.appendChild(img);
        }
        swapSprite(img, url);
    };

    setImg(c1, photoUrl);
    setImg(c2, photoSecond);

    // Layout Logic
    if (count === 1) {
        c1.style.display = 'flex';
        c2.style.display = 'none';
    } else if (count === 2) {
        c1.style.display = 'flex';
        c2.style.display = 'flex';
    } else if (count === 3) {
        c1.style.display = 'none';
        c2.style.display = 'flex';
    }
}


document.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;

    const action = btn.dataset.action;
    const index = btn.dataset.index !== undefined ? Number(btn.dataset.index) : null;

    switch (action) {
        case "edit":
            if (index !== null) editMessage(index);
            break;
        case "delete":
            if (index !== null) deleteMessage(index);
            break;
        case "copy": {  // the words as shown (the translation when they read one), without the buttons
            const el = btn.closest('.message'), textDiv = el && el.querySelector('.message-text');
            if (!textDiv) break;
            const text = textDiv.innerText.trim();
            const done = () => { btn.textContent = '✓'; setTimeout(() => { btn.textContent = '📋'; }, 1200); };
            if (navigator.clipboard) navigator.clipboard.writeText(text).then(done).catch(() => showChatNotice('Could not copy it.'));
            else { const t = document.createElement('textarea'); t.value = text; document.body.append(t); t.select();
                   try { document.execCommand('copy'); done(); } catch (e) { showChatNotice('Could not copy it.'); } t.remove(); }
            break;
        }
        case "original": {  // 🌐 the English a translated reply was written in, and back
            const el = btn.closest('.message'), textDiv = el && el.querySelector('.message-text');
            if (!textDiv || !textDiv.dataset.original) break;
            const showing = btn.classList.toggle('on');
            textDiv.innerHTML = renderChatMessage(decodeURIComponent(showing ? textDiv.dataset.original : textDiv.dataset.raw), textDiv);
            btn.title = showing ? `Back to ${window.READING_LANGUAGE_NAME}` : 'Show the English it was written in';
            break;
        }
        case "translate":
            translateMessage(btn.closest('.message'));
            break;
        case "play-sound": {
            const i = btn.closest('.message') ? btn.closest('.message').dataset.index : index;
            voiceReply(btn, Number(i), event.shiftKey);
            break;
        }
        case "save-edit":
            if (index !== null) saveMessage(index);
            break;
        case "cancel-edit":
            if (index !== null) cancelEdit(index);
            break;
        case "branch":
            if (index !== null) openBranchModal(index);
            break;
        case "polish": {  // 🧹: Bulba's polish on this reply, now (shown while it fixes some habit)
            const el = btn.closest('.message');
            runPolish(el, true, Number(el && el.dataset.index !== undefined ? el.dataset.index : index));
            break;
        }
        case "condense": {
            const el = btn.closest('.message');
            condenseMessage(el, Number(el ? el.dataset.index : index));
            break;
        }
        default:
            break;
    }
});


function playCharacterAudio(audioUrl, btn) {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        document.querySelectorAll('.play-sound.playing').forEach(b => b.classList.remove('playing'));
    }
    currentAudio = new Audio(audioUrl);
    if (btn) {
        btn.classList.add('playing');
        currentAudio.addEventListener('ended', () => btn.classList.remove('playing'));
    }
    currentAudio.play().catch(err => console.error("Audio playback failed:", err));
}

// 🔊 on a reply: the first press has ElevenLabs read it (narrator and every speaker in their own voice) and keeps
// the recording with that version of the reply; later presses play or stop it. Shift-click makes it again.
async function voiceReply(btn, index, redo) {
    if (btn.classList.contains('playing') && currentAudio) {
        currentAudio.pause(); btn.classList.remove('playing'); return;
    }
    if (btn.classList.contains('busy')) return;
    btn.classList.add('busy'); btn.title = 'Reading it aloud… (can take a little while)';
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'voice', index, redo: !!redo }),
        });
        const d = await resp.json();
        if (!d.success) throw new Error(d.error || 'Could not read it aloud.');
        if (d.spending) updateSpending(d.spending);
        const cast = Object.entries(d.cast || {}).map(([who, v]) => `${who}: ${v}`).join(', ');
        btn.title = 'Play / stop' + (cast ? ` (${cast})` : '') + '. Shift-click to make it again.';
        playCharacterAudio(d.url, btn);
    } catch (err) {
        btn.title = 'Read aloud (ElevenLabs)';
        showChatNotice(err.message);
    } finally {
        btn.classList.remove('busy');
    }
}

function pauseCharacterAudio() {
    if (currentAudio) {
        currentAudio.pause();
    }
}
// --- Markdown + safe HTML helpers -------------------------------------------

function decodeEntities(s) {
    const t = document.createElement('textarea');
    t.innerHTML = s;
    return t.value;
}

function hydrateExistingMessages() {
    document.querySelectorAll('.message-text').forEach(el => {
        const rawAttr = el.getAttribute('data-raw');
        if (!rawAttr) return;
        const raw = decodeURIComponent(rawAttr);
        el.innerHTML = renderChatMessage(raw, el);
    });
}

// Display rules can depend on how far back a message is; re-render once a new message arrives
function refreshForDepth() {
    if (TextRules.usesDepth()) hydrateExistingMessages();
}

// Where a message sits: its role and depth (0 = the newest), for display text rules
function messagePlace(where) {
    if (!where) return { role: 'assistant', depth: 0 };
    if (!(where instanceof Element)) return where;
    const msg = where.closest('.message');
    if (!msg) return { role: 'assistant', depth: 0 };
    const all = [...document.querySelectorAll('.message:not(#typingMessage)')];
    const i = all.indexOf(msg);
    return { role: msg.classList.contains('user') ? 'user' : 'assistant', depth: i < 0 ? 0 : all.length - 1 - i };
}

// Quoted speech gets a highlight; HTML tags (from text rules) and code are left alone
function wrapQuoted(text) {
    const parts = text.split(/(<[^>]*>|`+[^`]*`+)/g);
    return parts.map((part, i) => {
        if (i % 2 === 1) return part;

        return part.replace(/"([^"\n]+)"/g, (_m, inner) =>
            `<span class="quoted">"${inner}"</span>`
        );
    }).join('');
}

// Inline styles from text rules may colour and lay out a message, never cover the page or load things
DOMPurify.addHook('uponSanitizeAttribute', (_node, data) => {
    if (data.attrName !== 'style') return;
    data.attrValue = data.attrValue
        .split(';')
        .filter(d => !/^\s*(position|z-index|behavior|-moz-binding)\s*:/i.test(d) && !/url\s*\(|expression\s*\(|@import/i.test(d))
        .join(';');
});


marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false,
    html: true
});


// where: an element inside the message (or {role, depth}); used by display text rules
// In-story objects the AI designs (```html blocks, mainapp/html_objects.py): each one runs in a sealed frame.
// No allow-same-origin, so its scripts can't reach this page, the account or cookies; the content policy keeps
// it off the network (Google Fonts aside); no popups, forms or navigating the page.
const HTML_FENCE = /```[ \t]*html[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```/gi;
const HTML_OPEN = /```[ \t]*html[ \t]*\r?\n[\s\S]*$/i;  // still being written
const objectHeights = new Map();  // keeps the page from jumping when a message is redrawn
function objectKey(code) { let h = 0; for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) | 0; return 'o' + (h >>> 0).toString(36); }
function objectFrame(code) {
    const key = objectKey(code);
    const doc = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src data:; script-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark">
<style>html,body{margin:0;padding:0;background:transparent;color:#e5e7eb;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
body{padding:2px}*{box-sizing:border-box;max-width:100%}</style></head><body>${code}
<script>(function(){var last=0;function tell(){var h=Math.ceil(document.documentElement.scrollHeight);if(h!==last){last=h;parent.postMessage({naObject:${JSON.stringify(key)},h:h},'*');}}
addEventListener('load',tell);try{new ResizeObserver(tell).observe(document.body);}catch(e){}setTimeout(tell,50);setTimeout(tell,600);})();<\/script></body></html>`;
    const frame = document.createElement('iframe');
    frame.className = 'html-object';
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.setAttribute('referrerpolicy', 'no-referrer');
    frame.setAttribute('loading', 'lazy');
    frame.setAttribute('title', 'In-story object');
    frame.dataset.object = key;
    frame.style.height = (objectHeights.get(key) || 160) + 'px';
    frame.setAttribute('srcdoc', doc);
    return frame;
}
window.addEventListener('message', (e) => {
    if (!e.data || typeof e.data.naObject !== 'string' || typeof e.data.h !== 'number') return;
    const h = Math.max(20, Math.min(4000, e.data.h));
    document.querySelectorAll('iframe.html-object').forEach(f => {
        if (f.contentWindow === e.source) { f.style.height = h + 'px'; objectHeights.set(f.dataset.object, h); }
    });
});

function renderChatMessage(rawText, where) {
    const place = messagePlace(where);
    // Designed objects come out first (text rules and markdown don't touch them), back in as frames at the end
    const objects = [];
    let source = String(rawText ?? '').replace(HTML_FENCE, (m, code) => { objects.push(code); return `\n\n<div class="object-slot n${objects.length - 1}"></div>\n\n`; });
    if (isGenerating) source = source.replace(HTML_OPEN, () => '\n\n<div class="object-slot drawing"></div>\n\n');  // a cut-off one stays code
    let shown = TextRules.any() ? TextRules.apply(source, place.role, place.depth) : source;
    // A character's direct thought ("Inner thoughts, shown apart" module): its own style
    shown = shown.replace(/<thought>([\s\S]*?)<\/thought>/gi, (m, t) => `<span class="thought">${t.trim()}</span>`);
    // Story extras' markers ([[extra 2]]) become slots; placeExtras() puts the app's drawing there
    shown = shown.replace(/\[\[extra (\d+)\]\]/g, '\n\n<div class="extra-slot n$1"></div>\n\n');
    const pre2 = wrapQuoted(shown);
    const html = marked.parse(pre2);

    const clean = DOMPurify.sanitize(html, {
        ALLOWED_TAGS: [
            'em', 'strong', 'code', 'pre', 'span', 'a', 'p', 'br', 'ul', 'ol', 'li', 'blockquote',
            'table', 'thead', 'tbody', 'tr', 'th', 'td',
            // what presets' display rules build: panels, fold-outs, small type
            'div', 'details', 'summary', 'b', 'i', 'u', 's', 'small', 'sub', 'sup', 'hr', 'mark',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'font', 'center'
        ],
        ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'class', 'style', 'open', 'color', 'align']
    });


    const tmp = document.createElement('div');
    tmp.innerHTML = clean;
    tmp.querySelectorAll('a').forEach(a => {
        a.setAttribute('rel', 'nofollow noopener noreferrer');
        a.setAttribute('target', '_blank');
    });
    tmp.querySelectorAll('.object-slot').forEach(slot => {
        const n = (slot.className.match(/\bn(\d+)\b/) || [])[1];
        if (n !== undefined && objects[n] !== undefined) slot.replaceWith(objectFrame(objects[n]));
        else if (slot.classList.contains('drawing')) slot.textContent = '🎨 Drawing…';
    });
    return tmp.innerHTML;
}
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const messagesContainer = document.getElementById('messagesContainer');
const typingMessage = document.getElementById('typingMessage');
const stopContainer = document.getElementById('stopContainer');
const stopBtn = document.getElementById('stopBtn');
const deleteModal = document.getElementById('deleteModal');

let isGenerating = false;
// A reply that's written but still being polished or translated: nothing new starts until it's finished
let finishing = 0;
function isBusy(say = false) {
    if (finishing && say) showChatNotice('One moment: Bulba is still finishing the last reply.');
    return isGenerating || finishing > 0;
}
let placeholderBefore = null;
function lockWhileFinishing() {
    finishing++;
    sendBtn.disabled = true;
    messagesContainer.classList.add('finishing');
    if (placeholderBefore === null) {
        placeholderBefore = messageInput.placeholder;
        messageInput.placeholder = 'Bulba is finishing the reply…';
    }
}
function unlockFinished() {
    finishing = Math.max(0, finishing - 1);
    if (finishing) return;
    messagesContainer.classList.remove('finishing');
    if (placeholderBefore !== null) { messageInput.placeholder = placeholderBefore; placeholderBefore = null; }
    if (!isGenerating) sendBtn.disabled = false;
}
let currentRequest = null;
let deleteMessageIndex = -1;
// Bulba's helpers in the chat (Write for me, ideas, wording a note, condensing) are waits too
const SLOW_ACTIONS = new Set(['expand', 'ideas', 'note_ideas', 'word_note', 'condense', 'polish', 'translate']);
let slowJobs = 0;
const pageFetch = window.fetch.bind(window);
window.fetch = function (url, opts) {
    let slow = false;
    try { slow = !!opts && typeof opts.body === 'string' && SLOW_ACTIONS.has(JSON.parse(opts.body).action); } catch (e) {}
    if (!slow) return pageFetch(url, opts);
    slowJobs++;
    return pageFetch(url, opts).finally(() => { slowJobs = Math.max(0, slowJobs - 1); });
};
if (window.NATomato) NATomato.watch(() => isBusy() || slowJobs > 0, 'chat');  // 🍅 a slow reply or a slow Bulba helper

messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
});

// note: a director's note, a message of its own (outside the story; edited and deleted like any message)
function addMessage(sender, text, specificAvatarUrl = null, note = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}${note ? ' note' : ''}`;

    const existingMessages = document.querySelectorAll('.message:not(#typingMessage)');
    const messageIndex = existingMessages.length;
    messageDiv.setAttribute('data-index', messageIndex);

    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const rendered = renderChatMessage(text, { role: sender === 'user' ? 'user' : 'assistant', depth: 0 });

    // --- NEW: Avatar Logic ---
    let avatarHtml = '';

    if (sender === 'user') {
        if (window.USER_AVATAR) {
            avatarHtml = `<img src="${window.USER_AVATAR}" class="message-avatar" style="object-fit:cover;">`;
        } else {
            avatarHtml = '<div class="message-avatar">You</div>';
        }
    } else {
        if (specificAvatarUrl) {
            avatarHtml = `<img src="${specificAvatarUrl}" class="message-avatar" style="object-fit:cover;">`;
        } else {
            avatarHtml = `<div class="message-avatar">${window.CHAR_INITIAL || '•'}</div>`;
        }
    }
    // -------------------------

    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            <div class="message-actions">
                <button class="message-btn edit" onclick="editMessage(${messageIndex})">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
                </button>
                <button class="message-btn condense" type="button" data-action="condense" data-index="${messageIndex}" title="Condense for the AI: it gets a short version, you still see all of it">🗜</button>
                ${sender === 'user' ? '' : `<button class="message-btn polish-btn" type="button" data-action="polish" data-index="${messageIndex}" title="${escHtml(window.POLISH_TITLE || 'Polish this reply')}">🧹</button>`}
                <button class="message-btn branch" type="button" data-action="branch" data-index="${messageIndex}" title="Branch: a new chat from this message"><svg class="icon" viewBox="0 0 24 24"><path d="M6 3a3 3 0 0 0-1 5.83v6.34A3 3 0 1 0 7 15.17V13.5c0-.83.67-1.5 1.5-1.5h5A3.5 3.5 0 0 0 17 8.5v-.67a3 3 0 1 0-2 0v.67c0 .83-.67 1.5-1.5 1.5h-5c-.53 0-1.03.1-1.5.28V8.83A3 3 0 0 0 6 3z"/></svg></button>
                <button class="message-btn copy" type="button" data-action="copy" data-index="${messageIndex}" title="Copy">📋</button>
                <button class="message-btn delete" onclick="deleteMessage(${messageIndex})">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>
                </button>
                ${sender !== 'user' && window.VOICE_ON ? `<button class="message-btn play-sound" type="button" data-action="play-sound" data-index="${messageIndex}" title="Read aloud (ElevenLabs)"><svg class="icon" viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.06c1.48-.74 2.5-2.26 2.5-4.03z"/></svg></button>` : ''}
            </div>
            <div class="message-text markdown-output" data-raw="${encodeURIComponent(text)}">${rendered}</div>
            <textarea class="edit-textarea" style="display: none;"></textarea>
            <div class="edit-actions">
                <button class="edit-btn save-btn" onclick="saveMessage(${messageIndex})">Save</button>
                <button class="edit-btn cancel-btn" onclick="cancelEdit(${messageIndex})">Cancel</button>
            </div>
            <div class="message-time">${time}</div>
        </div>
    `;

    const editTextarea = messageDiv.querySelector('.edit-textarea');
    editTextarea.value = text;

    messagesContainer.insertBefore(messageDiv, typingMessage);
    refreshForDepth();
    scrollToBottom();
}

// Scroll to bottom
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// --- Replies: one request helper for normal and streamed replies ---
// Resolves with the server's reply payload ({reply, photo_url, ...}), or {error}, or {stopped}.
// While streaming, the reply bubble is created at the first words and filled in live.
async function requestReply(body) {
    const controller = new AbortController();
    currentRequest = controller;
    const stream = !!window.STREAM_REPLIES;
    let bubble = null, text = '', thoughts = '', frame = null;

    const paint = () => {
        frame = null;
        bubble.innerHTML = renderChatMessage(text, bubble);
        bubble.setAttribute('data-raw', encodeURIComponent(text));
        if (window.READING_LANGUAGE) setStage(bubble.closest('.message'), '✍️ Writing…');  // shown once translated
        scrollToBottom();
    };

    const typingLabel = typingMessage.querySelector('.typing-indicator span');
    if (typingLabel) typingLabel.textContent = `${window.CHARACTER_NAME || 'The AI'} is typing`;
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ ...body, stream }),
            signal: controller.signal,
        });
        if (!(resp.headers.get('content-type') || '').includes('ndjson')) return await resp.json();

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let nl;
            while ((nl = buffer.indexOf('\n')) >= 0) {
                const line = buffer.slice(0, nl).trim();
                buffer = buffer.slice(nl + 1);
                if (!line) continue;
                const event = JSON.parse(line);
                const ensureBubble = () => {
                    if (bubble) return;
                    typingMessage.style.display = 'none';
                    addMessage('assistant', '', window.INIT_PHOTO_URL || null);
                    const all = messagesContainer.querySelectorAll('.message.assistant:not(#typingMessage) .message-text');
                    bubble = all[all.length - 1];
                    bubble.closest('.message').classList.add('streaming');
                };
                if (event.type === 'thinking') {
                    // Thinking models (MiMo, Claude...) reason before writing: show it live, folded once the reply starts
                    ensureBubble();
                    thoughts += event.text || '';
                    setThoughts(bubble.closest('.message'), thoughts, !text);
                    if (!text) bubble.innerHTML = `<span class="thinking-note">${escHtml(window.CHARACTER_NAME || 'The AI')} is thinking…</span>`;
                    scrollToBottom();
                } else if (event.type === 'delta') {
                    ensureBubble();
                    if (!text && thoughts) setThoughts(bubble.closest('.message'), thoughts, false);
                    text += event.text;
                    if (!frame) frame = requestAnimationFrame(paint);
                } else if (event.type === 'game') {
                    // A roll or an inventory change, as it happens
                    ensureBubble();
                    const msgEl = bubble.closest('.message');
                    const shown = [...msgEl.querySelectorAll('.game-lines > div')].map(d => d.textContent);
                    setGame(msgEl, shown.concat(event.line));
                    scrollToBottom();
                } else if (event.type === 'extra') {
                    ensureBubble();
                    setExtras(bubble.closest('.message'), [event.html], true);
                    scrollToBottom();
                } else if (event.type === 'done') {
                    return { ...event, bubble };
                } else if (event.type === 'error') {
                    if (bubble && !event.kept) { bubble.closest('.message').remove(); bubble = null; }
                    else if (bubble) { paint(); bubble.closest('.message').classList.remove('streaming'); }
                    return { error: event.error, bubble };  // a kept bubble was saved by the server
                }
            }
        }
        return { error: 'The reply stream ended unexpectedly.' };
    } catch (err) {
        if (err.name === 'AbortError') {
            if (bubble) { paint(); bubble.closest('.message').classList.remove('streaming'); }
            return { stopped: true, bubble };
        }
        throw err;
    } finally {
        currentRequest = null;
    }
}

// The month's spending in the tools menu, refreshed after every reply
function updateSpending(s) {
    if (!s) return;
    const line = document.getElementById('spendingLine'), fill = document.getElementById('spendingFill');
    if (line) line.textContent = `$${s.spent.toFixed(2)} of $${s.limit.toFixed(2)} used (chat, Bulba and background jobs)`;
    if (fill) fill.style.width = `${Math.min(100, s.spent / s.limit * 100)}%`;
}

const escHtml = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));

// What a thinking model thought before replying: a folded "Thoughts" box above the reply text
function setThoughts(messageEl, text, open = false) {
    if (!messageEl) return;
    let box = messageEl.querySelector('details.thoughts');
    if (!text) { if (box) box.remove(); return; }
    if (!box) {
        box = document.createElement('details');
        box.className = 'thoughts';
        box.innerHTML = '<summary>Thoughts</summary><div class="thoughts-text"></div>';
        const textEl = messageEl.querySelector('.message-text');
        textEl.parentNode.insertBefore(box, textEl);
    }
    box.querySelector('.thoughts-text').textContent = text;
    box.open = open;
}

// Dice rolls and inventory changes made while writing a reply (see mainapp/game.py), under its text
function setGame(messageEl, lines) {
    if (!messageEl) return;
    let box = messageEl.querySelector('.game-lines');
    if (!lines || !lines.length) { if (box) box.remove(); return; }
    if (!box) {
        box = document.createElement('div');
        box.className = 'game-lines';
        const textEl = messageEl.querySelector('.message-text');
        textEl.parentNode.insertBefore(box, textEl.nextSibling);
    }
    box.innerHTML = lines.map(l => `<div>${escHtml(l)}</div>`).join('');
}

// Letters, phone screens and milestones drawn by the app (server-rendered HTML, see mainapp/extras.py)
function setExtras(messageEl, htmlList, append = false) {
    if (!messageEl) return;
    let box = messageEl.querySelector('.story-extras');
    if (!append && (!htmlList || !htmlList.length)) { if (box) box.remove(); return; }
    if (!box) {
        box = document.createElement('div');
        box.className = 'story-extras';
        const textEl = messageEl.querySelector('.message-text');
        textEl.parentNode.insertBefore(box, textEl.nextSibling);
    }
    if (append) box.insertAdjacentHTML('beforeend', htmlList.join(''));
    else box.innerHTML = htmlList.join('');
}

// Put a finished reply on screen: fill the streamed bubble, or add a new message
function placeReply(data, avatarUrl) {
    updateSpending(data.spending);
    if (!data.bubble) {
        addMessage('assistant', data.reply, avatarUrl);
        const all = messagesContainer.querySelectorAll('.message.assistant:not(#typingMessage)');
        setThoughts(all[all.length - 1], data.reasoning || '');
        setGame(all[all.length - 1], data.game);
        setExtras(all[all.length - 1], data.extras_html);
        if (data.game_trackers && window.Trackers) Trackers.setState(data.game_trackers);
        return;
    }
    refreshForDepth();
    data.bubble.innerHTML = renderChatMessage(data.reply, data.bubble);
    data.bubble.setAttribute('data-raw', encodeURIComponent(data.reply));
    const message = data.bubble.closest('.message');
    message.classList.remove('streaming');
    setGame(message, data.game);
    setExtras(message, data.extras_html);
    if (data.game_trackers && window.Trackers) Trackers.setState(data.game_trackers);
    message.querySelector('.edit-textarea').value = data.reply;
    if (avatarUrl) {
        const avatar = message.querySelector('.message-avatar');
        if (avatar && avatar.tagName === 'IMG') avatar.src = avatarUrl;
        else if (avatar) avatar.outerHTML = `<img src="${avatarUrl}" class="message-avatar" style="object-fit:cover;">`;
    }
}

// Send message to server
// `noteOnly`: send the director's note on its own (the story goes on with no message from them)
function sendMessage(noteOnly = false) {
    if (messageInput.classList.contains('writing')) { showChatNotice('One moment: your message is still being written.'); return; }
    noteOnly = noteOnly === true;  // never an event object from a click handler
    const message = noteOnly ? '' : messageInput.value.trim();
    const guideInput = document.getElementById('guidanceInput');
    const guidance = guideInput ? guideInput.value.trim() : '';
    if ((!message && !(noteOnly && guidance)) || isBusy(true)) return;
    if (guideInput) guideInput.value = '';

    clearSwipeNav();
    if (message) {
        addMessage('user', message, window.USER_AVATAR);
        messageInput.value = '';
        messageInput.style.height = 'auto';
    }
    if (guidance) addMessage('user', guidance, window.USER_AVATAR, true);  // saved as a message of its own

    isGenerating = true;
    sendBtn.disabled = true;
    stopContainer.style.display = 'block';
    typingMessage.style.display = 'flex';
    scrollToBottom();

    requestReply({ message: message, guidance: guidance })
        .then(data => {
            if (data.refused) return handleRefusal(data);
            if (data.empty) { if (data.bubble) data.bubble.closest('.message')?.remove(); showChatError(data.error); return; }
            if (data.error || data.stopped) {
                if (data.bubble) setSwipes({ count: 1, current: 0 });  // the partial reply was kept
                if (data.bubble && window.READING_LANGUAGE) translateMessage(data.bubble.closest('.message'));
                if (data.error) showChatError(data.error);
                return;
            }
            let avatarToUse = data.photo_url;
            if (Number(data.char_count) === 3 && data.photo_second) {
                avatarToUse = data.photo_second;
            }
            placeReply(data, avatarToUse);
            setDirected(lastAssistant(), data.directed);
            setSwipes(data.swipes);
            updateCharacterImages(data.photo_url, data.photo_second, data.char_count);
            renderLore(data.lore);
            if (data.summary_due) generateSummary('append', true);
            if (window.Trackers) { Trackers.setStory(data.story); Trackers.afterReply(data); }
            if (window.Watch) Watch.afterReply(data);
            afterReplyText(lastAssistant(), data.polish_due);
            if (data.music_due) followSceneMusic();
            if (window.NAFeedback) NAFeedback.afterMessage();  // the tester feedback form, once a day at most

            if (data.photo_url) {  // the sprite itself fades over in updateCharacterImages
                const avatars = document.querySelectorAll('.message.assistant .message-avatar img');
                avatars.forEach(img => img.src = data.photo_url);
            }

            console.log("Emotion:", data.emotion);
        })
        .catch(error => {
            console.error('Error:', error);
            showChatError('Could not reach the app server. Check that it is still running.');
        })
        .finally(() => {
            isGenerating = false;
            sendBtn.disabled = isBusy();  // still finishing (polish, translation): stays off until it's done
            stopContainer.style.display = 'none';
            typingMessage.style.display = 'none';
            scrollToBottom();
            updateMessageIndices();
        });
}

// Update message indices after adding/removing messages
function updateMessageIndices() {
    const messages = document.querySelectorAll('.message:not(#typingMessage)');
    messages.forEach((message, index) => {
        message.setAttribute('data-index', index);

        // Update onclick handlers
        const editBtn = message.querySelector('.message-btn.edit');
        const deleteBtn = message.querySelector('.message-btn.delete');
        const saveBtn = message.querySelector('.save-btn');
        const cancelBtn = message.querySelector('.cancel-btn');

        if (editBtn) editBtn.setAttribute('onclick', `editMessage(${index})`);
        if (deleteBtn) deleteBtn.setAttribute('onclick', `deleteMessage(${index})`);
        if (saveBtn) saveBtn.setAttribute('onclick', `saveMessage(${index})`);
        if (cancelBtn) cancelBtn.setAttribute('onclick', `cancelEdit(${index})`);
        message.querySelectorAll('[data-index]').forEach(el => el.dataset.index = index);
    });
    if (window.Summary) Summary.messagesChanged(messages.length);
}

// Edit message functionality
function editMessage(index) {
    if (isBusy(true)) return;
    const message = document.querySelector(`[data-index="${index}"]`);
    if (!message) return;

    const messageText = message.querySelector('.message-text');
    const editTextarea = message.querySelector('.edit-textarea');

    const raw = decodeURIComponent(messageText.getAttribute('data-raw') || '');
    editTextarea.value = raw;

    message.classList.add('edit-mode');
    editTextarea.style.display = 'block';
    editTextarea.focus();

    // Auto-resize textarea
    editTextarea.style.height = 'auto';
    editTextarea.style.height = editTextarea.scrollHeight + 'px';
}

// Save edited message
function saveMessage(index) {
    const message = document.querySelector(`[data-index="${index}"]`);
    if (!message) return;

    const messageText = message.querySelector('.message-text');
    const editTextarea = message.querySelector('.edit-textarea');
    let newText = editTextarea.value.trim();

    if (!newText) {
        showChatError('A message can\'t be empty.');
        return;
    }

    // Send edit request to server (a translated reply: Bulba updates the English the story continues from)
    const translated = !!(window.READING_LANGUAGE && messageText.dataset.original);
    const saveBtn = message.querySelector('.save-btn');
    if (translated) {
        setStage(message, '🌐 Bulba is updating the English version…', true);
        if (saveBtn) saveBtn.disabled = true;
    }
    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            action: 'edit',
            index: index,
            text: newText
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (typeof data.text === 'string') newText = data.text;  // a text rule may have changed it
                const rendered = renderChatMessage(newText, messageText);
                messageText.innerHTML = rendered;
                messageText.setAttribute('data-raw', encodeURIComponent(newText));

                // Keep textarea synced with the raw text
                editTextarea.value = newText;
                if (data.original) messageText.dataset.original = encodeURIComponent(data.original);
                cancelEdit(index);
                if (data.watch && window.Watch) Watch.refresh(data.watch);  // edited a polished reply: Bulba asks why
            } else {
                if (data.resync) { showChatNotice(data.error); setTimeout(() => window.location.reload(), 900); }
                else showChatError(data.keep_draft ? data.error + ' Your edit is still here: press Save to try again.'
                                                   : 'Could not save it: ' + (data.error || 'unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showChatError('Could not save it: the app server didn\'t answer. Your edit is still here.');
        })
        .finally(() => {
            if (translated) { setStage(message, null); if (saveBtn) saveBtn.disabled = false; }
        });
}

// Cancel edit
function cancelEdit(index) {
    const message = document.querySelector(`[data-index="${index}"]`);
    if (!message) return;

    const editTextarea = message.querySelector('.edit-textarea');
    const messageText = message.querySelector('.message-text');

    const raw = messageText.getAttribute('data-raw')
        ? decodeURIComponent(messageText.getAttribute('data-raw'))
        : (messageText.textContent || '');

    // Reset textarea value
    editTextarea.value = raw;

    message.classList.remove('edit-mode');
    editTextarea.style.display = 'none';
}

// Delete message
function deleteMessage(index) {
    if (isBusy(true)) return;
    deleteMessageIndex = index;
    deleteModal.classList.add('show');
}

// Close delete modal
function closeDeleteModal() {
    deleteModal.classList.remove('show');
    deleteMessageIndex = -1;
}

// Confirm delete
function confirmDelete() {
    if (deleteMessageIndex === -1) return;

    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            action: 'delete',
            index: deleteMessageIndex
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove all messages from the specified index onwards
                const messages = document.querySelectorAll('.message:not(#typingMessage)');
                for (let i = deleteMessageIndex; i < messages.length; i++) {
                    messages[i].remove();
                }
                updateMessageIndices();
                setSwipes(data.swipes);
                // Summary pieces covering deleted messages are gone; trackers rewound to before them
                if (window.Summary) Summary.set(data.summary_data);
                if (window.Trackers && Trackers.setState) Trackers.setState(data.trackers);
                if (window.Trackers && Trackers.setStory) Trackers.setStory(data.story);
            } else if (data.resync) {
                showChatNotice(data.error);  // the page was out of step with the saved chat
                setTimeout(() => window.location.reload(), 900);
            } else {
                showChatError('Could not delete it: ' + (data.error || 'unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showChatError('Could not delete it: the app server didn\'t answer.');
        })
        .finally(() => {
            closeDeleteModal();
        });
}

// Stop generation
function stopGeneration() {
    if (currentRequest) {
        currentRequest.abort();  // the server keeps whatever text already arrived
        currentRequest = null;
    }
    isGenerating = false;
    sendBtn.disabled = isBusy();
    stopContainer.style.display = 'none';
    typingMessage.style.display = 'none';
}

// Event listeners
sendBtn.addEventListener('click', () => sendMessage());
stopBtn.addEventListener('click', stopGeneration);

// Enter is a new line (paragraphs, and phones have no Shift); the send button sends, or Ctrl/⌘+Enter on a computer
messageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.isComposing) {
        e.preventDefault();
        sendMessage();
    }
});

// Close modal when clicking outside
deleteModal.addEventListener('click', function (e) {
    if (e.target === deleteModal) {
        closeDeleteModal();
    }
});

// Resizable panel functionality
const chatPanel = document.querySelector('.chat-panel');
const resizeHandle = document.querySelector('.resize-handle');
let isResizing = false;

resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const containerWidth = document.querySelector('.chat-container').offsetWidth;
    const newWidth = (e.clientX / containerWidth) * 100;
    if (newWidth >= 25 && newWidth <= 80) {
        chatPanel.style.width = newWidth + '%';
    }
});

document.addEventListener('mouseup', () => {
    isResizing = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
});

document.addEventListener('DOMContentLoaded', () => {
    hydrateExistingMessages();
    scrollToBottom();
    fixHistoryAvatars();
    updateMessageIndices();
    if (window.SAVED_MUSIC && window.SAVED_MUSIC.url) loadMusic(window.SAVED_MUSIC.url, window.SAVED_MUSIC.name, true);

    if (window.SAVED_BG) {
        const bgEl = document.querySelector('.character-background');
        if (bgEl) {
            bgEl.style.backgroundImage = `url('${window.SAVED_BG}')`;
            bgEl.style.backgroundSize = 'cover';
            bgEl.style.backgroundPosition = 'center';
            bgEl.style.backgroundRepeat = 'no-repeat';
        }
    }
});

// --- NEW FEATURES LOGIC ---

// The pinned note: kept in mind for every reply in this chat (saved as you leave the box)
(function () {
    const box = document.getElementById('pinnedNote');
    if (!box) return;
    box.value = window.PINNED_NOTE || '';
    box.addEventListener('change', () => {
        fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'save_guides', note: box.value }),
        }).then(r => r.json()).then(d => { if (d.success) showChatNotice('Pinned note saved.'); });
    });
})();

// The pen menu's two parts: the director's note for the next reply (send it, have Bulba word it, or have Bulba
// come up with one), and redoing the last reply (shortcuts, wording, rewrite)
(function () {
    const input = document.getElementById('guidanceInput');
    const redo = document.getElementById('redoInput');
    if (!input || !redo) return;
    const post = async (body) => {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify(body),
        });
        const d = await resp.json();
        updateSpending(d.spending);
        if (!d.success) throw new Error(d.error || 'Bulba could not do it.');
        return d;
    };
    const busy = async (btn, label, work) => {
        const was = btn.textContent;
        btn.disabled = true;
        btn.textContent = label;
        try { await work(); } catch (err) { showChatNotice(err.message); }
        finally { btn.disabled = false; btn.textContent = was; }
    };
    const wordIt = (btn, box, rewrite) => btn.onclick = () => {
        const wish = box.value.trim();
        if (!wish) { box.focus(); box.placeholder = 'Write roughly what you want first, then press this.'; return; }
        busy(btn, '🥔 Wording…', async () => { box.value = (await post({ action: 'word_note', text: wish, rewrite })).note; });
    };
    wordIt(document.getElementById('wordNoteBtn'), input, false);
    wordIt(document.getElementById('wordRedoBtn'), redo, true);

    document.getElementById('sendNoteBtn').onclick = () => {
        if (!input.value.trim() && !messageInput.value.trim()) { input.focus(); return; }
        toggleTools();
        sendMessage(!messageInput.value.trim());  // with their message if they wrote one, else on its own
    };

    const ideasBox = document.getElementById('noteIdeas');
    const ideasBtn = document.getElementById('noteIdeasBtn');
    ideasBtn.onclick = () => busy(ideasBtn, '✨ Thinking…', async () => {
        const d = await post({ action: 'note_ideas' });
        ideasBox.innerHTML = [['logical', '🧭 What would happen'], ['creative', '✨ A twist']]
            .filter(([k]) => d[k]).map(([k, label]) => `<button type="button" class="note-idea" data-note="${encodeURIComponent(d[k])}">
                <b>${label}</b><span></span></button>`).join('');
        ideasBox.querySelectorAll('.note-idea').forEach(b => { b.querySelector('span').textContent = decodeURIComponent(b.dataset.note); });
        ideasBox.hidden = false;
    });
    ideasBox.addEventListener('click', e => {
        const b = e.target.closest('.note-idea');
        if (!b) return;
        input.value = decodeURIComponent(b.dataset.note);  // theirs to change before sending
        ideasBox.hidden = true;
        input.focus();
    });

    document.getElementById('rewriteWithNote').onclick = () => {
        const note = redo.value.trim();
        redo.value = '';
        toggleTools();
        regenerateReply(note);
    };
    document.getElementById('askBulbaFromNote').onclick = () => {
        toggleTools();
        if (window.askBulba) window.askBulba((redo.value.trim() || input.value.trim()));
    };
})();

// What steered a reply (a director's note), shown small above it
function setDirected(messageEl, note) {
    if (!messageEl) return;
    let line = messageEl.querySelector('.directed-line');
    if (!note) { if (line) line.remove(); return; }
    if (!line) {
        line = document.createElement('div');
        line.className = 'directed-line';
        const textEl = messageEl.querySelector('.message-text');
        textEl.parentNode.insertBefore(line, textEl);
    }
    line.textContent = `🎬 ${note}`;
}

// Toggle Tools
// Shows a failed generation in the chat; the user's message is kept, so Regenerate retries it
function showChatError(text) {
    const div = document.createElement('div');
    div.className = 'chat-error';
    div.textContent = `⚠️ ${text} — press Regenerate to try again.`;
    messagesContainer.insertBefore(div, typingMessage);
    setTimeout(() => div.remove(), 15000);
    scrollToBottom();
}

// Shows which worldbook entries were added to the last prompt, and why
function renderLore(lore) {
    const box = document.getElementById('loreDisplay');
    if (!box || !lore) return;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    const label = { included: '✅', over_budget: '⚠️ over budget', disabled: '⛔ disabled' };
    const rows = (lore.report || []).map(r =>
        `<div class="lore-row"><b>${label[r.status] || ''} ${esc(r.label)}</b><br><small>${esc(r.reason)}</small></div>`).join('');
    const notes = (lore.notes || []).map(n => `<div class="lore-row"><small>⚠️ ${esc(n)}</small></div>`).join('');
    box.innerHTML = notes + (rows || `No entries from “${esc(lore.book)}” fired for this reply.`);
}

function toggleTools() { document.getElementById('toolsMenu').classList.toggle('show'); document.getElementById('toolsBtn').classList.toggle('active'); }
function setGuidance(text) { document.getElementById('guidanceInput').value = text; }
function setRedo(text) { document.getElementById('redoInput').value = text; }


// Actions
// Update this function signature to accept 'mode'
// auto = started after a reply because the summary is set to run every N messages
function generateSummary(mode, auto = false) {
    if (!window.Summary) return;
    if (auto && Summary.paused) return;
    Summary.run(mode === 'regen' ? { mode: 'regen' } : {}, { quiet: auto });
}

// Write my message (impersonate): the AI writes your next message, or fleshes out your draft, following the
// preset, lore and summary. Nothing is sent: it lands in the box for you to edit.
async function expandInput() {
    if (isBusy(true)) return;
    const draft = messageInput.value;
    const btn = document.getElementById('expandBtn');
    if (btn) btn.disabled = true;
    // While it writes, the box is locked: a placeholder says so (nothing to erase), on one line on phones
    const placeholder = messageInput.placeholder;
    const narrow = window.matchMedia('(max-width: 560px)').matches;
    messageInput.value = '';
    messageInput.readOnly = true;
    messageInput.classList.add('writing');
    messageInput.placeholder = narrow ? '✍️ Writing…' : (draft ? '✍️ Writing it out…' : '✍️ Writing your message…');
    messageInput.style.height = 'auto';
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'expand', text: draft }),
        });
        const d = await resp.json();
        messageInput.value = d.success ? d.text : draft;
        if (!d.success) showChatNotice(d.error || 'Could not write it.');
        else if (d.polished) showChatNotice(`🧹 Bulba fixed ${d.polished} thing${d.polished === 1 ? '' : 's'} in it, as you asked.`);
        updateSpending(d.spending);
    } catch (err) { messageInput.value = draft; showChatNotice(err.message); }
    finally {
        if (btn) btn.disabled = false;
        messageInput.readOnly = false;
        messageInput.classList.remove('writing');
        messageInput.placeholder = placeholder;
        messageInput.style.height = 'auto';
        messageInput.style.height = messageInput.scrollHeight + 'px';
        messageInput.focus();
    }
}

function spellcheckInput() {
    const txt = messageInput.value; if (!txt) return;
    fetch(window.location.href, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ action: 'spellcheck', text: txt }) })
        .then(r => r.json()).then(d => { if (d.success) messageInput.value = d.text; });
}

function continueGeneration() {
    if (isBusy(true)) return;
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    // Ensure the last message is from the assistant
    if (msgs.length === 0 || !msgs[msgs.length - 1].classList.contains('assistant')) {
        return showChatError("Only the AI's last reply can be continued.");
    }

    isGenerating = true;
    typingMessage.style.display = 'flex';
    scrollToBottom();

    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'continue' })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // 1. Target the existing message element
                const lastMsgElement = msgs[msgs.length - 1];
                const messageTextDiv = lastMsgElement.querySelector('.message-text');
                const hiddenTextarea = lastMsgElement.querySelector('.edit-textarea');

                // 2. Render the new full text with Markdown/DOMPurify
                const renderedHtml = renderChatMessage(data.reply, messageTextDiv);

                // 3. Update the DOM
                messageTextDiv.innerHTML = renderedHtml;
                messageTextDiv.setAttribute('data-raw', encodeURIComponent(data.reply));
                hiddenTextarea.value = data.reply;
                setPolish(lastMsgElement, null);
                if (data.translated) setOriginal(lastMsgElement, data.original);  // only the new part was translated
                else afterReplyText(lastMsgElement, data.polish_due);

                scrollToBottom();
            } else {
                showChatError(data.error || "Couldn't continue the reply.");
            }
        }).finally(() => {
            isGenerating = false;
            typingMessage.style.display = 'none';
        });
}

// Media
const mediaModal = document.getElementById('mediaModal');
const bgMusic = document.getElementById('bgMusicPlayer');
// The music: a ▶/❚❚ button in the header (shown when a track is set) follows what the audio actually does;
// the picker holds the track name, the volume and "None"
let musicHeld = false;  // they paused or stopped it themselves: don't start it again on their next click
function loadMusic(url, name, onLoad = false) {
    bgMusic.src = url;
    bgMusic.volume = Number(document.getElementById('musicVolume')?.value || 0.3);
    document.getElementById('nowPlayingText').innerText = name || 'Music';
    document.getElementById('musicNow').hidden = false;
    const btn = document.getElementById('playPauseBtn');
    btn.hidden = false;
    musicHeld = false;
    bgMusic.play().catch(() => {
        // Browsers only allow sound after a click or key press: start on the first one
        if (!onLoad) return;
        const start = () => { if (!musicHeld && bgMusic.paused && bgMusic.src) bgMusic.play().catch(() => {}); };
        document.addEventListener('pointerdown', start, { once: true, capture: true });
        document.addEventListener('keydown', start, { once: true, capture: true });
    });
}
function syncMusicButton() {
    const btn = document.getElementById('playPauseBtn');
    if (!btn) return;
    btn.textContent = bgMusic.paused ? '▶' : '❚❚';
    btn.title = `${bgMusic.paused ? 'Play' : 'Pause'}: ${document.getElementById('nowPlayingText').innerText}`;
    btn.classList.toggle('playing', !bgMusic.paused);
}
bgMusic.addEventListener('play', syncMusicButton);
bgMusic.addEventListener('pause', syncMusicButton);
let currentMediaType = 'bg';

function openMediaModal(type) {
    currentMediaType = type;
    document.getElementById('mediaModalTitle').innerText = type === 'bg' ? "Select Background" : "Select Music";
    document.getElementById('musicFollowRow').hidden = type !== 'music';
    mediaModal.dataset.type = type;  // the background picker hides the music controls (CSS)
    document.getElementById('musicFollow').checked = !!window.MUSIC_FOLLOW;
    mediaModal.classList.add('show');
    fetch('/main/api/media-resources/').then(r => r.json()).then(d => {
        const grid = document.getElementById('mediaGrid'); grid.innerHTML = '';
        const items = type === 'bg' ? d.backgrounds : d.music;
        items.forEach(i => {
            const div = document.createElement('div'); div.className = 'media-item';
            div.innerHTML = type === 'bg' ? `<img src="${i.url}"><div class="label">${i.name}</div>` : `<div style="height:80px;background:#333;color:#fff;display:flex;align-items:center;justify-content:center;">🎵</div><div class="label">${i.name}</div>`;
            div.onclick = () => selectMedia(i.url, i.name);
            grid.appendChild(div);
        });
    });
}
function closeMediaModal() { mediaModal.classList.remove('show'); }
function selectMedia(url, name) {
    if (currentMediaType === 'bg') {
        // 1. Target the specific background element used in your CSS
        const bgEl = document.querySelector('.character-background');

        if (bgEl) {
            // 2. Set the image and ensure it covers the area
            bgEl.style.backgroundImage = `url('${url}')`;
            bgEl.style.backgroundSize = 'cover';
            bgEl.style.backgroundPosition = 'center';
            bgEl.style.backgroundRepeat = 'no-repeat';

        }
        saveMediaState('bg', url, name);
    } else {
        loadMusic(url, name);

        saveMediaState('music', url, name);
    }
    closeMediaModal();
}
function resetMedia() {
    if (currentMediaType === 'bg') {
        const bgEl = document.querySelector('.character-background');
        if (bgEl) {

            bgEl.style.backgroundImage = '';
            bgEl.style.backgroundSize = '';
            bgEl.style.backgroundPosition = '';
        }
        saveMediaState('bg', '', '');
    } else {
        stopMusic();
        saveMediaState('music', '', '');
    }
    closeMediaModal();
}
function uploadMedia() {
    const f = document.getElementById('fileUpload').files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f); fd.append('type', currentMediaType);
    fetch('/main/api/media-resources/', { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') }, body: fd })
        .then(r => r.json())
        .then(d => { if (d.success) selectMedia(d.url, d.name); else showChatNotice(d.error || 'Upload failed.'); })
        .catch(() => showChatNotice('Upload failed: the file may be too big.'))
        .finally(() => { document.getElementById('fileUpload').value = ''; });
}
function togglePlay() {
    if (bgMusic.paused) { musicHeld = false; bgMusic.play().catch(() => {}); }
    else { musicHeld = true; bgMusic.pause(); }
}
function stopMusic() {
    musicHeld = true;
    bgMusic.pause();
    bgMusic.removeAttribute('src');
    document.getElementById('playPauseBtn').hidden = true;
    document.getElementById('musicNow').hidden = true;
}
function setVolume(v) { bgMusic.volume = v; }


// A new version of the AI's last reply. The old one stays as a swipe (and comes back if this fails).
function regenerateReply(guidance = '', model = '') {
    if (isBusy(true)) return;
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    const last = msgs[msgs.length - 1];
    const old = last && last.classList.contains('assistant') ? last : null;
    const before = window.LAST_SWIPES;
    if (old) old.style.display = 'none';
    clearSwipeNav();
    isGenerating = true; sendBtn.disabled = true; typingMessage.style.display = 'flex'; scrollToBottom();
    stopContainer.style.display = 'block';
    const restore = () => { if (old) { old.style.display = ''; setSwipes(before); } };
    requestReply(model ? { action: 'regenerate', guidance: guidance, model } : { action: 'regenerate', guidance: guidance })
        .then(d => {
            if (d.refused) { restore(); return handleRefusal(d); }  // the server kept the old reply
            if (d.empty) { if (d.bubble) d.bubble.closest('.message')?.remove(); restore(); showChatError(d.error); return; }
            if (d.error || d.stopped) {
                // The server keeps any text that arrived as a new version; with none, the old reply stays
                if (!d.bubble) restore();
                else {
                    if (old) old.remove();
                    setSwipes(before ? { count: before.count + 1, current: before.count } : { count: 1, current: 0 });
                    if (window.READING_LANGUAGE) translateMessage(d.bubble.closest('.message'));
                }
                if (d.error) showChatError(d.error);
                return;
            }
            if (old) old.remove();
            placeReply(d, d.photo_url); setDirected(lastAssistant(), d.directed); setSwipes(d.swipes);
            updateCharacterImages(d.photo_url, d.photo_second, d.char_count); renderLore(d.lore);
            if (d.summary_due) generateSummary('append', true);
            if (window.Trackers) { Trackers.setStory(d.story); Trackers.afterReply(d); }
            if (window.Watch) Watch.afterReply(d);
            afterReplyText(lastAssistant(), d.polish_due);
            if (d.music_due) followSceneMusic();
        })
        .catch(err => { console.error(err); restore(); showChatError('Could not reach the app server.'); })
        .finally(() => { isGenerating = false; sendBtn.disabled = isBusy(); stopContainer.style.display = 'none'; typingMessage.style.display = 'none'; updateMessageIndices(); });
}

// --- Swipes: ‹ 2/3 › under the AI's last reply ---
function clearSwipeNav() {
    document.querySelectorAll('.swipe-nav').forEach(n => n.remove());
}

function setSwipes(info) {
    window.LAST_SWIPES = info || null;
    clearSwipeNav();
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    const last = msgs[msgs.length - 1];
    if (!info || !last || !last.classList.contains('assistant')) return;
    const nav = document.createElement('div');
    nav.className = 'swipe-nav';
    nav.innerHTML = `
        <button type="button" class="swipe-btn" data-swipe="-1" title="Previous version" ${info.current === 0 ? 'disabled' : ''}>‹</button>
        <span class="swipe-count">${info.count > 1 ? `${info.current + 1}/${info.count}` : ''}</span>
        <button type="button" class="swipe-btn" data-swipe="1" title="${info.current === info.count - 1 ? 'Write another version' : 'Next version'}">›</button>`;
    last.querySelector('.message-content').appendChild(nav);
}

function swipe(step) {
    const info = window.LAST_SWIPES;
    if (!info || isBusy(true)) return;
    const to = info.current + step;
    if (to < 0) return;
    if (to >= info.count) { regenerateReply(); return; }  // past the newest: write a new one
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'swipe', to }),
    })
        .then(r => r.json())
        .then(d => {
            if (!d.success) { showChatError(d.error || 'Could not switch versions.'); return; }
            const msgs = document.querySelectorAll('.message:not(#typingMessage)');
            const last = msgs[msgs.length - 1];
            const textDiv = last.querySelector('.message-text');
            textDiv.innerHTML = renderChatMessage(d.reply, textDiv);
            setOriginal(last, d.original || '');
            if (d.untranslated && window.READING_LANGUAGE) translateMessage(last);
            setThoughts(last, d.reasoning || '');
            setGame(last, d.game);
            setExtras(last, d.extras_html);
            if (d.game_trackers && window.Trackers) Trackers.setState(d.game_trackers);
            textDiv.setAttribute('data-raw', encodeURIComponent(d.reply));
            last.querySelector('.edit-textarea').value = d.reply;
            last.dataset.emotion = d.emotion;
            last.dataset.charCount = d.char_count;
            const avatar = last.querySelector('img.message-avatar');
            const avatarUrl = Number(d.char_count) === 3 && d.photo_second ? d.photo_second : d.photo_url;
            if (avatar && avatarUrl) avatar.src = avatarUrl;
            updateCharacterImages(d.photo_url, d.photo_second, d.char_count);
            setSwipes(d.swipes);
            setPolish(last, d.polish);
            setDirected(last, d.directed);
        })
        .catch(() => showChatError('Could not reach the app server.'));
}

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.swipe-btn');
    if (btn && !btn.disabled) swipe(Number(btn.dataset.swipe));
});

// ← / → swipe too, while the message box is empty (as in SillyTavern)
document.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    const el = document.activeElement;
    const typing = el && (el.isContentEditable || ['INPUT', 'SELECT'].includes(el.tagName)
        || (el.tagName === 'TEXTAREA' && (el !== messageInput || messageInput.value)));
    if (typing || document.querySelector('.modal-overlay.show')) return;
    e.preventDefault();
    swipe(e.key === 'ArrowRight' ? 1 : -1);
});

// Add listeners for new Modals
if (mediaModal) mediaModal.addEventListener('click', (e) => { if (e.target === mediaModal) closeMediaModal(); });


function saveMediaState(type, url, name) {
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'save_media', type: type, url: url, name: name })
    });
    // "Also use it for every chat with them": the character's theme
    const asTheme = document.getElementById('mediaAsTheme');
    if (asTheme && asTheme.checked) {
        fetch(window.location.href, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'save_theme', type: type, url: url, name: name })
        }).then(() => showChatNotice('Saved as their theme.'));
        asTheme.checked = false;
    }
}

function initCharactersFromLastAssistantMessage() {
    const msgs = document.querySelectorAll('.message.assistant');
    if (!msgs.length) return;

    const last = msgs[msgs.length - 1];

    const charCount = Number(last.dataset.charCount);
    if (Number.isNaN(charCount)) return;

    updateCharacterImages(
        window.INIT_PHOTO_URL,
        window.INIT_PHOTO_SECOND,
        charCount
    );
}

function fixHistoryAvatars() {
    const messages = document.querySelectorAll('.message.assistant');

    messages.forEach(msg => {
        const charCount = Number(msg.dataset.charCount);
        const avatarImg = msg.querySelector('.message-avatar');

        // If it's an image tag and we have a second photo URL
        if (avatarImg && avatarImg.tagName === 'IMG' && window.INIT_PHOTO_SECOND) {
            // Logic: If char_count is 3, it refers to Character 2
            if (charCount === 3) {
                // Update the src to the second character's photo
                avatarImg.src = window.INIT_PHOTO_SECOND;
            }
        }
    });
}
setSwipes(JSON.parse(document.getElementById('swipes-data')?.textContent || 'null'));
scrollToBottom();

// --- Branches: a new chat with everything up to a message ---
const branchModal = document.getElementById('branchModal');
let branchIndex = null;

function openBranchModal(index) {
    branchIndex = index;
    document.getElementById('branchError').textContent = '';
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'branch_info', index }),
    })
        .then(r => r.json())
        .then(d => {
            if (!d.success) { showChatError(d.error || 'Could not branch here.'); return; }
            document.getElementById('branchCount').textContent = d.count;
            branchModal.querySelectorAll('.branch-n').forEach(el => el.textContent = d.count);
            document.getElementById('branchModel').textContent = d.summary_model || 'your summary model';
            const text = document.getElementById('branchSummaryText');
            text.value = d.summary || '';
            text.placeholder = d.summary ? '' : 'No summary covers these messages yet. You can write one here.';
            const pick = branchModal.querySelector(`input[name=branchSummary][value=${d.summary ? 'transfer' : 'clear'}]`);
            pick.checked = true;
            document.getElementById('branchTrackersNote').textContent = d.has_trackers ? ''
                : 'No tracker values were saved at this message yet, so the branch starts with empty trackers either way.';
            branchModal.classList.add('show');
        })
        .catch(() => showChatError('Could not reach the app server.'));
}

function closeBranchModal() { branchModal.classList.remove('show'); branchIndex = null; }

function confirmBranch() {
    if (branchIndex === null) return;
    const mode = branchModal.querySelector('input[name=branchSummary]:checked').value;
    const btn = document.getElementById('branchConfirm');
    btn.disabled = true;
    btn.textContent = mode === 'rerun' ? 'Summarizing…' : 'Creating…';
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({
            action: 'branch', index: branchIndex, summary_mode: mode,
            summary_text: document.getElementById('branchSummaryText').value,
            trackers_mode: branchModal.querySelector('input[name=branchTrackers]:checked').value,
        }),
    })
        .then(r => r.json())
        .then(d => {
            if (!d.success) { document.getElementById('branchError').textContent = d.error || 'Could not create the branch.'; return; }
            const url = new URL(window.location.href);
            url.searchParams.set('chat', d.go_to);
            window.location.href = url.toString();
        })
        .catch(() => { document.getElementById('branchError').textContent = 'Could not reach the app server.'; })
        .finally(() => { btn.disabled = false; btn.textContent = 'Create branch'; });
}

// Typing in the summary box means "transfer this"
document.getElementById('branchSummaryText').addEventListener('input', () => {
    branchModal.querySelector('input[name=branchSummary][value=transfer]').checked = true;
});
branchModal.addEventListener('click', (e) => { if (e.target === branchModal) closeBranchModal(); });

// --- Dialogue colour (tools menu): saved on the account ---
(function () {
    const box = document.getElementById('dialogueColors');
    if (!box) return;
    const apply = color => {
        document.body.dataset.dialogue = color === 'preset' ? 'preset' : 'color';
        if (color !== 'preset') document.body.style.setProperty('--dialogue-color', color);
        box.querySelectorAll('[data-color]').forEach(b => b.classList.toggle('on', b.dataset.color === color));
    };
    const save = async color => {
        apply(color);
        try {
            await fetch(window.location.href, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ action: 'appearance', dialogue_color: color }),
            });
        } catch (e) { showChatError('Could not save the colour.'); }
    };
    box.addEventListener('click', e => { const b = e.target.closest('[data-color]'); if (b) save(b.dataset.color); });
    const custom = document.getElementById('dialogueCustom');
    custom.addEventListener('input', () => apply(custom.value));
    custom.addEventListener('change', () => save(custom.value));
})();

// --- Who the user is in this chat (tools menu); empty = their usual persona ---
(function () {
    const form = document.getElementById('personaForm');
    if (!form) return;
    const line = document.getElementById('personaLine');
    document.getElementById('personaEdit').onclick = () => { form.hidden = !form.hidden; };
    const save = async (name, description, action = 'chat_persona') => {
        try {
            const resp = await fetch(window.location.href, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ action, name, description }),
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.error || 'Not saved.');
            const b = document.createElement('b'); b.textContent = data.name;
            line.firstChild && line.replaceChildren(b, document.createTextNode(data.persona.name ? ' (this chat only) ' : ' (your usual persona) '),
                                                  document.getElementById('personaEdit'));
            form.hidden = true;
        } catch (e) { showChatError(e.message || 'Could not save who you are in this chat.'); }
    };
    form.addEventListener('submit', e => {
        e.preventDefault();
        save(document.getElementById('personaName').value.trim(), document.getElementById('personaDesc').value.trim());
    });
    document.getElementById('personaMakeUsual').onclick = async () => {
        const name = document.getElementById('personaName').value.trim();
        if (!name) { showChatError('Give the persona a name first.'); return; }
        if (!await NADialog.confirm(`Make “${name}” your usual persona? It replaces the one on your profile, and every chat without its own persona will use it.`,
                                    { ok: 'Make it usual' })) return;
        save(name, document.getElementById('personaDesc').value.trim(), 'persona_to_account');
    };
    document.getElementById('personaReset').onclick = () => {
        document.getElementById('personaName').value = ''; document.getElementById('personaDesc').value = '';
        save('', '');
    };
})();

// --- Bulba in the chat: a side panel (full screen on phones) with Bulba looking at this chat ---
(function () {
    const drawer = document.getElementById('bulbaDrawer');
    const btn = document.getElementById('bulbaBtn');
    if (!drawer || !btn) return;
    const frame = document.getElementById('bulbaFrame');
    const toggle = (open) => {
        drawer.hidden = !open;
        if (open && !frame.src) frame.src = drawer.dataset.src;  // loaded the first time it opens
        btn.classList.toggle('active', open);
    };
    btn.onclick = () => toggle(drawer.hidden);
    // On a chat page the top bar's Bulba means "Bulba about this chat", not the setup conversation
    document.querySelector('.na-links a[href$="/bulba/"]')?.addEventListener('click', (e) => {
        e.preventDefault();
        toggle(true);
    });
    // Coming back from the setup page's list (?bulba=1): open the panel straight away
    if (new URLSearchParams(window.location.search).get('bulba') === '1') toggle(true);
    // From another page with something to ask (?bulba_ask=...): Bulba opens with it typed, not sent
    const askFromUrl = new URLSearchParams(window.location.search).get('bulba_ask');
    if (askFromUrl) setTimeout(() => window.askBulba && window.askBulba(askFromUrl.slice(0, 600)), 0);
    // Open Bulba with something already typed for it (it isn't sent until they press Send)
    window.askBulba = (draft) => {
        if (!frame.src) {
            frame.src = drawer.dataset.src + (draft ? `?draft=${encodeURIComponent(draft)}` : '');
            toggle(true);
        } else {
            toggle(true);
            if (draft) frame.contentWindow.postMessage({ bulbaDraft: draft }, window.location.origin);
        }
    };
    // A Bulba Watch note: open Bulba with that note loaded (Bulba explains it and proposes a fix)
    window.openBulbaNote = (id) => {
        if (!frame.src) {
            frame.src = drawer.dataset.src + `?note=${encodeURIComponent(id)}`;
            toggle(true);
        } else {
            toggle(true);
            frame.contentWindow.postMessage({ bulbaNote: id }, window.location.origin);
        }
    };
    document.getElementById('bulbaClose').onclick = () => toggle(false);
    window.addEventListener('message', (e) => {
        if (e.origin !== window.location.origin || !e.data) return;
        if (e.data.watch && window.Watch) { Watch.refresh(e.data.watch); return; }  // Bulba opened a note
        if (!e.data.bulba) return;
        if (e.data.bulba === 'reply') {  // Bulba's rewrite is now the last reply: show it (Bulba stays open)
            const url = new URL(window.location.href);
            url.searchParams.set('bulba', '1');
            window.location.href = url.toString();
            return;
        }
        showChatNotice(e.data.bulba === 'undo' ? 'Bulba undid its change.' : 'Bulba changed your setup: the next reply uses it.');
    });
})();

function showChatNotice(text) {
    let note = document.getElementById('chatNotice');
    if (!note) {
        note = document.createElement('div');
        note.id = 'chatNotice';
        note.className = 'chat-notice';
        document.body.appendChild(note);
    }
    note.textContent = text;
    note.classList.add('show');
    clearTimeout(note._t);
    note._t = setTimeout(() => note.classList.remove('show'), 4000);
}

// --- Layout: chat bubbles, or a book where replies read as chapters and your messages fold away ---
(function () {
    const choice = document.getElementById('layoutChoice');
    if (choice) choice.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-layout]');
        if (!b) return;
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'appearance', layout: b.dataset.layout }),
        });
        const d = await resp.json().catch(() => ({}));
        if (!d.success) { showChatNotice(d.error || 'Could not change the layout.'); return; }
        document.body.classList.toggle('layout-book', d.layout === 'book');
        choice.querySelectorAll('[data-layout]').forEach(x => x.classList.toggle('on', x.dataset.layout === d.layout));
        if (d.watch && window.Watch) Watch.refresh(d.watch);  // the book without director mode: Bulba may offer it
    });
    // In the book, your messages are small markers between chapters: click one to read or edit it
    document.getElementById('messagesContainer')?.addEventListener('click', (e) => {
        if (!document.body.classList.contains('layout-book')) return;
        const msg = e.target.closest('.message.user');
        if (!msg) return;
        if (!msg.classList.contains('open')) { msg.classList.add('open'); return; }
        if (e.target === msg) msg.classList.remove('open');  // the "✎ you" marker itself folds it again
    });
})();

// Story extras sit where the model put their markers: a copy of each drawing goes into its slot in the text
// (the text is re-rendered while streaming, so the drawings themselves stay in .story-extras, hidden once placed)
function placeExtras(root) {
    // Suggested actions only make sense under the newest reply
    const replies = [...document.querySelectorAll('#messagesContainer .message.assistant:not(#typingMessage)')];
    replies.forEach((m, i) => m.classList.toggle('latest-reply', i === replies.length - 1));
    (root || document).querySelectorAll('.extra-slot').forEach(slot => {
        if (slot.firstChild) return;
        const n = (slot.className.match(/\bn(\d+)\b/) || [])[1];
        const msg = slot.closest('.message');
        const original = n && msg && msg.querySelector(`.story-extras > .story-extra[data-n="${n}"]`);
        if (!original) return;
        slot.appendChild(original.cloneNode(true));
        original.classList.add('placed');
    });
}
(function () {
    const box = document.getElementById('messagesContainer');
    if (!box) return;
    let queued = false;
    new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; placeExtras(box); });
    }).observe(box, { childList: true, subtree: true });
    placeExtras(box);
})();

// A suggested action fills the message box (nothing is sent until they press Send)
document.getElementById('messagesContainer')?.addEventListener('click', (e) => {
    const b = e.target.closest('.choice-btn');
    if (!b) return;
    messageInput.value = b.dataset.choice;
    messageInput.focus();
    messageInput.style.height = 'auto';
    messageInput.style.height = messageInput.scrollHeight + 'px';
});

// Sprites with a transparent background (the corners are see-through) stand in the scene
function markStanding(img) {
    const box = img.closest('.character-image-container');
    if (!box || !img.naturalWidth) return;
    try {
        const c = document.createElement('canvas');
        c.width = c.height = 8;
        const ctx = c.getContext('2d');
        ctx.drawImage(img, 0, 0, 8, 8);
        const d = ctx.getImageData(0, 0, 8, 8).data;
        const alpha = i => d[i * 4 + 3];
        box.classList.toggle('standing', alpha(0) < 40 && alpha(7) < 40);
    } catch (e) { box.classList.remove('standing'); }
}
document.addEventListener('load', e => {
    if (e.target.matches && e.target.matches('img.character-sprite')) markStanding(e.target);
}, true);
document.querySelectorAll('img.character-sprite').forEach(img => { if (img.complete) markStanding(img); });


// Bulba's ideas (an extra): three ways to go on. Playing: things you could say or do (send as they are, or
// have them written out in your voice). Directing: things that could happen next.
async function showIdeas() {
    const box = document.getElementById('ideasBox'), btn = document.getElementById('ideasBtn');
    if (!box || isGenerating) return;
    if (!box.hidden && !box.dataset.busy) { box.hidden = true; return; }
    box.hidden = false; box.dataset.busy = '1';
    box.innerHTML = '<div class="ideas-head">🥔 Bulba is thinking…</div>';
    if (btn) btn.disabled = true;
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'ideas' }),
        });
        const d = await resp.json();
        if (!d.success) throw new Error(d.error || 'No ideas this time.');
        updateSpending(d.spending);
        const directing = d.mode === 'director';
        const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
        box.innerHTML = `<div class="ideas-head">🥔 ${directing ? 'What could happen next' : 'You could…'}
                <button type="button" class="ideas-x" title="Close">✕</button></div>` +
            d.ideas.map((idea, i) => `<div class="idea"><span>${esc(idea)}</span><span class="idea-actions">
                <button type="button" data-idea="${i}" data-how="use">Use</button>
                ${directing ? '' : `<button type="button" data-idea="${i}" data-how="write" title="Have it written out in your voice">Write it</button>`}
                </span></div>`).join('') +
            `<button type="button" class="ideas-more">↻ Other ideas</button>`;
        box.onclick = e => {
            if (e.target.closest('.ideas-x')) { box.hidden = true; return; }
            if (e.target.closest('.ideas-more')) { delete box.dataset.busy; box.hidden = true; showIdeas(); return; }
            const pick = e.target.closest('[data-idea]');
            if (!pick) return;
            messageInput.value = d.ideas[Number(pick.dataset.idea)];
            box.hidden = true;
            if (pick.dataset.how === 'write') expandInput();
            else { messageInput.style.height = 'auto'; messageInput.style.height = messageInput.scrollHeight + 'px'; messageInput.focus(); }
        };
    } catch (err) {
        box.innerHTML = `<div class="ideas-head">🥔 ${err.message} <button type="button" class="ideas-x">✕</button></div>`;
        box.onclick = e => { if (e.target.closest('.ideas-x')) box.hidden = true; };
    } finally {
        delete box.dataset.busy;
        if (btn) btn.disabled = false;
    }
}

// --- Bulba's polish (mainapp/bulba/polish.py): the habits they asked to have fixed, rewritten in each new reply ---
function lastAssistant() {
    const all = document.querySelectorAll('.message.assistant:not(#typingMessage)');
    return all[all.length - 1];
}

function showText(messageEl, text) {
    const textDiv = messageEl.querySelector('.message-text');
    textDiv.innerHTML = renderChatMessage(text, textDiv);
    textDiv.setAttribute('data-raw', encodeURIComponent(text));
    const area = messageEl.querySelector('.edit-textarea');
    if (area) area.value = text;
}

// The line under a reply: "Polishing…", or what was fixed with Show original / Undo fixes. info null removes it.
function setPolish(messageEl, info, busy = false) {
    if (!messageEl) return;
    let line = messageEl.querySelector('.polish-line');
    if (!info && !busy) { if (line) line.remove(); return; }
    if (!line) {
        line = document.createElement('div');
        line.className = 'polish-line';
        const after = messageEl.querySelector('.game-lines') || messageEl.querySelector('.story-extras')
            || messageEl.querySelector('.message-text');
        after.parentNode.insertBefore(line, after.nextSibling);
    }
    if (busy) { line.innerHTML = '<span class="polish-busy">🧹 Polishing…</span>'; return; }
    line._info = info;
    line._polished = decodeURIComponent(messageEl.querySelector('.message-text').getAttribute('data-raw') || '');
    const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const list = (info.fixes || []).map(f => `<li><s>${esc(f.before)}</s>${f.after ? ` → ${esc(f.after)}` : ' (removed)'}</li>`).join('');
    line.innerHTML = `<details><summary>🧹 Bulba fixed ${info.count} thing${info.count === 1 ? '' : 's'}</summary><ul>${list}</ul></details>
        <button type="button" class="link" data-polish="toggle">Show original</button>
        <button type="button" class="link" data-polish="undo">Undo fixes</button>
        ${info.verdict ? '' : `<span class="polish-rate">Better?
            <button type="button" class="link" data-polish="up" title="Yes, the fixes work">👍</button>
            <button type="button" class="link" data-polish="down" title="No: rewrite it again, stop fixing this, or tell Bulba what's wrong">👎</button></span>`}`;
}

// now: they just pressed "Fix this automatically", so this reply is polished too and they hear why if it isn't
function runPolish(messageEl, now = false, index = null, again = false) {
    if (!messageEl) { if (now) showChatNotice("There's no reply to polish yet; the next one will be."); return; }
    if (window.READING_LANGUAGE) setStage(messageEl, '🧹 Revising…');  // the stage line says it (one line, not two)
    else setPolish(messageEl, null, true);
    lockWhileFinishing();
    return fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(index === null || Number.isNaN(index) ? { action: 'polish', now, again } : { action: 'polish', now, index, again }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.spending) updateSpending(d.spending);
            if (!d.success || !d.changed) {
                setPolish(messageEl, null);
                if (d.error) showChatNotice(`Polish skipped: ${d.error}`);
                else if (now && d.reason) showChatNotice(d.reason);
                return;
            }
            showText(messageEl, d.reply);
            setPolish(messageEl, d.polish);
        })
        .catch(() => setPolish(messageEl, null))
        .then(() => window.READING_LANGUAGE ? translateMessage(messageEl) : null)  // polished English, then translated
        .finally(unlockFinished);
}

window.polishLatestNow = () => runPolish(lastAssistant(), true);
// "Rewrite it again" from the fixes-didn't-land question: from the original, avoiding what they turned down
window.repolishMessage = (index) => {
    const el = document.querySelector(`.message[data-index="${index}"]`) || lastAssistant();
    runPolish(el, true, Number(index), true);
};

document.addEventListener('click', e => {
    const b = e.target.closest('.polish-line [data-polish]');
    if (!b) return;
    const line = b.closest('.polish-line');
    const messageEl = b.closest('.message');
    if (b.dataset.polish === 'toggle') {
        const showingOriginal = b.textContent === 'Hide original';
        showText(messageEl, showingOriginal ? line._polished : line._info.original);
        b.textContent = showingOriginal ? 'Show original' : 'Hide original';
        return;
    }
    const rate = b.dataset.polish === 'up' || b.dataset.polish === 'down';
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(rate ? { action: 'polish_feedback', index: Number(messageEl.dataset.index), verdict: b.dataset.polish }
                                  : { action: 'polish_undo', index: Number(messageEl.dataset.index) }),
    })
        .then(r => r.json())
        .then(d => {
            if (!d.success) { showChatError(d.error || (rate ? 'Could not save that.' : 'Could not undo.')); return; }
            if (rate) {
                const span = line.querySelector('.polish-rate');
                if (span) span.textContent = b.dataset.polish === 'up' ? 'Thanks: noted.' : '';
            } else {
                showText(messageEl, d.reply);
                setPolish(messageEl, null);
            }
            if (d.watch && window.Watch) Watch.refresh(d.watch);  // a 👎 or an undo asks what to do next
        });
});

// Replies polished before the page loaded
document.querySelectorAll('.polish-line[data-polish]').forEach(line => {
    try {
        const info = JSON.parse(line.getAttribute('data-polish'));
        line.removeAttribute('data-polish');
        if (info && info.count) setPolish(line.closest('.message'), info);
    } catch (err) { line.remove(); }
});

// The pen menu's "What the AI saw": what the last reply got besides the preset and the messages
document.getElementById('aiSawBox')?.addEventListener('toggle', async (e) => {
    if (!e.target.open) return;
    const box = document.getElementById('aiSaw');
    const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    box.textContent = 'Loading…';
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'ai_saw' }),
        });
        const d = await resp.json();
        if (!d.success) throw new Error(d.error || 'Could not load it.');
        const block = (title, body) => `<div class="ai-saw-part"><b>${title}</b><div>${body}</div></div>`;
        box.innerHTML = block('📚 Story summary', d.summary.length ? d.summary.map(p => `<p>${esc(p.text)}</p>`).join('') : '<i>none yet</i>')
            + block('📌 Pinned note', d.pinned_note ? esc(d.pinned_note) : '<i>none</i>')
            + block('📊 Trackers', d.trackers ? `<pre>${esc(d.trackers)}</pre>` : '<i>none</i>')
            + block('📖 Lore that fired', d.lore.fired.length ? esc(d.lore.fired.join(', ')) : `<i>${d.lore.book ? 'nothing this time' : 'no worldbook'}</i>`)
            + ((d.recalled || []).length ? block('🔁 Brought back from earlier', d.recalled.map(r => `<p><b>${esc(r.who)}:</b> ${esc(r.text)}</p>`).join('')
                + '<p class="tool-help">Old messages that had fallen out of the AI\'s context, matched to the current scene (free).</p>') : '')
            + '<p class="tool-help">Something wrong here? Bulba can fix the summary or the pinned note: ask it in the 🥔 panel.</p>';
    } catch (err) { box.textContent = err.message; }
});

// --- Condensed messages: the AI gets a short version, the chat still shows all of it (editable, redoable) ---
function setCondensed(messageEl, text) {
    if (!messageEl) return;
    let line = messageEl.querySelector('.condensed-line');
    if (!text) { if (line) line.remove(); return; }
    if (!line) {
        line = document.createElement('div');
        line.className = 'condensed-line';
        const after = messageEl.querySelector('.polish-line') || messageEl.querySelector('.game-lines')
            || messageEl.querySelector('.story-extras') || messageEl.querySelector('.message-text');
        after.parentNode.insertBefore(line, after.nextSibling);
    }
    line.removeAttribute('data-condensed');
    line._text = text;
    line.innerHTML = `<span>🗜 Condensed for the AI</span>
        <button type="button" class="link" data-cond="show">Show</button>
        <button type="button" class="link" data-cond="edit">Edit</button>
        <button type="button" class="link" data-cond="redo">Redo</button>
        <button type="button" class="link" data-cond="undo">Undo</button>
        <div class="condensed-text" hidden></div>`;
    line.querySelector('.condensed-text').textContent = text;
}

async function condenseRequest(messageEl, body) {
    const resp = await fetch(window.location.href, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ ...body, index: Number(messageEl.dataset.index) }),
    });
    const d = await resp.json();
    if (d.spending) updateSpending(d.spending);
    if (!d.success) throw new Error(d.error || 'Could not condense it.');
    setCondensed(messageEl, d.condensed);
    return d;
}

function condenseMessage(messageEl) {
    if (!messageEl) return;
    showChatNotice('🗜 Condensing…');
    condenseRequest(messageEl, { action: 'condense' })
        .then(() => showChatNotice('Condensed: the AI gets the short version from now on.'))
        .catch(err => showChatNotice(err.message));
}

document.addEventListener('click', e => {
    const b = e.target.closest('.condensed-line [data-cond]');
    if (!b) return;
    const line = b.closest('.condensed-line');
    const messageEl = b.closest('.message');
    const box = line.querySelector('.condensed-text');
    const what = b.dataset.cond;
    if (what === 'show') { box.hidden = !box.hidden; b.textContent = box.hidden ? 'Show' : 'Hide'; return; }
    if (what === 'edit') {
        box.hidden = false;
        box.innerHTML = '<textarea rows="4"></textarea><button type="button" class="link" data-cond="save">Save</button>';
        box.querySelector('textarea').value = line._text;
        box.querySelector('textarea').focus();
        return;
    }
    const run = what === 'save' ? condenseRequest(messageEl, { action: 'condense', text: box.querySelector('textarea').value })
        : what === 'redo' ? (showChatNotice('🗜 Condensing again…'), condenseRequest(messageEl, { action: 'condense' }))
        : condenseRequest(messageEl, { action: 'condense_undo' });
    run.catch(err => showChatNotice(err.message));
});

// Messages condensed before the page loaded
document.querySelectorAll('.condensed-line[data-condensed]').forEach(line => setCondensed(line.closest('.message'), line.getAttribute('data-condensed')));

// Music that follows the scene (built-in tracks): after some replies, a tiny call picks the track that fits
document.getElementById('musicFollow')?.addEventListener('change', async (e) => {
    const resp = await fetch(window.location.href, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'music_follow', on: e.target.checked }),
    });
    const d = await resp.json().catch(() => ({}));
    window.MUSIC_FOLLOW = !!d.on;
    showChatNotice(d.on ? 'The music follows the scene from your next replies.' : 'The music stays as you set it.');
});

async function followSceneMusic() {
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'scene_music' }),
        });
        const d = await resp.json();
        if (!d.success || !d.music) return;
        // A soft crossfade: down, switch, back up (unless they paused it themselves)
        const target = Number(document.getElementById('musicVolume')?.value || 0.3);
        const wasPlaying = !bgMusic.paused;
        for (let v = bgMusic.volume; wasPlaying && v > 0.02; v -= 0.05) { bgMusic.volume = Math.max(0, v); await new Promise(r => setTimeout(r, 40)); }
        if (musicHeld) { bgMusic.src = d.music.url; document.getElementById('nowPlayingText').innerText = d.music.name; bgMusic.volume = target; return; }
        loadMusic(d.music.url, d.music.name);
        bgMusic.volume = 0;
        for (let v = 0; v < target; v += 0.05) { bgMusic.volume = Math.min(target, v); await new Promise(r => setTimeout(r, 60)); }
        bgMusic.volume = target;
        showChatNotice(`🎵 ${d.music.name}`);
    } catch (err) { /* the music is a nicety */ }
}

// Voice input: the browser's own speech-to-text fills the message box (free; hidden where the browser can't)
(function () {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const btn = document.getElementById('micBtn');
    if (!Recognition || !btn) return;
    btn.hidden = false;
    let rec = null;
    btn.addEventListener('click', () => {
        if (rec) { rec.stop(); return; }
        rec = new Recognition();
        rec.lang = document.documentElement.lang && document.documentElement.lang !== 'en' ? document.documentElement.lang : (navigator.language || 'en-US');
        rec.interimResults = true;
        rec.continuous = true;
        const before = messageInput.value ? messageInput.value.replace(/\s*$/, ' ') : '';
        rec.onresult = (e) => {
            let text = '';
            for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
            messageInput.value = before + text;
            messageInput.style.height = 'auto';
            messageInput.style.height = messageInput.scrollHeight + 'px';
        };
        rec.onerror = (e) => { if (e.error !== 'aborted') showChatNotice(e.error === 'not-allowed' ? 'The microphone is blocked for this site.' : 'Could not hear that. Try again.'); };
        rec.onend = () => { rec = null; btn.classList.remove('listening'); btn.title = 'Speak your message'; messageInput.focus(); };
        rec.start();
        btn.classList.add('listening');
        btn.title = 'Listening… press again to stop';
    });
})();

// "Who are you in this story?": asked once per account, when there's no persona yet
document.getElementById('personaHint')?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-persona-hint]');
    if (!b) return;
    document.getElementById('personaHint').remove();
    fetch(window.location.href, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'persona_hint_seen' }), keepalive: true,  // survives going to the profile
    }).catch(() => { /* asked again next time: harmless */ });
    if (b.dataset.personaHint === 'bulba' && window.askBulba) window.askBulba('Help me make my persona: who I am in this story.');
});

// 🔞 Mature content: switched straight in the active preset (Bulba's own model won't do it)
document.getElementById('matureToggle')?.addEventListener('change', async (e) => {
    const box = e.target, on = box.checked;
    if (on && !await NADialog.confirm('Mature content is for adults only. Are you 18 or older?',
                                      { title: '🔞 Adult scenes', ok: "Yes, I'm 18+", cancel: 'No' })) { box.checked = false; return; }
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'mature', on, adult: on }),
        });
        const d = await resp.json();
        if (!d.success) throw new Error(d.error || 'Could not change it.');
    } catch (err) {
        box.checked = !on;
        alert(err.message);
    }
});

// The ✏️ panel: two tabs (🎬 Steer the story · ⚙ This chat), the last one used opens next time
(function () {
    const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* fine: the first tab opens */ } } };
    const tabs = document.querySelectorAll('.tools-tab');
    const show = (id) => {
        tabs.forEach(t => t.classList.toggle('on', t.dataset.pane === id));
        document.querySelectorAll('.tools-pane').forEach(p => { p.hidden = p.id !== id; });
        store.set('na-tools-tab', id);
    };
    tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.pane)));
    if (store.get('na-tools-tab') === 'paneChat') show('paneChat');
    // "Four ways to steer": open the first time, folded after that (a click opens it again)
    const guide = document.getElementById('steerGuide');
    if (guide) {
        if (store.get('na-steer-guide-seen')) guide.open = false;
        document.getElementById('toolsBtn')?.addEventListener('click', () => store.set('na-steer-guide-seen', '1'));
    }
})();

// 🎭 Director mode: switched straight in the active preset (replies read as a book while it's on)
document.getElementById('directorToggle')?.addEventListener('change', async (e) => {
    const box = e.target, on = box.checked;
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'director_switch', on }),
        });
        const d = await resp.json();
        if (!d.success) throw new Error(d.error || 'Could not switch.');
        document.body.classList.toggle('layout-book', d.layout === 'book');
        document.querySelectorAll('#layoutChoice [data-layout]').forEach(x => x.classList.toggle('on', x.dataset.layout === d.layout));
        if (window.showChatNotice) showChatNotice(on
            ? 'Director mode is on: your messages are directions now, and the AI narrates the whole scene. Switch it off here any time.'
            : 'Director mode is off: you play your character again.');
    } catch (err) {
        box.checked = !on;
        alert(err.message);
    }
});

// The message box's hint fits on one line: the long one where there's room, "Your turn…" on narrow screens
(function () {
    const box = document.getElementById('messageInput');
    if (!box) return;
    const long = box.getAttribute('placeholder'), short = box.dataset.shortPlaceholder || long;
    const fit = () => { box.setAttribute('placeholder', box.clientWidth < 320 ? short : long); };
    window.addEventListener('resize', fit);
    fit();
})();


// A refused reply (a provider's filter, or the model declining) never goes into the story. The first time, they
// pick which model steps in; after that, a refused reply is rewritten on it (just that one reply)
function handleRefusal(d) {
    if (d.bubble) d.bubble.closest('.message')?.remove();
    const nameOf = id => ((d.options || []).find(o => o.id === id) || {}).name || id;
    if (d.already) {
        showChatError(`${d.model} refused this one too. Try Regenerate, reword your message, or switch on 🔞 Mature content (pen menu → This chat).`);
        return;
    }
    if (d.stand_in) {
        showChatNotice(`${d.model} refused this reply, so ${nameOf(d.stand_in)} is writing it instead (just this one).`);
        setTimeout(() => regenerateReply('', d.stand_in), 0);
        return;
    }
    const box = document.createElement('div');
    box.className = 'refusal-ask';
    box.setAttribute('role', 'dialog');
    box.innerHTML = `<b>${escHtml(d.model)} refused this reply</b>
        <p>It wasn't saved. Which model should step in when a reply is refused? It writes only that reply; your chat
        model stays the same. You're asked once.</p>
        <div class="refusal-options">${(d.options || []).map(o => `<button type="button" data-standin="${escHtml(o.id)}">
            <b>${escHtml(o.name)}</b><small>${escHtml(o.note)}</small></button>`).join('')}</div>
        <button type="button" class="link-btn" data-standin="">Not now</button>`;
    document.body.appendChild(box);
    box.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-standin]');
        if (!b) return;
        box.remove();
        if (!b.dataset.standin) return;
        await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'refusal_model', model: b.dataset.standin }),
        }).catch(() => {});
        regenerateReply('', b.dataset.standin);
    });
}

// 🖼 Chat style: the character's, one of the four for this chat, or plain; the effects switch is per browser
(function () {
    const choice = document.getElementById('skinChoice');
    if (choice) choice.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-skin]');
        if (!b) return;
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'set_skin', skin: b.dataset.skin }),
        });
        const d = await resp.json().catch(() => ({}));
        if (!d.success) { showChatNotice(d.error || 'Could not change the chat style.'); return; }
        [...document.body.classList].filter(c => c.startsWith('skin-')).forEach(c => document.body.classList.remove(c));
        if (d.skin) document.body.classList.add('skin-' + d.skin);
        choice.querySelectorAll('[data-skin]').forEach(x => x.classList.toggle('on', x === b));
    });
    const fx = document.getElementById('skinFxToggle');
    if (fx) {
        fx.checked = !document.body.classList.contains('fx-off');
        fx.addEventListener('change', () => {
            document.body.classList.toggle('fx-off', !fx.checked);
            try { localStorage.setItem('chat-fx', fx.checked ? 'on' : 'off'); } catch (err) { /* this page only */ }
        });
    }
    // ✨ Effects on/off: both kinds at once (weather and time of day, the style's light effect)
    const all = document.getElementById('effectsAll'), atmo = document.getElementById('atmosphereToggle');
    if (all && fx && atmo) {
        const sync = () => { all.checked = fx.checked || atmo.checked; document.getElementById('effectsSub').classList.toggle('dim', !all.checked); };
        all.addEventListener('change', () => {
            const want = all.checked;  // read once: each box's own change re-syncs the main switch
            [fx, atmo].forEach(box => { if (box.checked !== want) { box.checked = want; box.dispatchEvent(new Event('change')); } });
            sync();
        });
        [fx, atmo].forEach(box => box.addEventListener('change', sync));
        setTimeout(sync, 0);  // after atmosphere.js has read its own setting
    }
})();

// "Your worldbook got better at your language": shown once per account, either button closes it for good
document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-forms-hint]');
    if (!b) return;
    document.getElementById('formsHint')?.remove();
    fetch(window.location.href, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'forms_hint_seen' }), keepalive: true,
    }).catch(() => { /* shown again next time: harmless */ });
});

// 🧠 Thinking before story replies (the active preset's reasoning effort, in plain words)
(function () {
    const choice = document.getElementById('thinkingChoice');
    if (!choice) return;
    choice.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-thinking]');
        if (!b) return;
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'thinking', level: b.dataset.thinking }),
        });
        const d = await resp.json().catch(() => ({}));
        if (!d.success) { showChatError(d.error || 'Could not change it.'); return; }
        choice.querySelectorAll('[data-thinking]').forEach(x => x.classList.toggle('on', x.dataset.thinking === d.level));
        const on = choice.querySelector(`[data-thinking="${d.level}"]`);
        const help = document.getElementById('thinkingHelp');
        if (on && help) help.textContent = `${on.textContent.trim()}: ${on.title}. Less thinking makes replies quicker and cheaper.`;
    });
})();


// --- Read in another language (profile → Story language): replies are written in English, then translated ---
// A stage line ("Writing…", "Revising…", "Translating…") stands in for the text until the translation is there.
function setStage(messageEl, text, keepText = false) {
    if (!messageEl) return;
    let line = messageEl.querySelector('.translate-stage');
    messageEl.classList.toggle('translating', !!text && !keepText);
    if (!text) { if (line) line.remove(); return; }
    if (!line) {
        line = document.createElement('div');
        line.className = 'translate-stage';
        const textDiv = messageEl.querySelector('.message-text');
        textDiv.parentNode.insertBefore(line, textDiv);
    }
    line.textContent = text;
}

// 🌐 on a translated reply: shows the English; 🌐 (translate) on one that isn't yet
function setOriginal(messageEl, original) {
    if (!messageEl) return;
    const textDiv = messageEl.querySelector('.message-text');
    const actions = messageEl.querySelector('.message-actions');
    messageEl.querySelectorAll('.original-btn, .translate-btn').forEach(b => b.remove());
    if (original) textDiv.dataset.original = encodeURIComponent(original);
    else delete textDiv.dataset.original;
    if (!window.READING_LANGUAGE || !actions || !messageEl.classList.contains('assistant')) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'message-btn ' + (original ? 'original-btn' : 'translate-btn');
    b.dataset.action = original ? 'original' : 'translate';
    b.dataset.index = messageEl.dataset.index;
    b.title = original ? 'Show the English it was written in' : `Translate into ${window.READING_LANGUAGE_NAME}`;
    b.textContent = '🌐';
    actions.insertBefore(b, actions.firstChild);
}

const translating = new WeakSet();
async function translateMessage(messageEl) {
    if (!window.READING_LANGUAGE || !messageEl || translating.has(messageEl)) return;
    translating.add(messageEl);
    lockWhileFinishing();
    setStage(messageEl, `🌐 Translating into ${window.READING_LANGUAGE_NAME}…`);
    try {
        const resp = await fetch(window.location.href, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ action: 'translate', index: Number(messageEl.dataset.index) }),
        });
        const d = await resp.json().catch(() => ({}));
        if (!d.success) {
            setOriginal(messageEl, '');
            if (d.resync) { showChatNotice('This chat changed since the page loaded. Reloading it.'); setTimeout(() => window.location.reload(), 900); }
            else showChatError(`${d.error || "Couldn't translate it."} The English is shown; press 🌐 on the reply to try again.`);
            return;
        }
        showText(messageEl, d.text);
        if (d.extras_html && d.extras_html.length) setExtras(messageEl, d.extras_html);  // letters, phone screens…
        if (d.same) messageEl.querySelectorAll('.original-btn, .translate-btn').forEach(b => b.remove());  // already in it
        else setOriginal(messageEl, d.original);
        messageEl.querySelector('.message-text').removeAttribute('data-untranslated');
    } catch (err) {
        setOriginal(messageEl, '');
        showChatError("Couldn't reach the app server to translate. The English is shown; press 🌐 to try again.");
    } finally {
        translating.delete(messageEl);
        unlockFinished();
        setStage(messageEl, null);
        scrollToBottom();
    }
}

// A reply is written: polish it if that's due (it translates after), else translate it now
async function afterReplyText(messageEl, polishDue) {
    if (!messageEl || !(polishDue || window.READING_LANGUAGE)) return;
    if (window.READING_LANGUAGE) setStage(messageEl, polishDue ? '🧹 Revising…' : `🌐 Translating into ${window.READING_LANGUAGE_NAME}…`);
    lockWhileFinishing();  // the reply isn't done until it's polished and translated
    try {
        await (polishDue ? runPolish(messageEl) : translateMessage(messageEl));
    } finally {
        unlockFinished();
    }
}

// On load: the newest reply (e.g. a new chat's greeting) is translated by itself; older ones on 🌐
(function () {
    if (!window.READING_LANGUAGE) return;
    document.querySelectorAll('.message.assistant:not(#typingMessage)').forEach(el => {
        const textDiv = el.querySelector('.message-text');
        if (textDiv && textDiv.dataset.original) setOriginal(el, decodeURIComponent(textDiv.dataset.original));
        else if (textDiv && textDiv.dataset.untranslated) setOriginal(el, '');
    });
    const last = lastAssistant();
    if (last && last.querySelector('.message-text[data-untranslated]')) translateMessage(last);
})();


// The chat page never scrolls as a whole (only the messages do): on phones the keyboard or a fling during a reply
// could push it up and leave it there, hiding the header
(function () {
    const back = () => { if (window.scrollY || document.documentElement.scrollTop) window.scrollTo(0, 0); };
    window.addEventListener('scroll', back, { passive: true });
    if (window.visualViewport) window.visualViewport.addEventListener('resize', () => setTimeout(back, 50));
})();

// The one-time preset note (preset_upgrade.py): moved to a new writing style, an offer to move, or a rebuild offer
document.getElementById('presetHint')?.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-preset-hint]');
    if (!b) return;
    const hint = document.getElementById('presetHint');
    const action = b.dataset.presetHint;
    const resp = await fetch(hint.dataset.url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action, kind: hint.dataset.kind, pair: hint.dataset.pair }) }).catch(() => null);
    const d = resp ? await resp.json().catch(() => ({})) : {};
    hint.remove();
    if (d.text) showChatNotice(d.text);
    if (['switch', 'undo', 'rebuild'].includes(action) && d.ok) {
        if (action === 'rebuild') showChatNotice(d.text + ' Changed your mind? Ask Bulba, or pick the previous one on the Presets page.');
        setTimeout(() => window.location.reload(), 1600);
    }
});
