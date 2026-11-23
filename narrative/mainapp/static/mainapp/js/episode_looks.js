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
  function cutCanvas(img, strength = "normal") {
    const w = img.naturalWidth, h = img.naturalHeight;
    const canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d", {willReadFrequently: true});
    ctx.drawImage(img, 0, 0);
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

  async function cutOne(look, mood, strength) {
    const entry = look.moods[mood];
    const img = await loadImage(entry.raw_url);
    const canvas = cutCanvas(img, strength);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("The browser couldn't make the cut-out.");
    const form = new FormData();
    form.append("kind", "episode_cut");
    form.append("look_id", look.id);
    form.append("mood", mood);
    form.append("file", blob, `${mood}.png`);
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
      const moods = all ? Object.keys(look.moods) : (look.needs_cut || []);
      let latest = look;
      for (const mood of moods) latest = await cutOne(latest, mood, strength);
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
          <figure class="ep-thumb ${e.cut ? "" : "ep-uncut"}" title="${esc(mood)}${e.cut ? "" : " (not cut out yet)"}">
            <img src="${esc(e.url)}" alt="${esc(mood)}" loading="lazy"><figcaption>${esc(mood)}</figcaption>
          </figure>`).join("") : "";
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
                <div class="ep-thumbs">${thumbs}</div>
                <div class="ep-actions">
                  ${look.needs_cut.length ? `<button type="button" class="tg-fmt-btn" onclick="EPISODE_LOOKS.recut(${look.id}, 'normal', false, this)">Cut out ${look.needs_cut.length} left</button>` : ""}
                  <select class="tg-select ep-small" onchange="EPISODE_LOOKS.recut(${look.id}, this.value, true, this); this.value=''" title="If edges look wrong, cut every mood again">
                    <option value="">Cut again…</option><option value="tight">Keep more edge</option><option value="normal">Normal</option><option value="loose">Remove more background</option>
                  </select>
                  <button type="button" class="tg-fmt-btn" onclick="EPISODE_LOOKS.addMoods(${look.id}, this)">Add moods</button>
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
      this.busy = true;
      const orig = btn ? btn.textContent : "";
      if (btn) {btn.disabled = true; btn.textContent = label;}
      try {await work();} catch (e) {window.VN_SCENES?.notify(e.message, true);} finally {
        this.busy = false;
        if (btn && btn.isConnected) {btn.disabled = false; btn.textContent = orig;}
        this.render();
      }
    },

    create(key, btn) {
      const row = btn.closest(".ep-look-row");
      const name = row.querySelector("[data-new-name]").value.trim();
      const outfit = row.querySelector("[data-new-outfit]").value.trim();
      return this.createFrom(key, name, outfit, btn);
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

    async createFrom(key, name, outfit, btn) {
      if (!outfit) {window.VN_SCENES?.notify("Write the outfit item by item first: that's what keeps it the same in every picture.", true); return false;}
      let made = false;
      await this.run(btn, "Drawing the look…", async () => {
        const data = await post({action: "episode_look_create", key, name, outfit});
        this.replace(data.look);
        this.picks[key] = data.look.id;
        this.render();
        window.VN_SCENES?.notify("Look drawn. Cutting it out in your browser…");
        this.replace(await this.cutLook(data.look));
        window.VN_SCENES?.notify(data.errors?.length ? `Look ready, but some moods failed: ${data.errors.join("; ")}` : "Look ready.", !!data.errors?.length);
        made = true;
      });
      return made;
    },

    recut(id, strength, all, btn) {
      if (!strength) return;
      const look = this.cast.flatMap((m) => m.looks).find((l) => l.id === id);
      return this.run(btn, "Cutting out…", async () => {this.replace(await this.cutLook(look, strength, all));});
    },

    addMoods(id, btn) {
      const look = this.cast.flatMap((m) => m.looks).find((l) => l.id === id);
      const missing = this.coreMoods.filter((m) => !(m in look.moods));
      const answer = window.prompt("Which moods should this look get? Separate them with commas. Each is one picture, edited from the neutral one.",
        missing.join(", ") || "thoughtful, smug");
      const moods = (answer || "").split(",").map((m) => m.trim().toLowerCase()).filter(Boolean);
      if (!moods.length) return;
      return this.run(btn, "Drawing moods…", async () => {
        const data = await post({action: "episode_look_moods", look_id: id, moods});
        this.replace(await this.cutLook(data.look));
        if (data.errors?.length) window.VN_SCENES?.notify(data.errors.join("; "), true);
      });
    },

    remove(id, btn) {
      if (!window.confirm("Delete this look and all its pictures? Episodes already saved keep their text.")) return;
      return this.run(btn, "Deleting…", async () => {
        await post({action: "episode_look_delete", look_id: id});
        this.cast.forEach((m) => {
          m.looks = m.looks.filter((l) => l.id !== id);
          if (this.picks[m.key] === id) this.picks[m.key] = m.looks[0]?.id || null;
        });
      });
    },
  };

  window.EPISODE_LOOKS = LOOKS;
  window.EpisodeCutout = {cutCanvas};
})();
