const $ = id => document.getElementById(id);
const INIT = JSON.parse($('bulba-data').textContent);
let state = INIT.state;
let events = INIT.events;
let busy = false;

const STAGE_LABELS = { extras: 'Extras', taste: 'How replies read', preset: 'Your preset', persona: 'You in the story',
                       character: 'Your character', done: 'Done' };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Light formatting for Bulba's messages: paragraphs, **bold**, *italics*
const fmt = t => esc(t).split(/\n{2,}/).map(p => `<p>${p.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>').replace(/\n/g, '<br>')}</p>`).join('');

function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

async function api(body) {
    const resp = await fetch(BULBA_API, {
        method: 'POST',
        headers: body instanceof FormData ? { 'X-CSRFToken': getCookie('csrftoken') }
                                          : { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: body instanceof FormData ? body : JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || 'Something went wrong.');
    return data;
}

// --------------------------------------------------------------- rendering
function proposalCard(ev) {
    const p = state.proposals.find(x => x.id === ev.id);
    if (!p) return '';
    const status = { pending: '', applied: '<span class="status ok">Applied</span>', dismissed: '<span class="status">Dismissed</span>',
                     undone: '<span class="status">Undone</span>', replaced: '<span class="status">Replaced by a newer one</span>' }[p.status] || '';
    const off = busy ? 'disabled' : '';
    const actions = p.status === 'pending'
        ? `<button type="button" data-act="apply" data-id="${p.id}" ${off}>Apply</button>
           <button type="button" class="ghost" data-act="dismiss" data-id="${p.id}" ${off}>Not this</button>`
        : p.status === 'applied' ? `<button type="button" class="ghost" data-act="undo" data-id="${p.id}" ${off}>Undo</button>` : '';
    const chatLink = p.status === 'applied' && p.result && p.result.slug
        ? `<a class="btn" href="/main/chat/${encodeURIComponent(p.result.slug)}">Chat now →</a>` : '';
    return `<div class="proposal ${p.status}">
        <div class="proposal-head"><b>${esc(p.title)}</b> ${status}</div>
        <div class="proposal-body${(p.summary || []).join('\n').length > 900 ? ' folded' : ''}">${(p.summary || []).map(l => /^[^\s].{0,40}:$/.test(l)
            ? `<div class="proposal-label">${esc(l.slice(0, -1))}</div>` : `<div>${esc(l)}</div>`).join('')}</div>
        ${(p.summary || []).join('\n').length > 900 ? '<button type="button" class="link unfold">Show all</button>' : ''}
        <div class="proposal-actions">${actions}${chatLink}</div>
      </div>`;
}

// The basics form: plain settings in one go (see BASICS in mainapp/bulba/agent.py)
const BASICS_FORM = [
    { section: 'How it’s written' },
    { key: 'language', label: 'Story language', text: 'English' },
    { key: 'pov', label: 'Point of view', options: [['second', 'You (“you step inside”)'], ['third', 'Third person (“she steps inside”)'], ['first', 'The character’s “I”']] },
    { key: 'tense', label: 'Tense', options: [['present', 'Present (“she turns”)'], ['past', 'Past (“she turned”)']] },
    { key: 'length', label: 'Reply length', options: [['short', 'A few lines'], ['medium', 'A few paragraphs'], ['long', 'A proper chunk']] },
    { key: 'format', label: 'Speech and actions', options: [['quotes', '“Speech”, actions as plain text'], ['asterisks', '“Speech”, *actions*'], ['any', 'Doesn’t matter']] },
    { key: 'colors', label: 'Coloured speech', hint: 'each character speaks in their own colour', options: [['on', 'Yes'], ['off', 'No']] },
    { key: 'panels', label: 'In-story panels', hint: 'phone messages, notes and signs drawn as little panels', options: [['on', 'Yes'], ['off', 'No']] },
    { section: 'What kind of story' },
    { key: 'genres', label: 'Genres', hint: 'pick any', multi: [['fluff', 'Fluff'], ['slice_of_life', 'Slice of life'], ['comedy', 'Comedy'], ['romance', 'Romance'], ['heartwarming', 'Heartwarming'], ['melancholy', 'Melancholy'], ['healing', 'Hurt/comfort'], ['angst', 'Angst'], ['tragedy', 'Tragedy']],
      adult: [['smut', 'Smut'], ['dead_dove', 'Dead dove']] },
    { key: 'pacing', label: 'Pacing', options: [['quick', 'Quick: skip the dull bits'], ['slow', 'Slow burn'], ['any', 'No preference']] },
    { key: 'voice', label: 'Narration voice', hint: 'optional', options: [['hemingway', 'Hemingway: lean'], ['mccarthy', 'McCarthy: solemn'], ['camus', 'Camus: wry'], ['kafka', 'Kafka: absurd'], ['ligotti', 'Ligotti: dread'], ['maupassant', 'Maupassant: cruel realism'], ['dickens', 'Dickens: theatrical'], ['ellis', 'Ellis: gossipy'], ['anime', 'Anime'], ['realism', 'Grounded realism'], ['fanfic', 'Fanfic'], ['webnovel', 'Web novel']] },
    { key: 'author', label: 'Write like', text: '', placeholder: 'Optional: an author whose style you love' },
    { key: 'keep_out', label: 'Anything to keep out?', text: '', placeholder: 'Optional, e.g. gore, spiders' },
];

function basicsForm(live) {
    const dis = live ? '' : 'disabled';
    const chips = (f, list) => list.map(([v, l]) => `<label class="pill"><input type="checkbox" name="b_${f.key}" value="${v}" ${dis}><span>${esc(l)}</span></label>`).join('');
    const rows = BASICS_FORM.map(f => f.section ? `<div class="form-section">${esc(f.section)}</div>` : f.multi ? `<div class="form-row">
        <div class="form-label">${esc(f.label)}${f.hint ? `<small>${esc(f.hint)}</small>` : ''}</div>
        <div class="form-field">${chips(f, f.multi)}
            ${f.adult ? `<span class="adult-chips" hidden>${chips(f, f.adult)}</span>
            <button type="button" class="link adult-toggle" ${dis}>Show 18+ genres</button>` : ''}</div></div>` : `<div class="form-row">
        <div class="form-label">${esc(f.label)}${f.hint ? `<small>${esc(f.hint)}</small>` : ''}</div>
        <div class="form-field">${f.options
            ? f.options.map(([v, l]) => `<label class="pill"><input type="radio" name="b_${f.key}" value="${v}" ${live ? '' : 'disabled'}><span>${esc(l)}</span></label>`).join('')
            : `<input type="text" name="b_${f.key}" value="${esc(f.text)}" placeholder="${esc(f.placeholder || '')}" ${live ? '' : 'disabled'}>`}
        </div></div>`).join('');
    return `<form class="basics-form" data-basics>${rows}
        ${live ? '<div class="form-actions"><button type="submit">Send</button><span class="help">Skip anything you don’t mind about.</span></div>' : ''}
      </form>`;
}

// When setup is done: the way into the chat, and where pictures go
function doneBlock() {
    if (state.stage !== 'done' || !state.chat) return '';
    return `<div class="done-block">
        <a class="btn" href="${esc(state.chat.url)}">Start chatting with ${esc(state.chat.name)} →</a>
        <a class="ghost-link" href="${esc(state.chat.edit_url)}">Add pictures for ${esc(state.chat.name)}</a>
      </div>`;
}

function render() {
    const types = events.map(e => e.type);
    const lastBulba = types.lastIndexOf('bulba');
    const lastSamples = types.lastIndexOf('samples');
    // Buttons only work on what came after the user's last move (an answer, or pressing Apply)
    const answeredUpTo = Math.max(types.lastIndexOf('user'), types.lastIndexOf('action'));
    const liveChoices = i => i === lastBulba && i > answeredUpTo && !busy;
    $('log').innerHTML = events.map((ev, i) => {
        if (ev.type === 'bulba') {
            const choices = (ev.choices || []).map(c => c.url
                ? `<a class="choice" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.label)} ↗</a>`
                : `<button type="button" class="choice" data-say="${esc(c.label)}" ${liveChoices(i) ? '' : 'disabled'}>${esc(c.label)}</button>`).join('');
            return `<div class="msg bulba"><span class="potato">🥔</span><div class="bubble">${fmt(ev.text)}
                    ${choices ? `<div class="choices">${choices}</div>` : ''}</div></div>`;
        }
        if (ev.type === 'user') return `<div class="msg user"><div class="bubble">${esc(ev.text)}</div></div>`;
        if (ev.type === 'action') return `<div class="action">${esc(ev.text)}</div>`;
        if (ev.type === 'note') return `<div class="note">✓ ${esc(ev.text)}</div>`;
        if (ev.type === 'error') return `<div class="error">${esc(ev.text)}</div>`;
        if (ev.type === 'stage') return `<div class="stage-mark">${esc(STAGE_LABELS[ev.stage] || ev.stage)}</div>`;
        if (ev.type === 'proposal') return proposalCard(ev);
        if (ev.type === 'card_upload') {
            const live = i === types.lastIndexOf('card_upload') && i > answeredUpTo && !busy;
            return `<form class="card-upload" data-card-upload>
                <label>Your card <small>(.png or .json, from SillyTavern, Chub and the like)</small>
                <input type="file" name="card" accept=".png,.json,image/png,application/json" ${live ? '' : 'disabled'}></label>
                <button type="submit" ${live ? '' : 'disabled'}>Import</button></form>`;
        }
        if (ev.type === 'form') return basicsForm(i === types.lastIndexOf('form') && i > answeredUpTo && !busy);
        if (ev.type === 'lookup') return `<div class="lookup">🔎 Looked up “${esc(ev.query)}”${(ev.sources || []).length
            ? ': ' + ev.sources.map(src => `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.title || src.url)}</a>`).join(', ') : ''}</div>`;
        if (ev.type === 'samples') {
            const live = i === lastSamples && i > answeredUpTo && !busy;
            const single = ev.samples.length === 1;
            return `<div class="samples">
                <div class="samples-head">Written by <b>${esc(ev.model)}</b>${ev.character ? ` as ${esc(ev.character)}` : ''}</div>
                ${ev.scenario ? `<div class="samples-scene">${esc(ev.scenario)}<br><i>You: ${esc(ev.user_turn)}</i></div>` : ''}
                <div class="sample-grid">${ev.samples.map(s => `
                    <div class="sample"><div class="sample-label">${esc(s.label)}</div><div class="sample-text">${fmt(s.text)}</div>
                    ${live && ev.samples.length > 1 ? `<button type="button" data-say="I prefer ${esc(s.label)}.">This one</button>` : ''}</div>`).join('')}</div>
                ${live && ev.samples.length > 1 ? `<div class="sample-actions">
                    <button type="button" class="ghost" data-say="I like both.">Both</button>
                    <button type="button" class="ghost" data-say="Neither of these.">Neither</button>
                    <button type="button" class="ghost" data-say="A bit of both. ">A bit of both…</button>
                    <button type="button" class="ghost" data-say="No preference, skip this one.">Skip</button></div>` : ''}
                ${live && single ? `<div class="sample-actions">
                    <span class="sample-ask">How does it read?</span>
                    <button type="button" data-say="I like it.">👍 Like it</button>
                    <button type="button" class="ghost" data-say="I like it, but ">👍 Like it, but…</button>
                    <button type="button" class="ghost" data-say="Not quite: ">👎 Not quite…</button></div>` : ''}
              </div>`;
        }
        return '';
    }).join('') + doneBlock();
    $('log').scrollTop = $('log').scrollHeight;
    renderPanel();
}

function renderPanel() {
    $('modelName').textContent = state.model;
    const current = state.stages.indexOf(state.stage);
    $('stages').innerHTML = state.stages.map((s, i) =>
        `<li class="${i < current ? 'done' : i === current ? 'current' : ''}">${esc(STAGE_LABELS[s] || s)}</li>`).join('');
    $('spent').textContent = `$${state.spent.toFixed(2)}`;
    $('budget').textContent = `$${state.budget.toFixed(2)}`;
    $('meterFill').style.width = `${Math.min(100, state.spent / state.budget * 100)}%`;
    $('panelChat').innerHTML = state.chat
        ? `<a class="btn" href="${esc(state.chat.url)}">Chat with ${esc(state.chat.name)} →</a>` : '';
    if (state.month) $('monthLine').textContent =
        `All AI use this month (chat and Bulba): $${state.month.spent.toFixed(2)} of $${state.month.limit.toFixed(2)}.`;
    $('prefs').innerHTML = state.preferences.length ? state.preferences.map(p => `
        <li><span>${esc(p.interpretation)}${p.status === 'tentative' ? ' <i>(guess)</i>' : ''}</span>
            <button type="button" class="x" data-forget="${p.id}" title="Forget this">✕</button></li>`).join('')
        : '<li class="empty">Nothing yet.</li>';
}

// --------------------------------------------------------------- actions
let activityTimer = null;
function pollActivity() {
    activityTimer = setTimeout(async () => {
        if (!busy) return;
        try {
            const resp = await fetch(BULBA_API, { headers: { 'Accept': 'application/json' } });
            const data = await resp.json();
            if (busy && data.activity) $('thinkingText').textContent = data.activity;
        } catch (e) { /* the status line is a nicety */ }
        if (busy) pollActivity();
    }, 1200);
}

async function run(body, label) {
    if (busy) return;
    busy = true;
    $('thinking').hidden = false;
    $('thinkingText').textContent = label || 'Thinking…';
    $('sendBtn').disabled = true;
    $('input').disabled = true;
    pollActivity();
    if (body.action === 'say') events.push({ type: 'user', text: body.text });
    render();
    try {
        const data = await api(body);
        if (window.parent !== window && ['apply', 'undo'].includes(body.action)) {
            window.parent.postMessage({ bulba: body.action }, window.location.origin);
        }
        if (body.action === 'say') events.pop();  // the server sends it back with the rest
        events = body.action === 'restart' ? data.events : events.concat(data.events);
        state = data.state;
    } catch (err) {
        if (body.action === 'say') events.pop();
        events.push({ type: 'error', text: err.message });
    } finally {
        busy = false;
        clearTimeout(activityTimer);
        $('thinking').hidden = true;
        $('sendBtn').disabled = false;
        $('input').disabled = false;
        $('input').focus();
        render();
    }
}

function say(text) {
    text = text.trim();
    if (text) run({ action: 'say', text }, 'Bulba is thinking… (samples take a little longer)');
}

$('composer').addEventListener('submit', e => {
    e.preventDefault();
    if (busy) return;  // keep what they typed until Bulba is done
    const text = $('input').value;
    $('input').value = '';
    say(text);
});
$('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('composer').requestSubmit(); }
});

$('log').addEventListener('click', e => {
    const sayBtn = e.target.closest('[data-say]');
    if (sayBtn && !sayBtn.disabled && !busy) {
        const text = sayBtn.dataset.say;
        if (text.endsWith(' ')) { $('input').value = text; $('input').focus(); return; }  // "A bit of both…": let them finish
        say(text);
        return;
    }
    const act = e.target.closest('[data-act]');
    if (act && !act.disabled) run({ action: act.dataset.act, id: act.dataset.id }, act.dataset.act === 'apply' ? 'Applying…' : 'One moment…');
});

$('log').addEventListener('click', e => {
    const t = e.target.closest('.adult-toggle');
    if (!t) return;
    const chips = t.previousElementSibling;
    chips.hidden = !chips.hidden;
    t.textContent = chips.hidden ? 'Show 18+ genres' : 'Hide 18+ genres';
});

$('log').addEventListener('submit', e => {
    const form = e.target.closest('[data-card-upload]');
    if (!form) return;
    e.preventDefault();
    const file = form.querySelector('input[type=file]').files[0];
    if (!file) return;
    const body = new FormData();
    body.append('card', file);
    run(body, 'Importing your card…');
});

$('log').addEventListener('submit', e => {
    const form = e.target.closest('[data-basics]');
    if (!form) return;
    e.preventDefault();
    const answers = {};
    BASICS_FORM.forEach(f => {
        if (f.section) return;
        if (f.multi) {
            const picked = [...form.querySelectorAll(`input[name="b_${f.key}"]:checked`)].map(el => el.value);
            if (picked.length) answers[f.key] = picked;
            return;
        }
        const el = f.options ? form.querySelector(`input[name="b_${f.key}"]:checked`) : form.querySelector(`input[name="b_${f.key}"]`);
        if (el && el.value.trim()) answers[f.key] = el.value.trim();
    });
    run({ action: 'basics', answers }, 'Bulba is reading your answers…');
});

$('prefs').addEventListener('click', async e => {
    const btn = e.target.closest('[data-forget]');
    if (!btn) return;
    try { state = (await api({ action: 'forget', id: btn.dataset.forget })).state; renderPanel(); }
    catch (err) { alert(err.message); }
});

// Bulba's own limit, shown against what the subscription covers this month (chat and Bulba together)
function budgetNote() {
    const m = state.month, value = parseFloat($('budgetInput').value);
    if (!m) return;
    const room = m.left + state.spent;  // what Bulba could still use this month, counting this session
    let text = `Your subscription covers $${m.limit.toFixed(2)} a month for chatting and Bulba together; both stop when it's used up. ` +
               `This month you've used $${m.spent.toFixed(2)}, so $${m.left.toFixed(2)} is left.`;
    if (!isNaN(value) && value > room) text += ` A $${value.toFixed(2)} limit is more than that: everything (chat and Bulba) stops when the month's money runs out.`;
    else if (!isNaN(value) && value > room / 2) text += ` That leaves about $${Math.max(0, room - value).toFixed(2)} for chatting.`;
    $('budgetNote').textContent = text;
    $('budgetNote').classList.toggle('warn', !isNaN(value) && value > room);
}
$('budgetBtn').onclick = () => {
    $('budgetForm').hidden = false;
    $('budgetInput').value = state.budget;
    budgetNote();
    $('budgetInput').focus();
};
$('budgetInput').addEventListener('input', budgetNote);
$('budgetCancel').onclick = () => { $('budgetForm').hidden = true; };
$('budgetForm').onsubmit = async e => {
    e.preventDefault();
    try {
        state = (await api({ action: 'budget', value: $('budgetInput').value })).state;
        $('budgetForm').hidden = true; renderPanel();
    } catch (err) { $('budgetNote').textContent = err.message; }
};

document.querySelectorAll('#restartBtn, [data-restart]').forEach(b => b.onclick = () => {
    if (confirm('Start the conversation over? Anything you already applied stays.')) run({ action: 'restart' });
});

render();

// Long proposals (a whole character card) start folded
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.unfold');
    if (!btn) return;
    const body = btn.previousElementSibling;
    body.classList.toggle('folded');
    btn.textContent = body.classList.contains('folded') ? 'Show all' : 'Show less';
});

// Opened from the chat's pen menu with something already typed: put it in the box, unsent
(function () {
    const fill = (text) => { if (text) { $('input').value = text; $('input').focus(); } };
    fill(new URLSearchParams(window.location.search).get('draft'));
    window.addEventListener('message', (e) => {
        if (e.origin === window.location.origin && e.data && e.data.bulbaDraft) fill(e.data.bulbaDraft);
    });
})();
