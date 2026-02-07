document.addEventListener('DOMContentLoaded', () => {

    const clearAllBtn = document.getElementById('clearAllBtn');
    const historyList = document.querySelector('.history-list');
    const totalSearchesEl = document.getElementById('totalSearches');
    const totalSavedEl = document.getElementById('totalSaved');
    const bestDealsEl = document.getElementById('bestDeals');

    // Function to calculate and update all stats
    function updateStats() {
        const cards = document.querySelectorAll('.history-card');

        // 1. Update Searches Count
        if (totalSearchesEl) {
            totalSearchesEl.textContent = cards.length;
        }

        // 2. Calculate Total Saved & Best Deals
        let totalSaved = 0;
        let dealsCount = 0;

        cards.forEach(card => {
            // Find the "Saved ₹XX" text
            const savedText = card.querySelector('.saved');
            if (savedText) {
                // Extract number: "Saved ₹14" -> 14
                const match = savedText.textContent.match(/₹(\d+)/);
                if (match && match[1]) {
                    const amount = parseInt(match[1]);
                    totalSaved += amount;
                    if (amount > 0) dealsCount++;
                }
            }
        });

        // Update DOM
        if (totalSavedEl) totalSavedEl.textContent = '₹' + totalSaved.toLocaleString();
        if (bestDealsEl) bestDealsEl.textContent = dealsCount;
    }

    // Initial count update
    updateStats();
    if (clearAllBtn && historyList) {
        clearAllBtn.addEventListener('click', () => {
            const cards = document.querySelectorAll('.history-card');

            // Staggered exit animation
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.classList.add('removing');
                    card.addEventListener('animationend', () => {
                        card.remove();
                        // Update count after last card is removed
                        if (index === cards.length - 1) {
                            updateStats();
                        }
                    });
                }, index * 50); // 50ms delay between each
            });

            setTimeout(() => {
                const headers = document.querySelectorAll('.date-header');
                headers.forEach(header => header.style.display = 'none');

                // Show "No history" message
                if (!document.querySelector('.no-history-msg')) {
                    const msg = document.createElement('div');
                    msg.className = 'no-history-msg';
                    msg.textContent = 'No search history found.';
                    historyList.appendChild(msg);
                }
                updateStats();
            }, cards.length * 50 + 300);
        });
    }

    // --- INDIVIDUAL DELETE FUNCTIONALITY ---
    if (historyList) {
        historyList.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) {
                const card = e.target.closest('.history-card');
                if (card) {
                    // Add animation class
                    card.classList.add('removing');

                    // Remove from DOM after animation finishes
                    card.addEventListener('animationend', () => {
                        card.remove();
                        updateStats(); // Update count immediately
                    });
                }
            }
        });
    }

});
