document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("searchInput");
    const charactersGrid = document.getElementById("charactersGrid");
    const characterCards = charactersGrid.querySelectorAll(".character-card");
    const emptyState = charactersGrid.querySelector(".empty-state");
    const tagFilter = document.getElementById("tagFilter");
    let tag = "";

    // Search by name and filter by tag together
    function apply() {
        const filter = searchInput.value.toLowerCase();
        let anyVisible = false;
        characterCards.forEach(card => {
            const name = card.querySelector(".character-info h3").textContent.toLowerCase();
            const tags = (card.dataset.tags || "").split("|");
            const show = name.includes(filter) && (!tag || tags.includes(tag));
            card.style.display = show ? "block" : "none";
            anyVisible = anyVisible || show;
        });
        if (emptyState) emptyState.style.display = anyVisible ? "none" : "block";
        if (tagFilter) tagFilter.querySelectorAll("[data-tag]").forEach(b => b.classList.toggle("on", b.dataset.tag === tag));
    }
    searchInput.addEventListener("input", apply);
    document.addEventListener("click", e => {
        const chip = e.target.closest("#tagFilter [data-tag], .character-tags [data-tag]");
        if (!chip) return;
        e.preventDefault(); e.stopPropagation();
        tag = chip.dataset.tag === tag && chip.closest(".character-tags") ? "" : chip.dataset.tag;
        apply();
    }, true);
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
