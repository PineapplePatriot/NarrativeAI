/* Responsive launcher/wallpaper checks. No model requests. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const base=process.env.VN_TEST_URL,session=process.env.VN_TEST_SESSION_FILE;
 assert(base&&session,'Set VN_TEST_URL and VN_TEST_SESSION_FILE.');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
 try{
  for(const width of [320,390,768,1024,1280]){
   const context=await browser.newContext({viewport:{width,height:900}});
   await context.addCookies([{name:'sessionid',value:JSON.parse(fs.readFileSync(session)).sessionid,url:base}]);
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/main/screen/api/**',route=>route.request().method()==='GET'?route.fulfill({contentType:'application/json',body:'{}'}):route.request().postDataJSON().action==='load_thread'?route.continue():route.abort());
   await page.goto(base+'/main/screen/');
   await page.locator('#app-home.active').waitFor();
   for(const value of ['moonlit-library','cloud-station','night-greenhouse']){
    await page.getByLabel('Wallpaper',{exact:true}).selectOption(value);
    const background=await page.locator('.screen-home').evaluate(el=>getComputedStyle(el).backgroundImage);
    assert(background.includes(value+'.webp'));
    const asset=new URL(background.match(/url\("?([^"\)]+)/)[1],base).href;
    const response=await context.request.get(asset);assert.equal(response.status(),200);
    assert.match(response.headers()['content-type'],/image\/webp/);
   }
   await page.getByLabel('Wallpaper',{exact:true}).selectOption('moonlit-library');
   const grid=page.locator('#screenAppGrid');
   assert.equal(await grid.locator('button').count(),8);
   const bounds=await grid.boundingBox();assert(bounds.x>=0 && bounds.x+bounds.width<=width+1);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert.equal(await page.locator('.screen-home').evaluate(el=>el.scrollWidth>el.clientWidth),false);
   if(width<=860){
    assert.equal(await page.locator('.screen-dock button:visible').count(),4);
    const rect=await page.locator('.screen-dock').boundingBox();assert(rect.x>=0 && rect.x+rect.width<=width+1);
   }
   // Background refreshes preserve the focused app tile rather than replacing it.
   await page.locator('#screenAppGrid [data-open="mail"]').focus();
   await page.evaluate(()=>document.dispatchEvent(new Event('telechat-rendered')));
   assert.equal(await page.evaluate(()=>document.activeElement.dataset.open),'mail');
   await page.locator('#screenAppGrid [data-open="files"]').click();
   await page.getByLabel('Title',{exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert.equal(await page.locator('.screen-home').evaluate(el=>el.scrollWidth>el.clientWidth),false);
   const primary=await page.locator('#screenDriveRoot .screen-primary').evaluate(el=>getComputedStyle(el).backgroundImage);
   assert(primary.includes('linear-gradient'));
   await page.locator('.screen-dock [data-app="home"]').click();
   await page.screenshot({path:`/tmp/screen-wallpaper-${width}.png`});
   // Appearance is local per account and survives a fresh tab/session draft store.
   const second=await context.newPage();await second.goto(base+'/main/screen/');
   assert.equal(await second.getByLabel('Wallpaper',{exact:true}).inputValue(),'moonlit-library');
   await second.close();
   await page.evaluate(()=>{localStorage.setItem('narrative-screen-wallpaper:'+TG.state.account_id,'not-a-wallpaper');sessionStorage.clear();});
   await page.reload();assert.equal(await page.getByLabel('Wallpaper',{exact:true}).inputValue(),'dusk');
   assert.deepEqual(errors,[]);await context.close();
   console.log(`Wallpapers, responsive grid/dock, focus and per-account preference: ${width}px passed.`);
  }
  // Storage restrictions must not stop navigation or wallpaper switching.
  const context=await browser.newContext({viewport:{width:390,height:900}});
  await context.addCookies([{name:'sessionid',value:JSON.parse(fs.readFileSync(session)).sessionid,url:base}]);
  const page=await context.newPage();
  await page.addInitScript(()=>{for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{get(){throw new Error('Storage blocked');}});});
  await page.route('**/main/screen/api/**',route=>route.fulfill({contentType:'application/json',body:'{}'}));
  await page.goto(base+'/main/screen/');await page.getByLabel('Wallpaper',{exact:true}).selectOption('cloud-station');
  assert.equal(await page.locator('body').getAttribute('data-screen-wallpaper'),'cloud-station');
  await context.close();console.log('Storage-blocked appearance fallback passed.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
