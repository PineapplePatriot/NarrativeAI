/* Casting: the sheet an episode starts from.
 *
 * Bulba proposes who is there, the place written out, each person's outfit, the facts that must stay true, how it
 * opens and one optional detail. Each part is a proposal: Apply, Edit or Not this, and Undo once applied. Only
 * applied parts go to the episode, where they stay fixed. Nothing is drawn until the user presses a button that
 * says how many pictures it costs.
 */
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const vn = () => window.VN_SCENES;
  const lines = (text) => String(text || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const STORE = "ep-casting:";

  const blank = () => ({
    cast: null, proposal: null, asking: false, error: "",
    place: {state: "empty", value: {name: "", time: "", light: "", weather: "", details: [], background_id: ""}},
    facts: {state: "empty", value: []},
    opening: {state: "empty", value: ""},
    nudge: {state: "empty", value: ""},
    outfits: {},
  });

  const CASTING = {
    sheets: {},
    threadId: null,

    sheet() {
      const id = this.threadId;
      if (!this.sheets[id]) {
        let saved = null;
        try {saved = JSON.parse(sessionStorage.getItem(STORE + id) || "null");} catch (_) {saved = null;}
        this.sheets[id] = saved ? {...blank(), ...saved, asking: false} : blank();
      }
      return this.sheets[id];
    },

    save() {
      const s = this.sheet();
      try {sessionStorage.setItem(STORE + this.threadId, JSON.stringify({...s, asking: false, error: ""}));} catch (_) {}
    },

    clear(threadId) {
      delete this.sheets[threadId];
      try {sessionStorage.removeItem(STORE + threadId);} catch (_) {}
    },

    members() {
      const t = TG.state.active_thread;
      const slugs = (t?.member_slugs || (t?.members || []).map((m) => m.slug)).filter(Boolean);
      return slugs.map((slug) => {
        const c = (TG.state.characters || []).find((x) => x.slug === slug) || {slug};
        return {key: slug, name: c.display_name || c.name || slug};
      });
    },

    director() {return (document.getElementById("vnAuthoringMode")?.value || this.sheet().authoring) === "director";},

    inCast(key) {
      if (key === "user") return this.director();
      const cast = this.sheet().cast;
      return !cast || cast.includes(key);
    },

    backdrops() {return (TG.state.vn_scenes && TG.state.vn_scenes.backgrounds) || [];},

    backdrop(id) {return this.backdrops().find((b) => b.id === id) || null;},

    /* ---------- rendering ---------- */

    render(root, thread) {
      this.threadId = thread ? thread.id : "none";
      const s = this.sheet();
      const pulse = vn().pendingPulse;
      const members = this.members();
      const placeBg = s.place.state === "applied" ? this.backdrop(s.place.value.background_id) : null;
      root.innerHTML = `
        <div class="ep-stage cast-stage">
          <div class="cast-backdrop" style="${placeBg ? `background-image:url(${esc(JSON.stringify(placeBg.url))})` : ""}"></div>
          <div class="cast-sheet" role="form" aria-label="Casting">
            <header class="cast-head">
              <div class="cast-top">
                <span class="cast-kicker">In person · continues ${esc(thread ? thread.title : "your chat")}</span>
                <span class="cast-links">
                  <button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.switchTab('gallery')">Saved episodes</button>
                  ${(TG.state.vn_scenes?.drafts || []).length ? `<button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.openVersions?.()">Unfinished (${TG.state.vn_scenes.drafts.length})</button>` : ""}
                </span>
              </div>
              <h2>Casting</h2>
              <p class="cast-muted">Who's there, the place, what they wear and what stays true. What you apply here stays fixed for the whole episode.</p>
              ${pulse ? `<div class="cast-plan"><strong>Pulse plan: ${esc(pulse.title)}</strong><span>${esc(pulse.when_label)} · ${esc(pulse.location)}</span><span>${esc(pulse.purpose)}</span></div>` : ""}
              <label class="cast-field">Anything you want from this episode? <span class="cast-muted">(optional, Bulba reads it)</span>
                <textarea class="ep-input cast-short" id="vnLocationHintInput" data-screen-field="location" rows="2" placeholder="Where you meet, what should happen, a mood…"></textarea>
              </label>
              <div class="cast-ask">
                <button type="button" class="ep-btn ep-btn-primary" onclick="CASTING.ask(this)" ${s.asking ? "disabled" : ""}>🥔 ${s.proposal ? "Ask Bulba again" : "Ask Bulba to cast it"}</button>
                ${s.proposal ? `<button type="button" class="ep-btn" onclick="CASTING.applyAll()">Apply everything</button>` : ""}
              </div>
              ${s.asking ? `<div class="cast-bulba" role="status"><span class="cast-potato" aria-hidden="true">🥔</span><span>Bulba is reading your chat<span class="cast-dots"><i>.</i><i>.</i><i>.</i></span></span></div>` : ""}
              ${s.error ? `<div class="cast-bulba cast-error" role="alert">${esc(s.error)}</div>` : ""}
            </header>

            <section class="cast-part">
              <h3>Who's there</h3>
              <div class="cast-chips">
                ${members.map((m) => `<button type="button" class="cast-chip ${this.inCast(m.key) ? "is-on" : ""}" aria-pressed="${this.inCast(m.key)}"
                  onclick="CASTING.toggle('${esc(m.key)}')" ${pulse ? "disabled title='The plan sets who is there'" : ""}>${esc(m.name)}</button>`).join("")}
              </div>
            </section>

            <section class="cast-part">${this.placePart(s)}</section>

            <section class="cast-part">
              <h3>What they wear</h3>
              <p class="cast-muted">Each look is one outfit with its moods, all edited from one picture so they match.</p>
              <div id="vnLooksPanel" class="ep-looks"></div>
            </section>

            <section class="cast-part">${this.factsPart(s)}</section>
            <section class="cast-part">${this.openingPart(s)}</section>

            <details class="cast-part cast-play" data-screen-field="play_open">
              <summary><h3>How you play</h3></summary>
              <label class="cast-field" for="vnInteractionMode">How you respond
                <select class="tg-select" id="vnInteractionMode" data-screen-field="mode"><option value="mixed">Choices and writing</option><option value="choices">Classic choices</option><option value="write">Write yourself</option></select></label>
              <label class="cast-field" for="vnAuthoringMode">Who writes the cast
                <select class="tg-select" id="vnAuthoringMode" data-screen-field="authoring" onchange="CASTING.sheet().authoring = this.value; CASTING.save(); window.EPISODE_LOOKS?.render()"><option value="roleplay">Roleplay: I control my character</option><option value="director">Directing: the storyteller may write my character too</option></select></label>
              <label class="cast-field" for="vnWritingDirection">Writing preferences <span class="cast-muted">(optional)</span>
                <textarea class="ep-input" id="vnWritingDirection" data-screen-field="direction" rows="2" placeholder="Length, narration, dialogue, pacing…"></textarea></label>
              <label class="cast-check"><input type="checkbox" id="vnPolishEnabled" data-screen-field="polish"> Let Bulba polish the habits I approved before each turn shows</label>
              ${s.place.state === "applied" ? "" : `<label class="cast-check"><input type="checkbox" id="vnGenerateBackground" data-screen-field="generate_background"> No place set: draw a backdrop for wherever the story starts (1 picture)</label>`}
            </details>

            <footer class="cast-foot">
              <button type="button" class="ep-btn ep-btn-quiet" onclick="TG.switchApp('messenger')">Back to the phone</button>
              <button type="button" class="ep-btn ep-btn-primary cast-start" onclick="VN_SCENES.launchFromActiveThread()">${
                s.place.state === "applied" && !placeBg ? "Start the episode<small>draws the place · 1 picture</small>" : "Start the episode"}</button>
            </footer>
          </div>
        </div>`;
    },

    actions(part, extra = "") {
      const state = this.sheet()[part].state;
      if (state === "proposed") return `<div class="cast-actions">
          <button type="button" class="ep-btn ep-btn-primary" onclick="CASTING.apply('${part}')">Apply</button>
          <button type="button" class="ep-btn" onclick="CASTING.edit('${part}')">Edit</button>
          <button type="button" class="ep-btn ep-btn-quiet" onclick="CASTING.reject('${part}')">Not this</button></div>`;
      if (state === "editing") return `<div class="cast-actions">
          <button type="button" class="ep-btn ep-btn-primary" onclick="CASTING.saveEdit('${part}')">Apply</button>
          <button type="button" class="ep-btn ep-btn-quiet" onclick="CASTING.cancelEdit('${part}')">Cancel</button></div>`;
      if (state === "applied") return `<div class="cast-actions">${extra}
          <button type="button" class="ep-btn" onclick="CASTING.edit('${part}')">Edit</button>
          <button type="button" class="ep-btn ep-btn-quiet" onclick="CASTING.undo('${part}')">Undo</button></div>`;
      return `<div class="cast-actions"><button type="button" class="ep-btn" onclick="CASTING.edit('${part}')">Write it yourself</button></div>`;
    },

    badge(part) {
      const state = this.sheet()[part].state;
      return {proposed: `<span class="cast-badge is-bulba">Bulba suggests</span>`, applied: `<span class="cast-badge is-set">Fixed</span>`,
        editing: `<span class="cast-badge">Editing</span>`}[state] || "";
    },

    placePart(s) {
      const p = s.place.value, state = s.place.state;
      const bg = this.backdrop(p.background_id);
      const head = `<h3>The place ${this.badge("place")}</h3>`;
      if (state === "editing") {
        return `${head}
          <div class="cast-grid">
            <label class="cast-field">Place<input class="ep-input" data-place="name" maxlength="120" value="${esc(p.name)}" placeholder="The archive's map room"></label>
            <label class="cast-field">Time<input class="ep-input" data-place="time" maxlength="120" value="${esc(p.time)}" placeholder="Friday, 9:10 pm"></label>
            <label class="cast-field">Light<input class="ep-input" data-place="light" maxlength="200" value="${esc(p.light)}" placeholder="green reading lamps"></label>
            <label class="cast-field">Weather<input class="ep-input" data-place="weather" maxlength="160" value="${esc(p.weather)}" placeholder="rain on the skylight"></label>
          </div>
          <label class="cast-field">Layout, as you stand in it<input class="ep-input" data-place="layout" maxlength="400" value="${esc(p.layout || "")}" placeholder="Shelves on the left, the oak table in the middle, the cabinet at the back, a window on the right"></label>
          <label class="cast-field">What stays put, one per line<textarea class="ep-input" data-place="details" rows="3">${esc((p.details || []).join("\n"))}</textarea></label>
          <label class="cast-field">Backdrop<select class="tg-select" data-place="background_id">
            <option value="">None yet (draw it after applying)</option>
            ${this.backdrops().map((b) => `<option value="${esc(b.id)}" ${b.id === p.background_id ? "selected" : ""}>${b.kept ? "Kept · " : ""}${esc(b.name)}</option>`).join("")}
          </select></label>
          ${this.actions("place")}`;
      }
      if (state === "empty") return `${head}<p class="cast-muted">Not set: the storyteller picks a place.</p>${this.actions("place")}`;
      const draw = !bg ? `<button type="button" class="ep-btn ep-btn-primary" onclick="CASTING.drawPlace(this)">Draw this place · 1 picture</button>` : "";
      return `${head}
        <div class="cast-place">
          ${bg ? `<img class="cast-place-img" src="${esc(bg.url)}" alt="">` : `<div class="cast-place-img cast-place-none">No backdrop yet</div>`}
          <div class="cast-place-text">
            <strong>${esc(p.name || "Unnamed place")}</strong>
            <span class="cast-muted">${[p.time, p.light, p.weather].filter(Boolean).map(esc).join(" · ")}</span>
            ${p.layout ? `<span class="cast-layout">${esc(p.layout)}</span>` : ""}
            ${(p.details || []).length ? `<ul>${p.details.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}
            ${bg ? `<span class="cast-muted">Backdrop: ${bg.kept ? "kept place · " : ""}${esc(bg.name)}</span>` : ""}
          </div>
        </div>
        ${this.actions("place", state === "applied" ? draw : "")}`;
    },

    factsPart(s) {
      const head = `<h3>What stays true ${this.badge("facts")}</h3>`;
      if (s.facts.state === "editing") {
        return `${head}<label class="cast-field">One fact per line<textarea class="ep-input" data-facts rows="5">${esc(s.facts.value.join("\n"))}</textarea></label>${this.actions("facts")}`;
      }
      if (s.facts.state === "empty") return `${head}<p class="cast-muted">Nothing fixed: the episode follows the chat's memory.</p>${this.actions("facts")}`;
      return `${head}<ul class="cast-facts">${s.facts.value.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>${this.actions("facts")}`;
    },

    openingPart(s) {
      let html = `<h3>How it opens ${this.badge("opening")}</h3>`;
      if (s.opening.state === "editing") html += `<textarea class="ep-input" data-opening rows="2">${esc(s.opening.value)}</textarea>`;
      else if (s.opening.state === "empty") html += `<p class="cast-muted">Right where the texts left off.</p>`;
      else html += `<p class="cast-opening">${esc(s.opening.value)}</p>`;
      html += this.actions("opening");
      if (s.nudge.value || s.nudge.state === "editing") {
        html += `<h3 class="cast-sub">A detail to use ${this.badge("nudge")}</h3>`;
        html += s.nudge.state === "editing" ? `<textarea class="ep-input" data-nudge rows="2">${esc(s.nudge.value)}</textarea>`
          : s.nudge.state === "empty" ? `<p class="cast-muted">None.</p>` : `<p class="cast-opening">${esc(s.nudge.value)}</p>`;
        html += this.actions("nudge");
      }
      return html;
    },

    /* Bulba's outfit card for one person, shown in their row of the looks panel. */
    outfitCard(key) {
      const o = this.sheet().outfits[key];
      if (!o || o.state === "done") return "";
      const member = window.EPISODE_LOOKS?.member(key);
      const look = o.look_id && member ? member.looks.find((l) => l.id === o.look_id) : null;
      return `<div class="cast-outfit">
          <span class="cast-badge is-bulba">Bulba suggests</span>
          <strong>${esc(look ? look.name : o.name)}</strong>
          <p>${esc(look ? (look.outfit || "") : o.items)}</p>
          ${o.why ? `<p class="cast-muted">${esc(o.why)}</p>` : ""}
          <div class="cast-actions">
            <button type="button" class="ep-btn ep-btn-primary" onclick="CASTING.applyOutfit('${esc(key)}', this)">${look ? "Use this look" : `Make this look · ${(window.EPISODE_LOOKS?.coreMoods || []).length || 6} pictures`}</button>
            ${look ? "" : `<button type="button" class="ep-btn" onclick="CASTING.editOutfit('${esc(key)}')">Edit</button>`}
            <button type="button" class="ep-btn ep-btn-quiet" onclick="CASTING.rejectOutfit('${esc(key)}')">Not this</button>
          </div>
        </div>`;
    },

    rerender() {
      const root = document.getElementById("vnScenesRoot");
      if (!root || vn().activeScene() || vn().tab !== "stage") return;
      const scroller = root.querySelector(".cast-sheet");
      const top = scroller ? scroller.scrollTop : 0;
      vn().renderStageOnly();
      const after = document.querySelector("#vnScenesRoot .cast-sheet");
      if (after) after.scrollTop = top;
    },

    /* ---------- Bulba ---------- */

    async ask(btn) {
      const s = this.sheet();
      const t = TG.state.active_thread;
      if (!t) {vn().notify("Open the chat this episode continues first.", true); return;}
      s.asking = true; s.error = "";
      this.rerender();
      const pulse = vn().pendingPulse;
      try {
        const data = await vn().apiPost({action: "casting_propose", thread_id: t.id,
          wish: document.getElementById("vnLocationHintInput")?.value || "",
          authoring_mode: document.getElementById("vnAuthoringMode")?.value || "roleplay",
          ...(pulse?.thread_id === t.id ? {pulse_event_id: pulse.id, pulse_event_revision: pulse.revision} : {})});
        if (data.backgrounds && TG.state.vn_scenes) TG.state.vn_scenes.backgrounds = data.backgrounds;
        this.take(data.casting);
      } catch (e) {
        s.error = e.message;
      } finally {
        s.asking = false;
        this.save();
        this.rerender();
      }
    },

    take(c) {
      const s = this.sheet();
      s.proposal = c;
      s.cast = c.cast && c.cast.length ? c.cast : s.cast;
      // A part the user already fixed stays as they left it; Bulba's new idea waits beside it as a proposal.
      if (s.place.state !== "applied" && c.place && c.place.name) s.place = {state: "proposed", value: {...c.place}};
      if (s.facts.state !== "applied" && c.facts?.length) s.facts = {state: "proposed", value: [...c.facts]};
      if (s.opening.state !== "applied" && c.opening) s.opening = {state: "proposed", value: c.opening};
      if (s.nudge.state !== "applied") s.nudge = c.nudge ? {state: "proposed", value: c.nudge} : {state: "empty", value: ""};
      s.outfits = {};
      (c.outfits || []).forEach((o) => {s.outfits[o.key] = {...o, state: "proposed"};});
    },

    applyAll() {
      const s = this.sheet();
      ["place", "facts", "opening", "nudge"].forEach((part) => {if (s[part].state === "proposed") s[part].state = "applied";});
      Object.entries(s.outfits).forEach(([key, o]) => {
        if (o.state === "proposed" && o.look_id) {window.EPISODE_LOOKS?.pick(key, o.look_id); o.state = "done";}
      });
      this.save();
      this.rerender();
      const left = Object.values(s.outfits).filter((o) => o.state === "proposed").length;
      vn().notify(left ? `Applied. ${left} new ${left === 1 ? "look needs" : "looks need"} drawing: press “Make this look” when you're ready.` : "Applied.");
    },

    apply(part) {this.sheet()[part].state = "applied"; this.save(); this.rerender();},
    reject(part) {const s = this.sheet(); s[part] = {...blank()[part]}; this.save(); this.rerender();},
    undo(part) {this.reject(part);},
    edit(part) {
      const s = this.sheet();
      s[part].before = JSON.parse(JSON.stringify(s[part]));
      s[part].state = "editing";
      this.rerender();
    },
    cancelEdit(part) {
      const s = this.sheet();
      const before = s[part].before;
      s[part] = before ? {state: before.state === "editing" ? "empty" : before.state, value: before.value} : {...blank()[part]};
      this.rerender();
    },
    saveEdit(part) {
      const s = this.sheet(), root = document.getElementById("vnScenesRoot");
      if (part === "place") {
        const v = {...s.place.value};
        root.querySelectorAll("[data-place]").forEach((el) => {
          v[el.dataset.place] = el.dataset.place === "details" ? lines(el.value).slice(0, 6) : el.value.trim();
        });
        if (!v.name) {vn().notify("Give the place a name.", true); return;}
        s.place = {state: "applied", value: v};
      } else if (part === "facts") {
        const v = lines(root.querySelector("[data-facts]")?.value).slice(0, 10);
        s.facts = v.length ? {state: "applied", value: v} : {state: "empty", value: []};
      } else {
        const v = (root.querySelector(`[data-${part}]`)?.value || "").trim();
        s[part] = v ? {state: "applied", value: v} : {state: "empty", value: ""};
      }
      this.save();
      this.rerender();
    },

    toggle(key) {
      const s = this.sheet();
      const all = this.members().map((m) => m.key);
      const cast = new Set(s.cast || all);
      if (cast.has(key)) cast.delete(key); else cast.add(key);
      if (!cast.size) {vn().notify("Someone has to be there.", true); return;}
      s.cast = all.filter((k) => cast.has(k));
      this.save();
      this.rerender();
    },

    async drawPlace(btn) {
      const s = this.sheet();
      const t = TG.state.active_thread;
      const modern = this.members().some((m) => (TG.state.characters || []).find((x) => x.slug === m.key)?.mode === "modern_au");
      const orig = btn.textContent;
      btn.disabled = true; btn.textContent = "Drawing the place…";
      try {
        const data = await vn().apiPost({action: "place_draw", place: s.place.value, setting: modern ? "modern" : "canon"});
        const list = this.backdrops();
        list.unshift({id: data.place.id, name: data.place.name, url: data.place.url, kept: true});
        if (TG.state.vn_scenes) TG.state.vn_scenes.backgrounds = list;
        s.place.value.background_id = data.place.id;
        this.save();
        vn().notify("Drawn and kept: next time the story goes there, it looks the same.");
      } catch (e) {
        vn().notify(e.message, true);
      } finally {
        if (btn.isConnected) {btn.disabled = false; btn.textContent = orig;}
        this.rerender();
      }
    },

    async applyOutfit(key, btn) {
      const o = this.sheet().outfits[key];
      if (!o) return;
      if (o.look_id) {
        window.EPISODE_LOOKS?.pick(key, o.look_id);
        o.state = "done"; this.save(); window.EPISODE_LOOKS?.render();
        return;
      }
      const made = await window.EPISODE_LOOKS?.createFrom(key, o.name, o.items, btn);
      if (made) {o.state = "done"; this.save(); window.EPISODE_LOOKS?.render();}
    },

    editOutfit(key) {
      const o = this.sheet().outfits[key];
      if (!o) return;
      window.EPISODE_LOOKS?.prefill(key, o.name, o.items);
      o.state = "done"; this.save();
    },

    rejectOutfit(key) {
      const o = this.sheet().outfits[key];
      if (o) {o.state = "done"; this.save(); window.EPISODE_LOOKS?.render();}
    },

    /* What the episode starts with: applied parts only. */
    payload() {
      const s = this.sheet();
      const out = {cast: (s.cast || this.members().map((m) => m.key)).filter((k) => k !== "user")};
      if (s.place.state === "applied") out.place = s.place.value;
      if (s.facts.state === "applied") out.facts = s.facts.value;
      if (s.opening.state === "applied") out.opening = s.opening.value;
      if (s.nudge.state === "applied") out.nudge = s.nudge.value;
      return out;
    },

    pending() {
      const s = this.sheet();
      return ["place", "facts", "opening", "nudge"].filter((p) => s[p].state === "proposed" || s[p].state === "editing").length +
        Object.values(s.outfits).filter((o) => o.state === "proposed").length;
    },
  };

  window.CASTING = CASTING;
})();
