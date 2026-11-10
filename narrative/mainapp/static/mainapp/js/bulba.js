const $ = id => document.getElementById(id);
const INIT = JSON.parse($('bulba-data').textContent);
let state = INIT.state;
let events = INIT.events;
let busy = false;
if (window.NATomato) NATomato.watch(() => busy);  // 🍅 a long Bulba turn

const STAGE_LABELS = { extras: 'Extras', taste: 'How replies read', preset: 'Your preset', persona: 'You in the story',
                       character: 'Your character', story: 'Story extras', done: 'Done' };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Light formatting for Bulba's messages: paragraphs, **bold**, *italics*
const fmt = t => esc(t).split(/\n{2,}/).map(p => `<p>${p.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>').replace(/\n/g, '<br>')}</p>`).join('');
// Samples are written by the user's model with their preset, which may colour speech with <font color> or use
// <b>, <i>, <span style="color:...">: show those few tags as in a chat (everything else stays escaped)
const COLOR = '(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})';
const fmtSample = t => fmt(t)
    .replace(new RegExp(`&lt;font color=(?:&quot;|')?${COLOR}(?:&quot;|')?&gt;`, 'g'), '<span style="color:$1">')
    .replace(/&lt;\/font&gt;/g, '</span>')
    .replace(new RegExp(`&lt;span style=(?:&quot;|')color:\\s*${COLOR};?(?:&quot;|')&gt;`, 'g'), '<span style="color:$1">')
    .replace(/&lt;\/span&gt;/g, '</span>')
    .replace(/&lt;(\/?)(b|i|em|strong|u|s)&gt;/g, '<$1$2>')
    .replace(/&lt;br\s*\/?&gt;/g, '<br>');

function getCookie(name) {
    const m = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

// In the panel beside the Quick setup form (not the in-chat Bulba, which is framed too)
const BESIDE_QUICK = window.parent !== window && document.body.classList.contains('embed') && INIT.state && INIT.state.mode === 'setup';
async function api(body) {
    if (BESIDE_QUICK && !(body instanceof FormData) && body.action === 'say') body = { ...body, beside_quick: true };
    let resp;
    try {
        resp = await fetch(BULBA_API, {
            method: 'POST',
            headers: body instanceof FormData ? { 'X-CSRFToken': getCookie('csrftoken') }
                                              : { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: body instanceof FormData ? body : JSON.stringify(body),
        });
    } catch (e) {  // the connection dropped (the phone slept, they switched apps): Bulba carries on on the server
        throw Object.assign(new Error('The connection dropped.'), { lost: true });
    }
    const data = await resp.json().catch(() => ({}));
    if (data.stale) setTimeout(() => window.location.reload(), 400);  // an out-of-date card: show the latest
    // No answer of ours (a gateway timeout, a restart) or "still busy": the turn may well finish anyway
    if (!resp.ok) throw Object.assign(new Error(data.error || 'Something went wrong.'),
                                      { lost: resp.status >= 502 || data.busy || !data.error });
    return data;
}

// --------------------------------------------------------------- rendering
let editingId = null;  // the proposal whose text is open for editing

// A proposal's text, editable in place before Apply
function proposalEditor(p) {
    const rows = p.editable.map(f => `<label class="edit-field"><span>${esc(f.label)}</span>
        ${f.long ? `<textarea data-path="${esc(f.path)}" rows="${Math.min(14, Math.max(3, Math.ceil((f.value || '').length / 70)))}">${esc(f.value)}</textarea>`
                 : `<input type="text" data-path="${esc(f.path)}" value="${esc(f.value)}">`}</label>`).join('');
    return `<div class="proposal pending editing" data-editor="${p.id}">
        <div class="proposal-head"><b>${esc(p.title)}</b> <span class="status">editing</span></div>
        <div class="proposal-edit">${rows}</div>
        <div class="proposal-actions">
            <button type="button" data-save-edit="${p.id}">Save changes</button>
            <button type="button" class="ghost" data-cancel-edit>Cancel</button></div>
      </div>`;
}

// A theme card shows the look itself: the background, the music (▶ to listen), the colour on a sample line
const WEATHER_ICON = { rain: '🌧', snow: '❄️', fog: '🌫', storm: '⛈', clear: '☀️' };
function themePreview(v) {
    const color = /^#[0-9a-fA-F]{6}$/.test(v.color || '') ? v.color : '';
    return `<div class="theme-preview">
        ${v.bg ? `<div class="tp-bg" style="background-image:url('${encodeURI(v.bg)}')">
            ${v.weather && WEATHER_ICON[v.weather] ? `<span class="tp-weather">${WEATHER_ICON[v.weather]} ${esc(v.weather)}</span>` : ''}
            ${color ? `<span class="tp-line" style="color:${color}">“A line in this colour.”</span>` : ''}</div>`
          : color ? `<div class="tp-line solo" style="color:${color}">“A line in this colour.”</div>` : ''}
        ${v.skin_name ? `<span class="tp-skin tp-skin-${esc(v.skin || '')}">Chat style: ${esc(v.skin_name)}</span>` : ''}
        ${v.music ? `<button type="button" class="ghost tp-play" data-play="${esc(v.music)}">▶ Listen: ${esc(v.music_name || 'music')}</button>` : ''}
      </div>`;
}
let previewAudio = null;
document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-play]');
    if (!b) return;
    if (previewAudio && previewAudio.dataset.src === b.dataset.play && !previewAudio.paused) {
        previewAudio.pause(); b.textContent = b.textContent.replace('⏸', '▶'); return;
    }
    if (previewAudio) previewAudio.pause();
    document.querySelectorAll('[data-play]').forEach(x => { x.textContent = x.textContent.replace('⏸', '▶'); });
    previewAudio = new Audio(b.dataset.play);
    previewAudio.dataset.src = b.dataset.play;
    previewAudio.volume = 0.6;
    previewAudio.play().then(() => { b.textContent = b.textContent.replace('▶', '⏸'); }).catch(() => {});
    previewAudio.addEventListener('ended', () => { b.textContent = b.textContent.replace('⏸', '▶'); });
});

function proposalCard(ev) {
    const p = state.proposals.find(x => x.id === ev.id);
    if (!p) return '';
    const status = { pending: '', applied: '<span class="status ok">Applied</span>', dismissed: '<span class="status">Dismissed</span>',
                     undone: '<span class="status">Undone</span>', replaced: '<span class="status">Replaced by a newer one</span>' }[p.status] || '';
    const off = busy ? 'disabled' : '';
    const editable = (p.editable || []).length;
    if (p.status === 'pending' && editingId === p.id && editable) return proposalEditor(p);
    const actions = p.status === 'pending'
        ? `<button type="button" data-act="apply" data-id="${p.id}" ${off}>Apply</button>
           ${editable ? `<button type="button" class="ghost" data-edit-proposal="${p.id}" ${off}>Edit</button>` : ''}
           <button type="button" class="ghost" data-act="dismiss" data-id="${p.id}" ${off}>Not this</button>`
        : p.status === 'applied' ? `<button type="button" class="ghost" data-act="undo" data-id="${p.id}" ${off}>Undo</button>` : '';
    const chatLink = p.status === 'applied' && p.result && p.result.slug
        ? `<a class="btn" href="/main/chat/${encodeURIComponent(p.result.slug)}" ${window.parent !== window ? 'target="_top"' : ''}>Chat now →</a>` : '';
    return `<div class="proposal ${p.status}">
        <div class="proposal-head"><b>${esc(p.title)}</b> ${p.edited ? '<span class="status">edited by you</span>' : ''} ${status}</div>
        <div class="proposal-body${(p.summary || []).join('\n').length > 900 ? ' folded' : ''}">${(p.summary || []).map(l => /^[^\s].{0,40}:$/.test(l)
            ? `<div class="proposal-label">${esc(l.slice(0, -1))}</div>` : `<div>${esc(l)}</div>`).join('')}</div>
        ${(p.summary || []).join('\n').length > 900 ? '<button type="button" class="link unfold">Show all</button>' : ''}
        ${p.preview ? themePreview(p.preview) : ''}
        <div class="proposal-actions">${actions}${chatLink}</div>
      </div>`;
}

// The basics form: plain settings in one go (see BASICS in mainapp/bulba/agent.py)
// The questions (mainapp/data/bulba/basics_form.json via mainapp/basics.py), the same ones Quick setup asks
const BASICS_FORM = INIT.basics_form || [];

// `answers`: what they sent (kept on the event), so a sent form still shows their choices
function basicsForm(live, answers) {
    const dis = live ? '' : 'disabled';
    const a = answers || {};
    const on = (f, v) => (Array.isArray(a[f.key]) ? a[f.key].includes(v) : a[f.key] === v) ? 'checked' : '';
    const chips = (f, list) => list.map(([v, l]) => `<label class="pill"><input type="checkbox" name="b_${f.key}" value="${v}" ${on(f, v)} ${dis}><span>${esc(l)}</span></label>`).join('');
    const rows = BASICS_FORM.map(f => f.section ? `<div class="form-section">${esc(f.section)}</div>` : f.multi ? `<div class="form-row">
        <div class="form-label">${esc(f.label)}${f.hint ? `<small>${esc(f.hint)}</small>` : ''}</div>
        <div class="form-field">${chips(f, f.multi)}
            ${f.adult ? `<span class="adult-chips" ${f.adult.some(([v]) => on(f, v)) ? '' : 'hidden'}>${chips(f, f.adult)}</span>
            <button type="button" class="link adult-toggle" ${dis}>Show ${esc(f.adultLabel || '18+ genres')}</button>` : ''}</div></div>` : `<div class="form-row">
        <div class="form-label">${esc(f.label)}${f.hint ? `<small>${esc(f.hint)}</small>` : ''}</div>
        <div class="form-field">${f.options
            ? f.options.map(([v, l]) => `<label class="pill"><input type="radio" name="b_${f.key}" value="${v}" ${on(f, v)} ${live ? '' : 'disabled'}><span>${esc(l)}</span></label>`).join('')
            : `<input type="text" name="b_${f.key}" value="${esc(a[f.key] || f.text || '')}" placeholder="${esc(f.placeholder || '')}" ${live ? '' : 'disabled'}>`}
            ${f.help ? `<p class="help form-help">${esc(f.help)}</p>` : ''}
        </div></div>`).join('');
    return `<form class="basics-form" data-basics>${rows}
        ${live ? '<div class="form-actions"><button type="submit">Send</button><span class="help">Skip anything you don’t mind about.</span></div>' : ''}
      </form>`;
}

// What things cost, for the setup and memory forms' estimates (static/js/costs.js)
function costLines(form, ev) {
    const C = window.NACosts, steps = C.steps(ev.window.max);
    const size = steps[Number(form.querySelector('[name="x_chat_context"]').value)] || steps[0];
    const bgPick = form.querySelector('[name="x_background"]');
    const bg = (bgPick && bgPick.value !== 'chat' ? ev.prices.bg[bgPick.value] : ev.prices.chat) || null;
    const set = (key, text) => { const el = form.querySelector(`[data-cost="${key}"]`); if (el) el.textContent = text; };
    form.querySelector('[data-memory-value]').textContent = C.memory(size);
    set('chat', C.chat(ev.prices.chat, size));
    for (const task of ['summary', 'trackers']) {
        const every = form.querySelector(`[name="x_${task}_every"]`);
        if (!every) continue;
        const mode = (form.querySelector(`input[name="x_${task}"]:checked`) || {}).value;
        set(task, C.job(task, bg, size, mode, Number(every.value) || (task === 'summary' ? 10 : 2)));
    }
}
const formEventFor = form => [...events].reverse().find(x => x.type === 'extras_form' && x.part === form.dataset.extras);
$('log').addEventListener('input', e => {
    const form = e.target.closest('[data-extras="setup"], [data-extras="memory"]');
    const ev = form && formEventFor(form);
    if (ev && ev.window) costLines(form, ev);
});
function fillCosts() {
    document.querySelectorAll('#log [data-extras="setup"], #log [data-extras="memory"]').forEach(form => {
        const ev = formEventFor(form);
        if (ev && ev.window) costLines(form, ev);
    });
}

// The extras in one form: "setup" (summaries, trackers, pictures, Watch, background model) or "story" (dice,
// story extras, the ideas button, pre-ticked by Bulba). Sent answers are applied at once.
function extrasForm(ev, live) {
    const dis = live ? '' : 'disabled';
    const v = { ...ev.values, ...(ev.answers || {}) };
    const radio = (name, options, current) => options.map(([val, label]) => `<label class="pill"><input type="radio"
        name="x_${name}" value="${val}" ${current === val ? 'checked' : ''} ${dis}><span>${esc(label)}</span></label>`).join('');
    const check = (name, label, on) => `<label class="pill"><input type="checkbox" name="x_${name}" ${on ? 'checked' : ''} ${dis}><span>${esc(label)}</span></label>`;
    const every = (name, item) => `<label class="every">every <input type="number" name="x_${name}_every" min="1" max="200"
        value="${esc((item || {}).interval || (name === 'summary' ? 10 : 2))}" ${dis}> messages</label>`;
    const row = (label, field, hint) => `<div class="form-row"><div class="form-label">${esc(label)}${hint ? `<small>${esc(hint)}</small>` : ''}</div>
        <div class="form-field">${field}</div></div>`;
    let rows;
    const cost = key => `<span class="help cost" data-cost="${key}"></span>`;
    const memoryRow = () => {
        if (!ev.window) return '';
        const steps = window.NACosts.steps(ev.window.max);
        return row('Chat memory', `<div class="memory"><input type="range" name="x_chat_context" min="0" max="${steps.length - 1}" step="1"
                value="${window.NACosts.nearest(steps, v.chat_context)}" ${dis}><b data-memory-value></b>${cost('chat')}</div>`,
            `how much of the chat ${ev.window.model || 'the model'} rereads for each reply; more remembers more and costs more`);
    };
    if (ev.part === 'memory') {
        rows = memoryRow();
    } else if (ev.part === 'setup') {
        rows = memoryRow()
            + row('Voices', ev.has_voice_key ? '<span class="help">On: your ElevenLabs key is saved.</span>'
                : '<a class="choice" href="/users/extras/" target="_blank" rel="noopener">Add an ElevenLabs key ↗</a> <span class="help">optional; never paste keys in this chat</span>')
            + row('Story summary', radio('summary', [['auto', 'Automatic'], ['manual', 'Only when I ask']], (v.summary || {}).mode) + every('summary', v.summary) + cost('summary'), 'keeps long chats on track')
            + row('Story trackers', radio('trackers', [['auto', 'Automatic'], ['manual', 'Only when I ask']], (v.trackers || {}).mode) + every('trackers', v.trackers) + cost('trackers'), 'keeps long, plot-heavy stories consistent: where, when, who, how they feel, what you carry')
            + row('Character pictures', check('sprites', 'Change with the mood', v.sprites), 'one small call per reply')
            + row('Bulba Watch', check('watch', 'On', v.watch), 'reads replies now and then for habits that repeat')
            + row('Fixing habits', radio('fix_model', [['bulba', "Bulba's model (cheaper)"], ['chat', 'My chat model (closer to its voice)']], v.fix_model || 'bulba'),
                  'only habits you approve get rewritten, in new replies')
            + ((ev.cheap_models || []).length ? row('Background jobs', `<select name="x_background" ${dis}>
                <option value="chat" ${v.background === 'chat' ? 'selected' : ''}>My chat model</option>
                ${ev.cheap_models.map(m => `<option value="${esc(m.id)}" ${v.background === m.id ? 'selected' : ''}>${esc(m.name)} (cheaper)</option>`).join('')}
              </select>`, 'summaries and trackers') : '');
    } else {
        rows = (ev.why ? `<p class="help form-why">🥔 ${esc(ev.why)}</p>` : '')
            + row('Chance', radio('game', [['off', 'No dice'], ['dice', 'Dice'], ['full', 'Dice, inventory and conditions']], v.game))
            + row('Story extras', (ev.kinds || []).map(k => `<label class="pill"><input type="checkbox" name="x_story_extras"
                value="${esc(k.id)}" ${(v.story_extras || []).includes(k.id) ? 'checked' : ''} ${dis}><span>${esc(k.label)}</span></label>`).join(''))
            + row("Bulba's ideas button", check('ideas', 'Show it by the message box', v.ideas))
            + (ev.trackers ? row(`Trackers for ${ev.character}`, ev.trackers.map(t => `<label class="pill" title="${esc(t.help)}"><input type="checkbox" name="x_trackers"
                value="${esc(t.id)}" ${(v.trackers || []).includes(t.id) ? 'checked' : ''} ${dis}><span>${t.icon} ${esc(t.label)}</span></label>`).join('')) : '');
    }
    return `<form class="basics-form extras-form" data-extras="${esc(ev.part)}">${rows}
        ${live ? '<div class="form-actions"><button type="submit">Save these</button><span class="help">All of it can be changed later on the Extras page.</span></div>' : ''}
      </form>`;
}

$('log').addEventListener('submit', e => {
    const form = e.target.closest('[data-extras]');
    if (!form) return;
    e.preventDefault();
    const part = form.dataset.extras;
    const get = n => form.querySelector(`[name="x_${n}"]`);
    const picked = n => (form.querySelector(`input[name="x_${n}"]:checked`) || {}).value;
    let answers;
    if (part === 'setup') {
        answers = { sprites: get('sprites').checked, watch: get('watch').checked, fix_model: picked('fix_model') };
        for (const t of ['summary', 'trackers']) {
            if (picked(t)) answers[t] = { mode: picked(t), interval: Number(get(`${t}_every`).value) || undefined };
        }
        if (get('background')) answers.background = get('background').value;
    }
    if (part === 'setup' || part === 'memory') {
        answers = answers || {};
        const memory = get('chat_context'), formEv = formEventFor(form);
        if (memory && formEv && formEv.window) answers.chat_context = window.NACosts.steps(formEv.window.max)[Number(memory.value)];
    } else {
        answers = { game: picked('game'), ideas: get('ideas').checked,
                    story_extras: [...form.querySelectorAll('input[name="x_story_extras"]:checked')].map(b => b.value) };
        if (form.querySelector('input[name="x_trackers"]'))
            answers.trackers = [...form.querySelectorAll('input[name="x_trackers"]:checked')].map(b => b.value);
    }
    const formEvent = [...events].reverse().find(ev => ev.type === 'extras_form' && ev.part === part);
    if (formEvent) formEvent.answers = answers;  // the sent form keeps showing what they picked
    run({ action: 'extras_form', part, answers }, 'Saving…');
});

// When setup is done: the way into the chat, and where pictures go
function doneBlock() {
    if (state.stage !== 'done' || !state.chat) return '';
    return `<div class="done-block">
        <a class="btn" href="${esc(state.chat.url)}">Start chatting with ${esc(state.chat.name)} →</a>
        <a class="ghost-link" href="${esc(state.chat.edit_url)}">Add pictures for ${esc(state.chat.name)}</a>
      </div>`;
}

// Their last message when only errors came after it (mainapp/bulba/agent.py failed_tail)
function failedTail() {
    let idx = -1;
    for (let i = events.length - 1; i >= 0; i--) if (events[i].type === 'user') { idx = i; break; }
    if (idx < 0 || idx === events.length - 1) return null;
    return events.slice(idx + 1).every(e => e.type === 'error') ? idx : null;
}
async function copyText(text, btn) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {  // older phones: the selection way
        const t = document.createElement('textarea'); t.value = text; document.body.append(t); t.select();
        try { document.execCommand('copy'); } catch (e2) {} t.remove();
    }
    if (btn) { const was = btn.textContent; btn.textContent = '✓ Copied'; setTimeout(() => { btn.textContent = was; }, 1200); }
}
document.addEventListener('click', e => {
    const c = e.target.closest('[data-copy]');
    if (c && events[Number(c.dataset.copy)]) { copyText(events[Number(c.dataset.copy)].text || '', c); return; }
    const f = e.target.closest('[data-failed]');
    if (f && !busy) run({ action: f.dataset.failed === 'retry' ? 'retry_failed' : 'remove_failed' },
                        f.dataset.failed === 'retry' ? 'Trying again…' : 'Removing…');
});

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
                : c.route  // the opening's full setup / fast route: handled without Bulba's model
                ? `<button type="button" class="choice${c.hint ? ' with-hint' : ''}" data-route="${esc(c.route)}" data-label="${esc(c.label)}" ${liveChoices(i) ? '' : 'disabled'}>${esc(c.label)}${c.hint ? `<small>${esc(c.hint)}</small>` : ''}</button>`
                : `<button type="button" class="choice" data-say="${esc(c.label)}" ${liveChoices(i) ? '' : 'disabled'}>${esc(c.label)}</button>`).join('');
            return `<div class="msg bulba"><span class="potato">🥔</span><div class="bubble">${fmt(ev.text)}
                    ${choices ? `<div class="choices">${choices}</div>` : ''}</div></div>`;
        }
        if (ev.type === 'user') return `<div class="msg user"><div class="bubble">${esc(ev.text)}</div>
            <button type="button" class="msg-copy" data-copy="${i}" title="Copy">📋</button></div>`;
        if (ev.type === 'picture') return `<div class="msg user"><div class="bubble picture-bubble">
                <img src="${esc(ev.src)}" alt="Your picture">${ev.text ? `<div>${esc(ev.text)}</div>` : ''}</div></div>`;
        if (ev.type === 'action') return `<div class="action">${esc(ev.text)}</div>`;
        if (ev.type === 'note') return `<div class="note">✓ ${esc(ev.text)}</div>`;
        if (ev.type === 'watch') return '';  // sent to the chat page (Bulba switched Watch)
        if (ev.type === 'error') {  // the last thing on the page after their message: try it again, copy it, or drop it
            const failed = i === events.length - 1 && failedTail() !== null && !busy;
            return `<div class="error">${esc(ev.text)}${failed ? `<div class="error-actions">
                <button type="button" data-failed="retry">↻ Try again</button>
                <button type="button" class="ghost" data-copy="${failedTail()}">📋 Copy my message</button>
                <button type="button" class="ghost" data-failed="remove">🗑 Remove it</button></div>` : ''}</div>`;
        }
        if (ev.type === 'stage') return `<div class="stage-mark">${esc(STAGE_LABELS[ev.stage] || ev.stage)}</div>`;
        if (ev.type === 'proposal') return proposalCard(ev);
        if (ev.type === 'card_upload') {
            const live = i === types.lastIndexOf('card_upload') && i > answeredUpTo && !busy;
            return `<form class="card-upload" data-card-upload>
                <label>Your card <small>(.png or .json, from SillyTavern, Chub and the like)</small>
                <input type="file" name="card" accept=".png,.json,image/png,application/json" ${live ? '' : 'disabled'}></label>
                <button type="submit" ${live ? '' : 'disabled'}>Import</button></form>`;
        }
        if (ev.type === 'preset_upload') {
            const live = i === types.lastIndexOf('preset_upload') && i > answeredUpTo && !busy;
            return `<form class="card-upload" data-preset-upload>
                <label>Your preset <small>(.json: a SillyTavern chat-completion preset, or one exported from here)</small>
                <input type="file" name="preset" accept=".json,application/json" ${live ? '' : 'disabled'}></label>
                <button type="submit" ${live ? '' : 'disabled'}>Import</button></form>`;
        }
        if (ev.type === 'make_pictures') return `<div class="make-pictures" data-url="${esc(ev.url)}" data-moods="${esc(ev.moods.join(','))}">
            <button type="button" data-make-pictures>🎨 Make ${ev.moods.length} mood picture${ev.moods.length === 1 ? '' : 's'} of ${esc(ev.name)}</button>
            <small>A few cents each, on your key. About 15 seconds per picture.${ev.later_url ? ` Later is fine too: the
              <a href="${esc(ev.later_url)}" target="_blank" rel="noopener">character's page</a> has a “✨ Make the missing moods” button, or ask me in any chat.` : ''}</small><div class="progress"></div></div>`;
        if (ev.type === 'downloads') return `<div class="downloads">⬇ ${(ev.links || []).map(l =>
            `<a href="${esc(l.url)}" download>${esc(l.label)}</a>`).join('')}</div>`;
        if (ev.type === 'form') return basicsForm(i === types.lastIndexOf('form') && i > answeredUpTo && !busy, ev.answers);
        if (ev.type === 'extras_form') return extrasForm(ev, i === types.lastIndexOf('extras_form') && i > answeredUpTo && !busy && !ev.answers);
        if (ev.type === 'lookup') return `<div class="lookup">🔎 Looked up “${esc(ev.query)}”${(ev.sources || []).length
            ? ': ' + ev.sources.map(src => `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.title || src.url)}</a>`).join(', ') : ''}</div>`;
        if (ev.type === 'samples') {
            const live = i === lastSamples && i > answeredUpTo && !busy;
            const single = ev.samples.length === 1;
            return `<div class="samples">
                <div class="samples-head">Written by <b>${esc(ev.model)}</b>${ev.character ? ` as ${esc(ev.character)}` : ''}</div>
                ${ev.scenario ? `<div class="samples-scene">${esc(ev.scenario)}<br><i>You: ${esc(ev.user_turn)}</i></div>` : ''}
                <div class="sample-grid">${ev.samples.map(s => `
                    <div class="sample"><div class="sample-label">${esc(s.label)}</div><div class="sample-text">${fmtSample(s.text)}</div>
                    ${live && ev.samples.length > 1 ? `<button type="button" data-say="I prefer ${esc(s.label)}.">This one</button>` : ''}</div>`).join('')}</div>
                ${live && ev.samples.length > 1 ? `<div class="sample-actions">
                    <button type="button" class="ghost" data-say="I like both.">Both</button>
                    <button type="button" class="ghost" data-say="Neither of these.">Neither</button>
                    <button type="button" class="ghost" data-say="A bit of both. ">A bit of both…</button>
                    <button type="button" class="ghost" data-say="No preference, skip this one.">Skip</button></div>` : ''}
                ${ev.retry_id && !ev.used && window.parent !== window ? `<div class="sample-actions">
                    <button type="button" data-use-retry="${esc(ev.retry_id)}">Use this in the chat</button></div>` : ''}
                ${live && single ? `<div class="sample-actions">
                    <span class="sample-ask">How does it read?</span>
                    <button type="button" data-say="I like it.">👍 Like it</button>
                    <button type="button" class="ghost" data-say="I like it, but ">👍 Like it, but…</button>
                    <button type="button" class="ghost" data-say="Not quite: ">👎 Not quite…</button></div>` : ''}
              </div>`;
        }
        return '';
    }).join('') + doneBlock();
    fillCosts();
    $('log').scrollTop = $('log').scrollHeight;
    renderPanel();
}

// The setup's stages: done (green), skipped, the current one with its small steps, and what's left
function renderStages() {
    const pr = state.progress;
    if (!pr) {
        const current = state.stages.indexOf(state.stage);
        $('stages').innerHTML = state.stages.map((s, i) =>
            `<li class="${i < current ? 'done' : i === current ? 'current' : ''}">${esc(STAGE_LABELS[s] || s)}</li>`).join('');
        return;
    }
    const finished = state.stage === 'done';
    $('progressLine').textContent = finished ? 'All done. You can still change anything.'
        : `Step ${pr.step} of ${pr.of}` + (pr.questions_left ? ` · about ${pr.questions_left} question${pr.questions_left === 1 ? '' : 's'} left` : '');
    $('stages').innerHTML = pr.stages.map(st => {
        const mark = { done: '✓', skipped: '⤼', current: '●', todo: '' }[st.status];
        const steps = st.status === 'current' && st.steps.length > 1 ? `<ul class="steps">${st.steps.map(x =>
            `<li class="${x.done ? 'done' : ''}">${x.done ? '✓' : '◻'} ${esc(x.label)}${x.optional ? ' <i>(optional)</i>' : ''}</li>`).join('')}</ul>` : '';
        const hint = ['current', 'todo'].includes(st.status) ? `<small>${esc(st.hint)}</small>` : '';
        const note = st.status === 'skipped' ? ' <i>skipped</i>' : '';
        return `<li class="${st.status}"><span class="mark">${mark}</span><div><span class="stage-name">${esc(st.label)}</span>${note}${hint}${steps}</div></li>`;
    }).join('');
    $('miniProgress').hidden = false;
    $('miniProgressText').textContent = `${$('progressLine').textContent}` + (finished ? '' : ` · ${pr.stages[pr.step - 1].label}`);
    $('miniSkip').hidden = !pr.can_skip;
    $('miniSkip').disabled = busy;
    $('skipBtn').hidden = !pr.can_skip;
    $('skipBtn').disabled = busy;
    $('skipTip').hidden = !pr.can_skip;
}

function renderPanel() {
    $('modelName').textContent = state.model;
    renderStages();
    $('spent').textContent = `$${state.spent.toFixed(2)}`;
    $('budget').textContent = `$${state.budget.toFixed(2)}`;
    $('meterFill').style.width = `${Math.min(100, state.spent / state.budget * 100)}%`;
    $('panelChat').innerHTML = state.chat
        ? `<a class="btn" href="${esc(state.chat.url)}">Chat with ${esc(state.chat.name)} →</a>` : '';
    if (state.month) $('monthLine').textContent =
        `All AI use this month (chat and Bulba): $${state.month.spent.toFixed(2)} of $${state.month.limit.toFixed(2)}.`;
    $('prefs').innerHTML = state.preferences.length ? state.preferences.map(p => `
        <li><span>${esc(p.interpretation)}${p.status === 'tentative' ? ' <i>(guess)</i>' : ''}</span>
            <span class="pref-btns"><button type="button" class="x" data-edit-pref="${p.id}" title="Change the wording">✎</button>
            <button type="button" class="x" data-forget="${p.id}" title="Forget this">✕</button></span></li>`).join('')
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

// After a dropped connection: Bulba keeps working on the server, so wait for it and show what it did
async function recover(before) {
    $('thinkingText').textContent = '📶 The connection dropped, but Bulba keeps working. Waiting for its answer…';
    const sep = BULBA_API.includes('?') ? '&' : '?';
    for (let i = 0; i < 120; i++) {  // up to six minutes: longer than any turn can take
        await new Promise(r => setTimeout(r, 3000));
        try {
            const resp = await fetch(BULBA_API + sep + 'full=1', { headers: { 'Accept': 'application/json' } });
            const data = await resp.json();
            if (data.busy) { if (data.activity) $('thinkingText').textContent = '📶 ' + data.activity; continue; }
            if (!data.events || data.events.length <= before) return false;  // it didn't get to finish
            events = data.events;
            state = data.state;
            if (window.parent !== window) window.parent.postMessage({ quickBulba: 'changed' }, window.location.origin);
            return true;
        } catch (e) { /* still offline: try again */ }
    }
    return false;
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
            const changed = (data.state.proposals || []).find(x => x.id === body.id);
            // A fixed message changes what the chat shows: the page reloads with Bulba still open
            window.parent.postMessage({ bulba: changed && changed.kind === 'message_fix' ? 'reply' : body.action },
                                      window.location.origin);
        }
        if (window.parent !== window && data.watch) window.parent.postMessage({ watch: data.watch }, window.location.origin);
        // Bulba switched Watch on or off: the chat page shows it at once
        const switched = (data.events || []).filter(ev => ev.type === 'watch' && ev.watch).pop();
        if (window.parent !== window && switched) window.parent.postMessage({ watch: switched.watch }, window.location.origin);
        if (body.action === 'say') events.pop();  // the server sends it back with the rest
        events = (body.action === 'restart' || data.replace) ? data.events : events.concat(data.events);
        const wasDone = state.stage === 'done';
        state = data.state;
        // Beside Quick setup: the form shows what Bulba just set (a character, persona, worldbook, extras…)
        if (window.parent !== window) window.parent.postMessage({ quickBulba: 'changed' }, window.location.origin);
        // …and when Bulba says it's all set, the panel closes so "Save and start chatting" is in view
        if (BESIDE_QUICK && !wasDone && state.stage === 'done')
            window.parent.postMessage({ quickBulba: 'done' }, window.location.origin);
    } catch (err) {
        if (body.action === 'say') events.pop();
        const recovered = err.lost && await recover(events.length);
        if (!recovered && body.action === 'say' && !$('input').value.trim()) $('input').value = body.text;  // not lost
        if (!recovered)
            events.push({ type: 'error', text: err.lost ? "The connection dropped and Bulba didn't get to finish that one. Send it again." : err.message });
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
    fitInput(false);
    say(text);
});
$('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('composer').requestSubmit(); }
});

$('log').addEventListener('click', e => {
    const routeBtn = e.target.closest('[data-route]');
    if (routeBtn && !routeBtn.disabled && !busy && routeBtn.dataset.route === 'fast') {
        window.top.location.href = QUICK_URL;  // the quick way is a short form of its own
        return;
    }
    if (routeBtn && !routeBtn.disabled && !busy) {
        run({ action: 'route', route: routeBtn.dataset.route }, routeBtn.dataset.route.startsWith('fast:') ? 'Setting it up…' : 'One moment…');
        return;
    }
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
    t.textContent = t.textContent.replace(chips.hidden ? 'Hide' : 'Show', chips.hidden ? 'Show' : 'Hide');
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
    const form = e.target.closest('[data-preset-upload]');
    if (!form) return;
    e.preventDefault();
    const file = form.querySelector('input[type=file]').files[0];
    if (!file) return;
    const body = new FormData();
    body.append('preset', file);
    run(body, 'Importing your preset…');
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
    const formEvent = [...events].reverse().find(ev => ev.type === 'form');
    if (formEvent) formEvent.answers = answers;  // keep the choices visible while Bulba reads them
    run({ action: 'basics', answers }, 'Bulba is reading your answers…');
});

$('prefs').addEventListener('click', async e => {
    const edit = e.target.closest('[data-edit-pref]');
    if (edit) {
        const pref = state.preferences.find(p => p.id === edit.dataset.editPref);
        const text = pref && await NADialog.prompt('How should Bulba remember this?', pref.interpretation,
                                                   { multiline: true, ok: 'Save' });
        if (!text || !text.trim() || text.trim() === pref.interpretation) return;
        try { state = (await api({ action: 'edit_preference', id: pref.id, text: text.trim() })).state; renderPanel(); }
        catch (err) { alert(err.message); }
        return;
    }
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

document.querySelectorAll('#restartBtn, [data-restart]').forEach(b => b.onclick = async () => {
    if (await NADialog.confirm('Start the conversation over? Anything you already applied stays.', { ok: 'Start over' })) run({ action: 'restart' });
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

// Opened from the chat's pen menu with something already typed: put it in the box, unsent.
// Or from a Bulba Watch note: Bulba looks at it straight away.
(function () {
    // (the box then grows to fit it, as when typing)
    const fill = (text) => {
        if (!text) return;
        $('input').value = text;
        $('input').focus();
        setTimeout(() => $('input').dispatchEvent(new Event('input')), 0);  // after the box's resize handler exists
    };
    const note = (id) => { if (id) run({ action: 'note', id }, 'Bulba is looking at it…'); };
    const params = new URLSearchParams(window.location.search);
    fill(params.get('draft'));
    note(params.get('note'));
    window.addEventListener('message', (e) => {
        if (e.origin !== window.location.origin || !e.data) return;
        if (e.data.bulbaDraft) fill(e.data.bulbaDraft);
        if (e.data.bulbaNote) note(e.data.bulbaNote);
    });
})();

// Pictures: just to show Bulba, or the character's (neutral or a mood) or a background, applied at once (Undo on the card)
(function () {
    const form = $('pictureForm');
    if (!form) return;
    $('attachBtn').onclick = () => {
        form.hidden = !form.hidden;
        // Their character has no picture yet (Bulba usually just asked for it): a picture sent now is that one
        if (!form.hidden && typeof state !== 'undefined' && state && state.needs_portrait) $('pictureAs').value = 'neutral';
    };
    $('pictureCancel').onclick = () => { form.hidden = true; };
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const file = $('pictureFile').files[0];
        if (!file) return;
        const body = new FormData();
        body.append('picture', file);
        body.append('as', $('pictureAs').value);
        body.append('text', $('pictureText').value.trim());
        const looking = $('pictureAs').value === 'look';
        form.hidden = true;
        $('pictureFile').value = ''; $('pictureText').value = '';
        run(body, looking ? 'Bulba is looking at the picture…' : 'Adding the picture…');
    });
})();

// Mood pictures, one at a time, from the neutral one (the character page's picture maker, step by step)
$('log').addEventListener('click', async e => {
    const btn = e.target.closest('[data-make-pictures]');
    if (!btn) return;
    const box = btn.closest('.make-pictures'), progress = box.querySelector('.progress');
    const moods = box.dataset.moods.split(',');
    btn.disabled = true;
    let made = 0;
    for (const mood of moods) {
        progress.textContent = `Making ${mood}… (${made + 1} of ${moods.length})`;
        try {
            const resp = await fetch(box.dataset.url, { method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ emotion: mood }) });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || 'The picture maker failed.');
            made += 1;
            progress.insertAdjacentHTML('afterend', `<img class="made" src="${esc(data.url)}" alt="${esc(mood)}" title="${esc(mood)}">`);
        } catch (err) {
            progress.textContent = `Stopped at ${mood}: ${err.message}`;
            btn.disabled = false;
            return;
        }
    }
    progress.textContent = `Done: ${made} picture${made === 1 ? '' : 's'}. They show in chats from the next reply.`;
});

// Edit / save / cancel on a proposal
$('log').addEventListener('click', async e => {
    const open = e.target.closest('[data-edit-proposal]');
    if (open && !busy) { editingId = open.dataset.editProposal; render(); return; }
    if (e.target.closest('[data-cancel-edit]')) { editingId = null; render(); return; }
    const save = e.target.closest('[data-save-edit]');
    if (!save || busy) return;
    const box = save.closest('[data-editor]');
    const values = {};
    box.querySelectorAll('[data-path]').forEach(el => { values[el.dataset.path] = el.value; });
    save.disabled = true;
    try {
        const data = await api({ action: 'edit_proposal', id: save.dataset.saveEdit, values });
        state = data.state;
        events.push(...(data.events || []));
        editingId = null;
        render();
    } catch (err) { alert(err.message); save.disabled = false; }
});

// A rewritten reply goes into the chat as a new version of the last reply; the chat page reloads to show it
$('log').addEventListener('click', async e => {
    const btn = e.target.closest('[data-use-retry]');
    if (!btn || busy) return;
    btn.disabled = true;
    try {
        const data = await api({ action: 'use_retry', id: btn.dataset.useRetry });
        const ev = events.find(x => x.retry_id === btn.dataset.useRetry);
        if (ev) ev.used = true;
        events = events.concat(data.events || []);
        state = data.state;
        render();
        window.parent.postMessage({ bulba: 'reply' }, window.location.origin);
    } catch (err) { alert(err.message); btn.disabled = false; }
});

// --------------------------------------------------------------- skipping
if ($('skipBtn')) {
    const skip = () => { if (!busy) run({ action: 'skip' }, 'Skipping…'); };
    $('skipBtn').addEventListener('click', skip);
    $('miniSkip').addEventListener('click', skip);
}

// Beside the Quick setup form: the ✕ closes the panel (the form reloads to show what Bulba applied)
document.querySelector('[data-embed-close]')?.addEventListener('click', () => {
    window.parent.postMessage({ quickBulba: 'close' }, window.location.origin);
});

// The message box grows with the text (up to ~40% of the screen); ⤢ opens it nearly full height for long texts
function fitInput(big) {
    const box = $('input'), wrap = box.closest('.composer-field');
    if (typeof big === 'boolean') wrap.classList.toggle('big', big);
    const isBig = wrap.classList.contains('big');
    $('growBtn').textContent = isBig ? '⤡' : '⤢';
    $('growBtn').title = isBig ? 'Back to a small box' : 'A bigger box, for longer texts';
    box.style.height = 'auto';
    if (!isBig) box.style.height = Math.min(box.scrollHeight + 2, window.innerHeight * 0.4) + 'px';
}
$('input').addEventListener('input', () => fitInput());
$('growBtn').addEventListener('click', () => { fitInput(!$('input').closest('.composer-field').classList.contains('big')); $('input').focus(); });

// Opened again from the browser's back/forward memory (phones keep pages): the conversation may have moved on
// meanwhile (Bulba beside Quick setup, another tab), so load it fresh instead of showing an old copy
window.addEventListener('pageshow', (e) => { if (e.persisted) window.location.reload(); });
