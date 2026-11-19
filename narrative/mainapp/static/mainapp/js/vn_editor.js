/* Episode settings, passage revisions, saved versions and prepared-request inspection. */
(() => {
  const node = (tag, text, cls) => {const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e;};
  const button = (text, fn) => {const b = node('button', text, 'tg-fmt-btn'); b.type = 'button'; b.addEventListener('click', fn); return b;};
  const text = (value, placeholder = '') => {const t = node('textarea', null, 'tg-textarea'); t.value = value || ''; t.placeholder = placeholder; return t;};
  const vn = () => window.VN_SCENES;
  async function change(action, extra = {}) {
    try {
      const previousBeat = vn().currentBeat()?.id;
      vn().notify(action === 'edit_passage' ? 'Bulba is saving the edit and updating continuity…' : 'Working on this episode…');
      const result = await vn().apiPost({action, ...extra});
      TG.state.vn_scenes = result.vn_scenes;
      vn().lastFinaleEntry = null;
      vn().tab = 'stage';
      if (result.thread) TG.state.active_thread = result.thread;
      if (result.threads) TG.state.threads = result.threads;
      const scene = result.scene;
      const first = action === 'episode_preferences' ? previousBeat : scene.current_beats?.[0]?.id;
      vn().beatIndex = first ? Math.max(0, scene.beats.findIndex(b => b.id === first)) : Math.max(0, scene.beats.length - 1);
      TG.renderSidebar?.(); TG.renderMainChat?.(); vn().switchTab('stage');
      vn().notify(action === 'episode_preferences' ? 'Episode preferences saved.' :
        ['edit_passage', 'regenerate_passage', 'branch_passage'].includes(action) ? 'Saved. Your previous version is under Versions.' : 'Episode opened as a separate branch.');
    } catch (error) {vn().notify(error.message, true);}
  }
  function select(label, value, choices, apply) {
    const wrap = node('label', label + ' '); const input = node('select', null, 'tg-select');
    choices.forEach(([key, name]) => input.append(new Option(name, key, false, key === value)));
    input.addEventListener('change', () => apply(input.value)); wrap.append(input); return wrap;
  }
  function settings(root, scene) {
    const details = node('details', null, 'vn-editor-settings'); details.append(node('summary', 'Episode preferences'));
    const content = node('div', null, 'vn-editor-content'); details.append(content);
    content.append(select('Respond with', scene.interaction_mode || 'mixed', [['choices', 'Classic choices'], ['write', 'Write yourself'], ['mixed', 'Choices and writing']],
      value => change('episode_preferences', {interaction_mode: value})));
    content.append(select('Authorship', scene.authoring_mode || 'roleplay', [['roleplay', 'I control my character'], ['director', 'Direct the cast, including my character']],
      value => change('episode_preferences', {authoring_mode: value})));
    const directions = text(scene.direction, 'Length, pacing, voice or other writing directions');
    const label = node('label', 'Bulba polish '); const polish = node('input'); polish.type = 'checkbox'; polish.checked = !!scene.polish_enabled; label.append(polish);
    content.append(directions, label, button('Save directions', () => change('episode_preferences', {direction: directions.value, polish_enabled: polish.checked})));
    const inspect = node('details'); inspect.append(node('summary', 'Prepared request and matched lore'));
    inspect.addEventListener('toggle', async () => {
      if (!inspect.open || inspect.querySelector('pre')) return;
      try {const result = await vn().apiPost({action: 'inspect_request'}); const pre = node('pre', JSON.stringify(result.request || {note: 'No generation request stored for this version.'}, null, 2)); pre.style.whiteSpace = 'pre-wrap'; inspect.append(pre);}
      catch (error) {vn().notify(error.message, true);}
    });
    content.append(inspect); root.prepend(details);
  }
  function passageTools(root, scene) {
    const current = vn().currentBeat(); if (!current) return;
    const dock = root.querySelector('.vn-dialogue-box'); if (!dock) return;
    const tools = node('details', null, 'vn-passage-tools'); tools.append(node('summary', 'Edit, regenerate or branch'));
    const body = node('div', null, 'vn-editor-content'); tools.append(body);
    body.append(node('p', 'A passage may span several pages. Editing or regenerating replaces its continuation in this version; the previous version is saved.'));
    const group = scene.beats.filter(b => (b.block_id || b.id) === (current.block_id || current.id));
    const original = group[0]?.block_text || group.map(b => b.text).join(' ');
    const edited = text(original);
    body.append(edited, button('Save edit and refresh continuity with Bulba (uses tokens)', () => change('edit_passage', {beat_id: current.id, text: edited.value})));
    if (current.speaker_slug !== 'user' || current.generated) {
      const direction = text('', 'What should change in this take? (optional)');
      body.append(direction, button('Regenerate from here (uses tokens)', () => change('regenerate_passage', {beat_id: current.id, direction: direction.value})));
    }
    body.append(button('Branch after this passage', () => change('branch_passage', {beat_id: current.id})));
    dock.append(tools);
  }
  function versions() {
    const modal = document.getElementById('modalStory'), body = document.getElementById('modalStoryBody');
    if (!modal || !body) return;
    body.replaceChildren(node('h3', 'Saved versions'));
    const drafts = TG.state.vn_scenes?.drafts || [];
    if (!drafts.length) body.append(node('p', 'Edits, regenerations and branches save their previous version here.'));
    drafts.forEach(draft => {const row = node('div', null, 'vn-editor-content'); row.append(node('strong', draft.title), node('span', draft.label),
      button('Resume as a separate branch', async () => {await change('resume_draft', {draft_id: draft.id}); modal.classList.remove('open');})); body.append(row);});
    body.append(button('Close', () => modal.classList.remove('open'))); modal.classList.add('open');
  }
  document.addEventListener('DOMContentLoaded', () => {
    if (!vn()) return;
    const original = vn().renderStageOnly.bind(vn());
    vn().renderStageOnly = () => {
      original(); const root = document.getElementById('vnScenesRoot'), scene = vn().activeScene();
      if (root && scene && vn().tab === 'stage') {settings(root, scene); passageTools(root, scene);}
    };
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
