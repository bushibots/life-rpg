// effects.js - The "Juice" Engine

// 1. The "Spark" Effect (High-Tech/Mechanical feel)
function triggerSparks(x, y) {
    var count = 200;
    
    // Convert click coordinates to canvas percentage
    // (Required by the library)
    const xPercent = x / window.innerWidth;
    const yPercent = y / window.innerHeight;

    confetti({
        particleCount: 50,
        spread: 60,
        origin: { x: xPercent, y: yPercent },
        colors: ['#0dcaf0', '#ffffff', '#ffd700'], // Cyan, White, Gold
        disableForReducedMotion: true,
        gravity: 2.5, // High gravity = feels heavy/precise like sparks
        scalar: 0.7,  // Small particles
        drift: 0,
        ticks: 80,    // Disappear quickly
        shapes: ['square'] // Square sparks look more digital
    });
}

// 2. The Floating Text (Heads-up Display style)
function showFloatingText(x, y, text) {
    const el = document.createElement('div');
    el.innerText = text;
    
    // Cyberpunk/HUD Styling
    el.style.position = 'fixed';
    el.style.left = (x + 15) + 'px'; // Slightly to the right of cursor
    el.style.top = (y - 20) + 'px';
    el.style.color = '#0dcaf0'; // Cyan
    el.style.fontFamily = "'Orbitron', sans-serif";
    el.style.fontSize = '12px';
    el.style.fontWeight = 'bold';
    el.style.letterSpacing = '1px';
    el.style.pointerEvents = 'none'; // Click through it
    el.style.zIndex = '9999';
    el.style.textShadow = '0 0 5px rgba(13, 202, 240, 0.5)'; // Neon glow
    el.style.transition = 'all 0.8s ease-out';
    
    document.body.appendChild(el);

    // Animation: Float up and vanish
    requestAnimationFrame(() => {
        el.style.transform = 'translateY(-40px)';
        el.style.opacity = '0';
    });

    // Cleanup memory
    setTimeout(() => {
        el.remove();
    }, 800);
}

// 3. Auto-Attach to Checkboxes
document.addEventListener('DOMContentLoaded', function() {
    // Find all un-checked boxes
    const checkboxLinks = document.querySelectorAll('a[href*="toggle_habit"]');
    
    checkboxLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            // Check if it's currently an empty square (meaning we are completing it)
            const icon = link.querySelector('i');
            if (icon && icon.classList.contains('bi-square')) {
                // Trigger effects at cursor position
                triggerSparks(e.clientX, e.clientY);
                showFloatingText(e.clientX, e.clientY, "PROTOCOL EXECUTED");
            }
        });
    });
});