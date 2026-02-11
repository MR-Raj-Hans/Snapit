document.addEventListener('DOMContentLoaded', () => {

    const clearAllBtn = document.getElementById('clearAllBtn');
    const historyList = document.querySelector('.history-list');
    const totalSearchesEl = document.getElementById('totalSearches');
    const totalSavedEl = document.getElementById('totalSaved');
    const bestDealsEl = document.getElementById('bestDeals');

    const loadHistory = () => {
        try {
            return JSON.parse(localStorage.getItem('snapit_history') || '[]');
        } catch (e) {
            return [];
        }
    };

    const loadSaved = () => {
        try {
            return JSON.parse(localStorage.getItem('snapit_saved') || '[]');
        } catch (e) {
            return [];
        }
    };

    const updateSavedTab = () => {
        const tabs = Array.from(document.querySelectorAll('.tab'));
        const savedTab = tabs.find((t) => t.textContent.trim().toLowerCase().startsWith('saved items'));
        if (!savedTab) return;
        const count = loadSaved().length;
        savedTab.textContent = `Saved Items (${count})`;
    };

    const saveHistory = (entries) => {
        localStorage.setItem('snapit_history', JSON.stringify(entries));
    };

    const formatTime = (iso) => {
        if (!iso) return 'You viewed';
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return 'You viewed';
        return `You viewed • ${d.toLocaleString()}`;
    };

    const renderHistory = () => {
        if (!historyList) return;
        historyList.innerHTML = '';

        const entries = loadHistory();
        if (!entries.length) {
            const msg = document.createElement('div');
            msg.className = 'no-history-msg';
            msg.textContent = 'No search history found.';
            historyList.appendChild(msg);
            updateStats();
            return;
        }

        const header = document.createElement('div');
        header.className = 'date-header';
        header.textContent = 'Recent';
        historyList.appendChild(header);

        entries.forEach((entry) => {
            const card = document.createElement('div');
            card.className = 'history-card';
            card.dataset.key = `${entry.term}::${entry.name}`.toLowerCase();
            card.innerHTML = `
                <div class="delete-btn">×</div>
                <div class="product-icon">🛒</div>
                <div class="history-card-content">
                    <h3>${entry.name || 'Unknown'}</h3>
                    <div class="date">${formatTime(entry.viewed_at)}</div>
                </div>
                <div class="price-info">
                    <span class="price">${entry.price || '—'}</span>
                    <span class="saved">${entry.saved || 'Saved ₹0'}</span>
                </div>
            `;
            historyList.appendChild(card);
        });

        updateStats();
        updateSavedTab();
    };

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

    // Initial render
    renderHistory();
    updateSavedTab();
    if (clearAllBtn && historyList) {
        clearAllBtn.addEventListener('click', () => {
            saveHistory([]);
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
                updateSavedTab();
            }, cards.length * 50 + 300);
        });
    }

    // --- INDIVIDUAL DELETE FUNCTIONALITY ---
    if (historyList) {
        historyList.addEventListener('click', (e) => {
            if (e.target.closest('.delete-btn')) {
                const card = e.target.closest('.history-card');
                if (card) {
                    const key = card.dataset.key;
                    const entries = loadHistory().filter(
                        (it) => `${it.term}::${it.name}`.toLowerCase() !== key
                    );
                    saveHistory(entries);

                    // Add animation class
                    card.classList.add('removing');

                    // Remove from DOM after animation finishes
                    card.addEventListener('animationend', () => {
                        card.remove();
                        if (!document.querySelector('.history-card')) {
                            const msg = document.createElement('div');
                            msg.className = 'no-history-msg';
                            msg.textContent = 'No search history found.';
                            historyList.appendChild(msg);
                        }
                        updateStats(); // Update count immediately
                    });
                }
            }
        });
    }

});
