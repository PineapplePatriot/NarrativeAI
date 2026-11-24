/* Episode looks: pick, make and cut out each person's outfit set before an episode starts.
 *
 * A look's pictures arrive from the server on a flat key colour. They are cut out here, in the browser, and the
 * transparent copies are sent back, so the server never runs a background remover. Every mood of a look keeps
 * the same picture size, so switching moods on stage never makes the character jump.
 */
(function () {
  const api = () => (window.TG_CFG && window.TG_CFG.vn_scenes_api) || "/main/screen/scenes/api/";
  const csrf = () => (window.TG_CFG && window.TG_CFG.csrf) || "";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  async function post(payload) {
    const resp = await fetch(api(), {method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
      body: JSON.stringify(payload)});
    let data;
    try {data = await resp.json();} catch (_) {throw new Error(`The server returned an unreadable response (HTTP ${resp.status}).`);}
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  /* ---------- the cut-out ---------- */

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Couldn't load the picture to cut it out."));
      img.src = url;
    });
  }

  function median(values) {
    const sorted = values.slice().sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)] || 0;
  }

  /* Remove the flat background around the character. `loose` widens how far from the key colour still counts
     as background (for a picture whose background came out uneven); `tight` keeps more of the edges. */
  function cutCanvas(img, strength = "normal", size = null) {
    // Every mood is cut at the neutral picture's size, so a character never changes size between moods.
    const w = size ? size.w : img.naturalWidth, h = size ? size.h : img.naturalHeight;
    const canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d", {willReadFrequently: true});
    if (size && (img.naturalWidth !== w || img.naturalHeight !== h)) {
      // A mood that came back in another shape is fitted into the neutral's frame, standing on its floor, never
      // stretched (stretching is what made proportions look wrong).
      // Matched by height (the person stands as tall as in the neutral), centred; the sides are trimmed or padded.
      const scale = h / img.naturalHeight;
      const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
      const probe = document.createElement("canvas"); probe.width = 1; probe.height = 1;
      const pctx = probe.getContext("2d"); pctx.drawImage(img, 0, 0, 1, 1, 0, 0, 1, 1);
      const [r, g, b] = pctx.getImageData(0, 0, 1, 1).data;  // the key colour fills the margins, so they cut away
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, (w - dw) / 2, h - dh, dw, dh);
    } else {
      ctx.drawImage(img, 0, 0, w, h);
    }
    const data = ctx.getImageData(0, 0, w, h);
    const p = data.data;
    // The real key colour, read off the picture's border rather than trusted from the prompt.
    const rs = [], gs = [], bs = [];
    const sample = (x, y) => {const i = (y * w + x) * 4; rs.push(p[i]); gs.push(p[i + 1]); bs.push(p[i + 2]);};
    for (let x = 0; x < w; x += 3) {sample(x, 0); sample(x, h - 1);}
    for (let y = 0; y < h; y += 3) {sample(0, y); sample(w - 1, y);}
    const kr = median(rs), kg = median(gs), kb = median(bs);
    const [hard, soft] = {tight: [34, 72], normal: [48, 100], loose: [70, 135]}[strength] || [48, 100];
    const dist = new Float32Array(w * h);
    for (let i = 0, j = 0; j < w * h; i += 4, j++) {
      const dr = p[i] - kr, dg = p[i + 1] - kg, db = p[i + 2] - kb;
      dist[j] = Math.sqrt(dr * dr + dg * dg + db * db);
    }
    const alpha = new Uint8ClampedArray(w * h).fill(255);
    const seen = new Uint8Array(w * h);
    const queue = new Int32Array(w * h);
    let head = 0, tail = 0;
    const visit = (j) => {
      if (seen[j] || dist[j] >= soft) return;
      seen[j] = 1;
      alpha[j] = dist[j] < hard ? 0 : Math.round((dist[j] - hard) / (soft - hard) * 255);
      if (dist[j] < hard) queue[tail++] = j;  // edges stop the spread, so it never eats into the character
    };
    for (let x = 0; x < w; x++) {visit(x); visit((h - 1) * w + x);}
    for (let y = 0; y < h; y++) {visit(y * w); visit(y * w + w - 1);}
    while (head < tail) {
      const j = queue[head++], x = j % w;
      if (x > 0) visit(j - 1);
      if (x < w - 1) visit(j + 1);
      if (j >= w) visit(j - w);
      if (j < w * (h - 1)) visit(j + w);
    }
    // Pockets of background closed off by an arm or hair: the key colour never appears on the character.
    for (let j = 0; j < w * h; j++) if (!seen[j] && dist[j] < hard * 0.6) alpha[j] = 0;
    // The edge band: kept pixels within three pixels of a removed one. Their colour is part key colour.
    let band = new Uint8Array(w * h);
    for (let j = 0; j < w * h; j++) if (alpha[j] < 255) band[j] = 1;
    for (let pass = 0; pass < 3; pass++) {
      const grown = band.slice();
      for (let j = 0; j < w * h; j++) {
        if (band[j]) continue;
        const x = j % w;
        if ((x > 0 && band[j - 1]) || (x < w - 1 && band[j + 1]) || (j >= w && band[j - w]) || (j < w * (h - 1) && band[j + w])) grown[j] = 1;
      }
      band = grown;
    }
    // Spill removal: take out the part of each edge pixel's colour that leans toward the key colour.
    const km = (kr + kg + kb) / 3;
    let dx = kr - km, dy = kg - km, dz = kb - km;
    const norm = Math.hypot(dx, dy, dz) || 1;
    dx /= norm; dy /= norm; dz /= norm;
    for (let i = 0, j = 0; j < w * h; i += 4, j++) {
      if (band[j] && alpha[j] > 0) {
        const m = (p[i] + p[i + 1] + p[i + 2]) / 3;
        const lean = (p[i] - m) * dx + (p[i + 1] - m) * dy + (p[i + 2] - m) * dz;
        if (lean > 0) {
          p[i] = Math.max(0, Math.min(255, p[i] - lean * dx));
          p[i + 1] = Math.max(0, Math.min(255, p[i + 1] - lean * dy));
          p[i + 2] = Math.max(0, Math.min(255, p[i + 2] - lean * dz));
        }
      }
      p[i + 3] = alpha[j];
    }
    ctx.putImageData(data, 0, 0);
    return canvas;
  }

  /* The character's outline on a small grid: which cells are mostly opaque. */
  function outline(canvas) {
    const gw = 64, gh = Math.max(8, Math.round(64 * canvas.height / canvas.width));
    const small = document.createElement("canvas");
    small.width = gw; small.height = gh;
    const sctx = small.getContext("2d", {willReadFrequently: true});
    sctx.drawImage(canvas, 0, 0, gw, gh);
    const px = sctx.getImageData(0, 0, gw, gh).data;
    const cells = new Uint8Array(gw * gh);
    for (let i = 0; i < cells.length; i++) cells[i] = px[i * 4 + 3] > 128 ? 1 : 0;
    return cells;
  }

  /* How much of the outline differs between two cut-outs (0 = the same shape). A face-only edit changes almost
     nothing; an extra arm or a new pose changes a lot. */
  function outlineChange(a, b) {
    let differ = 0, either = 0;
    for (let i = 0; i < a.length; i++) {
      if (a[i] || b[i]) either++;
      if (a[i] !== b[i]) differ++;
    }
    return either ? differ / either : 0;
  }

  const neutralCache = {};

  async function neutralOf(look) {
    const key = `${look.id}:${look.moods.neutral?.raw_url}`;
    if (neutralCache[key]) return neutralCache[key];
    const n = look.moods.neutral;
    if (!n) return null;
    const img = await loadImage(n.cut ? n.url : n.raw_url);
    const canvas = n.cut ? (() => {
      const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext("2d").drawImage(img, 0, 0); return c;
    })() : cutCanvas(img);
    neutralCache[key] = {size: {w: canvas.width, h: canvas.height}, outline: outline(canvas)};
    return neutralCache[key];
  }

  async function cutOne(look, mood, strength) {
    const entry = look.moods[mood];
    const img = await loadImage(entry.raw_url);
    const base = mood === "neutral" ? null : await neutralOf(look);
    const canvas = cutCanvas(img, strength, base ? base.size : null);
    const changed = base ? outlineChange(base.outline, outline(canvas)) : null;
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("The browser couldn't make the cut-out.");
    const form = new FormData();
    form.append("kind", "episode_cut");
    form.append("look_id", look.id);
    form.append("mood", mood);
    form.append("file", blob, `${mood}.png`);
    if (changed !== null) form.append("body_changed", changed.toFixed(4));
    const resp = await fetch(api(), {method: "POST", headers: {"X-CSRFToken": csrf()}, body: form});
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    return data.look;
  }

  const LOOKS = {
    cast: [],
    picks: {},
    coreMoods: [],
    thread: null,
    root: null,
    busy: false,

    chosen() {
      const out = {};
      Object.entries(this.picks).forEach(([key, id]) => {if (id) out[key] = id;});
      return out;
    },

    /* Cut out every mood of a look that is still on its key colour (or all of them, at a new strength). */
    async cutLook(look, strength = "normal", all = false) {
      if (!look) return look;
      const order = (list) => [...list].sort((a, b) => (a === "neutral" ? -1 : b === "neutral" ? 1 : 0));
      const moods = order(all ? Object.keys(look.moods) : (look.needs_cut || []));
      let latest = look;
      for (const mood of moods) latest = await cutOne(latest, mood, strength);
      // A mood whose body changed gets one automatic second try (one picture); if that's wrong too, it stays
      // flagged for the user, and off the stage.
      for (const [mood, entry] of Object.entries(latest.moods)) {
        if (!entry.flag || entry.retried || mood === "neutral") continue;
        window.VN_SCENES?.notify(`“${mood}” came out with a changed body: drawing it once more…`);
        const again = await post({action: "episode_look_redraw", look_id: latest.id, mood, auto: true});
        latest = await cutOne(again.look, mood, strength);
      }
      return latest;
    },

    async mount(root, thread) {
      this.root = root;
      this.thread = thread;
      if (!root) return;
      if (!thread) {root.innerHTML = ""; return;}
      root.innerHTML = `<p class="ep-looks-note">Loading episode looks…</p>`;
      try {
        const data = await post({action: "episode_looks", thread_id: thread.id});
        this.cast = data.cast || [];
        this.coreMoods = data.core_moods || [];
        this.models = data.picture_models || [["", "Nano Banana (Google): the app's default"]];
        this.defaultModel = data.default_model || "";
        this.cast.forEach((m) => {
          if (!(m.key in this.picks) || !m.looks.some((l) => l.id === this.picks[m.key])) this.picks[m.key] = m.chosen;
        });
        this.render();
      } catch (e) {
        root.innerHTML = `<p class="ep-looks-note ep-error">${esc(e.message)}</p>`;
      }
    },

    member(key) {return this.cast.find((m) => m.key === key);},

    lookOf(member) {return member.looks.find((l) => l.id === this.picks[member.key]) || null;},

    render() {
      if (!this.root) return;
      const rows = this.cast.filter((m) => !window.CASTING || CASTING.inCast(m.key)).map((m) => {
        const look = this.lookOf(m);
        const you = m.key === "user";
        const options = m.looks.map((l) => `<option value="${l.id}" ${look && l.id === look.id ? "selected" : ""}>${esc(l.name)}</option>`).join("");
        const thumbs = look ? Object.entries(look.moods).map(([mood, e]) => `
          <figure class="ep-thumb ${e.cut ? "" : "ep-uncut"} ${e.flag ? "ep-flagged" : ""}" onclick="EPISODE_LOOKS.manageMoods(${look.id}, '${esc(mood)}')" title="${esc(mood)}${e.cut ? "" : " (not cut out yet)"}${e.flag ? ": " + esc(e.flag) : ""}">
            <img src="${esc(e.url)}" alt="${esc(mood)}" loading="lazy"><figcaption>${e.flag ? "⚠ " : ""}${esc(mood)}</figcaption>
          </figure>`).join("") : "";
        const flagged = look ? Object.entries(look.moods).filter(([, e]) => e.flag) : [];
        const review = look?.review || {};
        const checks = look ? `
          ${review.ok === false ? `<div class="ep-check is-bad"><strong>Bulba checked the neutral picture</strong>
              <ul>${(review.issues || []).map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
              <button type="button" class="ep-btn" onclick="EPISODE_LOOKS.redraw(${look.id}, 'all', this)">Redraw the look · ${Object.keys(look.moods).length} pictures</button></div>`
            : review.ok === true ? `<p class="ep-check is-good">Bulba checked the neutral picture: two arms, same person, outfit there.</p>`
            : review.issues?.length ? `<p class="ep-check">${esc(review.issues[0])}</p>` : ""}
          ${flagged.map(([mood, e]) => `<div class="ep-check is-bad"><strong>“${esc(mood)}”</strong> ${esc(e.flag)}
              <button type="button" class="ep-btn" onclick="EPISODE_LOOKS.redraw(${look.id}, '${esc(mood)}', this)">Redraw “${esc(mood)}” · 1 picture</button></div>`).join("")}
          ${look.identity ? `<details class="ep-seen"><summary>What Bulba saw in the reference</summary><p>${esc(look.identity)}</p></details>` : ""}` : "";
        return `
          <div class="ep-look-row" data-key="${esc(m.key)}">
            <div class="ep-look-head">
              <strong>${esc(m.name)}</strong>
              <span class="ep-badge">${m.setting === "modern" ? "Modern" : "Canon"}</span>
              ${you ? `<span class="ep-looks-note">on stage because you're directing</span>` : ""}
            </div>
            ${window.CASTING ? CASTING.outfitCard(m.key) : ""}
            ${m.looks.length ? `
              <label class="ep-inline">Look
                <select class="tg-select" onchange="EPISODE_LOOKS.pick('${esc(m.key)}', this.value)">${options}${you ? `<option value="" ${look ? "" : "selected"}>None</option>` : ""}</select>
              </label>
              ${look ? `
                <p class="ep-outfit">${esc(look.outfit || "Outfit as in their references")}</p>
                <label class="ep-inline ep-model">Picture model
                  <select class="tg-select ep-small" onchange="EPISODE_LOOKS.setModel(${look.id}, this.value, this)">${this.modelOptions(look.model)}</select>
                </label>
                <div class="ep-thumbs">${thumbs}</div>
                ${checks}
                <div class="ep-actions">
                  ${look.needs_cut.length ? `<button type="button" class="tg-fmt-btn" onclick="EPISODE_LOOKS.recut(${look.id}, 'normal', false, this)">Cut out ${look.needs_cut.length} left</button>` : ""}
                  <select class="tg-select ep-small" onchange="EPISODE_LOOKS.recut(${look.id}, this.value, true, this); this.value=''" title="If edges look wrong, cut every mood again">
                    <option value="">Cut again…</option><option value="tight">Keep more edge</option><option value="normal">Normal</option><option value="loose">Remove more background</option>
                  </select>
                  <button type="button" class="tg-fmt-btn" onclick="EPISODE_LOOKS.manageMoods(${look.id})">Moods: redraw, add, notes</button>
                  <button type="button" class="tg-fmt-btn" onclick="EPISODE_LOOKS.remove(${look.id}, this)">Delete look</button>
                </div>` : ""}
            ` : `<p class="ep-looks-note">${you ? "No look for you yet." : "No episode look yet: the stage will show only their name."}</p>`}
            ${m.has_reference ? `
              <details class="ep-new" ${m.looks.length ? "" : "open"}>
                <summary>New look</summary>
                <label>Name <input class="tg-input" maxlength="60" data-new-name placeholder="Everyday, Gala night, Rainy walk…"></label>
                <label>Outfit, item by item
                  <textarea class="tg-textarea" maxlength="1200" data-new-outfit placeholder="black wool coat, knee length, silver buttons&#10;grey knitted scarf&#10;dark jeans"></textarea>
                </label>
                <label>Picture model <select class="tg-select" data-new-model>${this.modelOptions(this.defaultModel)}</select></label>
                <button type="button" class="tg-send-btn" onclick="EPISODE_LOOKS.create('${esc(m.key)}', this)">Make look · ${this.coreMoods.length} pictures</button>
              </details>` : `<p class="ep-looks-note">Add a ${m.setting === "modern" ? "phone portrait" : "neutral sprite"} first; looks are drawn from it.</p>`}
          </div>`;
      }).join("");
      this.root.innerHTML = rows;
    },

    pick(key, value) {
      this.picks[key] = value ? Number(value) : null;
      this.render();
    },

    replace(look) {
      const m = this.member(look.character_slug);
      if (!m) return;
      const at = m.looks.findIndex((l) => l.id === look.id);
      if (at >= 0) m.looks[at] = look; else m.looks.unshift(look);
    },

    async run(btn, label, work) {
      if (this.busy) return;
      if (!btn) label = "";
      this.busy = true;
      const orig = btn ? btn.textContent : "";
      if (btn) {btn.disabled = true; btn.textContent = label;}
      try {await work();} catch (e) {window.VN_SCENES?.notify(e.message, true);} finally {
        this.busy = false;
        if (btn && btn.isConnected) {btn.disabled = false; btn.textContent = orig;}
        this.render();
        window.CASTING?.refreshCost();
      }
    },

    create(key, btn) {
      const row = btn.closest(".ep-look-row");
      const name = row.querySelector("[data-new-name]").value.trim();
      const outfit = row.querySelector("[data-new-outfit]").value.trim();
      const carried = (this.pendingMoods || {})[key];  // the episode's moods, when this came from Bulba's casting
      return this.createFrom(key, name, outfit, btn, carried?.moods, carried?.notes);
    },

    /* Put an outfit into a person's "New look" form, for the user to change before drawing it. */
    prefill(key, name, outfit) {
      this.render();
      const row = this.root?.querySelector(`.ep-look-row[data-key="${CSS.escape(key)}"]`);
      const form = row?.querySelector(".ep-new");
      if (!form) {window.VN_SCENES?.notify("Add a picture of them first: looks are drawn from it.", true); return;}
      form.open = true;
      form.querySelector("[data-new-name]").value = name || "";
      form.querySelector("[data-new-outfit]").value = outfit || "";
      form.querySelector("[data-new-outfit]").focus();
    },

    async createFrom(key, name, outfit, btn, moods = null, moodNotes = null) {
      if (!outfit) {window.VN_SCENES?.notify("Write the outfit item by item first: that's what keeps it the same in every picture.", true); return false;}
      let made = false;
      await this.run(btn, "Drawing the look…", async () => {
        const model = this.root?.querySelector(`.ep-look-row[data-key="${CSS.escape(key)}"] [data-new-model]`)?.value ?? this.defaultModel;
        const data = await post({action: "episode_look_create", key, name, outfit, model,
          ...(moods && moods.length ? {moods: ["neutral", ...moods], mood_notes: moodNotes || {}} : {})});
        this.replace(data.look);
        this.picks[key] = data.look.id;
        this.render();
        window.VN_SCENES?.notify("Look drawn. Cutting it out in your browser…");
        this.replace(await this.cutLook(data.look));
        window.VN_SCENES?.notify(data.errors?.length ? `Look ready, but some moods failed: ${data.errors.join("; ")}` : "Look ready.", !!data.errors?.length);
        made = data.look.id;
      });
      return made;
    },

    recut(id, strength, all, btn) {
      if (!strength) return;
      const look = this.cast.flatMap((m) => m.looks).find((l) => l.id === id);
      return this.run(btn, "Cutting out…", async () => {this.replace(await this.cutLook(look, strength, all));});
    },

    /* Draw these moods for a look (with Bulba's notes on how this person shows them), then cut them out. */
    drawMoods(id, moods, notes, btn) {
      return this.run(btn, "Drawing moods…", async () => {
        const data = await post({action: "episode_look_moods", look_id: id, moods, mood_notes: notes || {}});
        this.replace(await this.cutLook(data.look));
        if (data.errors?.length) window.VN_SCENES?.notify(data.errors.join(" "), true);
        else window.VN_SCENES?.notify(`Drawn: ${moods.join(", ")}.`);
      });
    },

    modelOptions(chosen) {
      return (this.models || [["", "Nano Banana (Google): the app's default"]]).map(([id, label]) =>
        `<option value="${esc(id)}" ${id === (chosen || "") ? "selected" : ""}>${esc(label.split(":")[0])}</option>`).join("");
    },

    lookById(id) {return this.cast.flatMap((m) => m.looks).find((l) => l.id === id);},

    setModel(id, model, el) {
      return this.run(null, "", async () => {
        const data = await post({action: "episode_look_model", look_id: id, model});
        this.replace(data.look);
        window.VN_SCENES?.notify(`From now on this look is drawn with ${data.look.model_name}. Redraw moods to use it.`);
      });
    },

    /* The mood manager: every mood with its picture and Bulba's line on how this person shows it; redraw one (with
       or without a note), redraw the whole look, remove one, add new ones. */
    manageMoods(id, focus) {
      const self = this;
      const render = (body, close) => {
        const look = self.lookById(id);
        if (!look) {close(null); return;}
        const notes = look.mood_notes || {};
        const missing = ["happy", "sad", "angry", "surprised", "flustered", "smug", "thoughtful", "worried", "tired",
          "annoyed", "embarrassed", "determined", "amused", "cold", "hurt"].filter((m) => !(m in look.moods));
        body.innerHTML = `
          <p class="ep-dialog-p">Every mood is an edit of the neutral picture. Bulba's line under each says how
            <strong>this</strong> person shows it; change it to make a mood quieter or stronger, then redraw.
            Drawn with ${esc(look.model_name || "the app's default")}.</p>
          <div class="ep-moods">
            ${Object.entries(look.moods).map(([mood, e]) => `
              <div class="ep-mood ${mood === focus ? "is-focus" : ""}" data-mood="${esc(mood)}">
                <img src="${esc(e.url)}" alt="${esc(mood)}">
                <div class="ep-mood-body">
                  <strong>${esc(mood)}${e.flag ? ` <span class="ep-mood-flag">⚠ ${esc(e.flag)}</span>` : ""}</strong>
                  ${mood === "neutral" ? `<span class="cast-muted">The base of every mood. Redrawing it redraws the whole look.</span>`
                    : `<textarea class="ep-input" data-note rows="2" placeholder="How this person shows it, e.g. a thin one-sided smile, eyes barely narrowed">${esc(notes[mood] || "")}</textarea>`}
                  <input class="ep-input" data-redo-note placeholder="Note for a redraw (optional): what was wrong, what to change">
                  <div class="ep-note-actions">
                    ${mood === "neutral"
                      ? `<button type="button" class="ep-btn" data-act="all">Redraw the whole look · ${Object.keys(look.moods).length} pictures</button>`
                      : `<button type="button" class="ep-btn" data-act="redraw">Redraw · 1 picture</button>
                         <button type="button" class="ep-btn ep-btn-quiet" data-act="remove">Remove</button>`}
                  </div>
                </div>
              </div>`).join("")}
          </div>
          <div class="ep-add-moods">
            <label class="ep-dialog-text">Add moods (comma-separated; one picture each)
              <input class="ep-input" data-add placeholder="${esc(missing.slice(0, 3).join(", "))}"></label>
            ${missing.length ? `<div class="cast-chips">${missing.slice(0, 10).map((m) => `<button type="button" class="cast-chip" data-suggest="${esc(m)}">${esc(m)}</button>`).join("")}</div>` : ""}
            <button type="button" class="ep-btn ep-btn-primary" data-act="add">Draw the new moods</button>
          </div>`;
        const busy = (btn, label) => {
          body.querySelectorAll("button").forEach((b) => {b.disabled = true;});
          if (btn) btn.textContent = label;
        };
        const done = async (data, message) => {
          let look2 = data.look;
          try {look2 = await self.cutLook(data.look);} catch (e) {window.VN_SCENES?.notify(e.message, true);}
          self.replace(look2);
          self.render();
          window.CASTING?.refreshCost();
          if (data.errors?.length) window.VN_SCENES?.notify(data.errors.join(" "), true);
          else if (message) window.VN_SCENES?.notify(message);
          render(body, close);
        };
        const fail = (e) => {window.VN_SCENES?.notify(e.message, true); render(body, close);};
        body.querySelectorAll("[data-suggest]").forEach((chip) => chip.addEventListener("click", () => {
          const input = body.querySelector("[data-add]");
          const have = input.value.split(",").map((x) => x.trim()).filter(Boolean);
          if (!have.includes(chip.dataset.suggest)) have.push(chip.dataset.suggest);
          input.value = have.join(", ");
        }));
        body.querySelectorAll(".ep-mood").forEach((row) => {
          const mood = row.dataset.mood;
          const noteBox = row.querySelector("[data-note]");
          noteBox?.addEventListener("change", async () => {
            try {self.replace((await post({action: "episode_look_note", look_id: id, mood, note: noteBox.value})).look);}
            catch (e) {window.VN_SCENES?.notify(e.message, true);}
          });
          row.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", async () => {
            const note = row.querySelector("[data-redo-note]").value.trim();
            const act = btn.dataset.act;
            try {
              if (act === "remove") {
                if (!(await EpDialog.confirm(`Remove “${mood}” from this look?`, {ok: "Remove", danger: true}))) return;
                busy(btn, "Removing…");
                await done(await post({action: "episode_look_remove_mood", look_id: id, mood}));
                return;
              }
              if (noteBox) await post({action: "episode_look_note", look_id: id, mood, note: noteBox.value});
              busy(btn, act === "all" ? "Redrawing the look…" : "Redrawing…");
              await done(await post({action: "episode_look_redraw", look_id: id, mood: act === "all" ? "all" : mood, note}), "Redrawn.");
            } catch (e) {fail(e);}
          }));
        });
        body.querySelector('[data-act="add"]').addEventListener("click", async (event) => {
          const moods = body.querySelector("[data-add]").value.split(",").map((m) => m.trim().toLowerCase()).filter(Boolean);
          if (!moods.length) {window.VN_SCENES?.notify("Write the moods to add, or tap the suggestions.", true); return;}
          busy(event.target, "Drawing…");
          try {await done(await post({action: "episode_look_moods", look_id: id, moods}), "New moods drawn.");}
          catch (e) {fail(e);}
        });
        if (focus) body.querySelector(`.ep-mood[data-mood="${CSS.escape(focus)}"]`)?.scrollIntoView({block: "center"});
      };
      return EpDialog.open({title: "Moods", wide: true, onMount: render});
    },

    redraw(id, mood, btn) {
      return this.run(btn, "Redrawing…", async () => {
        const data = await post({action: "episode_look_redraw", look_id: id, mood});
        this.replace(await this.cutLook(data.look));
        window.VN_SCENES?.notify(data.errors?.length ? data.errors.join("; ") : "Redrawn.", !!data.errors?.length);
      });
    },

    remove(id, btn) {
      return EpDialog.confirm("Delete this look and all its pictures? Episodes already saved keep their text.",
        {ok: "Delete the look", danger: true}).then((yes) => yes && this.run(btn, "Deleting…", async () => {
        await post({action: "episode_look_delete", look_id: id});
        this.cast.forEach((m) => {
          m.looks = m.looks.filter((l) => l.id !== id);
          if (this.picks[m.key] === id) this.picks[m.key] = m.looks[0]?.id || null;
        });
      }));
    },
  };

  window.EPISODE_LOOKS = LOOKS;
  window.EpisodeCutout = {cutCanvas, outline, outlineChange};
})();
