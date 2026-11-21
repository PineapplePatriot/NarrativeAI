/* Against the disposable fixture + run_pulse_browser_server.py. No live provider calls. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const base=process.env.VN_TEST_URL,session=process.env.VN_TEST_SESSION_FILE;
 assert(base&&session,'Set VN_TEST_URL and VN_TEST_SESSION_FILE.');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
 try{
  for(const width of [390,1280]){
   const page=await browser.newPage({viewport:{width,height:950}}),errors=[];
   let starts=0,replies=0;
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',request=>{if(request.method()!=='POST')return;try{const d=request.postDataJSON();if(d.action==='start_scene')starts++;if(d.action==='pulse_respond')replies++;}catch(_){}});
   const open=async app=>{await page.locator('.screen-dock [data-app="home"]').click();await page.locator('#screenAppGrid [data-open="'+app+'"]').click();};
   await page.context().addCookies([{name:'sessionid',value:JSON.parse(fs.readFileSync(session)).sessionid,url:base}]);
   await page.goto(base+'/main/screen/?app=pulse');
   await page.locator('#screenPulseRoot .screen-record').filter({hasText:`Pulse archive visit ${width}`}).click();
   assert.equal(starts,0);assert.equal(replies,0);
   assert.equal(await page.locator('[data-pulse-participant="screen-workflow-mira"]').isChecked(),true);
   assert.equal(await page.locator('[data-pulse-participant="pulse-browser-oren"]').isChecked(),false);
   await page.getByRole('button',{name:'Send invitation to chat',exact:true}).click();
   await page.getByRole('button',{name:'Get character replies · uses model tokens',exact:true}).waitFor();
   assert.equal(replies,0);
   await page.getByRole('button',{name:'Get character replies · uses model tokens',exact:true}).click();
   await page.getByRole('button',{name:'Prepare VN scene · free',exact:true}).waitFor();
   assert.equal(replies,1);assert.equal(await page.getByLabel('Record status').inputValue(),'confirmed');
   const purpose=await page.getByLabel('Purpose / notes').inputValue();
   await page.getByLabel('Purpose / notes').fill('Unsaved changed purpose');
   await page.getByRole('button',{name:'Prepare VN scene · free',exact:true}).click();
   await page.getByText('Save your plan changes before sending invitations or preparing a scene.',{exact:true}).waitFor();
   await page.getByLabel('Purpose / notes').fill(purpose);
   await page.getByRole('button',{name:'Prepare VN scene · free',exact:true}).click();
   await page.locator('#vnPulsePlan').waitFor();
   assert.equal(starts,0);
   assert.equal(await page.locator('#vnLaunchAutoSprites').isChecked(),false);
   assert.match(await page.locator('#vnPulsePlan').innerText(),/Gate Nine/);
   await page.getByRole('button',{name:'🎬 Launch Meet-Up Scene · uses model tokens ➤',exact:true}).click();
   await page.waitForFunction(()=>TG.state.vn_scenes.active_scene?.pulse_event);
   const scene=await page.evaluate(()=>TG.state.vn_scenes.active_scene);
   assert.equal(starts,1);assert.deepEqual(scene.character_slugs,['screen-workflow-mira']);
   assert.equal(scene.pulse_event.title,`Pulse archive visit ${width}`);
   assert.equal(scene.context.clock,scene.pulse_event.when_label);
   // A second preparation cannot replace the open episode or trigger a second generation.
   await open('pulse');
   await page.getByRole('button',{name:'Prepare VN scene · free',exact:true}).click();
   await page.getByRole('alert').waitFor();assert.equal(starts,1);
   assert.equal(await page.evaluate(()=>TG.state.vn_scenes.active_scene.id),scene.id);
   await open('scenes');
   await page.locator('.vn-editor-settings').evaluate(el=>el.open=true);
   await page.getByRole('button',{name:'Save unfinished episode',exact:true}).click();
   await page.waitForFunction(()=>!TG.state.vn_scenes.active_scene);
   await open('pulse');
   await page.getByRole('button',{name:'+ New plan',exact:true}).click();
   await page.getByLabel('Title',{exact:true}).fill('Reminder check '+width);
   const before=new Date(Date.now()-60000);const local=new Date(+before-before.getTimezoneOffset()*60000).toISOString().slice(0,16);
   await page.getByLabel('When (your device’s local time)').fill(local);
   await page.getByLabel('Record status').selectOption('confirmed');
   await page.getByLabel('Chat reminder').selectOption('0');
   await page.getByRole('button',{name:'Create plan',exact:true}).click();
   await page.getByRole('button',{name:'Check due reminders · free',exact:true}).waitFor();
   const id=await page.evaluate(()=>Number(ScreenHome.state.selection.get(ScreenHome.state.thread+':pulse')));
   for(let i=0;i<2;i++){
    await page.getByRole('button',{name:'Check due reminders · free',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('pulseReminderState')?.textContent.includes('delivered'));
   }
   await page.getByRole('button',{name:'Open this chat',exact:true}).click();
   await page.locator('#app-messenger.active').waitFor();
   const messages=await page.evaluate(id=>TG.state.active_thread.messages.filter(m=>m.pulse_event_id===id && m.role==='system'),id);
   assert.equal(messages.length,1);assert.match(messages[0].text,/Pulse reminder/);
   // A timer refresh must not supersede a chat selection already in flight.
   const target=await page.evaluate(()=>TG.state.threads.find(t=>t.id!==TG.state.active_thread.id).id);
   let releaseSwitch,switchHeld;
   const switchReady=new Promise(resolve=>switchHeld=resolve),switchRelease=new Promise(resolve=>releaseSwitch=resolve);
   await page.route('**/main/screen/api/**',async route=>{
    const req=route.request();
    if(req.method()==='POST' && req.postDataJSON().action==='load_thread' && req.postDataJSON().thread_id===target){const response=await route.fetch();switchHeld();await switchRelease;return route.fulfill({response});}
    return route.continue();
   });
   await page.evaluate(target=>{window.pulseTestSwitch=TG.selectThread(target);},target);await switchReady;
   await page.evaluate(()=>ScreenHome.remindersDelivered({delivered:1,thread_ids:[TG.state.active_thread.id],reminders:[]}));
   releaseSwitch();await page.evaluate(()=>window.pulseTestSwitch);
   assert.equal(await page.evaluate(()=>TG.state.active_thread.id),target);
   // Return to the reminder's source chat, then follow its direct plan link.
   await page.evaluate(()=>TG.selectThread(Number(ScreenHome.state.thread)));
   await page.getByRole('button',{name:'View plan',exact:true}).last().click();
   await page.locator('#app-pulse.active').waitFor();
   assert.equal(await page.getByLabel('Title',{exact:true}).inputValue(),'Reminder check '+width);
   assert.equal(starts,1);assert.equal(replies,1);
   await open('pulse');
   await page.getByRole('button',{name:'Use as new plan',exact:true}).click();
   assert.equal(await page.getByLabel('Title',{exact:true}).inputValue(),'Coffee after the archive');
   assert.equal(await page.getByLabel('When (your device’s local time)').inputValue(),'');
   assert.equal(await page.getByLabel('Clock',{exact:true}).inputValue(),'chat');
   assert.equal(starts,1);assert.equal(replies,1);
   await page.locator('#screenPulseRoot [data-action="select"][data-id="'+id+'"]').click();
   await page.screenshot({path:`/tmp/pulse-workflow-${width}.png`});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert.deepEqual(errors,[]);
   await page.close();console.log(`Pulse invitations, exact-cast VN launch, active-episode guard and duplicate-free reminders: ${width}px passed.`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
