/* The guided tours (the screen darkens and one thing at a time is lit, with a note beside it) and "What's this?"
   (click anything and Bulba explains it). Texts and steps live in help_text.js; the top bar loads both on every
   signed-in page and sets NA_HELP_CFG. A page with its own tour sets window.NA_PAGE_TOUR = {name, auto}. */
(function () {
    const HELP = window.NA_HELP;
    const CFG = window.NA_HELP_CFG || {};
    if (!HELP) return;

    const store = {
        get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window: the tour just shows again */ } },
    };
    let lang = store.get('na-lang') || ((navigator.language || '').toLowerCase().startsWith('uk') ? 'uk' : 'en');
    const t = key => (HELP.ui[lang] || HELP.ui.en)[key];
    const words = item => item[lang] || item.en;
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const make = (tag, cls, html) => { const n = document.createElement(tag); n.className = cls; if (html) n.innerHTML = html; return n; };

    function setLang(next) {
        lang = next;
        store.set('na-lang', next);
        document.dispatchEvent(new CustomEvent('na-lang', { detail: next }));
    }
    const langSwitch = () => `<span class="na-lang" role="group" aria-label="${esc(t('lang'))}">
        <button type="button" data-lang="en" class="${lang === 'en' ? 'on' : ''}">EN</button>
        <button type="button" data-lang="uk" class="${lang === 'uk' ? 'on' : ''}">УКР</button></span>`;

    function visible(node) {
        if (!node) return false;
        const r = node.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(node).visibility !== 'hidden';
    }

    // On small screens the top bar's links hide behind ☰: a step about one opens that menu while it's shown
    const topbar = () => document.querySelector('.na-topbar');
    function closeLinks() {
        const bar = topbar();
        if (bar && bar.classList.contains('na-tour-opened')) bar.classList.remove('open', 'na-tour-opened');
    }
    function find(item) {
        if (!item || item.center) return null;
        for (const sel of [].concat(item.sel || [])) {
            const all = [...document.querySelectorAll(sel)];
            for (const node of item.last ? all.reverse() : all) {
                const bar = node.closest('.na-links') && topbar();
                if (bar && !visible(node) && !bar.classList.contains('open')) bar.classList.add('open', 'na-tour-opened');
                if (visible(node)) return node;
            }
        }
        return null;
    }

    // Where a box goes beside the thing it's about: below if it fits, else above, else over its bottom edge
    function placeBeside(box, rect) {
        const gap = 14, edge = 12, w = box.offsetWidth, h = box.offsetHeight;
        if (!rect) {
            box.style.left = Math.max(edge, (innerWidth - w) / 2) + 'px';
            box.style.top = Math.max(edge, (innerHeight - h) / 2) + 'px';
            return;
        }
        let top = rect.bottom + gap;
        if (top + h > innerHeight - edge) top = rect.top - gap - h;
        if (top < edge) top = Math.max(edge, innerHeight - h - edge);
        const left = Math.min(Math.max(edge, rect.left + rect.width / 2 - w / 2), innerWidth - w - edge);
        box.style.top = top + 'px';
        box.style.left = Math.max(edge, left) + 'px';
    }

    // ---------------------------------------------------------------- Tours
    let tour = null;  // {name, steps, i, target, shade, spot, box}

    function start(name) {
        const keys = (HELP.tours[name] || []).filter(k => HELP.items[k] && (HELP.items[k].center || find(HELP.items[k])));
        closeLinks();
        if (!keys.length) return;
        end();
        closeMenu();
        stopPick();
        closeBubble();
        tour = { name, steps: keys, i: 0, target: null };
        tour.shade = make('div', 'na-tour-shade');
        tour.spot = make('div', 'na-tour-spot');
        tour.box = make('div', 'na-tour-box');
        tour.box.setAttribute('role', 'dialog');
        tour.box.setAttribute('aria-modal', 'true');
        document.body.append(tour.shade, tour.spot, tour.box);
        tour.box.addEventListener('click', onBoxClick);
        addEventListener('resize', place);
        addEventListener('scroll', place, true);
        document.addEventListener('keydown', onKey, true);
        show(0);
    }

    function show(i) {
        if (!tour) return;
        if (i < 0) i = 0;
        if (i >= tour.steps.length) return end();
        closeLinks();
        tour.i = i;
        const item = HELP.items[tour.steps[i]];
        tour.target = find(item);
        if (tour.target) bringIntoView(tour.target);
        const [title, text] = words(item);
        const last = i === tour.steps.length - 1;
        const body = item.routes ? routesHtml() : `<p>${text}</p>`;
        tour.box.classList.toggle('wide', !!item.routes);
        tour.box.innerHTML = `
            <div class="na-tour-top"><span class="na-tour-count">${i + 1} ${esc(t('of'))} ${tour.steps.length}</span>
              ${langSwitch()}<button type="button" class="na-x" data-act="end" aria-label="${esc(t('close'))}">✕</button></div>
            <h3>${esc(title)}</h3>${body}
            <div class="na-tour-nav">
              ${last ? '' : `<button type="button" class="na-tbtn link" data-act="end">${esc(t('skip'))}</button>`}
              ${i > 0 ? `<button type="button" class="na-tbtn" data-act="back">${esc(t('back'))}</button>` : ''}
              ${item.routes ? `<button type="button" class="na-tbtn" data-act="end">${esc(t('myself'))}</button>`
                            : `<button type="button" class="na-tbtn primary" data-act="next">${esc(t(last ? 'done' : 'next'))}</button>`}
            </div>`;
        tour.box.setAttribute('aria-label', title);
        place();
        (tour.box.querySelector('[data-act="next"]') || tour.box.querySelector('.na-route'))?.focus({ preventScroll: true });
    }

    // Into view below the sticky top bar: centred when it fits, else its top edge, so tall sections read from the top
    function bringIntoView(node) {
        const r = node.getBoundingClientRect(), bar = 60;
        if (r.top >= bar && r.bottom <= innerHeight - 8) return;
        const fits = r.height < innerHeight - bar - 180;
        node.scrollIntoView({ block: fits ? 'center' : 'start', inline: 'nearest' });
        const top = node.getBoundingClientRect().top;
        if (top < bar) scrollBy(0, top - bar - 12);
    }

    function routesHtml() {
        const url = route => esc((CFG.bulba || '/main/bulba/') + '?route=' + route);
        return `<div class="na-routes">
            <a class="na-route" href="${url('full')}"><b>${esc(t('full'))}</b><small>${esc(t('fullTime'))}</small><span>${esc(t('fullText'))}</span></a>
            <a class="na-route" href="${url('fast')}"><b>${esc(t('fast'))}</b><small>${esc(t('fastTime'))}</small><span>${esc(t('fastText'))}</span></a>
          </div><p class="na-tour-note">${esc(t('routesNote'))}</p>`;
    }

    function place() {
        if (!tour) return;
        const pad = 6, spot = tour.spot.style;
        if (tour.target && visible(tour.target)) {
            const r = tour.target.getBoundingClientRect();
            const top = Math.max(2, r.top - pad), left = Math.max(2, r.left - pad);
            const bottom = Math.min(innerHeight - 2, r.bottom + pad), right = Math.min(innerWidth - 2, r.right + pad);
            tour.spot.classList.remove('center');
            Object.assign(spot, { top: top + 'px', left: left + 'px', width: Math.max(0, right - left) + 'px', height: Math.max(0, bottom - top) + 'px' });
            placeBeside(tour.box, { top, left, bottom, right, width: right - left, height: bottom - top });
        } else {
            tour.spot.classList.add('center');
            Object.assign(spot, { top: '50%', left: '50%', width: '0px', height: '0px' });
            placeBeside(tour.box, null);
        }
    }

    function onBoxClick(e) {
        const lng = e.target.closest('[data-lang]');
        if (lng) { setLang(lng.dataset.lang); show(tour.i); return; }
        const act = e.target.closest('[data-act]')?.dataset.act;
        if (act === 'next') show(tour.i + 1);
        else if (act === 'back') show(tour.i - 1);
        else if (act === 'end') end();
        else if (e.target.closest('.na-route')) end();  // the link itself goes on to Bulba
    }

    function onKey(e) {
        if (!tour) return;
        if (e.key === 'Escape') { e.preventDefault(); end(); }
        else if (e.key === 'ArrowRight' && !HELP.items[tour.steps[tour.i]].routes) { e.preventDefault(); show(tour.i + 1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); show(tour.i - 1); }
    }

    function end() {
        if (!tour) return;
        store.set('na-tour-' + tour.name, 'seen');
        tour.shade.remove(); tour.spot.remove(); tour.box.remove();
        removeEventListener('resize', place);
        removeEventListener('scroll', place, true);
        document.removeEventListener('keydown', onKey, true);
        tour = null;
        closeLinks();
    }

    // ---------------------------------------------------------------- The ? menu in the top bar
    let menu = null;
    function pageTour() { const p = window.NA_PAGE_TOUR; return p && (typeof p === 'string' ? p : p.name); }

    function openMenu(btn) {
        closeMenu();
        menu = make('div', 'na-help-menu');
        menu.setAttribute('role', 'menu');
        const own = pageTour();
        menu.innerHTML = `
            ${own && own !== 'app' ? `<button type="button" class="item" data-do="page">▶ ${esc(t('menuPage'))}</button>` : ''}
            <button type="button" class="item" data-do="app">▶ ${esc(t('menuApp'))}</button>
            <button type="button" class="item" data-do="pick">🔍 ${esc(t('menuPick'))}</button>
            <button type="button" class="item" data-do="reset">↺ ${esc(t('menuReset'))}</button>
            <div class="lang-row"><span>${esc(t('lang'))}</span>${langSwitch()}</div>`;
        document.body.append(menu);
        const r = btn.getBoundingClientRect();
        menu.style.top = (r.bottom + 8) + 'px';
        menu.style.left = Math.max(8, Math.min(r.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8)) + 'px';
        btn.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
        menu.addEventListener('click', e => {
            const lng = e.target.closest('[data-lang]');
            if (lng) { e.stopPropagation(); setLang(lng.dataset.lang); openMenu(btn); return; }  // the old menu is gone: not an outside click
            const what = e.target.closest('[data-do]')?.dataset.do;
            if (what === 'page') start(own);
            else if (what === 'app') start('app');
            else if (what === 'pick') pick();
            else if (what === 'reset') { resetTours(); start(own || 'app'); }
        });
    }
    function closeMenu() {
        if (!menu) return;
        menu.remove();
        menu = null;
        document.querySelectorAll('.na-help-btn').forEach(b => { b.classList.remove('open'); b.setAttribute('aria-expanded', 'false'); });
    }
    document.addEventListener('click', e => {
        const btn = e.target.closest('.na-help-btn');
        if (btn) { e.preventDefault(); if (menu) closeMenu(); else openMenu(btn); return; }
        if (menu && !menu.contains(e.target)) closeMenu();
    });

    // ---------------------------------------------------------------- What's this?
    let picking = false, hl = null, banner = null, bubble = null;
    const known = Object.entries(HELP.items).filter(([, item]) => item.sel && !item.center);

    function keyOf(node) {
        for (const [key, item] of known) {
            if ([].concat(item.sel).some(sel => { try { return node.matches(sel); } catch (e) { return false; } })) return key;
        }
        return null;
    }
    // What a click means: the nearest thing with its own help, else the nearest control or labelled block
    function resolve(node) {
        for (let n = node; n && n !== document.body; n = n.parentElement) {
            const key = keyOf(n);
            if (key) return { node: n, key };
        }
        const near = node.closest('button, a, input, select, textarea, label, summary, [title], h1, h2, h3, h4, '
                                  + '.message, .card, section, aside, form, li');
        return { node: near || node, key: null };
    }
    function outline(node) {
        if (!hl) { hl = make('div', 'na-pick-hl'); document.body.append(hl); }
        const r = node.getBoundingClientRect();
        Object.assign(hl.style, { top: (r.top - 3) + 'px', left: (r.left - 3) + 'px', width: (r.width + 6) + 'px', height: (r.height + 6) + 'px' });
    }

    function pick() {
        closeMenu();
        closeBubble();
        if (picking) return;
        picking = true;
        document.body.classList.add('na-picking');
        banner = make('div', 'na-pick-banner', `<span>🔍 ${esc(t('pickBanner'))}</span><button type="button">${esc(t('pickStop'))}</button>`);
        document.body.append(banner);
        document.addEventListener('mouseover', onHover, true);
        document.addEventListener('click', onPick, true);
        document.addEventListener('keydown', onPickKey, true);
    }
    function stopPick() {
        if (!picking) return;
        picking = false;
        document.body.classList.remove('na-picking');
        banner?.remove(); banner = null;
        document.removeEventListener('mouseover', onHover, true);
        document.removeEventListener('click', onPick, true);
        document.removeEventListener('keydown', onPickKey, true);
        if (!bubble) { hl?.remove(); hl = null; }
    }
    function onHover(e) {
        if (banner?.contains(e.target)) return;
        outline(resolve(e.target).node);
    }
    function onPickKey(e) { if (e.key === 'Escape') { e.preventDefault(); stopPick(); } }
    function onPick(e) {
        if (banner?.contains(e.target)) { e.preventDefault(); e.stopPropagation(); stopPick(); return; }
        e.preventDefault();
        e.stopPropagation();
        const { node, key } = resolve(e.target);
        stopPick();
        explain(node, key);
    }

    function labelOf(node) {
        const text = node.getAttribute('aria-label') || node.getAttribute('title') || node.getAttribute('placeholder')
            || (node.innerText || node.value || '').trim();
        return text.replace(/\s+/g, ' ').slice(0, 300);
    }
    function headingOf(node) {
        for (let n = node.parentElement; n && n !== document.body; n = n.parentElement) {
            const h = n.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > .step-body > h2, :scope > summary');
            if (h && !h.contains(node)) return h.innerText.trim().slice(0, 160);
        }
        return (document.querySelector('h1')?.innerText || '').trim().slice(0, 160);
    }

    function explain(node, key) {
        closeBubble();
        const item = key && HELP.items[key];
        const [title, text] = item ? words(item) : [labelOf(node).slice(0, 60) || t('thisThing'), ''];
        bubble = make('div', 'na-bubble');
        bubble.setAttribute('role', 'dialog');
        bubble.innerHTML = `
            <div class="na-tour-top"><span class="na-tour-count">🔍</span>${langSwitch()}
              <button type="button" class="na-x" data-act="close" aria-label="${esc(t('close'))}">✕</button></div>
            <h3>${esc(title)}</h3>${text ? `<p>${text}</p>` : ''}
            <div class="na-answer" aria-live="polite"></div>
            <form class="na-ask"><input type="text" maxlength="400" placeholder="${esc(t('askPh'))}">
              <button type="submit" class="na-tbtn primary">${esc(t('ask'))}</button></form>
            ${item ? `<button type="button" class="na-tbtn link na-more" data-act="more">${esc(t('more'))}</button>` : ''}`;
        document.body.append(bubble);
        bubble.target = node;
        bubble.known = item ? text.replace(/<[^>]+>/g, '') : '';
        outline(node);
        placeBubble();
        bubble.addEventListener('click', e => {
            const lng = e.target.closest('[data-lang]');
            if (lng) { setLang(lng.dataset.lang); explain(node, key); return; }
            const act = e.target.closest('[data-act]')?.dataset.act;
            if (act === 'close') closeBubble();
            else if (act === 'more') { e.target.remove(); ask(''); }
        });
        bubble.querySelector('form').addEventListener('submit', e => {
            e.preventDefault();
            const input = bubble.querySelector('input');
            ask(input.value.trim());
            input.value = '';
        });
        addEventListener('resize', placeBubble);
        addEventListener('scroll', placeBubble, true);
        document.addEventListener('keydown', onBubbleKey, true);
        if (!item) ask('');
        else bubble.querySelector('input').focus({ preventScroll: true });
    }
    function placeBubble() {
        if (!bubble) return;
        const node = bubble.target;
        if (!node.isConnected) return closeBubble();
        outline(node);
        placeBeside(bubble, node.getBoundingClientRect());
    }
    function onBubbleKey(e) { if (e.key === 'Escape' && bubble) { e.preventDefault(); closeBubble(); } }
    function closeBubble() {
        if (!bubble) return;
        bubble.remove();
        bubble = null;
        hl?.remove(); hl = null;
        removeEventListener('resize', placeBubble);
        removeEventListener('scroll', placeBubble, true);
        document.removeEventListener('keydown', onBubbleKey, true);
    }

    async function ask(question) {
        if (!bubble || !CFG.explain) return;
        const box = bubble.querySelector('.na-answer'), node = bubble.target, mine = bubble;
        const button = bubble.querySelector('.na-ask button');
        box.innerHTML = `<p class="na-wait">${esc(t('thinking'))}</p>`;
        button.disabled = true;
        placeBubble();
        try {
            const resp = await fetch(CFG.explain, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrf || '' },
                body: JSON.stringify({
                    lang, question, page: location.pathname, page_title: document.title, tag: node.tagName.toLowerCase(),
                    label: labelOf(node), title: node.getAttribute('title') || '', placeholder: node.getAttribute('placeholder') || '',
                    heading: headingOf(node), known: mine.known,
                }),
            });
            const data = await resp.json().catch(() => ({}));
            if (bubble !== mine) return;
            if (!resp.ok) throw new Error(data.error || resp.statusText);
            box.innerHTML = (question ? `<p class="na-q">${esc(question)}</p>` : '')
                + `<p>${esc(data.text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n+/g, '<br>')}</p>`;
        } catch (err) {
            if (bubble === mine) box.innerHTML = `<p class="na-err">${esc(t('fail') + err.message)}</p>`;
        } finally {
            if (bubble === mine) { button.disabled = false; placeBubble(); }
        }
    }

    // Every tour shows again on its page (this page's starts now)
    function resetTours() {
        try {
            Object.keys(localStorage).filter(k => k.startsWith('na-tour-')).forEach(k => localStorage.removeItem(k));
        } catch (e) { /* storage blocked: tours already show every time */ }
    }

    window.NATour = { start, pick, end, reset: resetTours, seen: name => store.get('na-tour-' + name) === 'seen', lang: () => lang };

    // A page's own tour starts by itself the first time that page is opened
    function autoStart() {
        const own = window.NA_PAGE_TOUR;
        if (own && own.auto && !window.NATour.seen(own.name)) setTimeout(() => { if (!tour) start(own.name); }, own.delay || 800);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', autoStart);
    else autoStart();
})();
