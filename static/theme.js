// theme.js - Handlers for the Theme Switcher

document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('theme-toggle');
    const icon = toggleBtn.querySelector('i');
    
    // 1. Check LocalStorage for saved preference
    const currentTheme = localStorage.getItem('app-theme');
    
    // 2. Apply saved theme on load
    if (currentTheme === 'light') {
        enableLightMode();
    }

    // 3. Listen for clicks
    toggleBtn.addEventListener('click', () => {
        if (document.body.classList.contains('light-mode')) {
            disableLightMode();
        } else {
            enableLightMode();
        }
    });

    function enableLightMode() {
        document.body.classList.add('light-mode');
        localStorage.setItem('app-theme', 'light');
        icon.classList.remove('bi-moon-stars');
        icon.classList.add('bi-sun-fill');
        toggleBtn.classList.remove('btn-outline-light');
        toggleBtn.classList.add('btn-outline-dark');
    }

    function disableLightMode() {
        document.body.classList.remove('light-mode');
        localStorage.setItem('app-theme', 'dark');
        icon.classList.remove('bi-sun-fill');
        icon.classList.add('bi-moon-stars');
        toggleBtn.classList.remove('btn-outline-dark');
        toggleBtn.classList.add('btn-outline-light');
    }
});