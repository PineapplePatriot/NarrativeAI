/* Real mini-app CRUD in the disposable Screen fixture. Model calls fail closed. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const base=process.env.VN_TEST_URL,sessionFile=process.env.VN_TEST_SESSION_FILE;
  assert(base && sessionFile,'Set VN_TEST_URL and VN_TEST_SESSION_FILE.');
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
  try {
    for(const width of [390,1280]) {
      const page=await browser.newPage({viewport:{width,height:900}}), errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('response',async r=>{if(r.request().method()==='POST' && r.url().includes('/apps/') && r.status()>=400) console.log('App error:',await r.text());});
      await page.context().addCookies([{name:'sessionid',value:JSON.parse(fs.readFileSync(sessionFile)).sessionid,url:base}]);
      await page.route('**/main/screen/api/**',route=>{
        const req=route.request();
        if(req.method()==='GET') return route.fulfill({contentType:'application/json',body:'{}'});
        if(req.postDataJSON().action==='load_thread') return route.continue();
        return route.fulfill({status:400,contentType:'application/json',body:'{"error":"Model calls disabled in browser verification."}'});
      });
      await page.route('**/main/screen/apps/api/**',route=>{
        const req=route.request();
        if(req.method()==='POST' && req.postDataJSON().action==='draft_mail') return route.fulfill({contentType:'application/json',body:JSON.stringify({draft:'I kept the map for you.',sender:'Mira',sender_slug:'screen-workflow-mira',revision:req.postDataJSON().revision})});
        return route.continue();
      });
      await page.goto(base+'/main/screen/');
      await page.locator('#app-home.active').waitFor();
      assert.equal(await page.locator('#screenAppGrid button').count(),8);
      await page.getByLabel('Wallpaper',{exact:true}).selectOption('forest');
      await page.locator('#screenAppGrid button[data-open="files"]').click();
      await page.getByLabel('Title',{exact:true}).waitFor();
      const originalThread=await page.locator('#screenAppThread').inputValue();
      await page.getByLabel('Title',{exact:true}).fill('Shared map '+width);
      await page.getByLabel('Document',{exact:true}).fill('The copper gate opens at dawn.');
      await page.getByLabel('Who can read it?').selectOption('shared');
      await page.getByRole('button',{name:'Create document',exact:true}).click();
      await page.getByRole('button',{name:'Save changes',exact:true}).waitFor();
      await page.getByLabel('Document',{exact:true}).fill('UNSAVED local detail');
      await page.locator('.screen-dock [data-app="wave"]').click();
      await page.getByLabel('Artist',{exact:true}).waitFor();
      await page.locator('.screen-dock [data-app="files"]').click();
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'UNSAVED local detail');
      const other=await page.locator('#screenAppThread option').evaluateAll(opts=>opts.map(x=>x.value));
      await page.locator('#screenAppThread').selectOption(other.find(x=>x!==originalThread));
      await page.waitForFunction(()=>document.getElementById('miniTitle')?.value==='');
      await page.locator('#screenAppThread').selectOption(originalThread);
      await page.waitForFunction(()=>document.getElementById('miniBody')?.value==='UNSAVED local detail');
      // Error response must retain the editable local document.
      let failSave=true;
      await page.route('**/main/screen/apps/api/**',async route=>{
        if(failSave && route.request().method()==='POST' && route.request().postDataJSON().action==='save') {failSave=false;return route.fulfill({status:500,contentType:'text/html',body:'error'});}
        return route.fallback();
      });
      await page.getByRole('button',{name:'Save changes',exact:true}).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'UNSAVED local detail');
      await page.getByRole('button',{name:'Save changes',exact:true}).click();
      await page.waitForFunction(()=>!document.querySelector('.screen-form[disabled]'));
      // A delayed pre-save list response must not replace the new saved record.
      let releaseList, listHeld, heldOnce=false;
      const heldReady=new Promise(resolve=>listHeld=resolve), releaseReady=new Promise(resolve=>releaseList=resolve);
      await page.route('**/main/screen/apps/api/**',async route=>{
        if(!heldOnce && route.request().method()==='GET' && !route.request().url().includes('overview')) {
          heldOnce=true;const response=await route.fetch();listHeld();await releaseReady;return route.fulfill({response});
        }
        return route.fallback();
      });
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await heldReady;
      await page.getByLabel('Document',{exact:true}).fill('Saved after the delayed refresh');
      await page.getByRole('button',{name:'Save changes',exact:true}).click();
      await page.waitForFunction(()=>ScreenHome.state.cache.get(String(ScreenHome.state.thread)).entries.some(e=>e.body==='Saved after the delayed refresh'));
      releaseList();await page.waitForTimeout(100);
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'Saved after the delayed refresh');
      // Refreshing while another tab changes the record must keep our draft's base revision.
      await page.getByLabel('Document',{exact:true}).fill('My conflicting local draft');
      await page.evaluate(async()=>{
        const s=ScreenHome.state,entry=s.cache.get(String(s.thread)).entries.find(e=>e.body==='Saved after the delayed refresh');
        const response=await fetch(TG_CFG.screen_apps_api,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':TG_CFG.csrf},body:JSON.stringify({action:'save',thread_id:s.thread,id:entry.id,revision:entry.revision,title:entry.title,body:'Newer version from another tab',data:entry.data})});
        if(!response.ok)throw new Error('Could not create conflict fixture.');
      });
      await page.getByRole('button',{name:'Refresh',exact:true}).click();
      await page.waitForFunction(()=>ScreenHome.state.cache.get(String(ScreenHome.state.thread)).entries.some(e=>e.body==='Newer version from another tab'));
      await page.getByRole('button',{name:'Save changes',exact:true}).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'My conflicting local draft');
      await page.getByText('Review saved version',{exact:true}).click();
      page.once('dialog',dialog=>dialog.accept());
      await page.getByRole('button',{name:'Load saved version (replaces this draft)…',exact:true}).click();
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'Newer version from another tab');
      await page.locator('.screen-dock [data-app="mail"]').click();
      await page.getByLabel('Title',{exact:true}).fill('Archive correspondence '+width);
      await page.getByRole('button',{name:'Create subject',exact:true}).click();
      await page.getByLabel('Write a letter').fill('Can you keep the map?');
      await page.getByRole('button',{name:'Send my letter',exact:true}).click();
      await page.getByText('Can you keep the map?',{exact:true}).waitFor();
      await page.getByText('Draft a character reply',{exact:true}).click();
      let mailHeld,releaseMail;
      const mailReady=new Promise(resolve=>mailHeld=resolve),mailRelease=new Promise(resolve=>releaseMail=resolve);
      await page.route('**/main/screen/apps/api/**',async route=>{
        if(route.request().method()==='POST' && route.request().postDataJSON().action==='draft_mail') {
          const revision=route.request().postDataJSON().revision;mailHeld();await mailRelease;
          return route.fulfill({contentType:'application/json',body:JSON.stringify({draft:'I kept the map for you.',sender:'Mira',sender_slug:'screen-workflow-mira',revision})});
        }
        return route.fallback();
      });
      await page.getByRole('button',{name:'Draft reply · uses model tokens',exact:true}).click();await mailReady;
      await page.locator('.screen-dock [data-app="wave"]').click();releaseMail();
      await page.waitForFunction(()=>!ScreenHome.state.busy);
      await page.getByLabel('Artist',{exact:true}).waitFor();
      assert.equal(await page.getByLabel('Artist',{exact:true}).isEnabled(),true);
      await page.locator('.screen-dock [data-app="mail"]').click();
      await page.getByLabel('Reply preview',{exact:true}).waitFor();
      assert.equal(await page.locator('.screen-letter').count(),1);
      await page.getByLabel('Reply preview',{exact:true}).fill('Reviewed reply: the map is safe.');
      await page.getByRole('button',{name:'Deliver this reply',exact:true}).click();
      await page.getByText('Reviewed reply: the map is safe.',{exact:true}).waitFor();
      await page.locator('.screen-dock [data-app="pulse"]').click();
      await page.getByLabel('Title',{exact:true}).fill('Meet at the archive '+width);
      await page.getByLabel('When (your device’s local time)').fill('2026-12-01T14:30');
      await page.getByLabel('Place',{exact:true}).fill('Gate Nine');
      await page.getByRole('button',{name:'Create plan',exact:true}).click();
      await page.getByRole('button',{name:'Save changes',exact:true}).waitFor();
      await page.locator('.screen-dock [data-app="wave"]').click();
      await page.getByLabel('Title',{exact:true}).fill('Night walk '+width);
      await page.getByLabel('Artist',{exact:true}).fill('An artist');
      await page.getByLabel('Track link (optional)').fill('https://example.com/song');
      await page.getByRole('button',{name:'Create track',exact:true}).click();
      await page.getByRole('link',{name:'Open selected track on its service ↗'}).waitFor();
      assert.equal(await page.evaluate(()=>[...document.querySelectorAll('audio')].some(a=>!a.paused)),false);
      await page.locator('.screen-dock [data-app="home"]').click();
      assert.deepEqual(await page.locator('.dock-app-btn.active[data-app]').evaluateAll(els=>els.map(el=>el.dataset.app)),['home']);
      await page.screenshot({path:`/tmp/screen-home-${width}.png`,fullPage:true});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      assert.equal(await page.locator('body').getAttribute('data-screen-wallpaper'),'forest');
      await page.reload();
      await page.locator('#app-home.active').waitFor();
      assert.equal(await page.locator('body').getAttribute('data-screen-wallpaper'),'forest');
      assert.deepEqual(errors,[]);
      await page.close();console.log(`Home, Drive drafts, failures, mail preview/delivery, Pulse, Wave at ${width}px: passed.`);
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
