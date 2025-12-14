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
        el.innerHTML = renderChatMessage(raw);
    });
}


function wrapQuoted(text) {
    const parts = text.split(/(`+[^`]*`+)/g);
    return parts.map((part, i) => {
        if (i % 2 === 1) return part;

        return part.replace(/"([^"\n]+)"/g, (_m, inner) =>
            `<span class="quoted">"${inner}"</span>`
        );
    }).join('');
}


marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false,
    html: true
});


function renderChatMessage(rawText) {
    const pre2 = wrapQuoted(rawText);
    const html = marked.parse(pre2);

    const clean = DOMPurify.sanitize(html, {
        ALLOWED_TAGS: [
            'em', 'strong', 'code', 'pre', 'span', 'a', 'p', 'br', 'ul', 'ol', 'li', 'blockquote',
            'table', 'thead', 'tbody', 'tr', 'th', 'td'
        ],
        ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'class']
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
    const rendered = renderChatMessage(text);

    // --- NEW: Avatar Logic ---
    let avatarHtml = '';

    if (sender === 'user') {
        // Check the global variable set in HTML
        if (window.USER_AVATAR) {
            avatarHtml = `<img src="${window.USER_AVATAR}" class="message-avatar" style="object-fit:cover;">`;
        } else {
            avatarHtml = '<div class="message-avatar">You</div>';
        }
    } else {
        // For assistant, allow passing a specific emotion avatar, or fallback to current global
        const url = specificAvatarUrl || window.INIT_PHOTO_URL;
        if (url) {
            avatarHtml = `<img src="${url}" class="message-avatar" style="object-fit:cover;">`;
        } else {
            avatarHtml = '<div class="message-avatar">E</div>';
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

// Send message to server
function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isGenerating) return;

    addMessage('user', message);
    messageInput.value = '';
    messageInput.style.height = 'auto';

    isGenerating = true;
    sendBtn.disabled = true;
    stopContainer.style.display = 'block';
    typingMessage.style.display = 'flex';
    scrollToBottom();

    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ message: message })
    })
        .then(response => response.json())
        .then(data => {
            addMessage('assistant', data.reply);
            updateCharacterImages(data.photo_url, data.photo_second, data.char_count);

            if (data.photo_url) {
                const characterSprite = document.querySelector('.character-sprite');
                if (characterSprite) {
                    characterSprite.src = data.photo_url;
                }
                const avatars = document.querySelectorAll('.message.assistant .message-avatar img');
                avatars.forEach(img => img.src = data.photo_url);
            }

            // Додаємо кнопку аудіо, якщо вона прийшла з сервера
            if (data.audio_url) {
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
            addMessage('assistant', 'Sorry, there was an error getting a response...');
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
    });
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
    const newText = editTextarea.value.trim();

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
                const rendered = renderChatMessage(newText);
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
function generateSummary(mode) {
    const summaryBox = document.getElementById('summaryDisplay');
    const originalText = summaryBox.innerText;
    summaryBox.innerText = mode === 'regen' ? "Regenerating full summary..." : "Appending recent events...";

    // Lock buttons roughly
    const btns = document.querySelectorAll('.tool-section .tool-action-btn');
    btns.forEach(b => b.disabled = true);

    fetch(window.location.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        // Pass the mode in the body
        body: JSON.stringify({ action: 'summarize', mode: mode })
    })
        .then(r => r.json()).then(d => {
            if (d.success) {
                document.getElementById('summaryDisplay').innerText = d.summary;
            } else {
                summaryBox.innerText = originalText; // Revert on error
                alert(d.error);
            }
        })
        .finally(() => {
            btns.forEach(b => b.disabled = false);
        });
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
                const renderedHtml = renderChatMessage(data.reply);

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

// --- IMPORTANT: OVERRIDE sendMessage ---
// To support guidance, we override the existing function variable
const oldSendMessage = sendMessage;
sendMessage = function () {
    const txt = messageInput.value.trim();
    const guide = document.getElementById('guidanceInput').value.trim();
    if (!txt && !guide) return;
    if (isGenerating) return;

    if (txt) { addMessage('user', txt); messageInput.value = ''; messageInput.style.height = 'auto'; }
    document.getElementById('guidanceInput').value = '';

    isGenerating = true; sendBtn.disabled = true; stopContainer.style.display = 'block'; typingMessage.style.display = 'flex'; scrollToBottom();

    fetch(window.location.href, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'chat', message: txt, guidance: guide })
    }).then(r => r.json()).then(d => {
        addMessage('assistant', d.reply);
        updateCharacterImages(d.photo_url, d.photo_second, d.char_count);
        if (d.audio_url) playCharacterAudio(d.audio_url);
    }).finally(() => { isGenerating = false; sendBtn.disabled = false; stopContainer.style.display = 'none'; typingMessage.style.display = 'none'; scrollToBottom(); updateMessageIndices(); });
};

// Regeneration Logic
const regenModal = document.getElementById('regenModal');
function openRegenModal() { regenModal.classList.add('show'); }
function closeRegenModal() { regenModal.classList.remove('show'); }
function confirmRegenerate() {
    const msgs = document.querySelectorAll('.message:not(#typingMessage)');
    if (msgs.length && msgs[msgs.length - 1].classList.contains('assistant')) msgs[msgs.length - 1].remove();
    const g = document.getElementById('regenGuidance').value;
    closeRegenModal();
    isGenerating = true; typingMessage.style.display = 'flex'; scrollToBottom();
    fetch(window.location.href, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ action: 'regenerate', guidance: g }) })
        .then(r => r.json()).then(d => { addMessage('assistant', d.reply); updateCharacterImages(d.photo_url, d.photo_second, d.char_count); })
        .finally(() => { isGenerating = false; typingMessage.style.display = 'none'; updateMessageIndices(); });
}

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