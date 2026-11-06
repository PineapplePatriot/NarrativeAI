/* A round ↓ button that appears when you've scrolled up from the latest messages, and takes you back down.
   NAScrollDown.attach(listElement, {above: elementItShouldSitAbove}). Works whether the list scrolls itself
   (the chat, Bulba on a computer) or the whole page scrolls (Bulba on a phone). */
(function () {
const CSS = `/* ↓ back to the latest message (static/js/scrolldown.js) */
.na-scroll-down { position: fixed; z-index: 40; width: 42px; height: 42px; border-radius: 50%; border: 1px solid rgba(167, 139, 250, .6);
    background: rgba(30, 27, 60, .92); color: #ede9fe; cursor: pointer; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 18px rgba(0, 0, 0, .4); padding: 0; transition: transform .15s; }
.na-scroll-down:hover { transform: translateY(2px); background: #4c1d95; }
.na-scroll-down svg { width: 24px; height: 24px; fill: currentColor; }
.na-scroll-down[hidden] { display: none; }`;

window.NAScrollDown = {
    attach(list, opts = {}) {
        if (!list) return;
        const SHOW_AFTER = 260;  // px from the bottom before the button appears
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'na-scroll-down';
        btn.title = 'Down to the latest';
        btn.setAttribute('aria-label', 'Scroll down to the latest message');
        btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16.5l-6-6 1.4-1.4 4.6 4.6 4.6-4.6L18 10.5z"/></svg>';
        btn.hidden = true;
        if (!document.getElementById('naScrollDownCss')) {  // here, not in a stylesheet: Bulba's panel in a chat has none
            const style = document.createElement('style');
            style.id = 'naScrollDownCss';
            style.textContent = CSS;
            document.head.appendChild(style);
        }
        document.body.appendChild(btn);

        const ownScroll = () => list.scrollHeight > list.clientHeight + 4 && getComputedStyle(list).overflowY !== 'visible';
        const scroller = () => (ownScroll() ? list : document.scrollingElement);
        const fromBottom = () => { const s = scroller(); return s.scrollHeight - s.scrollTop - s.clientHeight; };

        function place() {
            const show = fromBottom() > SHOW_AFTER;
            btn.hidden = !show;
            if (!show) return;
            const box = list.getBoundingClientRect();
            const limit = opts.above ? opts.above.getBoundingClientRect().top : window.innerHeight;
            const bottom = Math.min(box.bottom, limit, window.innerHeight);
            btn.style.left = `${Math.max(8, Math.min(box.right, window.innerWidth) - 56)}px`;
            btn.style.top = `${Math.max(8, bottom - 56)}px`;
        }
        btn.addEventListener('click', () => {
            const s = scroller();
            (s === document.scrollingElement ? window : s).scrollTo({ top: s.scrollHeight, behavior: 'smooth' });
        });
        let queued = false;
        const later = () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; place(); }); } };
        list.addEventListener('scroll', later, { passive: true });
        window.addEventListener('scroll', later, { passive: true });
        window.addEventListener('resize', later);
        new MutationObserver(later).observe(list, { childList: true, subtree: true });  // new messages
        place();
    },
};
})();
