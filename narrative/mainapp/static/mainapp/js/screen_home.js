/* Home and mini-apps share a shell, not hidden background generations. */
(() => {
  'use strict';
  const apps = [
    ['messenger','TeleChat','↗','#387795'], ['scenes','Scenes','▣','#785eaa'],
    ['subtext','Subtext','@','#53699b'], ['files','Drive','▰','#b9935b'],
    ['mail','Mail','✉','#708bb2'], ['wave','Wave','♫','#967b95'],
    ['pulse','Pulse','▦','#6b998d'], ['moments','Moments','✧','#9b778f'],
  ];
  const roots = {files:'screenDriveRoot', mail:'screenMailRoot', pulse:'screenPulseRoot', wave:'screenWaveRoot'};
  const kinds = {files:'document',mail:'mail',pulse:'event',wave:'track'};
  const descriptions = {
    files:'Documents, private scratchpads, and an archive of what was actually shared in this chat.',
    mail:'Longer correspondence with the participants of this chat. Draft, review, then deliver.',
    pulse:'Keep plans for this story. Dates use your device’s timezone; plans do not send automatic messages.',
    wave:'A shared playlist and the voice notes already sent in this chat. Playback starts only when you press play.',
  };
  const S = {app:'home',thread:null,cache:new Map(),epochs:new Map(),selection:new Map(),dirtyThreads:new Set(),busy:false,errors:new Map(),tab:'documents',overview:null};
  const icons = {
    messenger:'M4 5h16v11H9l-5 4V5z M8 9h8 M8 12h5',
    scenes:'M4 8h16v12H4z M4 8V4h16v4 M8 4l-2 4 M14 4l-2 4 M20 4l-2 4 M10 12l5 3-5 3z',
    subtext:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c-5 5-5 13 0 18 M12 3c5 5 5 13 0 18',
    files:'M3 6V4h7l2 3h9v13H3V6z M3 10h18',
    mail:'M3 5h18v14H3z M3 6l9 7 9-7',
    wave:'M4 14v-3a8 8 0 0 1 16 0v3 M4 12h3v8H4z M17 12h3v8h-3z',
    pulse:'M4 5h16v16H4z M4 10h16 M8 3v4 M16 3v4 M8 14h1 M12 14h1 M16 14h1 M8 18h1 M12 18h1',
    moments:'M12 3l3 6 6 3-6 3-3 6-3-6-6-3 6-3z',
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button = (label, action, attrs='') => `<button type="button" data-action="${action}" ${attrs}>${label}</button>`;
  const url = value => {
    if (!value) return '';
    try {const result = new URL(value, location.origin); return ['http:','https:'].includes(result.protocol) ? result.href : '';} catch (_) {return '';}
  };
  const date = value => {const d = new Date(value); return Number.isNaN(+d) ? String(value || 'No date') : d.toLocaleString([], {dateStyle:'medium',timeStyle:'short'});};
  const name = id => {const t = TG.state.threads.find(t => String(t.id) === String(id)); return t?.chat_name || t?.title || 'Chat';};
  const cache = () => S.cache.get(String(S.thread));
  const selectKey = () => `${S.thread}:${S.app}`;
  const selected = () => S.selection.get(selectKey()) || 'new';
  const current = () => cache()?.entries.find(e => String(e.id) === selected());
  const draftKey = () => `apps:${S.thread}:${S.app}:${selected()}`;
  async function request(body=null, params={}) {
    const endpoint = new URL(TG_CFG.screen_apps_api, location.origin);
    Object.entries(params).forEach(([key,value]) => endpoint.searchParams.set(key,value));
    const response = await fetch(endpoint, body ? {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':TG_CFG.csrf},body:JSON.stringify(body)} : {});
    let data; try {data = await response.json();} catch (_) {throw new Error('The server could not save this request. Your local draft is kept.');}
    if (!response.ok) {const error = new Error(data.error || 'Request failed. Your draft is kept.'); error.current = data.current; throw error;}
    return data;
  }
  function toast(message) {const el = document.getElementById('screenAppStatus');el.hidden=false;el.textContent=message;clearTimeout(S.toastTimer);S.toastTimer=setTimeout(()=>el.hidden=true,6000);}
  function tick() {
    const now = new Date();
    document.getElementById('screenHomeTime').textContent=now.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
    document.getElementById('screenHomeDate').textContent=now.toLocaleDateString([], {weekday:'long',day:'numeric',month:'long'});
  }
  function home() {
    const grid = document.getElementById('screenAppGrid');
    grid.innerHTML=apps.map(([id,label,icon,color])=>`<button type="button" class="screen-app-tile" data-open="${id}"><span class="screen-app-symbol" style="--icon:${color}"><svg aria-hidden="true" width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"><path d="${icons[id]}"></path></svg></span><span>${label}</span></button>`).join('');
    document.getElementById('screenRecentChats').innerHTML=TG.state.threads.slice(0,3).map(t=>`<button type="button" class="screen-recent" data-thread="${esc(t.id)}"><span>${esc(t.chat_name || t.title || 'Chat')}</span><small>${Number(t.unread)>0 ? esc(t.unread)+' unread' : 'Open ↗'}</small></button>`).join('') || '<p class="screen-muted">Your conversations will appear here. Open TeleChat to start one.</p>';
    const data=S.overview;
    document.getElementById('screenDeskSummary').innerHTML=data ? `<div class="screen-desk-stats"><div><strong>${esc(data.documents)}</strong><span>documents</span></div><div><strong>${esc(data.events)}</strong><span>open plans</span></div><div><strong>${esc(data.mail)}</strong><span>mail subjects</span></div></div>` : '<p class="screen-muted">Open Drive, Mail, or Pulse to start filling your desk.</p>';
  }
  async function overview() {try {S.overview=await request(null,{action:'overview'});home();} catch (_) {home();}}
  async function load(force=false) {
    const thread=String(S.thread);
    if (!thread || thread==='null') return render();
    if(S.cache.has(thread) && !force) return;
    const epoch=(S.epochs.get(thread)||0)+1;S.epochs.set(thread,epoch);
    try {const data=await request(null,{thread_id:thread});if(S.epochs.get(thread)!==epoch)return;if(thread===String(S.thread)) capture();S.cache.set(thread,data);if(thread===String(S.thread)) render();}
    catch(error) {if(thread===String(S.thread)) {S.errors.set(selectKey(),{message:error.message});render();}}
  }
  function field(label, id, value='', type='input', extra='') {
    const control=type==='textarea' ? `<textarea id="${id}" data-screen-field="${id}" ${extra}>${esc(value)}</textarea>` : `<input id="${id}" data-screen-field="${id}" value="${esc(value)}" ${extra}>`;
    return `<div class="screen-field"><label for="${id}">${label}</label>${control}</div>`;
  }
  function header() {
    const title=apps.find(a=>a[0]===S.app)?.[1];
    return `<header class="screen-mini-header"><div>${button('⌂ Home','home')}<h1>${esc(title)}</h1><p>${esc(descriptions[S.app])}</p></div><div class="screen-context"><label for="screenAppThread">Story / chat<select id="screenAppThread">${TG.state.threads.map(t=>`<option value="${esc(t.id)}" ${String(t.id)===String(S.thread)?'selected':''}>${esc(t.chat_name||t.title||'Chat')}</option>`).join('')}</select></label>${button('Refresh','refresh')}</div></header>`;
  }
  function editor(item) {
    const kind=kinds[S.app];
    let html = item?.kind==='mail' ? mail(item) : field('Title','miniTitle',item?.title || '', 'input','maxlength="200"');
    if(kind==='document') {
      html+=`<label for="miniScope">Who can read it?<select id="miniScope" data-screen-field="miniScope"><option value="private" ${item?.data.scope!=='shared'?'selected':''}>Private scratchpad — only you</option><option value="shared" ${item?.data.scope==='shared'?'selected':''}>Shared with this chat’s characters</option></select></label>`;
      html+=field('Document','miniBody',item?.body || '','textarea','maxlength="30000"');
    } else if(kind==='event') {
      let when='';if(item?.data.when) {const d=new Date(item.data.when);when=new Date(+d-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
      html+=field('When (your device’s local time)','miniWhen',when,'input','type="datetime-local" required');
      html+=field('Place','miniLocation',item?.data.location || '','input','maxlength="200"');
      html+=field('Notes','miniBody',item?.body || '','textarea','maxlength="30000"');
      html+=`<label for="miniDone">Status<select id="miniDone" data-screen-field="miniDone"><option value="false" ${!item?.data.done?'selected':''}>Planned</option><option value="true" ${item?.data.done?'selected':''}>Done</option></select></label><p class="screen-muted">Visible to this chat’s characters. This records a plan; it does not confirm attendance or trigger a call.</p>`;
    } else if(kind==='track') {
      html+=field('Artist','miniArtist',item?.data.artist || '','input','maxlength="200"');
      html+=field('Track link (optional)','miniUrl',item?.data.url || '','input','type="url" placeholder="https://…" maxlength="2000"');
      html+=field('Why this track / mood','miniBody',item?.body || '','textarea','maxlength="30000"');
      html+='<p class="screen-muted">Links open on the music service. Wave does not download or autoplay external songs.</p>';
    } else if(kind==='mail' && !item) {
      html+='<p class="screen-muted">Create a subject, then write the first letter. Correspondence is kept separate until you explicitly forward it to TeleChat.</p>';
    }
    if(kind!=='mail' || !item) html+=`<div class="screen-actions">${button(item?'Save changes':'Create '+({document:'document',event:'plan',track:'track',mail:'subject'}[kind]),'save','class="screen-primary"')}${item?button('Delete…','delete'):''}</div>`;
    if(item && ['document','track'].includes(kind)) html+=`<div class="screen-actions">${button('Send a copy to TeleChat…','forward')}</div>`;
    const error=S.errors.get(selectKey());
    if(error) html+=`<div class="screen-error" role="alert">${esc(error.message)}</div>` + (error.current ? `<details class="screen-preview"><summary>Review saved version</summary><pre>${esc(JSON.stringify(error.current,null,2))}</pre>${button('Load saved version (replaces this draft)…','reload-record')}</details>` : '');
    return `<fieldset class="screen-form" ${S.busy?'disabled':''} style="border:0;margin:0;padding:0;min-width:0" aria-busy="${S.busy}">${html}</fieldset>`;
  }
  function mail(item) {
    const members=TG.state.threads.find(t=>String(t.id)===String(S.thread))?.member_slugs || [];
    return `<h2>${esc(item.title)}</h2><p class="screen-muted">Correspondence for ${esc(name(S.thread))}. Character replies are previews until delivered.</p>`+
      (item.data.messages||[]).map(m=>`<article class="screen-letter"><strong>${esc(m.sender)}</strong> <small>${esc(date(m.at))}</small><p>${esc(m.body)}</p></article>`).join('')+
      field('Write a letter','miniLetter','','textarea','maxlength="30000"')+
      `<div class="screen-actions">${button('Send my letter','send-mail','class="screen-primary"')}${button('Forward correspondence to TeleChat…','forward')}</div>`+
      `<details><summary>Draft a character reply</summary><p class="screen-muted">One model request. Review and edit the preview before delivering it.</p><label for="miniCharacter">From<select id="miniCharacter" data-screen-field="miniCharacter">${TG.state.characters.filter(c=>members.includes(c.slug)).map(c=>`<option value="${esc(c.slug)}">${esc(c.name)}</option>`).join('')}</select></label>`+
      field('Direction (optional)','miniDirection','','textarea','maxlength="2000"')+button('Draft reply · uses model tokens','draft-mail')+`</details><div id="miniMailPreview"></div><div class="screen-actions">${button('Delete subject…','delete')}</div>`;
  }
  function receipt(r) {
    const p=r.payload;
    let body='';
    if(r.kind==='file') body=`<pre>${esc(p.content || '')}</pre>`;
    if(r.kind==='photo') body=url(p.url) ? `<img loading="lazy" src="${esc(url(p.url))}" alt="${esc(p.caption || 'Shared photo')}">` : '<p class="screen-muted">Picture not rendered. Open its message in TeleChat to generate it.</p>';
    if(r.kind==='voice') body=`<pre>${esc(p.transcript || '')}</pre>`+(url(p.audio_url) ? `<audio controls preload="none" src="${esc(url(p.audio_url))}"></audio>` : '<p class="screen-muted">No saved audio. Open the message in TeleChat if you want to generate it.</p>');
    return `<article class="screen-receipt"><h3>${esc(p.name || p.caption || ({file:'Document',photo:'Photo',voice:'Voice note'}[r.kind]))}</h3><small class="screen-muted">${esc(r.sender)} · ${esc(r.time)}</small>${body}${button('Open source message','source',`data-id="${esc(r.id)}"`)}</article>`;
  }
  function render() {
    const root=document.getElementById(roots[S.app]); if(!root) return;
    let html=header();
    if(!S.thread) {root.innerHTML=html+'<p class="screen-empty">Start a TeleChat conversation to give this app a story context.</p>';return;}
    const data=cache();
    if(!data) {root.innerHTML=html+`<p class="screen-empty">${esc(S.errors.get(selectKey())?.message || 'Opening your saved workspace…')}</p>`;return;}
    const kind=kinds[S.app];
    if(S.app==='files') html+=`<nav class="screen-tabs" aria-label="Drive views">${[['documents','Documents'],['receipts','Chat archive'],['legacy','Earlier personal notes']].map(([v,l])=>button(l,'tab',`data-tab="${v}" aria-pressed="${S.tab===v}"`)).join('')}</nav>`;
    if(S.app==='files' && S.tab==='receipts') html+=`<section class="screen-card"><h2>Shared in ${esc(name(S.thread))}</h2><p class="screen-muted">Live archive of the latest 200 delivered attachments. Deleted messages disappear here too; no private drafts are imported.</p>${data.receipts.length?data.receipts.slice().reverse().map(receipt).join(''):'<p class="screen-empty">No shared files, photos, or voice notes yet.</p>'}</section>`;
    else if(S.app==='files' && S.tab==='legacy') html+=`<section class="screen-card"><h2>Earlier personal notes</h2><p class="screen-muted">Account-wide notes from the original Files app, kept read-only here. These are private.</p>${data.legacy_notes.map(n=>`<article class="screen-receipt"><h3>${esc(n.title)}</h3><pre>${esc(n.text)}</pre></article>`).join('') || '<p class="screen-empty">No earlier notes.</p>'}</section>`;
    else {
      let entries=data.entries.filter(e=>e.kind===kind);
      if(kind==='event') entries=entries.slice().sort((a,b)=>new Date(a.data.when)-new Date(b.data.when));
      html+=`<div class="screen-app-columns"><aside class="screen-card"><h2>${{document:'Documents',mail:'Correspondence',event:'Plans',track:'Playlist'}[kind]}</h2>${button('+ New '+{document:'document',mail:'subject',event:'plan',track:'track'}[kind],'new')}${entries.map(e=>`<button type="button" class="screen-record" data-action="select" data-id="${esc(e.id)}" aria-current="${String(e.id)===selected()}"><strong>${esc(e.title)}</strong><small>${esc(kind==='event'?(e.data.done?'Done · ':'')+date(e.data.when):kind==='document'?(e.data.scope==='shared'?'Shared with this chat':'Private scratchpad'):kind==='mail'?(e.data.messages||[]).length+' letters':e.data.artist || 'Track')}</small></button>`).join('')}${data.total>200?'<p class="screen-muted">Showing the latest 200 records in this chat.</p>':''}</aside><section class="screen-card">${editor(current())}</section></div>`;
      if(kind==='track') {
        const voices=data.receipts.filter(r=>r.kind==='voice');
        html+=`<section class="screen-card" style="margin-top:22px"><h2>Voice archive</h2><p class="screen-muted">Voice notes already delivered in this chat. No offline calls or unheard audio are invented.</p>${voices.length?voices.slice().reverse().map(receipt).join(''):'<p class="screen-empty">Voice notes sent in TeleChat will appear here.</p>'}</section>`;
        const item=current(); if(item && url(item.data.url)) html+=`<p><a href="${esc(url(item.data.url))}" target="_blank" rel="noopener noreferrer" style="color:#c6b7f7">Open selected track on its service ↗</a></p>`;
      }
      if(kind==='event' && data.legacy_events.length) html+=`<section class="screen-card" style="margin-top:22px"><h2>Plans mentioned in TeleChat</h2><p class="screen-muted">Original chat event notes. Dates may be informal; add a dated plan above when ready.</p>${data.legacy_events.map(e=>`<div class="screen-event ${e.done?'done':''}"><strong>${esc(e.title)}</strong><p class="screen-muted">${esc(e.when)} ${esc(e.notes)}</p></div>`).join('')}</section>`;
    }
    root.innerHTML=html;
    root.dataset.draftKey=draftKey();root.dataset.revision=String(current()?.revision || '');
    ScreenDrafts.bind(root,draftKey());
    restorePreview(root);
    if(!ScreenDrafts.persistent) root.insertAdjacentHTML('beforeend','<p class="screen-muted">Browser storage is unavailable. Copy unsaved text before reloading this page.</p>');
    if(S.busy) root.querySelectorAll('button,select,input,textarea').forEach(el=>el.disabled=true);
  }
  function capture() {
    const root=document.getElementById(roots[S.app]);
    if(!root?.dataset.draftKey || !root.querySelector('[data-screen-field]'))return;
    const key=root.dataset.draftKey, draft={...ScreenDrafts.get(key)};
    root.querySelectorAll('[data-screen-field]').forEach(el=>{draft[el.dataset.screenField]=el.value;});
    if(root.dataset.revision && !draft.baseRevision)draft.baseRevision=Number(root.dataset.revision);
    ScreenDrafts.put(key,draft);
  }
  function restorePreview(root) {
    const preview=ScreenDrafts.get(draftKey()).mailPreview;
    const el=root.querySelector('#miniMailPreview');if(!el||!preview) return;
    el.innerHTML=`<section class="screen-preview"><strong>Preview from ${esc(preview.sender)}</strong>${field('Reply preview','miniReply',preview.body,'textarea','maxlength="30000"')}<div class="screen-actions">${button('Deliver this reply','deliver-preview','class="screen-primary"')}${button('Discard preview…','discard-preview')}</div></section>`;
    ScreenDrafts.bind(el,draftKey());
  }
  function value(id) {return document.getElementById(id)?.value || '';}
  async function mutate(payload, onSuccess) {
    if(S.busy) return;
    const thread=String(S.thread), app=S.app, key=selectKey();
    S.epochs.set(thread,(S.epochs.get(thread)||0)+1);
    S.busy=true; S.errors.delete(key);
    document.getElementById(roots[app])?.querySelectorAll('button,select,input,textarea').forEach(el=>el.disabled=true);
    try {
      const result=await request({...payload,thread_id:thread});
      if(result.forwarded) S.dirtyThreads.add(thread);
      const data=S.cache.get(thread);
      if(result.entry && data) {data.entries=data.entries.filter(e=>e.id!==result.entry.id);data.entries.unshift(result.entry);}
      if(result.deleted && data) data.entries=data.entries.filter(e=>String(e.id)!==String(payload.id));
      await onSuccess?.(result,thread,app);
      toast(result.draft?'Reply preview ready. Review it before delivery.':result.forwarded?'Copy sent to TeleChat. No reply was generated.':'Saved.');
      overview();
    } catch(error) {S.errors.set(key,{message:error.message,current:error.current});}
    finally {S.busy=false;if(roots[S.app]) render();}
  }
  async function openSource(messageId, thread=String(S.thread)) {
    if(S.busy) return;
    const ok=await TG.selectThread(Number(thread)); if(ok===false) return;
    S.dirtyThreads.delete(String(thread));
    TG.switchApp('messenger');
    if(messageId) document.getElementById('msg-'+messageId)?.scrollIntoView({block:'center'});
  }
  async function action(action,el) {
    if(action==='home') return TG.switchApp('home');
    if(action==='refresh') return load(true);
    if(action==='source') return openSource(el.dataset.id);
    if(S.busy) return;
    if(action==='tab') {S.tab=el.dataset.tab;return render();}
    if(action==='select'||action==='new') {S.selection.set(selectKey(),action==='new'?'new':el.dataset.id);S.errors.delete(selectKey());return render();}
    const item=current(), key=draftKey();
    if(action==='reload-record') {
      const saved=S.errors.get(selectKey())?.current;
      if(saved && confirm('Replace the local draft with the saved version?')) {const data=cache();data.entries=data.entries.filter(e=>e.id!==saved.id);data.entries.unshift(saved);ScreenDrafts.clear(key);S.errors.delete(selectKey());render();}return;
    }
    if(action==='discard-preview') {if(confirm('Discard this reply preview?')){ScreenDrafts.clear(key,['mailPreview','miniReply']);render();}return;}
    if(action==='save') {
      const kind=kinds[S.app];let details={};
      if(kind==='document') details={scope:value('miniScope')};
      if(kind==='event') {const d=new Date(value('miniWhen'));if(Number.isNaN(+d)) return toast('Choose a valid date and time.');details={when:d.toISOString(),location:value('miniLocation'),done:value('miniDone')==='true'};}
      if(kind==='track') details={url:value('miniUrl'),artist:value('miniArtist')};
      const selectedAtStart=selectKey();
      if(!item && selected()!=='new') return toast('This saved record is no longer listed. Copy your draft before starting a new record.');
      return mutate({action:item?'save':'create',id:item?.id,revision:ScreenDrafts.get(key).baseRevision || item?.revision,kind,title:value('miniTitle'),body:value('miniBody'),data:details},result=>{ScreenDrafts.clear(key);S.selection.set(selectedAtStart,String(result.entry.id));});
    }
    if(!item) return;
    const base={id:item.id,revision:item.revision};
    if(action==='delete') {if(confirm('Delete this saved record? This cannot be undone.')) {const selectionAtStart=selectKey();return mutate({...base,action:'delete'},()=>{ScreenDrafts.clear(key);S.selection.set(selectionAtStart,'new');});}return;}
    if(action==='forward') {if(confirm('Send a copy to everyone in '+name(S.thread)+'? This does not generate a reply.')) return mutate({...base,action:'forward'});return;}
    if(action==='draft-mail') {
      const direction=value('miniDirection'), character_slug=value('miniCharacter');
      if(ScreenDrafts.get(key).mailPreview && !confirm('Replace the existing reply preview?')) return;
      return mutate({...base,action:'draft_mail',direction,character_slug},result=>ScreenDrafts.put(key,{...ScreenDrafts.get(key),mailPreview:{body:result.draft,sender:result.sender,slug:result.sender_slug,revision:result.revision},miniReply:result.draft}));
    }
    if(action==='send-mail'||action==='deliver-preview') {
      const preview=ScreenDrafts.get(key).mailPreview;
      const payload={...base,action:'send_mail',body:action==='send-mail'?value('miniLetter'):value('miniReply'),sender_slug:action==='send-mail'?'user':preview?.slug};
      if(action==='deliver-preview') payload.revision=preview?.revision;
      return mutate(payload,()=>{ScreenDrafts.clear(key,action==='send-mail'?['miniLetter']:['mailPreview','miniReply']);});
    }
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const original=TG.switchApp.bind(TG);
    TG.switchApp=app=>{
      if(!document.getElementById('app-'+app)) return;
      // Pause app audio when leaving; never start audio because an app was opened.
      document.querySelectorAll('.screen-mini-root audio').forEach(audio=>audio.pause());
      Object.entries(roots).forEach(([id,root])=>{if(id!==app)document.getElementById(root).replaceChildren();});
      original(app);S.app=app;document.body.dataset.screenApp=app;
      const active=TG.state.active_thread;
      if(app==='messenger' && active && (active.unread>0 || S.dirtyThreads.has(String(active.id)))) {
        TG.selectThread(active.id).then(ok=>{if(ok)S.dirtyThreads.delete(String(active.id));});
      }
      if(app==='home'){home();overview();}
      if(roots[app]) {S.thread ||= TG.state.active_thread?.id || TG.state.threads[0]?.id;render();load();}
      window.dispatchEvent(new CustomEvent('screen-app-changed',{detail:{app}}));
    };
    document.getElementById('screenAppGrid').addEventListener('click',e=>{const b=e.target.closest('[data-open]');if(b) TG.switchApp(b.dataset.open);});
    document.getElementById('screenRecentChats').addEventListener('click',e=>{const b=e.target.closest('[data-thread]');if(b) openSource(null,b.dataset.thread);});
    Object.values(roots).forEach(id=>{
      const root=document.getElementById(id);
      root.addEventListener('click',e=>{const b=e.target.closest('button[data-action]');if(b) action(b.dataset.action,b).catch(error=>toast(error.message));});
      root.addEventListener('input',e=>{if(e.target.matches('[data-screen-field]') && root.dataset.revision){const key=root.dataset.draftKey,draft=ScreenDrafts.get(key);if(!draft.baseRevision)ScreenDrafts.put(key,{...draft,baseRevision:Number(root.dataset.revision)});}});
      root.addEventListener('change',e=>{if(e.target.id==='screenAppThread'){S.thread=e.target.value;render();load();}});
    });
    const wallpaper=document.getElementById('screenWallpaper');
    wallpaper.value=ScreenDrafts.get('home').wallpaper || 'dusk';document.body.dataset.screenWallpaper=wallpaper.value;
    wallpaper.addEventListener('change',()=>{document.body.dataset.screenWallpaper=wallpaper.value;ScreenDrafts.put('home',{wallpaper:wallpaper.value});});
    tick();setInterval(tick,30000);
    const query=new URLSearchParams(location.search);
    const wanted=query.get('app') || (query.has('thread')||query.has('char')?'messenger':'home');
    TG.switchApp(document.getElementById('app-'+wanted)?wanted:'home');
    document.addEventListener('telechat-rendered',()=>{if(S.app==='home') home();});
    window.ScreenHome={state:S,open:app=>TG.switchApp(app)};
  });
})();
