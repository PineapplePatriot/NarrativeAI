/* Against scripts/seed_screen_workflow.py's disposable fixture; no model requests. */
const {chromium} = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const base = process.env.VN_TEST_URL;
  const sessionFile = process.env.VN_TEST_SESSION_FILE;
  assert(base && sessionFile, 'Set VN_TEST_URL and VN_TEST_SESSION_FILE for the disposable fixture.');
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({viewport: {width, height: 900}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/main/screen/api/**', async route => {
        const request = route.request();
        if (request.method() === 'GET' && new URL(request.url()).searchParams.get('action') === 'poll') {
          return route.fulfill({contentType: 'application/json', body: '{}'});
        }
        if (request.method() === 'POST' && request.postDataJSON().action !== 'load_thread') {
          return route.fulfill({status: 400, contentType: 'application/json', body: '{"error":"Model calls are disabled in this browser check."}'});
        }
        await route.continue();
      });
      // Fail closed if the UI unexpectedly tries an operation that could call a model.
      await page.route('**/main/screen/scenes/api/', async route => {
        const body = route.request().postDataJSON();
        if (!['episode_preferences', 'branch_passage', 'inspect_request', 'resume_draft', 'set_stage'].includes(body.action)) {
          return route.fulfill({status: 400, contentType: 'application/json', body: '{"error":"Model calls are disabled in this browser check."}'});
        }
        await route.continue();
      });
      await page.route('**/main/screen/lore/api/**', async route => {
        if (route.request().method() === 'POST' && !['save', 'copy', 'mode'].includes(route.request().postDataJSON().action)) {
          return route.fulfill({status: 400, contentType: 'application/json', body: '{"error":"Model calls are disabled in this browser check."}'});
        }
        await route.continue();
      });
      const {sessionid} = JSON.parse(fs.readFileSync(sessionFile));
      await page.context().addCookies([{name: 'sessionid', value: sessionid, url: base}]);
      await page.goto(new URL('/main/screen/', base).href);
      await page.locator('.tg-thread-item.active').click();
      await page.locator('#screenLorePanel > details > summary').click();
      await page.getByLabel('Lorebook title').waitFor();
      await page.getByRole('button', {name: 'New book', exact: true}).click();
      await page.getByLabel('Lorebook title').fill('Private archive lore');
      await page.getByRole('button', {name: 'Add entry', exact: true}).click();
      await page.getByLabel('Entry name').fill('The key');
      await page.getByLabel('Keywords (separated by commas)').fill('brass,key');
      await page.getByLabel('Facts', {exact: true}).fill('The brass key opens Gate Nine.');
      await page.getByRole('button', {name: 'Save to this chat', exact: true}).click();
      await page.waitForFunction(() => document.getElementById('screenLoreStatus').textContent.includes('Saved'));
      assert.equal(await page.evaluate(() => TG.state.active_thread.lore.mode), 'local');
      await page.locator('button[onclick="VN_SCENES.openLaunchModalFromChat()"]').first().click();
      await page.locator('.vn-beat-text').waitFor();
      await page.evaluate(() => {VN_SCENES.beatIndex = 0; VN_SCENES.renderStageOnly();});
      assert.equal(await page.evaluate(() => VN_SCENES.currentBeat().stage.location), 'Outside the archive');
      const first = await page.locator('.vn-stage-wrap').evaluate(el => el.style.backgroundImage);
      await page.getByRole('button', {name: /Next ▶/}).click();
      assert.equal(await page.evaluate(() => VN_SCENES.currentBeat().stage.location), 'Inside the archive');
      assert.notEqual(first, await page.locator('.vn-stage-wrap').evaluate(el => el.style.backgroundImage));
      await page.getByText('Episode preferences', {exact: true}).click();
      await page.locator('.vn-editor-settings select').first().selectOption('choices');
      await page.waitForFunction(() => TG.state.vn_scenes.active_scene.interaction_mode === 'choices');
      assert.equal(await page.locator('#vnShortInput').count(), 0);
      assert.equal(await page.evaluate(() => VN_SCENES.currentBeat().stage.location), 'Inside the archive');
      await page.getByText('Episode preferences', {exact: true}).click();
      await page.locator('.vn-editor-settings select').first().selectOption('write');
      await page.waitForFunction(() => TG.state.vn_scenes.active_scene.interaction_mode === 'write');
      await page.locator('#vnShortInput').waitFor();
      assert.equal(await page.locator('.vn-choice-chip').count(), 0);
      await page.getByRole('button', {name: 'Versions', exact: true}).click();
      await page.getByRole('button', {name: 'Close', exact: true}).last().click();
      await page.getByText('Edit, regenerate or branch', {exact: true}).click();
      const original = await page.evaluate(() => VN_SCENES.activeScene().id);
      await page.getByRole('button', {name: 'Branch after this passage', exact: true}).click();
      await page.waitForFunction(id => TG.state.vn_scenes.active_scene.id !== id, original);
      assert.equal(await page.evaluate(() => TG.state.active_thread.lore.title), 'Private archive lore');
      assert.deepEqual(errors, []);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.close();
      console.log(`Integrated lore editing, passage visuals, interaction modes and branching pass at ${width}px.`);
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
