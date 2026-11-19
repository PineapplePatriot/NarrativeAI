/* Disposable fixture only. Paid actions are mocked or blocked. */
const {chromium} = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const base = process.env.VN_TEST_URL, sessionFile = process.env.VN_TEST_SESSION_FILE;
  assert(base && sessionFile, 'Seed the disposable fixture and set VN_TEST_URL/VN_TEST_SESSION_FILE.');
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({viewport: {width, height: 844}});
      const errors = []; let failLore = true, failPreference = false, finishes = 0, releaseGeneration;
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/main/screen/api/**', route => {
        if (route.request().method() === 'GET') return route.fulfill({contentType: 'application/json', body: '{}'});
        assert.equal(route.request().postDataJSON().action, 'load_thread'); return route.continue();
      });
      await page.route('**/main/screen/lore/api/**', async route => {
        if (route.request().method() !== 'POST') return route.continue();
        const body = route.request().postDataJSON();
        if (body.action === 'save' && failLore) {failLore = false; return route.fulfill({status: 500, contentType: 'text/html', body: '<h1>Temporary error</h1>'});}
        assert.notEqual(body.action, 'draft', 'No live Bulba calls in this browser check.');
        return route.continue();
      });
      await page.route('**/main/screen/scenes/api/', async route => {
        if (route.request().method() !== 'POST') return route.continue();
        const body = route.request().postDataJSON();
        if (body.action === 'finish_scene') {finishes++; throw Error('An unsent draft must block finishing.');}
        if (body.action === 'regenerate_passage') {
          const snapshot = await page.evaluate(() => structuredClone({state: TG.state.vn_scenes, phone: TG.state.active_thread, threads: TG.state.threads}));
          await new Promise(resolve => releaseGeneration = resolve);
          return route.fulfill({contentType: 'application/json', body: JSON.stringify({scene: snapshot.state.active_scene, vn_scenes: snapshot.state, thread: snapshot.phone, threads: snapshot.threads})});
        }
        if (body.action === 'episode_preferences' && failPreference) {failPreference = false; return route.fulfill({status: 500, contentType: 'text/html', body: 'temporary error'});}
        if (body.action === 'suggest_choices') {
          const state = await page.evaluate(() => structuredClone(TG.state.vn_scenes));
          state.active_scene.choices = ['Wait by the door.', 'Ask about the map.'];
          return route.fulfill({contentType: 'application/json', body: JSON.stringify({scene: state.active_scene, vn_scenes: state})});
        }
        if (body.action === 'resume_draft' && body.draft_id === 'missing-version') return route.fulfill({status: 404, contentType: 'application/json', body: '{"error":"That saved version is gone."}'});
        assert(['episode_preferences', 'park_scene', 'resume_draft', 'inspect_request', 'set_stage'].includes(body.action), body.action);
        return route.continue();
      });
      const {sessionid} = JSON.parse(fs.readFileSync(sessionFile));
      await page.context().addCookies([{name: 'sessionid', value: sessionid, url: base}]);
      await page.goto(new URL('/main/screen/', base).href);
      await page.locator('.tg-thread-item.active').click();
      await page.locator('#screenLorePanel > details > summary').click();
      await page.getByLabel('Lorebook title').waitFor();
      const tid = await page.evaluate(() => TG.state.active_thread.id);
      const title = 'UNSAVED LORE ' + width;
      await page.getByLabel('Lorebook title').fill(title);
      await page.locator('#screenLorePanel textarea[placeholder^="Directions"]').fill('Keep these directions.');
      await page.evaluate(() => TG.renderMainChat());
      assert.equal(await page.getByLabel('Lorebook title').inputValue(), title);
      const other = await page.evaluate(() => TG.state.threads.find(t => t.id !== TG.state.active_thread.id).id);
      await page.evaluate(id => TG.selectThread(id), other);
      await page.waitForFunction(id => TG.state.active_thread.id === id, other);
      await page.evaluate(id => TG.selectThread(id), tid);
      await page.waitForFunction(id => TG.state.active_thread.id === id, tid);
      await page.getByLabel('Lorebook title').waitFor();
      assert.equal(await page.getByLabel('Lorebook title').inputValue(), title);
      assert.equal(await page.locator('#screenLorePanel textarea[placeholder^="Directions"]').inputValue(), 'Keep these directions.');
      await page.getByRole('button', {name: 'Save to this chat', exact: true}).click();
      await page.waitForFunction(() => document.getElementById('screenLoreStatus').textContent.includes('preserved'));
      assert.equal(await page.getByLabel('Lorebook title').inputValue(), title);
      await page.evaluate(async () => fetch(TG_CFG.screen_lore_api, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': TG_CFG.csrf},
        body: JSON.stringify({thread_id: TG.state.active_thread.id, action: 'save', book: {title: 'NEWER SAVED BOOK', entries: []}})}));
      await page.getByRole('button', {name: 'Save to this chat', exact: true}).click();
      await page.getByText('Review the saved version on the server', {exact: true}).waitFor();
      assert.equal(await page.getByLabel('Lorebook title').inputValue(), title);
      await page.getByRole('button', {name: 'Save my draft instead of that version', exact: true}).click();
      await page.waitForFunction(() => document.getElementById('screenLoreStatus').textContent.includes('Saved for'));
      await page.locator('button[onclick="VN_SCENES.openLaunchModalFromChat()"]').first().click();
      await page.evaluate(() => {VN_SCENES.beatIndex = VN_SCENES.activeScene().beats.length - 1; VN_SCENES.renderStageOnly();});
      const reply = 'UNSENT REPLY ' + width;
      await page.locator('#vnShortInput').fill(reply);
      await page.evaluate(() => {VN_SCENES.prevBeat(); VN_SCENES.nextBeat();});
      assert.equal(await page.locator('#vnShortInput').inputValue(), reply);
      await page.locator('.vn-passage-tools').evaluate(el => el.open = true);
      await page.getByRole('button', {name: 'Regenerate from here (uses tokens)', exact: true}).click();
      await page.waitForFunction(() => VN_SCENES.busy);
      assert.equal(await page.locator('#vnShortInput').isDisabled(), true);
      await page.getByRole('button', {name: 'Back to phone', exact: true}).click();
      await page.evaluate(id => TG.selectThread(id), other);
      await page.waitForFunction(id => TG.state.active_thread.id === id, other);
      await page.locator('#tgMessageInput').fill('FOR THE OTHER CHAT');
      for (let i = 0; !releaseGeneration && i < 100; i++) await new Promise(resolve => setTimeout(resolve, 10));
      assert(releaseGeneration); releaseGeneration();
      await page.waitForFunction(() => !VN_SCENES.busy);
      assert.equal(await page.evaluate(() => TG.state.active_thread.id), other, 'late generation must not redirect the phone');
      assert.equal(await page.locator('#tgMessageInput').inputValue(), 'FOR THE OTHER CHAT');
      await page.locator('#tgMessageInput').fill('');
      await page.evaluate(id => TG.selectThread(id), tid);
      await page.waitForFunction(id => TG.state.active_thread.id === id, tid);
      await page.locator('button[onclick="VN_SCENES.openLaunchModalFromChat()"]').first().click();
      await page.evaluate(() => {VN_SCENES.beatIndex = VN_SCENES.activeScene().beats.length - 1; VN_SCENES.renderStageOnly();});
      await page.locator('.vn-editor-settings').evaluate(el => el.open = true);
      await page.locator('.vn-editor-settings textarea').first().fill('UNSAVED WRITING DIRECTIONS');
      await page.locator('.vn-editor-settings select').first().selectOption('choices');
      await page.waitForFunction(() => VN_SCENES.activeScene().interaction_mode === 'choices');
      assert.equal(await page.locator('.vn-editor-settings textarea').first().inputValue(), 'UNSAVED WRITING DIRECTIONS');
      await page.locator('.vn-editor-settings select').first().selectOption('mixed');
      await page.waitForFunction(() => VN_SCENES.activeScene().interaction_mode === 'mixed');
      assert.equal(await page.locator('#vnShortInput').inputValue(), reply);
      failPreference = true;
      await page.locator('.vn-editor-settings select').first().selectOption('write');
      await page.waitForFunction(() => document.getElementById('vnNotice').textContent.includes('unreadable'));
      assert.equal(await page.locator('.vn-editor-settings select').first().inputValue(), 'mixed');
      assert.equal(await page.locator('#vnShortInput').inputValue(), reply);
      await page.locator('.vn-end-options').evaluate(el => el.open = true);
      await page.getByRole('button', {name: 'Finish & Save', exact: true}).click();
      assert.equal(finishes, 0);
      await page.locator('.vn-visual-settings').evaluate(el => el.open = true);
      await page.locator('.vn-visual-settings input[type=checkbox]').check();
      await page.waitForFunction(() => VN_SCENES.activeScene().auto_generate_sprites === true);
      await page.getByRole('button', {name: 'Save unfinished episode', exact: true}).click();
      await page.waitForFunction(() => !VN_SCENES.activeScene());
      assert.equal(await page.locator('#vnLaunchAutoSprites').isChecked(), false);
      await page.getByRole('button', {name: 'Versions', exact: true}).click();
      await page.getByRole('button', {name: 'Resume as a separate branch', exact: true}).last().click();
      await page.waitForFunction(() => VN_SCENES.activeScene()?.resumed_from);
      await page.evaluate(() => {VN_SCENES.beatIndex = VN_SCENES.activeScene().beats.length - 1; VN_SCENES.renderStageOnly();});
      assert.equal(await page.locator('#vnShortInput').inputValue(), reply);
      assert.equal(await page.locator('.vn-visual-settings input[type=checkbox]').isChecked(), true);
      await page.evaluate(() => {TG.state.vn_scenes.drafts.push({id: 'missing-version', title: 'Missing test version', label: 'Test'});});
      await page.getByRole('button', {name: 'Versions', exact: true}).click();
      await page.getByRole('button', {name: 'Resume as a separate branch', exact: true}).last().click();
      await page.locator('#modalStoryBody').getByText('That saved version is gone.', {exact: true}).waitFor();
      assert(await page.locator('#modalStory').evaluate(el => el.classList.contains('open')));
      await page.getByRole('button', {name: 'Close', exact: true}).last().click();
      await page.evaluate(() => {
        window.safeBeat = structuredClone(VN_SCENES.currentBeat());
        const beat = VN_SCENES.currentBeat(); beat.character_slug = 'listener'; beat.character_name = 'Ivo "the listener"'; beat.emotion = 'surprised'; beat.sprite_url = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg"/%3E';
        VN_SCENES.renderStageOnly();
      });
      assert.equal(await page.locator('.vn-central-sprite-img').getAttribute('alt'), 'Ivo "the listener"');
      assert(!(await page.locator('.vn-speaker-plate').textContent()).includes('surprised'));
      await page.locator('.vn-central-sprite-img').evaluate(image => image.dispatchEvent(new Event('error')));
      await page.locator('.vn-unavailable-sprite').getByText('Image unavailable', {exact: true}).waitFor();
      await page.evaluate(() => {Object.assign(VN_SCENES.currentBeat(), window.safeBeat); VN_SCENES.renderStageOnly();});
      const passages = await page.evaluate(() => VN_SCENES.activeScene().beats.length);
      await page.evaluate(() => {VN_SCENES.activeScene().choices = []; VN_SCENES.activeScene().interaction_mode = 'choices'; VN_SCENES.renderStageOnly();});
      await page.getByRole('button', {name: 'Suggest options (uses tokens)', exact: true}).click();
      await page.getByRole('button', {name: /Wait by the door/}).waitFor();
      assert.equal(await page.evaluate(() => VN_SCENES.activeScene().beats.length), passages);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Draft recovery, failed saves, lore conflicts, mode changes, unfinished episodes and expression labels pass at ${width}px.`);
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
