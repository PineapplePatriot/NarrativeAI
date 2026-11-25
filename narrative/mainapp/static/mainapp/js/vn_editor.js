/* Episode settings, passage revisions, saved versions and prepared-request inspection. */
(() => {
  const node = (tag, text, cls) => {const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e;};
  const button = (text, fn, mutation = false) => {const b = node('button', text, 'tg-fmt-btn'); b.type = 'button'; if (mutation) b.dataset.vnMutation = 'true'; b.addEventListener('click', fn); return b;};
  const text = (value, placeholder = '') => {const t = node('textarea', null, 'tg-textarea'); t.value = value || ''; t.placeholder = placeholder; return t;};
  const vn = () => window.VN_SCENES;
  async function change(action, extra = {}, errorTarget = null) {
    try {
      const previousBeat = vn().currentBeat()?.id;
      const previousPhone = TG.state.active_thread?.id;
      vn().notify(action === 'edit_passage' && vn().currentBeat()?.kind !== 'direction' ? 'Bulba is saving the edit and updating continuity…' : 'Working on this episode…');
      const result = await vn().apiPost({action, ...extra});
      TG.state.vn_scenes = result.vn_scenes;
      vn().lastFinaleEntry = null;
      vn().tab = 'stage';
      const samePhone = TG.state.active_thread?.id === previousPhone;
      if (result.thread && samePhone) TG.state.active_thread = result.thread;
      if (result.threads) TG.state.threads = result.threads;
      const scene = result.scene;
      if (scene?.resumed_from && action === 'resume_draft' && window.ScreenDrafts) ScreenDrafts.put('vn:' + scene.id, {...ScreenDrafts.get('vn:' + scene.resumed_from)});
      if (action === 'episode_preferences' && ('direction' in extra || 'polish_enabled' in extra)) window.ScreenDrafts?.clear('vn:' + scene.id, ['direction', 'polish']);
      const first = action === 'episode_preferences' ? previousBeat : scene?.current_beats?.[0]?.id;
      vn().beatIndex = scene ? first ? Math.max(0, scene.beats.findIndex(b => b.id === first)) : Math.max(0, scene.beats.length - 1) : 0;
      TG.renderSidebar?.(); if (samePhone) TG.renderMainChat?.(); vn().switchTab('stage');
      vn().notify(action === 'park_scene' ? 'Unfinished episode saved under Versions. You can start another episode.' : action === 'episode_preferences' ? 'Episode preferences saved.' :
        ['edit_passage', 'regenerate_passage', 'branch_passage'].includes(action) ? 'Saved. Your previous version is under Versions.' : 'Episode opened as a separate branch.');
      return true;
    } catch (error) {
      if (errorTarget) errorTarget.textContent = error.message;
      vn().renderStageOnly(); vn().notify(error.message, true); return false;
    }
  }
  function select(label, value, choices, apply) {
    const wrap = node('label', label + ' '); const input = node('select', null, 'tg-select');
    choices.forEach(([key, name]) => input.append(new Option(name, key, false, key === value)));
    input.addEventListener('change', () => apply(input.value)); wrap.append(input); return wrap;
  }
  function settings(root, scene) {
    const details = node('details', null, 'vn-editor-settings'); details.append(node('summary', 'Episode preferences'));
    details.dataset.screenField = 'preferences_open';
    const content = node('div', null, 'vn-editor-content'); details.append(content);
    content.append(select('Respond with', scene.interaction_mode || 'mixed', [['choices', 'Classic choices'], ['write', 'Write yourself'], ['mixed', 'Choices and writing']],
      value => change('episode_preferences', {interaction_mode: value})));
    content.append(select('Authorship', scene.authoring_mode || 'roleplay', [['roleplay', 'I control my character'], ['director', 'Direct the cast, including my character']],
      value => change('episode_preferences', {authoring_mode: value})));
    content.append(select('Dialogue and narration', scene.balance || 'balanced', [['balanced', 'Balanced'], ['dialogue', 'More dialogue'], ['narration', 'More narration and description']],
      value => change('episode_preferences', {balance: value})));
    content.append(select('Each turn writes', scene.length || 'medium', [['medium', 'Medium'], ['short', 'Short'], ['long', 'Long']],
      value => change('episode_preferences', {length: value})));
    content.append(select('My notes', scene.write_out === false ? 'as_is' : 'write_out', [['write_out', "Turn into my character's words"], ['as_is', 'Use exactly as I type them']],
      value => change('episode_preferences', {write_out: value === 'write_out'})));
    const directions = text(scene.direction, 'Length, pacing, voice or other writing directions');
    directions.dataset.screenField = 'direction';
    const label = node('label', 'Bulba polish '); const polish = node('input'); polish.type = 'checkbox'; polish.checked = !!scene.polish_enabled; label.append(polish);
    polish.dataset.screenField = 'polish';
    content.append(directions, label, button('Save directions', () => change('episode_preferences', {direction: directions.value, polish_enabled: polish.checked}), true));
    content.append(button('Save unfinished episode', () => change('park_scene'), true));
    content.append(button('Reload saved episode', () => vn().reloadScene(), true));
    const unsent = window.ScreenDrafts?.all('vn:').filter(draft => String(draft.reply || '').trim()) || [];
    if (unsent.length) {
      const recover = node('details'); recover.append(node('summary', ScreenDrafts.persistent ? 'Unsent replies saved in this tab' : 'Unsent replies on this page — copy before reloading'));
      unsent.forEach(draft => {const copy = text(draft.reply); copy.readOnly = true; recover.append(node('strong', draft.title || 'Episode'), copy);});
      content.append(recover);
    }
    const inspect = node('details'); inspect.append(node('summary', 'Prepared request and matched lore'));
    inspect.addEventListener('toggle', async () => {
      if (!inspect.open || inspect.querySelector('pre')) return;
      try {const result = await vn().apiPost({action: 'inspect_request'}); const pre = node('pre', JSON.stringify(result.request || {note: 'No generation request stored for this version.'}, null, 2)); pre.style.whiteSpace = 'pre-wrap'; inspect.append(pre);}
      catch (error) {vn().notify(error.message, true);}
    });
    content.append(inspect, button('Versions', versions));
    (root.querySelector('#epSheetEpisode') || root).append(details);
    window.ScreenDrafts?.bind(details, 'vn:' + scene.id);
  }
  function passageTools(root, scene) {
    const current = vn().currentBeat(); if (!current) return;
    const dock = root.querySelector('#epSheetPassage'); if (!dock) return;
    const tools = node('details', null, 'vn-passage-tools'); tools.append(node('summary', 'Edit, regenerate or branch from here'));
    tools.dataset.screenField = 'open';
    const body = node('div', null, 'vn-editor-content'); tools.append(body);
    body.append(node('p', 'A passage may span several pages. Editing or regenerating replaces its continuation in this version; the previous version is saved.'));
    const group = scene.beats.filter(b => (b.block_id || b.id) === (current.block_id || current.id));
    const original = group[0]?.block_text || group.map(b => b.text).join(' ');
    const edited = text(original);
    edited.dataset.screenField = 'text';
    body.append(edited, button(current.kind === 'direction' ? 'Save direction' : 'Save edit and refresh continuity with Bulba (uses tokens)', () => change('edit_passage', {beat_id: current.id, text: edited.value}), true));
    if (current.generated || current.speaker_slug !== 'user' && current.kind !== 'direction') {
      const direction = text('', 'What should change in this take? (optional)');
      direction.dataset.screenField = 'direction';
      body.append(direction, button('Regenerate from here (uses tokens)', () => change('regenerate_passage', {beat_id: current.id, direction: direction.value}), true));
    }
    body.append(button('Branch after this passage', () => change('branch_passage', {beat_id: current.id}), true));
    dock.append(tools);
    window.ScreenDrafts?.bind(tools, 'vn-edit:' + scene.id + ':' + (current.block_id || current.id));
  }
  function versions() {
    const modal = document.getElementById('modalStory'), body = document.getElementById('modalStoryBody');
    if (!modal || !body) return;
    body.replaceChildren(node('h3', 'Saved versions'));
    const drafts = TG.state.vn_scenes?.drafts || [];
    if (!drafts.length) body.append(node('p', 'Edits, regenerations and branches save their previous version here.'));
    drafts.forEach(draft => {const row = node('div', null, 'vn-editor-content'); const error = node('div'); error.setAttribute('role', 'alert'); row.append(node('strong', draft.title), node('span', draft.label),
      button('Resume as a separate branch', async () => {if (await change('resume_draft', {draft_id: draft.id}, error)) modal.classList.remove('open');}, true), error); body.append(row);});
    const local = window.ScreenDrafts?.all('vn:').filter(draft => String(draft.reply || '').trim()) || [];
    if (local.length) body.append(node('h4', 'Unsent local replies'));
    local.forEach(draft => {const copy = text(draft.reply); copy.readOnly = true; body.append(node('strong', draft.title || 'Episode'), copy);});
    body.append(button('Close', () => modal.classList.remove('open'))); modal.classList.add('open');
    vn().setBusy(vn().busy);
  }
  document.addEventListener('DOMContentLoaded', () => {
    if (!vn()) return;
    const original = vn().renderStageOnly.bind(vn());
    vn().renderStageOnly = () => {
      original(); const root = document.getElementById('vnScenesRoot'), scene = vn().activeScene();
      if (root && scene && vn().tab === 'stage') {settings(root, scene); passageTools(root, scene); vn().setBusy(vn().busy);}
    };
    vn().openVersions = versions;
    vn().passageChange = change;
    const nav = document.querySelector('#app-scenes .vn-nav-tabs');
    if (nav) nav.append(button('Versions', versions));
    const gallery = vn().renderGallery.bind(vn());
    vn().renderGallery = root => {
      gallery(root);
      root.querySelectorAll('.vn-cg-card').forEach((card, index) => {
        const entry = TG.state.vn_scenes.gallery[index];
        if (entry.episode) card.querySelector('.vn-cg-body').append(button('Reopen as a separate branch', () => change('reopen_completed', {episode_id: entry.id})));
      });
    };
    vn().render();
  });
})();
