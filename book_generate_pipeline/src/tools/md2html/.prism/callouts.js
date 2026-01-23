document.addEventListener('DOMContentLoaded', () => {
    const callouts = document.querySelectorAll('.callout');

    callouts.forEach(callout => {
        const title = callout.querySelector('.callout-title');
        if (title) {
            title.addEventListener('click', () => {
                callout.classList.toggle('is-open');
            });
        }
    });
});
