/* A show/hide button on every password box (login, register, keys): one tap to check what you typed. */
(function () {
    function add(input) {
        if (input.dataset.eye) return;
        input.dataset.eye = '1';
        const wrap = document.createElement('span');
        wrap.className = 'pw-wrap';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pw-eye';
        btn.setAttribute('aria-label', 'Show password');
        btn.textContent = '👁';
        btn.addEventListener('click', () => {
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.textContent = show ? '🙈' : '👁';
            btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            input.focus();
        });
        wrap.appendChild(btn);
    }
    const run = () => document.querySelectorAll('input[type=password]').forEach(add);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
