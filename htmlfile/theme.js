document.addEventListener('DOMContentLoaded', () => {
    // 1. Check storage
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.body.setAttribute('data-theme', savedTheme);

    const themeBtn = document.getElementById('themeBtn');
    if (themeBtn) {
        updateIcon(themeBtn, savedTheme);

        themeBtn.addEventListener('click', () => {
            const current = document.body.getAttribute('data-theme');
            const newTheme = current === 'light' ? 'dark' : 'light';

            document.body.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateIcon(themeBtn, newTheme);
        });
    }
});

function updateIcon(btn, theme) {
    btn.textContent = theme === 'light' ? '☀️' : '🌙';
}
