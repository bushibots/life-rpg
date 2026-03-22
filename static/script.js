document.addEventListener('DOMContentLoaded', () => {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].forEach(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    if ('Notification' in window && Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
    }

    setInterval(checkReminders, 60000);
    checkAdLock();

    if (localStorage.getItem('zenMode') === 'true') {
        toggleZen();
    }

    initRevealAnimations();
    initCommandPalette();
    initAmbientTilt();
    updateSystemClock();
    setInterval(updateSystemClock, 1000);
});

function initRevealAnimations() {
    const elements = document.querySelectorAll('.reveal-up, .card, .goal-card, .analytics-panel, .analytics-kpi, .quick-insight, .task-item');
    if (!('IntersectionObserver' in window)) {
        elements.forEach(el => el.classList.add('is-visible'));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.14 });

    elements.forEach((el, index) => {
        if (!el.classList.contains('reveal-up')) {
            el.classList.add('reveal-up');
            el.style.transitionDelay = `${Math.min(index * 35, 280)}ms`;
        }
        observer.observe(el);
    });
}

function initAmbientTilt() {
    const hero = document.querySelector('.page-hero');
    if (!hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    hero.addEventListener('mousemove', (event) => {
        const rect = hero.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;
        hero.style.transform = `perspective(1400px) rotateX(${(0.5 - y) * 3}deg) rotateY(${(x - 0.5) * 4}deg)`;
    });

    hero.addEventListener('mouseleave', () => {
        hero.style.transform = 'perspective(1400px) rotateX(0deg) rotateY(0deg)';
    });
}

function initCommandPalette() {
    const palette = document.getElementById('command-palette');
    const openBtn = document.getElementById('open-command-palette');
    const input = document.getElementById('command-search');
    const items = [...document.querySelectorAll('.palette-item')];
    if (!palette || !input) return;

    const setActive = (target) => {
        items.forEach(item => item.classList.toggle('active', item === target));
    };

    const visibleItems = () => items.filter(item => item.style.display !== 'none');

    const filterItems = () => {
        const term = input.value.trim().toLowerCase();
        let firstVisible = null;
        items.forEach(item => {
            const haystack = `${item.textContent} ${item.dataset.commandSearch || ''}`.toLowerCase();
            const match = haystack.includes(term);
            item.style.display = match ? '' : 'none';
            if (match && !firstVisible) firstVisible = item;
        });
        setActive(firstVisible);
    };

    const openPalette = () => {
        palette.classList.add('active');
        palette.setAttribute('aria-hidden', 'false');
        input.value = '';
        filterItems();
        setTimeout(() => input.focus(), 20);
    };

    const closePalette = () => {
        palette.classList.remove('active');
        palette.setAttribute('aria-hidden', 'true');
    };

    if (openBtn) {
        openBtn.addEventListener('click', openPalette);
    }
    palette.addEventListener('click', (event) => {
        if (event.target === palette) closePalette();
    });
    input.addEventListener('input', filterItems);

    document.addEventListener('keydown', (event) => {
        if (!palette.classList.contains('active')) return;
        if (event.key === 'Escape') {
            closePalette();
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const visible = visibleItems();
            if (!visible.length) return;
            const current = visible.findIndex(item => item.classList.contains('active'));
            const delta = event.key === 'ArrowDown' ? 1 : -1;
            const next = visible[(current + delta + visible.length) % visible.length] || visible[0];
            setActive(next);
            next.scrollIntoView({ block: 'nearest' });
        } else if (event.key === 'Enter') {
            const active = visibleItems().find(item => item.classList.contains('active'));
            if (active) active.click();
        }
    });

    items.forEach(item => item.addEventListener('mouseenter', () => setActive(item)));
}

function toggleZen() {
    const hiddenElements = document.querySelectorAll('.zen-hidden');
    const isZen = document.body.classList.toggle('zen-mode');
    hiddenElements.forEach(el => {
        el.style.display = isZen ? 'none' : '';
    });
    localStorage.setItem('zenMode', isZen);
}

function requestNotificationPermission() {
    if (!('Notification' in window)) return;
    Notification.requestPermission().then(permission => {
        if (permission === 'granted') {
            new Notification('System Online', { body: 'Reminders are active.' });
        }
    });
}

function checkReminders() {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    fetch('/get_reminders')
        .then(response => response.json())
        .then(data => {
            if (data.alert) {
                new Notification('Mission Alert', { body: data.message });
            }
        })
        .catch(err => console.log('Reminder check failed', err));
}

function checkAdLock() {
    const unlockTime = localStorage.getItem('pentagonUnlockTime');
    const now = Date.now();
    const overlay = document.getElementById('adOverlay');
    if (!overlay) return;
    if (unlockTime && now < parseInt(unlockTime, 10)) {
        overlay.style.display = 'none';
        if (typeof window.renderLockedRadar === 'function') {
            window.renderLockedRadar();
        }
    }
}

function playAd() {
    const btn = document.getElementById('adBtn');
    const loader = document.getElementById('adLoader');
    const text = document.getElementById('adText');
    const overlay = document.getElementById('adOverlay');
    btn.style.display = 'none';
    loader.style.display = 'block';
    text.style.display = 'block';
    setTimeout(() => {
        const expiryTime = Date.now() + (18 * 60 * 60 * 1000);
        localStorage.setItem('pentagonUnlockTime', expiryTime);
        overlay.style.transition = 'opacity 0.5s ease';
        overlay.style.opacity = '0';
        setTimeout(() => { overlay.style.display = 'none'; }, 500);
        if (typeof window.renderLockedRadar === 'function') {
            window.renderLockedRadar();
        }
    }, 5000);
}

function populateEditModal(id, name, difficulty, isDaily) {
    document.getElementById('edit_habit_id').value = id;
    document.getElementById('edit_habit_name').value = name;
    document.getElementById('edit_habit_difficulty').value = difficulty;
    const dailyBox = document.getElementById('edit_habit_daily');
    dailyBox.checked = isDaily === 'True' || isDaily === 'true' || isDaily === true;
    new bootstrap.Modal(document.getElementById('editHabitModal')).show();
}

function updateSystemClock() {
    const clock = document.getElementById('system-clock');
    const date = document.getElementById('system-date');
    if (!clock || !date) return;
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const dateString = now.toLocaleDateString('en-GB', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    });
    clock.innerText = timeString;
    date.innerText = dateString.toUpperCase();
}

function triggerGenie(event) {
    event.preventDefault();
    if (navigator.vibrate) {
        navigator.vibrate([100, 50, 100, 50, 400]);
    }
    const overlay = document.getElementById('genie-overlay');
    if (overlay) {
        overlay.classList.remove('d-none');
    }
    document.body.classList.add('screen-shake');
    setTimeout(() => {
        window.location.href = '/genie';
    }, 2800);
}
