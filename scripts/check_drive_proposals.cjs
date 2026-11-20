const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const base=process.env.VN_TEST_URL,session=process.env.VN_TEST_SESSION_FILE;
  assert(base&&session,'Set VN_TEST_URL and VN_TEST_SESSION_FILE.');
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
  try{
    for(const width of [390,1280]){
      const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.context().addCookies([{name:'sessionid',value:JSON.parse(fs.readFileSync(session)).sessionid,url:base}]);
      await page.route('**/main/screen/api/**',route=>route.request().method()==='GET'?route.fulfill({contentType:'application/json',body:'{}'}):route.request().postDataJSON().action==='load_thread'?route.continue():route.abort());
      let preview;
      await page.route('**/main/screen/apps/api/**',route=>{
        if(route.request().method()==='POST'&&route.request().postDataJSON().action==='draft_document')return route.fulfill({contentType:'application/json',body:JSON.stringify({proposal:preview})});
        return route.continue();
      });
      await page.goto(base+'/main/screen/?app=files');
      await page.getByRole('button',{name:`Shared packing list ${width} Shared with this chat`,exact:true}).first().click();
      preview=await page.evaluate(width=>{const data=ScreenHome.state.cache.get(String(ScreenHome.state.thread));const entry=data.entries.find(e=>e.title===`Shared packing list ${width}`);return data.proposals.find(p=>p.document_id===entry.id);},width);
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'Packing list\n- Map');
      await page.getByText('Invite a character to edit',{exact:true}).click();
      await page.getByLabel('What should they change?').fill('Add a lantern.');
      await page.getByRole('button',{name:'Request edit · uses model tokens',exact:true}).click();
      await page.waitForFunction(()=>!ScreenHome.state.busy);
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'Packing list\n- Map');
      await page.getByLabel('Proposed replacement (editable)').fill('Packing list\n- Map\n- Lantern\n- Water');
      // Unsent document edits must be resolved before accepting a proposal.
      await page.getByLabel('Document',{exact:true}).fill('Unsaved local change');
      await page.getByRole('button',{name:'Apply this edit',exact:true}).click();
      await page.getByText('Save your document changes before requesting or applying a character edit.',{exact:true}).waitFor();
      await page.getByLabel('Document',{exact:true}).fill('Packing list\n- Map');
      await page.getByRole('button',{name:'Apply this edit',exact:true}).click();
      await page.waitForFunction(()=>document.getElementById('miniBody')?.value.includes('Water'));
      assert.equal(await page.getByLabel('Proposed replacement (editable)').count(),0);
      await page.reload();
      await page.getByRole('button',{name:`Shared packing list ${width} Shared with this chat`,exact:true}).first().click();
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'Packing list\n- Map\n- Lantern\n- Water');
      await page.getByText('Before this proposal',{exact:true}).click();
      await page.getByText('Packing list\n- Map',{exact:true}).waitFor();
      await page.getByRole('button',{name:`Stale packing list ${width} Shared with this chat`,exact:true}).first().click();
      await page.getByLabel('Document',{exact:true}).fill('A newer saved agreement');
      await page.getByRole('button',{name:'Save changes',exact:true}).click();
      await page.waitForFunction(()=>!ScreenHome.state.busy);
      assert.equal(await page.getByRole('button',{name:'Apply this edit',exact:true}).isDisabled(),true);
      await page.getByRole('button',{name:'Reject proposal',exact:true}).click();
      await page.waitForFunction(()=>!ScreenHome.state.busy);
      assert.equal(await page.getByLabel('Document',{exact:true}).inputValue(),'A newer saved agreement');
      assert.equal(await page.getByRole('button',{name:'Apply this edit',exact:true}).count(),0);
      assert.deepEqual(errors,[]);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:`/tmp/drive-proposals-${width}.png`});
      await page.close();console.log(`Drive review, edited acceptance, persistence, stale proposals and rejection: ${width}px passed.`);
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
