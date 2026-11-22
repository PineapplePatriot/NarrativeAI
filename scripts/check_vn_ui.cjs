/* Run with Playwright installed: node scripts/check_vn_ui.cjs
   Exercises the production renderer with local fixtures; no model calls. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({viewport: {width, height: 844}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('http://vn.test/', route => route.fulfill({contentType: 'text/html', body:
        '<div class="screen-hub-shell"><section id="app-scenes" class="screen-app-view active"><div id="vnNotice" hidden></div><div id="vnLaunchTransition" hidden><p id="vnLaunchDetail"></p></div><div id="vnScenesRoot"></div><audio id="vnAudioPlayer"></audio></section></div>'}));
      await page.goto('http://vn.test/');
      if (process.env.VN_TEST_BLOCK_STORAGE) await page.evaluate(() => {
        for (const name of ['sessionStorage', 'localStorage']) Object.defineProperty(window, name, {get() {throw new DOMException('Storage disabled in test', 'SecurityError');}});
      });
      const assets = path.join(__dirname, '../narrative/mainapp/static/mainapp');
      await page.addStyleTag({path: path.join(assets, 'css/messenger.css')});
      await page.addStyleTag({path: path.join(assets, 'css/vn_scenes.css')});
      await page.evaluate(() => {
        const scene = {id: 'fixture', title: 'The archive', character_slugs: [],
          beats: [{id: 'one', kind: 'narration', speaker: 'narrator', text: 'Rain hits the window.'}],
          choices: ['Tell me more.', '"For you," she says. <ordinary text>'], handoff: 'user_turn'};
        window.TG = {
          state: {account_id: 1, characters: [], active_thread: {id: 1, title: 'Mira'},
            vn_scenes: {active_scene: scene, gallery: [], music_tracks: [], backgrounds: []}},
          esc: s => {const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML;},
          switchApp() {}, toast() {}, renderSidebar() {}, renderMainChat() {},
        };
      });
      await page.addScriptTag({path: path.join(assets, 'js/screen_drafts.js')});
      await page.addScriptTag({path: path.join(assets, 'js/vn_scenes.js')});
      await page.evaluate(() => VN_SCENES.init());
      const originalStep = await page.evaluate(() => {
        window.savedStep = VN_SCENES.stepScene;
        VN_SCENES.stepScene = text => {window.choice = text;};
        return true;
      });
      assert(originalStep);
      await page.locator('.vn-choice-chip').nth(1).click();
      assert.equal(await page.evaluate(() => window.choice), '"For you," she says. <ordinary text>');
      assert.equal(await page.locator('.vn-short-input').evaluate(el => el.tagName), 'TEXTAREA');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, `horizontal overflow at ${width}px`);
      await page.evaluate(() => {
        TG.state.vn_scenes.active_scene.beats.push({id: 'two', kind: 'narration', speaker: 'narrator', text: 'A second line.'});
        VN_SCENES.nextBeat();
        VN_SCENES.beatIndex = 0;
        VN_SCENES.init();
      });
      assert.equal(await page.evaluate(() => VN_SCENES.beatIndex), 1, 'reading position survives reinitialization');
      await page.evaluate(() => {
        VN_SCENES.stepScene = window.savedStep;
        window.requests = [];
        window.fetch = async (_url, opts) => {
          const body = JSON.parse(opts.body); requests.push(body);
          if (body.action === 'finish_scene') {
            TG.state.active_thread = {id: 2, title: 'Another phone chat'};
            return {ok: true, json: async () => ({thread: {id: 1, title: 'Mira'},
              vn_scenes: {active_scene: null, gallery: []}, gallery_entry: {title: 'Saved', summary: 'They met.'}})};
          }
          const scene = TG.state.vn_scenes.active_scene;
          const next = {id: 'three', kind: 'narration', speaker: 'narrator', text: 'The next turn.'};
          scene.beats.push(next);
          return {ok: true, json: async () => ({scene, new_beats: [next], vn_scenes: TG.state.vn_scenes})};
        };
      });
      await page.locator('#vnShortInput').fill('Unsent draft');
      await page.evaluate(() => {VN_SCENES.prevBeat(); VN_SCENES.nextBeat();});
      assert.equal(await page.locator('#vnShortInput').inputValue(), 'Unsent draft');
      await page.locator('#vnShortInput').fill('A long reply.\n\nA second paragraph.');
      await page.getByRole('button', {name: 'Act / Speak'}).click();
      await page.waitForFunction(() => VN_SCENES.currentBeat().id === 'three');
      assert.equal(await page.evaluate(() => requests[0].user_input), 'A long reply.\n\nA second paragraph.');
      await page.locator('.vn-end-options').evaluate(el => el.open = true);
      await page.getByRole('button', {name: 'Finish & Save', exact: true}).click();
      await page.waitForFunction(() => VN_SCENES.lastFinaleEntry);
      assert.equal(await page.evaluate(() => requests.at(-1).capture_image), false);
      assert.equal(await page.evaluate(() => TG.state.active_thread.id), 2, 'finishing must not replace a newer phone selection');
      await page.evaluate(() => {
        VN_SCENES.startAnotherScene();
        const launchResponse = new Promise(resolve => { window.completeLaunch = resolve; });
        window.fetch = () => launchResponse;
      });
      await page.locator('#vnWritingDirection').fill('Keep this draft.');
      await page.getByRole('button', {name: /Launch Meet-Up Scene/}).click();
      await page.locator('#vnLaunchTransition').waitFor({state: 'visible'});
      assert.equal(await page.locator('#vnScenesRoot').isVisible(), false);
      await page.evaluate(() => completeLaunch({
        ok: false, status: 400, json: async () => ({error: 'The model returned an invalid cast.'}),
      }));
      await page.getByRole('alert').waitFor({state: 'visible'});
      assert.equal(await page.locator('#vnLaunchTransition').isVisible(), false);
      assert.equal(await page.locator('#vnWritingDirection').inputValue(), 'Keep this draft.');
      await page.evaluate(() => {
        const launchResponse = new Promise(resolve => { window.completeLaunch = resolve; });
        window.fetch = () => launchResponse;
      });
      await page.getByRole('button', {name: /Launch Meet-Up Scene/}).click();
      await page.locator('#vnLaunchTransition').waitFor({state: 'visible'});
      await page.evaluate(() => {
        const scene = {id: 'launched', title: 'The meeting', character_slugs: [],
          beats: [{id: 'opening', kind: 'narration', speaker: 'narrator', text: 'The door opens.'}],
          handoff: 'user_turn'};
        completeLaunch({ok: true, json: async () => ({
          scene, vn_scenes: {...TG.state.vn_scenes, active_scene: scene},
        })});
      });
      await page.getByText('The door opens.', {exact: true}).waitFor({state: 'visible'});
      assert.equal(await page.locator('#vnLaunchTransition').isVisible(), false);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`VN renderer: choices, paragraphs, resume, launch recovery, completion and layout pass at ${width}px.`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
