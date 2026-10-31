/* The tester feedback form (FEEDBACK_FORM_URL on the server): a 📝 button in the top bar on every page, and a
   small card after they send a chat message (at most once a day), until they press "I've filled it in". */
(function () {
    const CFG = window.NA_FEEDBACK;
    if (!CFG) return;
    const WORDS = {
        en: { title: 'Help us test Narrative AI', text: 'A few questions about how it went: what worked, what got in the way. A couple of minutes.',
              open: 'Open the form ↗', done: "I've filled it in", later: 'Later' },
        uk: { title: 'Допоможіть нам протестувати Narrative AI', text: 'Кілька запитань про ваш досвід: що вдалося, що заважало. Кілька хвилин.',
              open: 'Відкрити форму ↗', done: 'Я вже заповнив(-ла)', later: 'Пізніше' },
    };
    const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* the card may show again */ } } };
    const words = () => WORDS[(window.NATour && NATour.lang && NATour.lang()) || 'en'] || WORDS.en;
    let card = null;

    function close() { if (card) { card.remove(); card = null; } }
    function show() {
        close();
        const w = words();
        card = document.createElement('div');
        card.className = 'na-feedback-card';
        card.setAttribute('role', 'dialog');
        card.innerHTML = `<button type="button" class="na-x" data-act="later" aria-label="${w.later}">✕</button>
            <b>📝 ${w.title}</b><p>${w.text}</p>
            <div class="na-feedback-actions">
              <a class="na-tbtn primary" href="${encodeURI(CFG.url)}" target="_blank" rel="noopener" data-act="open">${w.open}</a>
              <button type="button" class="na-tbtn" data-act="done">${w.done}</button>
              <button type="button" class="na-tbtn link" data-act="later">${w.later}</button>
            </div>`;
        document.body.appendChild(card);
        card.addEventListener('click', async e => {
            const act = e.target.closest('[data-act]')?.dataset.act;
            if (act === 'later') close();
            else if (act === 'done') {
                try {
                    const resp = await fetch(CFG.done, { method: 'POST', headers: { 'X-CSRFToken': CFG.csrf } });
                    if (!resp.ok) throw new Error();
                    close();
                    document.querySelectorAll('.na-feedback-btn').forEach(b => b.remove());
                    window.NA_FEEDBACK = null;
                } catch (err) { /* stays, so they can press it again */ }
            }
        });
    }
    document.addEventListener('click', e => { if (e.target.closest('.na-feedback-btn')) show(); });

    window.NAFeedback = {
        show,
        // After a chat message: the card, once a day at most (the 📝 button is always there)
        afterMessage() {
            if (!window.NA_FEEDBACK) return;
            const today = new Date().toISOString().slice(0, 10);
            if (store.get('na-feedback-shown') === today) return;
            store.set('na-feedback-shown', today);
            setTimeout(show, 1500);
        },
    };
})();
