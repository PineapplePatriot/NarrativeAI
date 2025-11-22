let djangoSettings = {};
const settingsScript = document.getElementById('django-settings-data');
if (settingsScript && settingsScript.textContent.trim() !== "") {
  try {
    djangoSettings = JSON.parse(settingsScript.textContent);
  } catch (e) {
    console.error("Invalid Django settings JSON:", e);
  }
}

settings = mergeDeep(JSON.parse(JSON.stringify(DEFAULTS)), djangoSettings);
let hasUnsavedChanges = false;

// Enable/disable save button based on changes
function markAsChanged() {
  hasUnsavedChanges = true;
  document.getElementById('saveButton').disabled = false;
}

function markAsSaved() {
  hasUnsavedChanges = false;
  document.getElementById('saveButton').disabled = true;
}

// Get CSRF token for Django
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

// Initialize NSFW styles
function initNSFWStyles() {
  const container = document.getElementById('nsfwStyles');
  container.innerHTML = '';

  for (const [key, data] of Object.entries(settings.nsfw.styles)) {
    const div = document.createElement('div');
    div.className = 'style-option';
    div.innerHTML = `
          <div class="style-header">
            <span class="style-name">${data.name}</span>
            <span class="style-badge">${data.badge}</span>
          </div>
          <button class="expand-btn" onclick="togglePrompt('nsfw-${key}')">Edit Prompt</button>
          <div class="expandable-prompt" id="prompt-nsfw-${key}">
            <textarea id="prompt-text-nsfw-${key}" style="min-height: 100px;">${data.prompt}</textarea>
          </div>
        `;
    container.appendChild(div);

    const textarea = div.querySelector(`#prompt-text-nsfw-${key}`);
    if (textarea) {
      textarea.addEventListener('input', () => {
        settings.nsfw.styles[key].prompt = textarea.value;
        updateJSON();
      });
    }
  }
}

// Toggle add NSFW form
function toggleAddNSFWForm() {
  const form = document.getElementById('addNSFWForm');
  form.classList.toggle('show');
  if (form.classList.contains('show')) {
    document.getElementById('newNSFWName').focus();
  }
}

// Save new NSFW style
function saveNewNSFWStyle() {
  const name = document.getElementById('newNSFWName').value.trim();
  const badge = document.getElementById('newNSFWBadge').value.trim();
  const prompt = document.getElementById('newNSFWPrompt').value.trim();

  if (!name) {
    alert('Please enter a style name');
    return;
  }

  const key = name.toLowerCase().replace(/[^a-z0-9]/g, '_');

  settings.nsfw.custom[key] = {
    name: name,
    badge: badge || 'Custom',
    prompt: prompt || 'Enter your custom NSFW style instructions here...'
  };

  // Clear form
  document.getElementById('newNSFWName').value = '';
  document.getElementById('newNSFWBadge').value = '';
  document.getElementById('newNSFWPrompt').value = '';
  document.getElementById('addNSFWForm').classList.remove('show');

  renderCustomNSFW();
  updateJSON();
  showStatus('Custom NSFW style added', 'success');
}

// Cancel add NSFW
function cancelAddNSFW() {
  document.getElementById('newNSFWName').value = '';
  document.getElementById('newNSFWBadge').value = '';
  document.getElementById('newNSFWPrompt').value = '';
  document.getElementById('addNSFWForm').classList.remove('show');
}

// Render custom NSFW styles
function renderCustomNSFW() {
  const container = document.getElementById('customNSFWStyles');
  container.innerHTML = '';

  for (const [key, data] of Object.entries(settings.nsfw.custom)) {
    const div = document.createElement('div');
    div.className = 'custom-nsfw-row';
    div.innerHTML = `
          <input type="text" value="${data.name}" placeholder="Style name">
          <input type="text" value="${data.badge}" placeholder="Badge">
          <textarea placeholder="Prompt instructions..." style="min-height: 80px;">${data.prompt}</textarea>
          <button class="btn btn-danger btn-small" onclick="deleteCustomNSFW('${key}')">Delete</button>
        `;

    const nameInput = div.querySelector('input:nth-of-type(1)');
    const badgeInput = div.querySelector('input:nth-of-type(2)');
    const promptTextarea = div.querySelector('textarea');

    nameInput.addEventListener('input', (e) => {
      settings.nsfw.custom[key].name = e.target.value;
      updateJSON();
    });

    badgeInput.addEventListener('input', (e) => {
      settings.nsfw.custom[key].badge = e.target.value;
      updateJSON();
    });

    promptTextarea.addEventListener('input', (e) => {
      settings.nsfw.custom[key].prompt = e.target.value;
      updateJSON();
    });

    container.appendChild(div);
  }
}

// Delete custom NSFW
function deleteCustomNSFW(key) {
  if (confirm('Delete this custom style?')) {
    delete settings.nsfw.custom[key];
    renderCustomNSFW();
    updateJSON();
    showStatus('Custom NSFW style deleted', 'success');
  }
}

// Toggle add prompt form
function toggleAddPromptForm() {
  const form = document.getElementById('addPromptForm');
  form.classList.toggle('show');
  if (form.classList.contains('show')) {
    document.getElementById('newPromptName').focus();
  }
}

// Save new prompt
function saveNewPrompt() {
  const name = document.getElementById('newPromptName').value.trim();
  const prompt = document.getElementById('newPromptText').value.trim();

  if (!name) {
    alert('Please enter a prompt name');
    return;
  }

  const key = name.toLowerCase().replace(/[^a-z0-9]/g, '_');

  settings.prompts.custom[key] = {
    name: name,
    prompt: prompt || 'Enter your custom prompt instructions here...'
  };

  // Clear form
  document.getElementById('newPromptName').value = '';
  document.getElementById('newPromptText').value = '';
  document.getElementById('addPromptForm').classList.remove('show');

  renderCustomPrompts();
  updateJSON();
  showStatus('Custom prompt added', 'success');
}

// Cancel add prompt
function cancelAddPrompt() {
  document.getElementById('newPromptName').value = '';
  document.getElementById('newPromptText').value = '';
  document.getElementById('addPromptForm').classList.remove('show');
}

// Render custom prompts
function renderCustomPrompts() {
  const container = document.getElementById('customPrompts');
  container.innerHTML = '';

  for (const [key, data] of Object.entries(settings.prompts.custom)) {
    const div = document.createElement('div');
    div.className = 'custom-field-row';
    div.innerHTML = `
          <input type="text" value="${data.name}" placeholder="Prompt name">
          <textarea placeholder="Prompt instructions..." style="min-height: 100px;">${data.prompt}</textarea>
          <button class="btn btn-danger btn-small" onclick="deleteCustomPrompt('${key}')">Delete</button>
        `;

    const nameInput = div.querySelector('input');
    const promptTextarea = div.querySelector('textarea');

    nameInput.addEventListener('input', (e) => {
      settings.prompts.custom[key].name = e.target.value;
      updateJSON();
    });

    promptTextarea.addEventListener('input', (e) => {
      settings.prompts.custom[key].prompt = e.target.value;
      updateJSON();
    });

    container.appendChild(div);
  }
}

// Delete custom prompt
function deleteCustomPrompt(key) {
  if (confirm('Delete this custom prompt?')) {
    delete settings.prompts.custom[key];
    renderCustomPrompts();
    updateJSON();
    showStatus('Custom prompt deleted', 'success');
  }
}

// Toggle prompt visibility
function togglePrompt(id) {
  const el = document.getElementById('prompt-' + id);
  if (el) el.classList.toggle('show');
}

// Collect settings from UI
function collectSettings() {
  settings.sampling.temperature = parseFloat(document.getElementById('temperature').value);
  settings.sampling.top_p = parseFloat(document.getElementById('top_p').value);
  settings.sampling.top_k = parseInt(document.getElementById('top_k').value);
  settings.sampling.min_p = parseFloat(document.getElementById('min_p').value);
  settings.sampling.frequency_penalty = parseFloat(document.getElementById('frequency_penalty').value);
  settings.sampling.presence_penalty = parseFloat(document.getElementById('presence_penalty').value);
  settings.sampling.repetition_penalty = parseFloat(document.getElementById('repetition_penalty').value);
  settings.sampling.tfs = parseFloat(document.getElementById('tfs').value);
  settings.sampling.context_size = parseInt(document.getElementById('context_size').value);
  settings.sampling.max_tokens = parseInt(document.getElementById('max_tokens').value);
  settings.sampling.stop_sequences = document.getElementById('stop_sequences').value;
  settings.sampling.seed = document.getElementById('seed').value || null;

  settings.behaviors.streaming = document.getElementById('enable_streaming').checked;
  settings.behaviors.continue = document.getElementById('enable_continue').checked;
  settings.behaviors.impersonate = document.getElementById('enable_impersonate').checked;
  settings.behaviors.add_bos = document.getElementById('add_bos_token').checked;
  settings.behaviors.ban_eos = document.getElementById('ban_eos_token').checked;
  settings.behaviors.skip_special = document.getElementById('skip_special_tokens').checked;

  settings.nsfw.is_18 = document.getElementById('is_18').checked;
  settings.nsfw.enabled = document.getElementById('nsfw_enabled').checked;

  // Collect NSFW prompts
  for (const key in settings.nsfw.styles) {
    const textarea = document.getElementById(`prompt-text-nsfw-${key}`);
    if (textarea) settings.nsfw.styles[key].prompt = textarea.value;
  }

  // Collect system prompts
  const promptFields = ['system', 'character', 'scenario', 'style', 'continue', 'impersonate',
    'jailbreak', 'claude_prefill', 'memory', 'safety', 'format', 'antirepetition'];
  promptFields.forEach(field => {
    const el = document.getElementById(field === 'claude_prefill' ? 'claude_prefill' : field + '_prompt');
    if (el) settings.prompts[field] = el.value;
  });
}

// Update JSON preview
function updateJSON() {
  collectSettings();
  document.getElementById('jsonOutput').textContent = JSON.stringify(settings, null, 2);
  markAsChanged();
}

// Apply settings to UI
function applySettingsToUI(skipMarkAsSaved = false) {
  document.getElementById('temperature').value = settings.sampling.temperature;
  document.getElementById('top_p').value = settings.sampling.top_p;
  document.getElementById('top_k').value = settings.sampling.top_k;
  document.getElementById('min_p').value = settings.sampling.min_p;
  document.getElementById('frequency_penalty').value = settings.sampling.frequency_penalty;
  document.getElementById('presence_penalty').value = settings.sampling.presence_penalty;
  document.getElementById('repetition_penalty').value = settings.sampling.repetition_penalty;
  document.getElementById('tfs').value = settings.sampling.tfs;
  document.getElementById('context_size').value = settings.sampling.context_size;
  document.getElementById('max_tokens').value = settings.sampling.max_tokens;
  document.getElementById('stop_sequences').value = settings.sampling.stop_sequences || '';
  document.getElementById('seed').value = settings.sampling.seed || '';

  document.getElementById('enable_streaming').checked = settings.behaviors.streaming;
  document.getElementById('enable_continue').checked = settings.behaviors.continue;
  document.getElementById('enable_impersonate').checked = settings.behaviors.impersonate;
  document.getElementById('add_bos_token').checked = settings.behaviors.add_bos;
  document.getElementById('ban_eos_token').checked = settings.behaviors.ban_eos;
  document.getElementById('skip_special_tokens').checked = settings.behaviors.skip_special;

  document.getElementById('is_18').checked = settings.nsfw.is_18;
  document.getElementById('nsfw_enabled').checked = settings.nsfw.enabled;

  // Apply system prompts
  const promptFields = ['system', 'character', 'scenario', 'style', 'continue', 'impersonate',
    'jailbreak', 'claude_prefill', 'memory', 'safety', 'format', 'antirepetition'];
  promptFields.forEach(field => {
    const el = document.getElementById(field === 'claude_prefill' ? 'claude_prefill' : field + '_prompt');
    if (el) el.value = settings.prompts[field] || '';
  });

  initNSFWStyles();
  renderCustomNSFW();
  renderCustomPrompts();
  updateRangeValues();
  toggleNSFWAccess();

  // Update JSON without marking as changed
  collectSettings();
  document.getElementById('jsonOutput').textContent = JSON.stringify(settings, null, 2);

  if (!skipMarkAsSaved) {
    markAsSaved();
  }
}

// Update range display values
function updateRangeValues() {
  const ranges = [
    { id: 'temperature', display: 'tempValue', decimals: 2 },
    { id: 'top_p', display: 'topPValue', decimals: 2 },
    { id: 'top_k', display: 'topKValue', decimals: 0 },
    { id: 'min_p', display: 'minPValue', decimals: 2 },
    { id: 'frequency_penalty', display: 'freqPenValue', decimals: 2 },
    { id: 'presence_penalty', display: 'presPenValue', decimals: 2 },
    { id: 'repetition_penalty', display: 'repPenValue', decimals: 2 },
    { id: 'tfs', display: 'tfsValue', decimals: 2 }
  ];

  ranges.forEach(r => {
    const val = document.getElementById(r.id).value;
    document.getElementById(r.display).textContent = parseFloat(val).toFixed(r.decimals);
  });
}

// Toggle NSFW access
function toggleNSFWAccess() {
  const is18 = document.getElementById('is_18').checked;
  const nsfwContent = document.getElementById('nsfwContent');

  if (is18) {
    nsfwContent.style.opacity = '1';
    nsfwContent.style.pointerEvents = 'auto';
    nsfwContent.querySelector('.age-warning').style.display = 'none';
  } else {
    nsfwContent.style.opacity = '0.5';
    nsfwContent.style.pointerEvents = 'none';
    nsfwContent.querySelector('.age-warning').style.display = 'flex';
    document.getElementById('nsfw_enabled').checked = false;
  }
  updateJSON();
}

// Save settings to Django backend
async function saveSettings() {
  try {
    collectSettings();

    const csrftoken = getCookie('csrftoken');
    const response = await fetch(window.location.href, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify(settings)
    });

    const result = await response.json();

    if (result.status === 'ok') {
      showStatus('Settings saved successfully!', 'success');
      markAsSaved();
    } else {
      showStatus(result.message || 'Failed to save settings', 'error');
    }
  } catch (error) {
    console.error('Save error:', error);
    showStatus('Error saving settings: ' + error.message, 'error');
  }
}

// Export JSON
function exportJSON() {
  collectSettings();
  const blob = new Blob([JSON.stringify(settings, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'chat-settings.json';
  a.click();
  URL.revokeObjectURL(url);
  showStatus('Settings exported!', 'success');
}

// Import JSON
function importJSON() {
  document.getElementById('importFile').click();
}

document.getElementById('importFile').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (event) => {
    try {
      const imported = JSON.parse(event.target.result);
      settings = imported;
      applySettingsToUI();
      showStatus('Settings imported successfully!', 'success');
    } catch (err) {
      alert('Failed to import: Invalid JSON file');
    }
  };
  reader.readAsText(file);
  e.target.value = '';
});

// Reset to defaults
function resetDefaults() {
  if (!confirm('Reset all settings to defaults? This cannot be undone.')) return;
  settings = JSON.parse(JSON.stringify(DEFAULTS));
  applySettingsToUI(true);
  markAsChanged();
  showStatus('Settings reset to defaults', 'success');
}

// Show status message
function showStatus(message, type) {
  const statusEl = document.getElementById('statusMessage');
  statusEl.textContent = message;
  statusEl.className = `status-message ${type} show`;
  setTimeout(() => statusEl.classList.remove('show'), 3000);
}

// Event listeners for ranges
const rangeInputs = ['temperature', 'top_p', 'top_k', 'min_p', 'frequency_penalty',
  'presence_penalty', 'repetition_penalty', 'tfs'];
rangeInputs.forEach(id => {
  document.getElementById(id).addEventListener('input', () => {
    updateRangeValues();
    updateJSON();
  });
});

// Event listeners for other inputs
['context_size', 'max_tokens', 'stop_sequences', 'seed'].forEach(id => {
  document.getElementById(id).addEventListener('input', updateJSON);
});

// Checkboxes
['enable_streaming', 'enable_continue', 'enable_impersonate', 'add_bos_token',
  'ban_eos_token', 'skip_special_tokens', 'nsfw_enabled'].forEach(id => {
    document.getElementById(id).addEventListener('change', updateJSON);
  });

document.getElementById('is_18').addEventListener('change', toggleNSFWAccess);

// Textareas
document.querySelectorAll('textarea').forEach(textarea => {
  textarea.addEventListener('input', updateJSON);
});

// Load settings from Django backend
function loadSettings() {
  try {
    // Check if Django provided settings data
    const settingsScript = document.getElementById('django-settings-data');
    if (settingsScript && settingsScript.textContent.trim() !== "") {
      const djangoSettings = JSON.parse(settingsScript.textContent);

      if (djangoSettings && Object.keys(djangoSettings).length > 0) {
        // Merge Django settings with defaults to ensure all fields exist
        settings = mergeDeep(JSON.parse(JSON.stringify(DEFAULTS)), djangoSettings);
        console.log('Loaded settings from Django:', settings);
      }
    }
  } catch (e) {
    console.error('Failed to load settings:', e);
  }

  applySettingsToUI();
}

// Deep merge helper function
function mergeDeep(target, source) {
  const output = Object.assign({}, target);
  if (isObject(target) && isObject(source)) {
    Object.keys(source).forEach(key => {
      if (isObject(source[key])) {
        if (!(key in target))
          Object.assign(output, { [key]: source[key] });
        else
          output[key] = mergeDeep(target[key], source[key]);
      } else {
        Object.assign(output, { [key]: source[key] });
      }
    });
  }
  return output;
}

function isObject(item) {
  return item && typeof item === 'object' && !Array.isArray(item);
}

// Initialize
window.addEventListener("load", loadSettings);