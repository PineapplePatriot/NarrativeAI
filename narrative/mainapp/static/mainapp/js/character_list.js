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