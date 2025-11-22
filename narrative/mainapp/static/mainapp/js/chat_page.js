let currentAudio = null;


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

function addMessage(sender, text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    const existingMessages = document.querySelectorAll('.message:not(#typingMessage)');
    const messageIndex = existingMessages.length;
    messageDiv.setAttribute('data-index', messageIndex);

    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const rendered = renderChatMessage(text);

    messageDiv.innerHTML = `
                <div class="message-avatar">${sender === 'user' ? 'You' : 'E'}</div>
                <div class="message-content">
                    <div class="message-actions">
                        <button class="message-btn edit" onclick="editMessage(${messageIndex})">
                            <svg class="icon" viewBox="0 0 24 24">
                                <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                            </svg>
                        </button>
                        <button class="message-btn delete" onclick="deleteMessage(${messageIndex})">
                            <svg class="icon" viewBox="0 0 24 24">
                                <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="message-text" data-raw="${encodeURIComponent(text)}">${rendered}</div>
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
});