/* The app's own pop-ups instead of the browser's grey ones (alert / confirm / prompt):
   NADialog.alert(text, {title})                       -> Promise<void>
   NADialog.confirm(text, {title, ok, cancel, danger}) -> Promise<boolean>
   NADialog.prompt(text, value, {title, ok, multiline}) -> Promise<string|null>
   window.alert is replaced too (nothing waits on an alert), so old calls look the same as new ones. */
(function () {
    if (window.NADialog) return;
    const css = `
.na-dlg-back { position: fixed; inset: 0; z-index: 10000; background: rgba(5, 7, 15, .62); display: flex;
    align-items: center; justify-content: center; padding: 16px; animation: naDlgIn .12s ease-out; }
.na-dlg { width: min(440px, 100%); background: var(--ui-secondary, #1e2130); color: var(--text-primary, #f1f5f9);
    border: 1px solid var(--border-color, rgba(255,255,255,.12)); border-radius: 16px; padding: 18px 18px 14px;
    box-shadow: 0 20px 50px rgba(0,0,0,.5); font: inherit; max-height: calc(100vh - 32px); overflow: auto; }
.na-dlg h3 { margin: 0 0 6px; font-size: 1.05rem; }
.na-dlg p { margin: 0 0 12px; line-height: 1.5; white-space: pre-line; color: var(--text-secondary, #cbd5e1); }
.na-dlg input, .na-dlg textarea { width: 100%; box-sizing: border-box; margin: 0 0 12px; padding: 9px 12px;
    border-radius: 10px; border: 1px solid var(--border-color, rgba(255,255,255,.15));
    background: var(--ui-tertiary, #0f172a); color: inherit; font: inherit; }
.na-dlg-btns { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.na-dlg-btns button { padding: 8px 16px; border-radius: 10px; border: 1px solid var(--border-color, rgba(255,255,255,.15));
    background: transparent; color: inherit; font: inherit; cursor: pointer; }
.na-dlg-btns .ok { background: #7c3aed; border-color: #8b5cf6; color: #fff; font-weight: 600; }
.na-dlg-btns .ok.danger { background: #dc2626; border-color: #ef4444; }
@keyframes naDlgIn { from { opacity: 0; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .na-dlg-back { animation: none; } }`;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));

    function open({ title = '', text = '', input = null, multiline = false, ok = 'OK', cancel = 'Cancel', danger = false }) {
        return new Promise(resolve => {
            const back = document.createElement('div');
            back.className = 'na-dlg-back';
            const field = input === null ? '' : multiline
                ? `<textarea rows="4">${esc(input)}</textarea>` : `<input type="text" value="${esc(input)}">`;
            back.innerHTML = `<div class="na-dlg" role="dialog" aria-modal="true">
                ${title ? `<h3>${esc(title)}</h3>` : ''}${text ? `<p>${esc(text)}</p>` : ''}${field}
                <div class="na-dlg-btns">${cancel ? `<button type="button" class="cancel">${esc(cancel)}</button>` : ''}
                    <button type="button" class="ok${danger ? ' danger' : ''}">${esc(ok)}</button></div></div>`;
            const before = document.activeElement;
            const box = back.querySelector('input, textarea');
            const done = (value) => {
                back.remove();
                document.removeEventListener('keydown', keys, true);
                try { before && before.focus && before.focus(); } catch (e) { /* the old focus is gone */ }
                resolve(value);
            };
            const yes = () => done(input === null ? true : box.value);
            const no = () => done(input === null ? (cancel ? false : undefined) : null);
            const keys = (e) => {
                if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); no(); }
                else if (e.key === 'Enter' && !(e.target.tagName === 'TEXTAREA' && !e.ctrlKey)) { e.preventDefault(); yes(); }
            };
            back.querySelector('.ok').onclick = yes;
            const c = back.querySelector('.cancel');
            if (c) c.onclick = no;
            back.addEventListener('mousedown', (e) => { if (e.target === back && cancel) no(); });
            document.addEventListener('keydown', keys, true);
            document.body.appendChild(back);
            (box || back.querySelector('.ok')).focus();
            if (box && box.select) box.select();
        });
    }

    window.NADialog = {
        alert: (text, o = {}) => open({ text, title: o.title || '', ok: o.ok || 'OK', cancel: '' }).then(() => undefined),
        confirm: (text, o = {}) => open({ text, title: o.title || '', ok: o.ok || 'OK', cancel: o.cancel || 'Cancel',
                                          danger: !!o.danger }),
        prompt: (text, value = '', o = {}) => open({ text, title: o.title || '', input: String(value ?? ''),
                                                     multiline: !!o.multiline, ok: o.ok || 'OK', cancel: o.cancel || 'Cancel' }),
    };
    window.alert = (text) => { NADialog.alert(text); };
})();
