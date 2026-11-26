/* Stories: long-form visual novels that start from scratch, played scene by scene.
 *
 * The list of your stories; a new story's sheet (your wishes, the cast, the setting, who you play), where Bulba
 * proposes the title, premise, world, side characters and opening for you to edit before anything is kept; and a
 * story's page: chapters reached, scenes to reread, the story bible, and the plan (hidden unless you ask for it).
 * "Play the next scene" opens the Scenes casting sheet fed from the story.
 */
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const lines = (text) => String(text || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const SETTINGS = [["canon", "Their own world"], ["modern", "Modern day"], ["original", "A new world for this story"]];

  async function post(payload) {
    const resp = await fetch((window.TG_CFG && TG_CFG.vn_scenes_api) || "/main/screen/scenes/api/", {
      method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": TG_CFG.csrf}, body: JSON.stringify(payload)});
    let data;
    try {data = await resp.json();} catch (_) {throw new Error(`The server returned an unreadable response (HTTP ${resp.status}).`);}
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  const blankDraft = () => ({wishes: "", cast: [], setting: "canon", tone: "", mode: "episodes", persona: {mode: "usual", name: "", description: ""},
                             setup: null, asking: false, error: "", showPlan: false});

  const STORIES = {
    view: "list", list: null, story: null, draft: blankDraft(), busy: false, error: "",

    root() {return document.getElementById("storiesRoot");},

    async load() {
      try {this.list = (await post({action: "story_list"})).stories; this.error = "";}
      catch (e) {this.error = e.message; this.list = this.list || [];}
      this.render();
    },

    async open(id) {
      this.opening = true;
      try {if (!document.getElementById("app-stories")?.classList.contains("active")) TG.switchApp("stories");}
      finally {this.opening = false;}
      this.view = "story";
      this.story = this.story?.id === id ? this.story : null;
      this.render();
      try {this.story = (await post({action: "story_get", story_id: id})).story; this.error = "";}
      catch (e) {this.error = e.message; this.view = "list";}
      this.render();
    },

    shown() {
      if (this.opening) return;
      this.view = this.view === "story" && this.story ? "story" : this.view;
      if (this.view === "story" && this.story) this.open(this.story.id); else {this.render(); this.load();}
    },

    render() {
      const root = this.root();
      if (!root) return;
      const body = this.view === "new" ? this.newSheet() : this.view === "story" ? this.storyPage() : this.listPage();
      root.innerHTML = `<div class="ep-stage cast-stage story-stage"><div class="cast-backdrop"></div>
        <div class="cast-sheet story-sheet">${this.error ? `<div class="cast-bulba cast-error" role="alert">${esc(this.error)}</div>` : ""}${body}</div></div>`;
    },

    /* ---------- the list ---------- */

    listPage() {
      const list = this.list;
      return `<header class="cast-head">
          <span class="cast-kicker">Stories</span>
          <h2>Stories</h2>
          <p class="cast-muted">Long visual novels that start from nothing, scene after scene. Bulba keeps the world, who stands where and what's still open, and steers toward a plan you only see if you ask.</p>
          <div class="cast-ask"><button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.startNew()">New story</button></div>
        </header>
        ${list === null ? `<p class="cast-muted">Loading your stories…</p>` : !list.length ? `<section class="cast-part"><p class="cast-muted">No stories yet.</p></section>` :
          list.map((s) => `<button type="button" class="cast-part story-row" onclick="STORIES.open(${Number(s.id)})">
            <span class="story-row-top"><b>${esc(s.title)}</b><span class="cast-badge ${s.status === "ended" ? "is-set" : ""}">${s.status === "ended" ? "Finished" : `Chapter ${s.chapter_now} of ${s.chapters}`}</span></span>
            <span class="story-row-text">${esc(s.premise)}</span>
            <span class="cast-muted">${esc(s.cast.map((c) => c.name).join(", "))} · ${s.scenes} ${s.scenes === 1 ? "scene" : "scenes"} · you play ${esc(s.persona)}</span>
          </button>`).join("")}`;
    },

    /* ---------- a new story ---------- */

    startNew() {this.view = "new"; this.error = ""; if (this.draft.setup === null && !this.draft.wishes) this.draft = blankDraft(); this.render();},

    characters() {return (TG.state.characters || []).map((c) => ({slug: c.slug, name: c.display_name || c.name}));},

    keep() {  // what's typed stays when the sheet redraws
      const root = this.root(), d = this.draft;
      if (!root || this.view !== "new") return;
      const val = (sel) => root.querySelector(sel)?.value;
      d.wishes = val("[data-st=wishes]") ?? d.wishes;
      d.tone = val("[data-st=tone]") ?? d.tone;
      d.setting = val("[data-st=setting]") ?? d.setting;
      d.mode = root.querySelector("[data-st=mode]:checked")?.value || d.mode;
      const mode = root.querySelector("[data-st=pmode]:checked")?.value;
      if (mode) d.persona.mode = mode;
      d.persona.name = val("[data-st=pname]") ?? d.persona.name;
      d.persona.description = val("[data-st=pdesc]") ?? d.persona.description;
      const s = d.setup;
      if (s) {
        s.title = val("[data-st=title]") ?? s.title;
        s.premise = val("[data-st=premise]") ?? s.premise;
        s.opening = val("[data-st=opening]") ?? s.opening;
        ["world", "relations", "threads"].forEach((k) => {const v = val(`[data-st=${k}]`); if (v !== undefined) s[k] = lines(v);});
        root.querySelectorAll("[data-side]").forEach((el) => {
          const side = s.side_characters[Number(el.dataset.side)];
          if (side) side[el.dataset.field] = el.value.trim();
        });
      }
    },

    toggleCast(slug) {
      this.keep();
      const cast = new Set(this.draft.cast);
      if (cast.has(slug)) cast.delete(slug); else if (cast.size < 6) cast.add(slug);
      this.draft.cast = [...cast];
      this.render();
    },

    newSheet() {
      const d = this.draft, s = d.setup;
      const chars = this.characters();
      const name = TG.state.user_profile?.display_name || "your usual persona";
      return `<header class="cast-head">
          <div class="cast-top"><span class="cast-kicker">Stories · new</span>
            <span class="cast-links"><button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.backToList()">All stories</button></span></div>
          <h2>A new story</h2>
          <p class="cast-muted">Tell Bulba what you'd like. It proposes the story; you change anything before it's kept.</p>
        </header>
        <section class="cast-part">
          <label class="cast-field">What do you want from this story? <span class="cast-muted">(a premise, a genre, a wish, or nothing)</span>
            <textarea class="ep-input" data-st="wishes" rows="3" placeholder="A slow mystery in a flooded city; we're rivals who end up working together…">${esc(d.wishes)}</textarea></label>
          <h3 class="cast-sub">The cast <span class="cast-muted">(up to 6; Bulba can add side characters)</span></h3>
          <div class="cast-chips">${chars.map((c) => `<button type="button" class="cast-chip ${d.cast.includes(c.slug) ? "is-on" : ""}" aria-pressed="${d.cast.includes(c.slug)}"
            onclick="STORIES.toggleCast('${esc(c.slug)}')">${esc(c.name)}</button>`).join("") || `<span class="cast-muted">You have no characters yet.</span>`}</div>
          <div class="cast-grid">
            <label class="cast-field">Setting<select class="tg-select" data-st="setting">${SETTINGS.map(([v, l]) => `<option value="${v}" ${d.setting === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="cast-field">Tone <span class="cast-muted">(optional)</span><input class="ep-input" data-st="tone" value="${esc(d.tone)}" placeholder="slow burn, dry humour…"></label>
          </div>
          <h3 class="cast-sub">How you play it</h3>
          <label class="cast-check"><input type="radio" name="stMode" data-st="mode" value="episodes" ${d.mode !== "roleplay" ? "checked" : ""}> Episodes: each scene is cast with Bulba first; short turns, choices if you like</label>
          <label class="cast-check"><input type="radio" name="stMode" data-st="mode" value="roleplay" ${d.mode === "roleplay" ? "checked" : ""}> Roleplay: only the first scene is planned; you write one to three paragraphs and get about as much back</label>
          <h3 class="cast-sub">Who you play</h3>
          <label class="cast-check"><input type="radio" name="stPersona" data-st="pmode" value="usual" ${d.persona.mode === "usual" ? "checked" : ""} onchange="STORIES.keep(); STORIES.render()"> As usual: ${esc(name)}</label>
          <label class="cast-check"><input type="radio" name="stPersona" data-st="pmode" value="story" ${d.persona.mode === "story" ? "checked" : ""} onchange="STORIES.keep(); STORIES.render()"> Someone for this story</label>
          ${d.persona.mode === "story" ? `<div class="cast-grid"><input class="ep-input" data-st="pname" value="${esc(d.persona.name)}" placeholder="Name">
            <textarea class="ep-input" data-st="pdesc" rows="2" placeholder="Who they are, how they look">${esc(d.persona.description)}</textarea></div>` : ""}
          <div class="cast-ask"><button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.ask()" ${d.asking ? "disabled" : ""}>🥔 ${s ? "Ask Bulba again" : "Ask Bulba to set it up"}</button></div>
          ${d.asking ? `<div class="cast-bulba" role="status"><span class="cast-potato" aria-hidden="true">🥔</span><span>Bulba is setting up your story<span class="cast-dots"><i>.</i><i>.</i><i>.</i></span></span></div>` : ""}
          ${d.error ? `<div class="cast-bulba cast-error" role="alert">${esc(d.error)}</div>` : ""}
        </section>
        ${s ? this.setupParts(s) : ""}`;
    },

    setupParts(s) {
      const d = this.draft;
      const list = (key, label, hint) => `<section class="cast-part"><h3>${label} <span class="cast-badge is-bulba">Bulba</span></h3>
        <p class="cast-muted">${hint}</p><textarea class="ep-input" data-st="${key}" rows="${Math.min(10, Math.max(3, (s[key] || []).length + 1))}">${esc((s[key] || []).join("\n"))}</textarea></section>`;
      return `<section class="cast-part"><h3>The story <span class="cast-badge is-bulba">Bulba</span></h3>
          <label class="cast-field">Title<input class="ep-input" data-st="title" value="${esc(s.title)}"></label>
          <label class="cast-field">Premise<textarea class="ep-input" data-st="premise" rows="4">${esc(s.premise)}</textarea></label>
          <label class="cast-field">How it opens<textarea class="ep-input" data-st="opening" rows="2">${esc(s.opening)}</textarea></label></section>
        ${list("world", "The world", "Facts every scene keeps true, one per line.")}
        <section class="cast-part"><h3>Side characters <span class="cast-badge is-bulba">Bulba</span></h3>
          <p class="cast-muted">Made for this story only: they never show up in your library or on the phone. Their first look is drawn from the appearance written here.</p>
          ${(s.side_characters || []).map((c, i) => `<div class="cast-outfit">
            <div class="cast-grid"><input class="ep-input" data-side="${i}" data-field="name" value="${esc(c.name)}" aria-label="Name">
              <input class="ep-input" data-side="${i}" data-field="role" value="${esc(c.role)}" aria-label="Role"></div>
            <textarea class="ep-input" data-side="${i}" data-field="appearance" rows="2" aria-label="Appearance">${esc(c.appearance)}</textarea>
            <textarea class="ep-input" data-side="${i}" data-field="personality" rows="2" aria-label="Personality">${esc(c.personality)}</textarea>
            <div class="cast-actions"><button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.dropSide(${i})">Not this one</button></div></div>`).join("")
            || `<p class="cast-muted">None: your cast carries the story.</p>`}</section>
        ${list("relations", "Where people stand", "With your character at the start, one per line.")}
        ${list("threads", "Open threads", "Questions, promises and problems at the start.")}
        <section class="cast-part"><h3>The plan <span class="cast-badge">hidden</span></h3>
          <p class="cast-muted">${s.arc.chapters.length} chapters with turning points, and a direction for the ending. The storyteller steers toward it quietly; your choices can change it. It stays a surprise unless you look.</p>
          <label class="cast-check"><input type="checkbox" ${d.showPlan ? "checked" : ""} onchange="STORIES.keep(); STORIES.draft.showPlan = this.checked; STORIES.render()"> Show me the plan</label>
          ${d.showPlan ? this.arcList(s.arc) : ""}</section>
        <div class="cast-ask story-go"><button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.create(this)">Keep this story</button>
          <button type="button" class="ep-btn" onclick="STORIES.discard()">Not this</button></div>`;
    },

    arcList(arc, at = null) {
      return `<ol class="story-arc">${(arc.chapters || []).map((ch, i) => `<li class="${at && i < at.chapter ? "is-done" : at && i === at.chapter ? "is-now" : ""}">
          <b>${esc(ch.title)}</b> <span class="cast-muted">${esc(ch.goal)}</span>
          <ul>${(ch.beats || []).map((b, j) => `<li class="${at && (i < at.chapter || (i === at.chapter && j < at.beat)) ? "is-done" : ""}">${esc(b)}</li>`).join("")}</ul>
          ${ch.ends_when ? `<span class="cast-muted">Closes when: ${esc(ch.ends_when)}</span>` : ""}</li>`).join("")}</ol>
        ${arc.ending ? `<p class="cast-muted"><b>Heading toward:</b> ${esc(arc.ending)}</p>` : ""}`;
    },

    dropSide(i) {this.keep(); this.draft.setup.side_characters.splice(i, 1); this.render();},

    async discard() {
      if (!(await EpDialog.confirm("Throw away Bulba's setup? Your wishes and cast stay.", {ok: "Throw it away"}))) return;
      this.keep(); this.draft.setup = null; this.render();
    },

    async ask() {
      this.keep();
      const d = this.draft;
      if (d.persona.mode === "story" && !d.persona.name.trim()) {d.error = "Give the character you play a name, or play as usual."; this.render(); return;}
      d.asking = true; d.error = ""; this.render();
      try {
        d.setup = (await post({action: "story_propose", wishes: d.wishes, cast: d.cast, setting: d.setting, tone: d.tone, persona: d.persona})).setup;
      } catch (e) {d.error = e.message;}
      d.asking = false; this.render();
    },

    async create(btn) {
      this.keep();
      const d = this.draft;
      if (!d.setup.title.trim()) {d.error = "Give the story a title."; this.render(); return;}
      btn.disabled = true;
      try {
        const data = await post({action: "story_create", setup: d.setup, cast: d.cast, setting: d.setting, persona: d.persona, mode: d.mode});
        this.draft = blankDraft();
        this.story = data.story; this.view = "story"; this.list = null;
        this.render();
      } catch (e) {d.error = e.message; btn.disabled = false; this.render();}
    },

    backToList() {this.keep(); this.view = "list"; this.error = ""; this.render(); this.load();},

    /* ---------- a story ---------- */

    storyPage() {
      const s = this.story;
      if (!s) return `<p class="cast-muted">Opening the story…</p>`;
      const bible = s.bible || {};
      const scenes = s.scene_list || [];
      const ended = s.status === "ended";
      const byChapter = {};
      scenes.forEach((sc) => {(byChapter[sc.chapter] = byChapter[sc.chapter] || []).push(sc);});
      const bl = (items) => (items || []).length ? `<ul class="cast-facts">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : `<p class="cast-muted">Nothing yet.</p>`;
      return `<header class="cast-head">
          <div class="cast-top"><span class="cast-kicker">Story · ${ended ? "finished" : `chapter ${s.chapter_now} of ${s.chapters}`}</span>
            <span class="cast-links"><button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.backToList()">All stories</button></span></div>
          <h2>${esc(s.title)}</h2>
          <p class="cast-opening">${esc(s.premise)}</p>
          <p class="cast-muted">You play ${esc(s.persona)} · ${esc(s.cast.map((c) => c.name + (c.side ? " (this story's)" : "")).join(", "))}${s.tone ? " · " + esc(s.tone) : ""}${s.cost ? ` · spent so far $${Number(s.cost).toFixed(2)}` : ""}</p>
          <div class="cast-ask">
            ${s.open_scene ? `<button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.resumeOpen()">▶ Continue “${esc(s.open_scene.title || "the scene")}”</button>`
              : ended ? "" : `<button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.play()">🎬 ${!scenes.length ? "Play the first scene" : s.mode === "roleplay" ? "Continue the story" : "Play the next scene"}</button>`}
            ${(s.drafts || []).map((d) => `<button type="button" class="ep-btn" onclick="STORIES.resumeDraft('${esc(d.id)}')">Resume “${esc(d.title)}”</button>`).join("")}
            <label class="cast-field story-mode">How you play
              <select class="tg-select" onchange="STORIES.setMode(this.value)">
                <option value="episodes" ${s.mode !== "roleplay" ? "selected" : ""}>Episodes: each scene is cast, short turns with choices</option>
                <option value="roleplay" ${s.mode === "roleplay" ? "selected" : ""}>Roleplay: you write paragraphs, the story flows on</option></select></label>
          </div>
        </header>
        ${(s.missing || []).length ? `<section class="cast-part"><h3>Not in the story yet</h3>
          <p class="cast-muted">These scenes finished, but Bulba couldn't add them to the story then.</p>
          ${s.missing.map((m) => `<div class="cast-outfit"><b>${esc(m.title || "A scene")}</b><span>${esc(m.summary)}</span>
            <div class="cast-actions"><button type="button" class="ep-btn" onclick="STORIES.catchUp('${esc(m.id)}', this)">Add it to the story</button></div></div>`).join("")}</section>` : ""}
        ${(s.new_people || []).length ? `<section class="cast-part"><h3>Bulba noticed <span class="cast-badge is-bulba">Bulba</span></h3>
          <p class="cast-muted">People who came up and may matter again. Added, they become this story's own characters with their own looks.</p>
          ${s.new_people.map((p) => `<div class="cast-outfit"><b>${esc(p.name)}</b> <span class="cast-muted">${esc(p.role)}</span><span>${esc(p.appearance)}</span>
            <div class="cast-actions"><button type="button" class="ep-btn" onclick="STORIES.newPerson('${esc(p.name)}', true)">Add to the story</button>
            <button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.newPerson('${esc(p.name)}', false)">Not this one</button></div></div>`).join("")}</section>` : ""}
        ${this.peoplePart(s)}
        <section class="cast-part"><h3>Scenes</h3>
          ${scenes.length ? Object.keys(byChapter).map((n) => `<div class="story-chapter">
              <h3 class="cast-sub">Chapter ${Number(n)}${(s.chapter_titles || [])[n - 1] ? ": " + esc(s.chapter_titles[n - 1]) : ""}</h3>
              ${byChapter[n].map((sc) => `<button type="button" class="story-scene" onclick="STORIES.reread(${Number(sc.id)})">
                ${sc.cg_url ? `<img src="${esc(sc.cg_url)}" alt="" loading="lazy">` : `<span class="story-scene-num">${sc.number}</span>`}
                <span><b>${esc(sc.title || "Scene " + sc.number)}</b> <span class="cast-muted">${esc(sc.place)}</span><br>${esc(sc.summary)}</span></button>
                ${sc.chapter_card?.title ? `<div class="story-card-mini"><b>Chapter ${sc.chapter_card.chapter} closed: ${esc(sc.chapter_card.title)}</b><span>${esc(sc.chapter_card.text)}</span></div>` : ""}`).join("")}
            </div>`).join("") : `<p class="cast-muted">${esc(bible.opening || "The first scene hasn't been played yet.")}</p>`}
        </section>
        <details class="cast-part cast-play"><summary><h3>The story so far, as Bulba keeps it</h3></summary>
          <h3 class="cast-sub">The world</h3>${bl(bible.world)}
          <h3 class="cast-sub">Where people stand</h3>${bl(bible.relations)}
          <h3 class="cast-sub">Open threads</h3>${bl(bible.threads)}
          <h3 class="cast-sub">Timeline</h3>${bl(bible.timeline)}
          ${bible.last?.place ? `<p class="cast-muted">Last scene ended at ${esc(bible.last.place)}${bible.last.time ? ", " + esc(bible.last.time) : ""}.</p>` : ""}
        </details>
        <section class="cast-part"><h3>The plan <span class="cast-badge">${s.show_arc ? "shown" : "hidden"}</span></h3>
          <label class="cast-check"><input type="checkbox" ${s.show_arc ? "checked" : ""} onchange="STORIES.showArc(this.checked)"> Show me the plan (it spoils the surprises)</label>
          ${s.show_arc && s.arc ? this.arcList(s.arc, s.arc.at) : ""}</section>
        <div class="cast-ask"><button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.remove()">Delete story</button></div>`;
    },

    /* The story's own people (side characters, and who you play when it's someone of your own): their cards. */
    peoplePart(s) {
      const people = [...(s.player ? [{...s.player, slug: "user", you: true}] : []), ...(s.sides || [])];
      if (!people.length) return "";
      const card = (p) => this.editing === p.slug ? `<div class="cast-outfit" data-edit="${esc(p.slug)}">
          <div class="cast-grid"><input class="ep-input" data-f="name" value="${esc(p.name)}" aria-label="Name">
            ${p.you ? "" : `<input class="ep-input" data-f="role" value="${esc(p.role)}" aria-label="Role">`}</div>
          <label class="cast-field">How they look<textarea class="ep-input" data-f="appearance" rows="2">${esc(p.appearance)}</textarea></label>
          ${p.you ? "" : `<label class="cast-field">Who they are<textarea class="ep-input" data-f="personality" rows="2">${esc(p.personality)}</textarea></label>
          <label class="cast-field">How they talk<input class="ep-input" data-f="speech" value="${esc(p.speech)}"></label>`}
          <p class="cast-muted">Looks they already have stay as they are; a new look follows the new description.</p>
          <div class="cast-actions"><button type="button" class="ep-btn ep-btn-primary" onclick="STORIES.saveSide('${esc(p.slug)}', this)">Save</button>
            <button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.editing = null; STORIES.render()">Cancel</button></div></div>`
        : `<div class="cast-outfit"><b>${esc(p.name)}${p.you ? " (you)" : ""}</b> <span class="cast-muted">${esc(p.you ? "who you play in this story" : p.role)}</span>
          <span>${esc(p.appearance)}</span>
          <div class="cast-actions"><button type="button" class="ep-btn ep-btn-quiet" onclick="STORIES.editing = '${esc(p.slug)}'; STORIES.render()">Edit</button></div></div>`;
      return `<section class="cast-part"><h3>This story's people</h3>${people.map(card).join("")}</section>`;
    },

    async saveSide(slug, btn) {
      const box = this.root().querySelector(`[data-edit="${CSS.escape(slug)}"]`);
      const body = {action: "story_side_edit", story_id: this.story.id, slug};
      box.querySelectorAll("[data-f]").forEach((el) => {body[el.dataset.f] = el.value.trim();});
      if (!body.name) {this.error = "Give them a name."; this.render(); return;}
      btn.disabled = true;
      await this.update(body);
      this.editing = null; this.render();
    },

    async update(body) {
      try {this.story = (await post(body)).story; this.error = "";}
      catch (e) {this.error = e.message;}
      this.render();
    },

    setMode(mode) {return this.update({action: "story_edit", story_id: this.story.id, mode});},
    newPerson(name, add) {return this.update({action: "story_new_person", story_id: this.story.id, name, add});},
    async catchUp(id, btn) {btn.disabled = true; btn.textContent = "Bulba is reading it…"; await this.update({action: "story_catch_up", story_id: this.story.id, episode_id: id});},

    resumeOpen() {
      VN_SCENES.story = this.packForScenes(); VN_SCENES.tab = "stage"; VN_SCENES.lastFinaleEntry = null;
      TG.switchApp("scenes"); VN_SCENES.render();
    },
    async resumeDraft(id) {
      try {
        const data = await VN_SCENES.apiPost({action: "resume_draft", draft_id: id});
        if (data.vn_scenes) TG.state.vn_scenes = data.vn_scenes;
        this.resumeOpen();
      } catch (e) {this.error = e.message; this.render();}
    },
    packForScenes() {
      const s = this.story;
      return {id: s.id, title: s.title, scenes: (s.scene_list || []).length, cast: s.cast, mode: s.mode, previously: s.previously};
    },

    async showArc(show) {
      try {this.story = (await post({action: "story_show_arc", story_id: this.story.id, show})).story;}
      catch (e) {this.error = e.message;}
      this.render();
    },

    play() {
      const s = this.story;
      if (!window.VN_SCENES) return;
      // a roleplay story is only planned once: after the first scene, it simply carries on
      if (s.mode === "roleplay" && (s.scene_list || []).length) VN_SCENES.continueStory(this.packForScenes());
      else VN_SCENES.playStory(this.packForScenes());
    },

    async reread(id) {
      let scene;
      try {scene = (await post({action: "story_scene", story_scene_id: id})).scene;}
      catch (e) {this.error = e.message; this.render(); return;}
      const pages = (scene.beats || []).filter((b) => b.kind !== "direction").map((b) => {
        const who = b.speaker_slug === "narrator" || b.kind === "narration" ? "" : `<b>${esc(b.speaker_name || b.speaker)}</b> `;
        return `<p class="story-line ${who ? "" : "is-narration"}">${who}${esc(b.text)}</p>`;
      }).join("");
      EpDialog.open({title: scene.title || "Scene", wide: true, html: `<div class="story-reread">
        ${scene.cg_url ? `<img src="${esc(scene.cg_url)}" alt="" class="story-reread-cg">` : ""}
        <p class="cast-muted">${esc(scene.place)}</p>${pages || `<p class="cast-muted">${esc(scene.summary)}</p>`}</div>`});
    },

    async remove() {
      const s = this.story;
      if (!(await EpDialog.confirm(`Delete “${s.title}”, its scenes and its side characters (with their looks)? This can't be undone.`,
          {ok: "Delete the story", danger: true}))) return;
      try {await post({action: "story_delete", story_id: s.id}); this.story = null; this.backToList();}
      catch (e) {this.error = e.message; this.render();}
    },
  };

  window.STORIES = STORIES;
  window.addEventListener("screen-app-changed", (e) => {if (e.detail?.app === "stories") STORIES.shown();});
})();
