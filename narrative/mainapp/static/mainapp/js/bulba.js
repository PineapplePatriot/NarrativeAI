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
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(body),
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
    const actions = p.status === 'pending'
        ? `<button type="button" data-act="apply" data-id="${p.id}">Apply</button>
           <button type="button" class="ghost" data-act="dismiss" data-id="${p.id}">Not this</button>`
        : p.status === 'applied' ? `<button type="button" class="ghost" data-act="undo" data-id="${p.id}">Undo</button>` : '';
    const chatLink = p.status === 'applied' && p.result && p.result.slug
        ? `<a class="btn" href="/main/chat/${encodeURIComponent(p.result.slug)}">Chat now →</a>` : '';
    return `<div class="proposal ${p.status}">
        <div class="proposal-head"><b>${esc(p.title)}</b> ${status}</div>
        <div class="proposal-body">${(p.summary || []).map(l => /^[^\s].{0,40}:$/.test(l)
            ? `<div class="proposal-label">${esc(l.slice(0, -1))}</div>` : `<div>${esc(l)}</div>`).join('')}</div>
        <div class="proposal-actions">${actions}${chatLink}</div>
      </div>`;
}

function render() {
    const lastBulba = events.map(e => e.type).lastIndexOf('bulba');
    const lastSamples = events.map(e => e.type).lastIndexOf('samples');
    $('log').innerHTML = events.map((ev, i) => {
        if (ev.type === 'bulba') {
            const choices = (ev.choices || []).map(c => c.url
                ? `<a class="choice" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.label)} ↗</a>`
                : `<button type="button" class="choice" data-say="${esc(c.label)}" ${i === lastBulba && !busy ? '' : 'disabled'}>${esc(c.label)}</button>`).join('');
            return `<div class="msg bulba"><span class="potato">🥔</span><div class="bubble">${fmt(ev.text)}
                    ${choices ? `<div class="choices">${choices}</div>` : ''}</div></div>`;
        }
        if (ev.type === 'user') return `<div class="msg user"><div class="bubble">${esc(ev.text)}</div></div>`;
        if (ev.type === 'action') return `<div class="action">${esc(ev.text)}</div>`;
        if (ev.type === 'note') return `<div class="note">✓ ${esc(ev.text)}</div>`;
        if (ev.type === 'error') return `<div class="error">${esc(ev.text)}</div>`;
        if (ev.type === 'stage') return `<div class="stage-mark">${esc(STAGE_LABELS[ev.stage] || ev.stage)}</div>`;
        if (ev.type === 'proposal') return proposalCard(ev);
        if (ev.type === 'samples') {
            const live = i === lastSamples && !busy;
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
              </div>`;
        }
        return '';
    }).join('');
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
    $('prefs').innerHTML = state.preferences.length ? state.preferences.map(p => `
        <li><span>${esc(p.interpretation)}${p.status === 'tentative' ? ' <i>(guess)</i>' : ''}</span>
            <button type="button" class="x" data-forget="${p.id}" title="Forget this">✕</button></li>`).join('')
        : '<li class="empty">Nothing yet.</li>';
}

// --------------------------------------------------------------- actions
async function run(body, label) {
    if (busy) return;
    busy = true;
    $('thinking').hidden = false;
    $('thinkingText').textContent = label || 'Thinking…';
    $('sendBtn').disabled = true;
    if (body.action === 'say') events.push({ type: 'user', text: body.text });
    render();
    try {
        const data = await api(body);
        if (body.action === 'say') events.pop();  // the server sends it back with the rest
        events = body.action === 'restart' ? data.events : events.concat(data.events);
        state = data.state;
    } catch (err) {
        if (body.action === 'say') events.pop();
        events.push({ type: 'error', text: err.message });
    } finally {
        busy = false;
        $('thinking').hidden = true;
        $('sendBtn').disabled = false;
        render();
    }
}

function say(text) {
    text = text.trim();
    if (text) run({ action: 'say', text }, 'Bulba is thinking… (samples take a little longer)');
}

$('composer').addEventListener('submit', e => {
    e.preventDefault();
    const text = $('input').value;
    $('input').value = '';
    say(text);
});
$('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('composer').requestSubmit(); }
});

$('log').addEventListener('click', e => {
    const sayBtn = e.target.closest('[data-say]');
    if (sayBtn && !sayBtn.disabled) {
        const text = sayBtn.dataset.say;
        if (text.endsWith(' ')) { $('input').value = text; $('input').focus(); return; }  // "A bit of both…": let them finish
        say(text);
        return;
    }
    const act = e.target.closest('[data-act]');
    if (act) run({ action: act.dataset.act, id: act.dataset.id }, act.dataset.act === 'apply' ? 'Applying…' : 'One moment…');
});

$('prefs').addEventListener('click', async e => {
    const btn = e.target.closest('[data-forget]');
    if (!btn) return;
    try { state = (await api({ action: 'forget', id: btn.dataset.forget })).state; renderPanel(); }
    catch (err) { alert(err.message); }
});

$('budgetBtn').onclick = async () => {
    const value = prompt('Spending limit for this session, in dollars:', state.budget);
    if (!value) return;
    try { state = (await api({ action: 'budget', value })).state; renderPanel(); }
    catch (err) { alert(err.message); }
};

$('restartBtn').onclick = () => {
    if (confirm('Start the conversation over? Anything you already applied stays.')) run({ action: 'restart' });
};

render();
