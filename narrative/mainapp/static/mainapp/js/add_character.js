document.addEventListener("DOMContentLoaded", function () {
    // "3 of 9 added" on the folded Sprites section; open it when a sprite has an error
    const spriteCount = document.getElementById('spriteCount');
    function countSprites() {
        const groups = [...document.querySelectorAll('.file-group')].filter(g => g.style.display !== 'none');
        const added = groups.filter(g => g.querySelector('.file-preview img')).length;
        if (spriteCount) spriteCount.textContent = `${added} of ${groups.length} added`;
    }
    const sprites = document.getElementById('spritesSection');
    if (sprites && [...sprites.querySelectorAll('.form-error')].some(e => e.textContent.trim())) sprites.open = true;

    document.querySelectorAll('.file-group').forEach(group => {
        const input = group.querySelector('input[type="file"]');
        const preview = group.querySelector('.file-preview');

        input.addEventListener('change', function () {
            preview.innerHTML = '';
            if (this.files && this.files[0] && this.files[0].type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    preview.appendChild(img);
                    countSprites();
                };
                reader.readAsDataURL(this.files[0]);
            } else {
                preview.textContent = '📷';
            }
        });
    });
    const isMultCheckbox = document.getElementById('id_is_mult');
    const fileGroups = document.querySelectorAll('.file-group');
    const secondVoiceContainer = document.getElementById('second-char-voice-container');

    function toggleSecondCharFields() {
        if (!isMultCheckbox) return;

        const isChecked = isMultCheckbox.checked;

        fileGroups.forEach(group => {
            const fieldName = group.getAttribute('data-field-name');

            if (fieldName && fieldName.includes('second')) {
                if (isChecked) {
                    group.style.display = 'flex';
                } else {
                    group.style.display = 'none';
                }
            }
        });

        if (secondVoiceContainer) {
            secondVoiceContainer.style.display = isChecked ? 'block' : 'none';
        }
        countSprites();
    }

    if (isMultCheckbox) {
        toggleSecondCharFields();
        isMultCheckbox.addEventListener('change', toggleSecondCharFields);
    }
    countSprites();
});
