document.addEventListener('DOMContentLoaded', () => {
    if (typeof particlesJS !== 'undefined') {
        particlesJS('particles-js', {
            particles: {
                number: { value: 60 },
                color: { value: "#00ccff" },
                shape: { type: "circle" },
                opacity: { value: 0.5, random: true },
                size: { value: 3, random: true },
                line_linked: { enable: true, distance: 150, color: "#0ff", opacity: 0.2 },
                move: { enable: true, speed: 2 }
            }
        });
    }

    const clickLinks = document.querySelectorAll('.track-click');
    clickLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const itemId = link.dataset.id;
            fetch(`/click/${itemId}`, { method: 'GET' });
        });
    });
});