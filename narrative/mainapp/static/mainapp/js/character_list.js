document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("searchInput");
    const charactersGrid = document.getElementById("charactersGrid");
    const characterCards = charactersGrid.querySelectorAll(".character-card");
    const emptyState = charactersGrid.querySelector(".empty-state");

    searchInput.addEventListener("input", function () {
        const filter = this.value.toLowerCase();
        let anyVisible = false;

        characterCards.forEach(card => {
            const name = card.querySelector(".character-info h3").textContent.toLowerCase();
            if (name.includes(filter)) {
                card.style.display = "block";
                anyVisible = true;
            } else {
                card.style.display = "none";
            }
        });

        if (emptyState) {
            emptyState.style.display = anyVisible ? "none" : "block";
        }
    });
});
// Importing a character card: upload, then open the new character's chat
document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("importInput");
    const form = document.getElementById("importForm");
    const message = document.getElementById("importMessage");
    if (!input) return;

    input.addEventListener("change", async function () {
        if (!input.files.length) return;
        message.hidden = false;
        message.className = "import-message";
        message.textContent = "Reading " + input.files[0].name + "…";
        try {
            const response = await fetch(form.action, {method: "POST", body: new FormData(form)});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Import failed.");
            message.textContent = "Imported " + data.name + (data.notes.length ? ". " + data.notes.join(" ") : ".");
            setTimeout(() => { window.location.href = data.url; }, data.notes.length ? 1800 : 400);
        } catch (err) {
            message.className = "import-message error";
            message.textContent = err.message;
        }
        input.value = "";
    });
});
