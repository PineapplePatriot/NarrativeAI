/* Pulse is an agenda and invitation workflow; only labelled reply buttons call a model. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const status = value => ({planned:'Planned',invited:'Invitation sent',tentative:'Tentative',confirmed:'Confirmed',declined:'Declined',cancelled:'Cancelled',completed:'Completed'}[value] || 'Planned');
  const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  function local(value) {const d=new Date(value);return Number.isNaN(+d)?'':new Date(+d-d.getTimezoneOffset()*60000).toISOString().slice(0,19).replace(/:00$/,'');}
  function members(){const thread=TG.state.threads.find(t=>String(t.id)===String(window.ScreenHome?.state.thread || TG.state.active_thread?.id));return (thread?.member_slugs || []).map(slug=>TG.state.characters.find(c=>c.slug===slug)).filter(Boolean);}
  function fields(item,{field,button,date,clock}) {
    const d=item?.data || {},state=d.status || (d.done?'completed':'planned');
    let html=field('When (your device’s local time)','miniWhen',d.when?local(d.when):'','input','type="datetime-local" step="1" required');
    html+=`<p class="screen-muted">Shown in ${escape(zone())}${d.timezone && d.timezone!==zone()?'; saved zone: '+escape(d.timezone):''}. The exact UTC instant is stored with the plan.</p>`;
    html+=`<div class="screen-field"><label for="pulseClock">Clock</label><select id="pulseClock" data-screen-field="pulseClock"><option value="real" ${d.clock!=='chat'?'selected':''}>Real time</option><option value="chat" ${d.clock==='chat'?'selected':''}>This chat’s story clock</option></select></div>`;
    html+=`<p class="screen-muted">Real now: ${escape(date(new Date()))}<br>Story now: ${escape(date(new Date(Date.now()+(clock?.offset || 0)*1000)))}</p>`;
    html+=field('Duration (minutes)','pulseDuration',d.duration_minutes || 60,'input','type="number" min="5" max="1440"');
    html+=field('Place','miniLocation',d.location || '','input','maxlength="200"');
    html+=field('Purpose / notes','miniBody',item?.body || '','textarea','maxlength="30000"');
    html+=`<div class="screen-field"><label for="pulseStatus">Record status</label><select id="pulseStatus" data-screen-field="pulseStatus">${['planned',...(state==='invited'?['invited']:[]),'tentative','confirmed','declined','cancelled','completed'].map(s=>`<option value="${s}" ${s===state?'selected':''}>${status(s)}</option>`).join('')}</select></div>`;
    html+='<p class="screen-muted">Record an agreement already reached in chat, or send an invitation below. Updating the time, place, purpose or cast resets invitation replies and returns the plan to Planned.</p>';
    html+=`<details ${item?'':'open'} class="pulse-cast"><summary>Participants</summary>${members().map(c=>`<label><input type="checkbox" data-pulse-participant="${escape(c.slug)}" data-screen-field="pulse-cast-${escape(c.slug)}" ${!d.participants || d.participants.includes(c.slug)?'checked':''}>${escape(c.name)}</label>`).join('') || '<p class="screen-muted">This chat has no characters. You can still keep a personal reminder.</p>'}</details>`;
    html+=`<div class="screen-field"><label for="pulseReminder">Chat reminder</label><select id="pulseReminder" data-screen-field="pulseReminder">${[['','Off'],['0','At the start'],['5','5 minutes before'],['15','15 minutes before'],['30','30 minutes before'],['60','1 hour before'],['1440','1 day before'],...(d.reminder_minutes!=null && ![0,5,15,30,60,1440].includes(d.reminder_minutes)?[[String(d.reminder_minutes),d.reminder_minutes+' minutes before']]:[])].map(([v,t])=>`<option value="${v}" ${v===(d.reminder_minutes==null?'':String(d.reminder_minutes))?'selected':''}>${t}</option>`).join('')}</select></div>`;
    html+='<p class="screen-muted">Reminders run only for confirmed plans and never generate replies. They follow the selected clock. They are delivered in TeleChat, including while you are away when the server is running.</p>';
    if(item) {
      const reminder=item.schedule || {};
      html+=`<p class="screen-muted" id="pulseReminderState">${reminder.delivered_at?'Reminder delivered: '+escape(date(reminder.delivered_at)):reminder.enabled?'Reminder queued for '+escape(date(reminder.due_at))+' ('+escape(d.clock || 'real')+' clock)':'No active reminder.'}</p>`;
      html+='<div class="screen-actions">';
      if(['planned','tentative','declined'].includes(state))html+=button('Send invitation to chat','pulse-invite');
      if(state==='invited' && d.invitation_id && !d.responses?.length)html+=button('Get character replies · uses model tokens','pulse-respond','class="screen-primary"');
      if(state==='confirmed')html+=button('Prepare VN scene · free','pulse-scene','class="screen-primary"');
      html+=button('Open this chat','pulse-chat')+button('Check due reminders · free','pulse-check')+'</div>';
      if(d.responses?.length)html+='<section class="pulse-responses"><h2>Invitation replies</h2>'+d.responses.map(r=>`<article class="screen-letter"><strong>${escape(r.name)} · ${escape(r.response)}</strong><p>${escape(r.text)}</p></article>`).join('')+'</section>';
    }
    return html;
  }
  function read(item=null) {
    const v=id=>document.getElementById(id)?.value || '';
    const input=v('miniWhen'),when=new Date(input);
    if(Number.isNaN(+when)||local(when)!==input)throw new Error('Choose a valid local date and time. That time may fall in a daylight-saving clock change.');
    const instant=item?.data.when && Math.abs(+when-+new Date(item.data.when))<1000?item.data.when:when.toISOString();
    return {when:instant,timezone:zone(),clock:v('pulseClock'),status:v('pulseStatus'),
      done:v('pulseStatus')==='completed',location:v('miniLocation'),duration_minutes:Number(v('pulseDuration')),
      reminder_minutes:v('pulseReminder')===''?null:Number(v('pulseReminder')),
      participants:[...document.querySelectorAll('#screenPulseRoot [data-pulse-participant]:checked')].map(el=>el.dataset.pulseParticipant)};
  }
  function unchanged(item) {
    const d=read(item),old=item.data;
    return document.getElementById('miniTitle').value===item.title && document.getElementById('miniBody').value===item.body &&
      +new Date(d.when)===+new Date(old.when) && d.clock===(old.clock || 'real') && d.status===(old.status || (old.done?'completed':'planned')) &&
      d.location===(old.location || '') && d.duration_minutes===(old.duration_minutes || 60) && d.reminder_minutes===(old.reminder_minutes ?? null) &&
      JSON.stringify([...d.participants].sort())===JSON.stringify([...(old.participants || members().map(c=>c.slug))].sort());
  }
  function agenda(entries, selected, clock, {button,date}) {
    const groups={Today:[],Upcoming:[],Earlier:[],'Completed / cancelled':[]};
    for(const e of entries.slice().sort((a,b)=>new Date(a.data.when)-new Date(b.data.when))){
      const d=e.data,when=new Date(d.when),now=new Date(Date.now()+(d.clock==='chat'?(clock?.offset || 0)*1000:0));
      const closed=['completed','cancelled','declined'].includes(d.status) || d.done;
      const key=closed?'Completed / cancelled':+when+(d.duration_minutes || 60)*60000<=+now?'Earlier':when.toDateString()===now.toDateString()?'Today':'Upcoming';
      groups[key].push(e);
    }
    return Object.entries(groups).filter(([,events])=>events.length).map(([label,events])=>`<section class="pulse-agenda-group"><h3>${label}</h3>${events.map(e=>button(`<strong>${escape(e.title)}</strong><small>${escape(date(e.data.when))} · ${escape(status(e.data.status || (e.data.done?'completed':'planned')))} · ${e.data.clock==='chat'?'Story':'Real'} clock</small>`,'select',`class="screen-record" data-id="${e.id}" aria-current="${String(e.id)===selected}"`)).join('')}</section>`).join('') || '<p class="screen-muted">No plans yet. Add one to start your agenda.</p>';
  }
  async function handle(action,item,{mutate,base,toast,key}){
    if(action==='pulse-chat'){if(await TG.selectThread(item.thread_id)!==false)TG.switchApp('messenger');return;}
    if(!unchanged(item)){toast('Save your plan changes before sending invitations or preparing a scene.');return;}
    const actions={'pulse-invite':'pulse_invite','pulse-respond':'pulse_respond','pulse-scene':'pulse_scene_seed'};
    return mutate({...base,action:actions[action]},async result=>{
      if(result.pulse_seed)await VN_SCENES.preparePulse(result.pulse_seed);
      else ScreenDrafts.clear(key);
    });
  }
  window.PulseUI={fields,read,agenda,handle};
  document.addEventListener('DOMContentLoaded',()=>queueMicrotask(()=>{
    let busy=false;
    const tick=async()=>{
      if(busy || document.hidden || !window.ScreenHome)return;
      busy=true;
      try{const result=await ScreenHome.request({action:'pulse_tick'});ScreenHome.remindersDelivered(result);}catch(_){}finally{busy=false;}
    };
    tick();setInterval(tick,60000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
  }));
})();
