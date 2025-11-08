document.addEventListener("DOMContentLoaded", function () {
    const apiKeyInput = document.getElementById('openrouter-key');
    const dropdown = document.getElementById('model-dropdown');
    const hiddenInput = document.getElementById('or_model_hidden');
    const status = document.getElementById('openrouter-status');

    async function loadOpenRouterModels(apiKey) {
        try {
            status.textContent = 'Loading...';
            status.className = 'status-indicator status-loading';
            status.style.display = 'inline-block';

            dropdown.innerHTML = '<option>Loading models...</option>';
            dropdown.disabled = true;

            const response = await fetch('https://openrouter.ai/api/v1/models', {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' }
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            dropdown.innerHTML = '';
            dropdown.disabled = false;

            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = 'Select a model...';
            dropdown.appendChild(defaultOption);

            const sortedModels = data.data.sort((a, b) => a.id.localeCompare(b.id));
            sortedModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name || model.id;
                if (model.id === hiddenInput.value) {
                    option.selected = true; // обираємо збережену модель
                }
                dropdown.appendChild(option);
            });

            status.textContent = 'Connected';
            status.className = 'status-indicator status-success';
        } catch (error) {
            console.error('Failed to load OpenRouter models:', error);
            dropdown.innerHTML = '<option>Failed to load models - check API key</option>';
            dropdown.disabled = false;
            status.textContent = 'Connection Failed';
            status.className = 'status-indicator status-error';
        }
    }

    // якщо ключ вже є, завантажуємо моделі
    if (apiKeyInput.value.trim().length > 0) {
        loadOpenRouterModels(apiKeyInput.value.trim());
    }

    // подія при зміні ключа
    apiKeyInput.addEventListener('input', function (e) {
        const apiKey = e.target.value.trim();
        if (apiKey.length > 10) {
            setTimeout(() => { if (e.target.value.trim() === apiKey) loadOpenRouterModels(apiKey); }, 1000);
        } else {
            dropdown.innerHTML = '<option value="">Enter API key first to load models...</option>';
            dropdown.disabled = true;
            status.style.display = 'none';
        }
    });

    // оновлення hidden input при зміні dropdown
    dropdown.addEventListener('change', function () {
        hiddenInput.value = this.value;
    });
});