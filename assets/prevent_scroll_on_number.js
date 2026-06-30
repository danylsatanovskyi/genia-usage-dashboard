// Prevent scroll wheel from changing number input values
document.addEventListener('wheel', function () {
    if (document.activeElement && document.activeElement.type === 'number') {
        document.activeElement.blur();
    }
}, { passive: true });
