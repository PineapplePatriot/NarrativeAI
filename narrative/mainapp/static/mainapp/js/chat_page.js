let currentAudio = null;

function updateCharacterImages(photoUrl, photoSecond, charCount) {
    const c1 = document.getElementById('char1Container');
    const c2 = document.getElementById('char2Container');

    // charCount = 2;
    const count = Number(charCount) || 1;

    // Helper to update src
    const setImg = (container, url) => {
        let img = container.querySelector('img.character-sprite');
        if (!img) {
            img = document.createElement('img');
            img.className = 'character-sprite';
            container.appendChild(img);
        }
        if (url) img.src = url;
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
        case "play-sound": {
            const url = btn.dataset.audioUrl;
            if (url) playCharacterAudio(url);
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
        default:
            break;
    }
});


function playCharacterAudio(audioUrl) {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
    }
    currentAudio = new Audio(audioUrl);
    currentAudio.play().catch(err => console.error("Audio playback failed:", err));
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
function renderChatMessage(rawText, where) {
    const place = messagePlace(where);
    const shown = TextRules.any() ? TextRules.apply(rawText, place.role, place.depth) : rawText;
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
let currentRequest = null;
let deleteMessageIndex = -1;

messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
});

function addMessage(sender, text, specificAvatarUrl = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

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
                <button class="message-btn branch" type="button" data-action="branch" data-index="${messageIndex}" title="Branch: a new chat from this message"><svg class="icon" viewBox="0 0 24 24"><path d="M6 3a3 3 0 0 0-1 5.83v6.34A3 3 0 1 0 7 15.17V13.5c0-.83.67-1.5 1.5-1.5h5A3.5 3.5 0 0 0 17 8.5v-.67a3 3 0 1 0-2 0v.67c0 .83-.67 1.5-1.5 1.5h-5c-.53 0-1.03.1-1.5.28V8.83A3 3 0 0 0 6 3z"/></svg></button>
                <button class="message-btn delete" onclick="deleteMessage(${messageIndex})">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>
                </button>
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
    let bubble = null, text = '', frame = null;

    const paint = () => {
        frame = null;
        bubble.innerHTML = renderChatMessage(text, bubble);
        bubble.setAttribute('data-raw', encodeURIComponent(text));
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
                if (event.type === 'thinking') {
                    // Thinking models (MiMo, Claude...) reason before writing; say so instead of looking stuck
                    const label = typingMessage.querySelector('.typing-indicator span');
                    if (label) label.textContent = `${window.CHARACTER_NAME || 'The AI'} is thinking`;
                } else if (event.type === 'delta') {
                    if (!bubble) {
                        typingMessage.style.display = 'none';
                        addMessage('assistant', '', window.INIT_PHOTO_URL || null);
                        const all = messagesContainer.querySelectorAll('.message.assistant:not(#typingMessage) .message-text');
                        bubble = all[all.length - 1];
                        bubble.closest('.message').classList.add('streaming');
                    }
                    text += event.text;
                    if (!frame) frame = requestAnimationFrame(paint);
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

// Put a finished reply on screen: fill the streamed bubble, or add a new message
function placeReply(data, avatarUrl) {
    updateSpending(data.spending);
    if (!data.bubble) {
        addMessage('assistant', data.reply, avatarUrl);
        return;
    }
    refreshForDepth();
    data.bubble.innerHTML = renderChatMessage(data.reply, data.bubble);
    data.bubble.setAttribute('data-raw', encodeURIComponent(data.reply));
    const message = data.bubble.closest('.message');
    message.classList.remove('streaming');
    message.querySelector('.edit-textarea').value = data.reply;
    if (avatarUrl) {
        const avatar = message.querySelector('.message-avatar');
        if (avatar && avatar.tagName === 'IMG') avatar.src = avatarUrl;
        else if (avatar) avatar.outerHTML = `<img src="${avatarUrl}" class="message-avatar" style="object-fit:cover;">`;
    }
}

// Send message to server
function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isGenerating) return;
    const guideInput = document.getElementById('guidanceInput');
    const guidance = guideInput ? guideInput.value.trim() : '';
    if (guideInput) guideInput.value = '';

    clearSwipeNav();
    addMessage('user', message, window.USER_AVATAR);
    messageInput.value = '';
    messageInput.style.height = 'auto';

    isGenerating = true;
    sendBtn.disabled = true;
    stopContainer.style.display = 'block';
    typingMessage.style.display = 'flex';
    scrollToBottom();

    requestReply({ message: message, guidance: guidance })
        .then(data => {
            if (data.error || data.stopped) {
                if (data.bubble) setSwipes({ count: 1, current: 0 });  // the partial reply was kept
                if (data.error) showChatError(data.error);
                return;
            }
            let avatarToUse = data.photo_url;
            if (Number(data.char_count) === 3 && data.photo_second) {
                avatarToUse = data.photo_second;
            }
            placeReply(data, avatarToUse);
            setSwipes(data.swipes);
            updateCharacterImages(data.photo_url, data.photo_second, data.char_count);
            renderLore(data.lore);
            if (data.summary_due) generateSummary('append', true);
            if (window.Trackers) Trackers.afterReply(data);

            if (data.photo_url) {
                const characterSprite = document.querySelector('.character-sprite');
                if (characterSprite) {
                    characterSprite.src = data.photo_url;
                }
                const avatars = document.querySelectorAll('.message.assistant .message-avatar img');
                avatars.forEach(img => img.src = data.photo_url);
            }

            // Voice: play it and add play/pause buttons to the reply
            if (data.audio_url) {
                playCharacterAudio(data.audio_url);
                const messages = document.querySelectorAll('.message.assistant');
                if (messages.length) {
                    const lastMessage = messages[messages.length - 1];
                    const actionsDiv = lastMessage.querySelector('.message-actions');
                    const audioBtn = document.createElement('button');
                    audioBtn.className = 'message-btn play-sound';
                    audioBtn.onclick = () => playCharacterAudio(data.audio_url);
                    audioBtn.innerHTML = `
                                <svg class="icon" viewBox="0 0 24 24">
                                    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.06c1.48-.74 2.5-2.26 2.5-4.03z"/>
                                    <path d="M0 0h24v24H0z" fill="none"/>
                                </svg>
                            `;

                    const pauseBtn = document.createElement('button');
                    pauseBtn.className = 'message-btn pause-sound';
                    pauseBtn.onclick = pauseCharacterAudio;
                    pauseBtn.innerHTML = `<svg class="icon" viewBox="0 0 24 24">
                                                    <path d="M6 6h12v12H6z"/>
                                                    <path d="M0 0h24v24H0z" fill="none"/>
                                                  </svg>`;
                    actionsDiv.appendChild(audioBtn);
                    actionsDiv.appendChild(pauseBtn);
                }
            }

            console.log("Emotion:", data.emotion);
        })
        .catch(error => {
            console.error('Error:', error);
            showChatError('Could not reach the app server. Check that it is still running.');
        })
        .finally(() => {
            isGenerating = false;
            sendBtn.disabled = false;
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
        alert('Message cannot be empty');
        return;
    }

    // Send edit request to server
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
                cancelEdit(index);
            } else {
                alert('Error saving message: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error saving message');
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
            } else {
                alert('Error deleting message: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error deleting message');
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
    sendBtn.disabled = false;
    stopContainer.style.display = 'none';
    typingMessage.style.display = 'none';
}

// Event listeners
sendBtn.addEventListener('click', sendMessage);
stopBtn.addEventListener('click', stopGeneration);

messageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
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
    if (window.SAVED_MUSIC && window.SAVED_MUSIC.url) {
        bgMusic.src = window.SAVED_MUSIC.url;
        document.getElementById('nowPlayingText').innerText = window.SAVED_MUSIC.name;
        musicWidget.classList.remove('hidden');
    }

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

// Context Loading
let contextGuides = {};
try { const raw = '{{ context_guides|escapejs }}'; if (raw && raw !== "{}") contextGuides = JSON.parse(raw); } catch (e) { }

function populateFields() {
    if (document.getElementById('ctx_situation')) {
        document.getElementById('ctx_situation').value = contextGuides.situation || "";
        document.getElementById('ctx_clothes').value = contextGuides.clothes || "";
        document.getElementById('ctx_state').value = contextGuides.state || "";
        document.getElementById('ctx_thinking').value = contextGuides.thinking || "";
    }
}
populateFields();

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

// Save State
function saveContext() {
    contextGuides = {
        situation: document.getElementById('ctx_situation').value,
        clothes: document.getElementById('ctx_clothes').value,
        state: document.getElementById('ctx_state').value,
        thinking: document.getElementById('ctx_thinking').value
    };
    fetch(window.location.href, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ action: 'save_guides', guides: contextGuides }) });
}

// Actions
// Update this function signature to accept 'mode'
// auto = started after a reply because the summary is set to run every N messages
function generateSummary(mode, auto = false) {
    if (!window.Summary) return;
    if (auto && Summary.paused) return;
    Summary.run(mode === 'regen' ? { mode: 'regen' } : {}, { quiet: auto });
}

function expandInput() {
    const txt = messageInput.value; if (!txt) return alert("Draft something first!");
    messageInput.value = "Expanding...";
    fetch(window.location.href, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ action: 'expand', text: txt }) })
        .then(r => r.json()).then(d => { if (d.success) messageInput.value = d.text; else messageInput.value = txt; });
}

function spellcheckInput() {
    const txt = messageInput.value; if (!txt) return;
    fetch(window.location.href, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ action: 'spellcheck', text: txt }) })
        .then(r => r.json()).then(d => { if (d.success) messageInput.value = d.text; });
}

function continueGeneration() {
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    // Ensure the last message is from the assistant
    if (msgs.length === 0 || !msgs[msgs.length - 1].classList.contains('assistant')) {
        return alert("Can only continue the AI's last message.");
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

                scrollToBottom();
            } else {
                alert(data.error || "Error continuing generation.");
            }
        }).finally(() => {
            isGenerating = false;
            typingMessage.style.display = 'none';
        });
}

// Media
const mediaModal = document.getElementById('mediaModal');
const bgMusic = document.getElementById('bgMusicPlayer');
const musicWidget = document.getElementById('musicWidget');
let currentMediaType = 'bg';

function openMediaModal(type) {
    currentMediaType = type;
    document.getElementById('mediaModalTitle').innerText = type === 'bg' ? "Select Background" : "Select Music";
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
        bgMusic.src = url;
        bgMusic.play();
        musicWidget.classList.remove('hidden');
        document.getElementById('nowPlayingText').innerText = name;

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
        bgMusic.pause();
        musicWidget.classList.add('hidden');
        saveMediaState('music', '', '');
    }
    closeMediaModal();
}
function uploadMedia() {
    const f = document.getElementById('fileUpload').files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f); fd.append('type', currentMediaType);
    fetch('/api/media-resources/', { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') }, body: fd })
        .then(r => r.json()).then(d => { if (d.success) selectMedia(d.url, d.name); else alert('Upload failed'); });
}
function togglePlay() { if (bgMusic.paused) { bgMusic.play(); document.getElementById('playPauseBtn').innerText = "❚❚"; } else { bgMusic.pause(); document.getElementById('playPauseBtn').innerText = "▶"; } }
function stopMusic() { bgMusic.pause(); musicWidget.classList.add('hidden'); }
function setVolume(v) { bgMusic.volume = v; }

// Regeneration Logic
const regenModal = document.getElementById('regenModal');
function openRegenModal() { regenModal.classList.add('show'); }
function closeRegenModal() { regenModal.classList.remove('show'); }
function confirmRegenerate() {
    const g = document.getElementById('regenGuidance').value;
    closeRegenModal();
    regenerateReply(g);
}

// A new version of the AI's last reply. The old one stays as a swipe (and comes back if this fails).
function regenerateReply(guidance = '') {
    if (isGenerating) return;
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    const last = msgs[msgs.length - 1];
    const old = last && last.classList.contains('assistant') ? last : null;
    const before = window.LAST_SWIPES;
    if (old) old.style.display = 'none';
    clearSwipeNav();
    isGenerating = true; sendBtn.disabled = true; typingMessage.style.display = 'flex'; scrollToBottom();
    stopContainer.style.display = 'block';
    const restore = () => { if (old) { old.style.display = ''; setSwipes(before); } };
    requestReply({ action: 'regenerate', guidance: guidance })
        .then(d => {
            if (d.error || d.stopped) {
                // The server keeps any text that arrived as a new version; with none, the old reply stays
                if (!d.bubble) restore();
                else { if (old) old.remove(); setSwipes(before ? { count: before.count + 1, current: before.count } : { count: 1, current: 0 }); }
                if (d.error) showChatError(d.error);
                return;
            }
            if (old) old.remove();
            placeReply(d, d.photo_url); setSwipes(d.swipes);
            updateCharacterImages(d.photo_url, d.photo_second, d.char_count); renderLore(d.lore);
            if (d.summary_due) generateSummary('append', true);
            if (window.Trackers) Trackers.afterReply(d);
        })
        .catch(err => { console.error(err); restore(); showChatError('Could not reach the app server.'); })
        .finally(() => { isGenerating = false; sendBtn.disabled = false; stopContainer.style.display = 'none'; typingMessage.style.display = 'none'; updateMessageIndices(); });
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
    if (!info || isGenerating) return;
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
            textDiv.setAttribute('data-raw', encodeURIComponent(d.reply));
            last.querySelector('.edit-textarea').value = d.reply;
            last.dataset.emotion = d.emotion;
            last.dataset.charCount = d.char_count;
            const avatar = last.querySelector('img.message-avatar');
            const avatarUrl = Number(d.char_count) === 3 && d.photo_second ? d.photo_second : d.photo_url;
            if (avatar && avatarUrl) avatar.src = avatarUrl;
            updateCharacterImages(d.photo_url, d.photo_second, d.char_count);
            setSwipes(d.swipes);
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
if (regenModal) regenModal.addEventListener('click', (e) => { if (e.target === regenModal) closeRegenModal(); });
if (mediaModal) mediaModal.addEventListener('click', (e) => { if (e.target === mediaModal) closeMediaModal(); });


function saveMediaState(type, url, name) {
    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'save_media', type: type, url: url, name: name })
    });
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
    const save = async (name, description) => {
        try {
            const resp = await fetch(window.location.href, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ action: 'chat_persona', name, description }),
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
    document.getElementById('personaReset').onclick = () => {
        document.getElementById('personaName').value = ''; document.getElementById('personaDesc').value = '';
        save('', '');
    };
})();
