document.addEventListener("DOMContentLoaded", function () {
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
                };
                reader.readAsDataURL(this.files[0]);
            } else {
                preview.textContent = '📷';
            }
        });
    });
    const isMultCheckbox = document.getElementById('id_is_mult');
    const fileGroups = document.querySelectorAll('.file-group');

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
    }

    if (isMultCheckbox) {
        toggleSecondCharFields();
        isMultCheckbox.addEventListener('change', toggleSecondCharFields);
    }
});