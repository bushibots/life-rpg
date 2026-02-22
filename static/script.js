/* static/script.js */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Bootstrap Tooltips & Popovers
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // 2. Request Notification Permission
    if (Notification.permission !== "granted" && Notification.permission !== "denied") {
        Notification.requestPermission();
    }

    // 3. Start Reminder Loop
    setInterval(checkReminders, 60000);

    // 4. CHECK AD LOCK STATUS (New!)
    // If unlocked, it will immediately draw the radar chart
    checkAdLock();

    // 5. Restore Zen Mode
    if (localStorage.getItem('zenMode') === 'true') {
        toggleZen();
    }
});

// --- ZEN MODE LOGIC ---
function toggleZen() {
    const hiddenElements = document.querySelectorAll('.zen-hidden');
    const isZen = document.body.classList.toggle('zen-mode');

    hiddenElements.forEach(el => {
        el.style.display = isZen ? 'none' : '';
    });

    localStorage.setItem('zenMode', isZen);
}

// --- REMINDER SYSTEM ---
function requestNotificationPermission() {
    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            new Notification("System Online", { body: "Reminders are active." });
        }
    });
}

function checkReminders() {
    if (Notification.permission !== "granted") return;

    fetch('/get_reminders')
        .then(response => response.json())
        .then(data => {
            if (data.alert) {
                new Notification("Mission Alert", { body: data.message });
            }
        })
        .catch(err => console.log("Reminder check failed", err));
}

// --- AD LOCK SYSTEM (18 HOUR TIMER) ---
function checkAdLock() {
    const unlockTime = localStorage.getItem('pentagonUnlockTime');
    const now = Date.now();
    const overlay = document.getElementById('adOverlay');

    // Only run if we are on the stats page (overlay exists)
    if (!overlay) return;

    // Check if unlocked AND time is still valid
    if (unlockTime && now < parseInt(unlockTime)) {
        // UNLOCKED: Hide overlay immediately
        overlay.style.display = 'none';

        // Execute the function we defined in stats.html to draw the chart
        if (typeof window.renderLockedRadar === 'function') {
            window.renderLockedRadar();
        }
    } else {
        // LOCKED: Overlay stays visible by default. Chart is NOT drawn.
    }
}

function playAd() {
    const btn = document.getElementById('adBtn');
    const loader = document.getElementById('adLoader');
    const text = document.getElementById('adText');
    const overlay = document.getElementById('adOverlay');

    // 1. UI: Hide button, show spinner
    btn.style.display = 'none';
    loader.style.display = 'block';
    text.style.display = 'block';

    // 2. SIMULATE AD (5 Seconds)
    // Replace this setTimeout with your Google AdSense code later
    setTimeout(() => {

        // 3. Ad Finished - Set Expiry (18 Hours)
        const hours18 = 18 * 60 * 60 * 1000;
        const expiryTime = Date.now() + hours18;

        localStorage.setItem('pentagonUnlockTime', expiryTime);

        // 4. Fade out overlay
        overlay.style.transition = "opacity 0.5s ease";
        overlay.style.opacity = "0";

        setTimeout(() => {
            overlay.style.display = 'none';
        }, 500);

        // 5. Draw the Radar Chart
        if (typeof window.renderLockedRadar === 'function') {
            window.renderLockedRadar();
        }

    }, 5000);
}

// --- EDIT MODAL LOGIC ---
function populateEditModal(id, name, difficulty, isDaily) {
    // 1. Fill the hidden ID
    document.getElementById('edit_habit_id').value = id;

    // 2. Fill Name & Difficulty
    document.getElementById('edit_habit_name').value = name;
    document.getElementById('edit_habit_difficulty').value = difficulty;

    // 3. Handle Checkbox (Python sends 'True' or 'False' as text string)
    const dailyBox = document.getElementById('edit_habit_daily');
    if (isDaily === 'True' || isDaily === 'true' || isDaily === true) {
        dailyBox.checked = true;
    } else {
        dailyBox.checked = false;
    }

    // 4. Show the Modal
    new bootstrap.Modal(document.getElementById('editHabitModal')).show();
}

function updateSystemClock() {
        const now = new Date();

        // Time Options (24-hour format like a system log)
        const timeString = now.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        // Date Options
        const dateString = now.toLocaleDateString('en-GB', {
            weekday: 'short',
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });

        document.getElementById('system-clock').innerText = timeString;
        document.getElementById('system-date').innerText = dateString.toUpperCase();
    }

    // Update immediately, then every second
    updateSystemClock();
    setInterval(updateSystemClock, 1000);

function triggerGenie(event) {
    event.preventDefault();

    // 1. Vibrate the phone
    if (navigator.vibrate) {
        navigator.vibrate([200, 100, 300]);
    }

    // 2. Show the overlay and play the video
    const overlay = document.getElementById('genie-overlay');
    const vid = document.getElementById('genie-video');
    const text = document.getElementById('genie-text');

    overlay.classList.remove('d-none');
    document.body.classList.add('screen-shake');
    vid.play();

    // 3. Flash the GENIE text after 1 second of video playing
    setTimeout(() => {
        text.classList.remove('d-none');
    }, 1000);

    // 4. Redirect to /genie just before the video ends (around 3 seconds)
    setTimeout(() => {
        window.location.href = "/genie";
    }, 3200);
}