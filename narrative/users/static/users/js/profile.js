const photoInput = document.getElementById("id_photo");
const photoPreview = document.getElementById("photo-preview");

photoInput.addEventListener("change", function() {
    const file = this.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            photoPreview.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }
});