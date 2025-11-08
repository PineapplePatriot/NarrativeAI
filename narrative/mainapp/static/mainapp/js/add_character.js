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
});