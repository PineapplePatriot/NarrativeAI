/* Subtext: the cast's social feed.
 *
 * A feed (everything, what your character can see, locked posts, AITA), the status updates at the top, a composer,
 * "new posts" from the characters, a post's thread with replies, and People: each locked account's followers.
 * Locked posts show who has seen them; "Who knows" ticks a character as knowing a post because of the story.
 */
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const api = () => (window.TG_CFG && TG_CFG.subtext_api) || "/main/screen/subtext/api/";
  const ACCOUNT_LABEL = {main: "Main", burner: "Locked", aita: "AITA"};

  async function call(body) {
    const opts = body ? {method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": TG_CFG.csrf}, body: JSON.stringify(body)} : {};
    const resp = await fetch(api(), opts);
    let data;
    try {data = await resp.json();} catch (_) {throw new Error(`The server returned an unreadable response (HTTP ${resp.status}).`);}
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  const SX = {
    data: null, view: "feed", filter: "all", open: null, busy: "", error: "", note: "",
    wave: {who: [], mode: "any", topic: ""}, compose: {account: "main", text: "", title: "", replies: true},

    root() {return document.getElementById("subtextRoot");},
    person(key) {return (this.data?.people || {})[key] || {name: "Someone", handle: "@someone", burner: "@someone_priv", avatar: ""};},
    characters() {return Object.values(this.data?.people || {}).filter((p) => p.key !== "user");},
    post(id) {return (this.data?.posts || []).find((p) => p.id === id);},

    async init() {
      if (!this.data && TG.state?.subtext?.people) this.data = TG.state.subtext;
      this.render();
      try {this.data = (await call()).subtext; this.error = "";} catch (e) {this.error = e.message;}
      this.render();
    },

    async act(body, busy = "working", after = null) {
      this.keep();
      this.busy = busy; this.error = ""; this.render();
      try {
        const data = await call(body);
        this.data = data.subtext;
        if (after) after(data);
      } catch (e) {this.error = e.message;}
      this.busy = ""; this.render();
    },

    keep() {  // what's typed survives a redraw
      const root = this.root();
      if (!root) return;
      const v = (sel) => root.querySelector(sel);
      if (v("#sxText")) this.compose.text = v("#sxText").value;
      if (v("#sxTitle")) this.compose.title = v("#sxTitle").value;
      if (v("#sxTopic")) this.wave.topic = v("#sxTopic").value;
      if (v("#sxReply")) this.replyDraft = v("#sxReply").value;
    },

    /* ---------- rendering ---------- */

    render() {
      const root = this.root();
      if (!root) return;
      if (!this.data) {root.innerHTML = `<div class="sx-shell"><p class="sx-muted">Loading Subtext…</p></div>`; return;}
      const main = this.view === "people" ? this.peopleView() : this.open ? this.threadView(this.post(this.open)) : this.feedView();
      root.innerHTML = `<div class="sx-shell">
          <header class="sx-head">
            <div><h2>Subtext</h2><p class="sx-muted">What they post, and who has seen it.</p></div>
            <nav class="sx-nav" aria-label="Subtext">
              <button type="button" class="${this.view === "feed" ? "is-on" : ""}" onclick="SUBTEXT.go('feed')">Feed</button>
              <button type="button" class="${this.view === "people" ? "is-on" : ""}" onclick="SUBTEXT.go('people')">People & locked accounts</button>
            </nav>
          </header>
          ${this.error ? `<div class="sx-alert" role="alert">${esc(this.error)}</div>` : ""}
          ${this.busy ? `<div class="sx-busy" role="status"><span class="sx-dot"></span>${esc(this.busyText())}</div>` : ""}
          <div class="sx-cols"><main class="sx-main">${main}</main>
            ${this.view === "feed" && !this.open ? `<aside class="sx-side">${this.wavePanel()}</aside>` : ""}</div>
        </div>`;
    },

    busyText() {
      return {wave: "They're writing new posts…", post: "Posting…", replies: "Getting replies…", photo: "Drawing the photo…",
              forward: "Sending it to the DM…"}[this.busy] || "Saving…";
    },

    go(view) {this.keep(); this.view = view; this.open = null; this.render(); this.root()?.scrollTo?.(0, 0);},

    statusStrip() {
      const list = this.data.statuses || [];
      if (!list.length) return "";
      return `<section class="sx-status" aria-label="Status updates">${list.map((s) => {
        const who = this.person(s.key);
        return `<div class="sx-status-item" title="${esc(who.name)}: ${esc(s.text)}">
          ${this.avatar(who, "sx-av-ring")}<span class="sx-status-name">${esc(who.name.split(" ")[0])}</span>
          <span class="sx-status-text">${esc(s.emoji)} ${esc(s.text)}</span></div>`;
      }).join("")}</section>`;
    },

    feedView() {
      const posts = (this.data.posts || []).filter((p) => this.filter === "all" ? true : this.filter === "mine" ? p.you_see
        : this.filter === "burner" ? p.account === "burner" : this.filter === "aita" ? p.account === "aita" : true);
      const tab = (id, label) => `<button type="button" class="${this.filter === id ? "is-on" : ""}" onclick="SUBTEXT.setFilter('${id}')">${label}</button>`;
      return `${this.statusStrip()}
        ${this.composer()}
        <div class="sx-tabs" role="tablist">${tab("all", "Everything")}${tab("mine", "What you can see")}${tab("burner", "Locked")}${tab("aita", "AITA")}</div>
        ${posts.length ? posts.map((p) => this.card(p)).join("") : `<p class="sx-empty">Nothing here yet. Ask for new posts, or post something yourself.</p>`}`;
    },

    setFilter(f) {this.keep(); this.filter = f; this.render();},

    composer() {
      const c = this.compose, me = this.person("user");
      return `<section class="sx-compose">
        ${this.avatar(me)}
        <div class="sx-compose-body">
          <select class="sx-select" onchange="SUBTEXT.keep(); SUBTEXT.compose.account = this.value; SUBTEXT.render()" aria-label="Post as">
            <option value="main" ${c.account === "main" ? "selected" : ""}>${esc(me.handle)} (main)</option>
            <option value="burner" ${c.account === "burner" ? "selected" : ""}>🔒 ${esc(me.burner)} (locked)</option>
            <option value="aita" ${c.account === "aita" ? "selected" : ""}>Anonymous AITA thread</option></select>
          ${c.account === "aita" ? `<input class="sx-input" id="sxTitle" value="${esc(c.title)}" placeholder="AITA for…">` : ""}
          <textarea class="sx-input" id="sxText" rows="2" placeholder="${c.account === "burner" ? "Only your followers will see this." : "What's happening?"}">${esc(c.text)}</textarea>
          <div class="sx-row">
            <label class="sx-check"><input type="checkbox" ${c.replies ? "checked" : ""} onchange="SUBTEXT.compose.replies = this.checked"> Let them reply</label>
            <button type="button" class="sx-btn sx-primary" onclick="SUBTEXT.postIt()" ${this.busy ? "disabled" : ""}>Post</button>
          </div>
        </div></section>`;
    },

    wavePanel() {
      const w = this.wave;
      const wide = window.matchMedia("(min-width: 901px)").matches;
      return `<details class="sx-panel sx-fold" ${wide || this.waveOpen ? "open" : ""} ontoggle="SUBTEXT.waveOpen = this.open">
        <summary><h3>New posts</h3></summary>
        <p class="sx-muted">The characters post from what's going on in your chats. Leave everyone off to let the first few post.</p>
        <div class="sx-chips">${this.characters().map((p) => `<button type="button" class="sx-chip ${w.who.includes(p.key) ? "is-on" : ""}"
          aria-pressed="${w.who.includes(p.key)}" onclick="SUBTEXT.toggleWho('${esc(p.key)}')">${esc(p.name)}</button>`).join("")}</div>
        <label class="sx-field">What kind
          <select class="sx-select" onchange="SUBTEXT.wave.mode = this.value">
            ${[["any", "Whatever they'd post"], ["main", "Main posts"], ["burner", "Locked posts"], ["aita", "An AITA thread"]]
              .map(([v, l]) => `<option value="${v}" ${w.mode === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="sx-field">About <span class="sx-muted">(optional)</span>
          <input class="sx-input" id="sxTopic" value="${esc(w.topic)}" placeholder="last night's argument, the new job…"></label>
        <button type="button" class="sx-btn sx-primary sx-wide" onclick="SUBTEXT.getWave()" ${this.busy ? "disabled" : ""}>Get new posts</button>
      </details>
      <section class="sx-panel sx-howto"><h3>Who sees what</h3>
        <p class="sx-muted">Main posts and AITA threads: everyone (but nobody knows who wrote an AITA thread). Locked posts: only that account's followers.
        Tick <b>knows</b> on a post when the story let someone see it anyway. What they've seen reaches the phone chats.</p></section>`;
    },

    toggleWho(key) {
      this.keep();
      const w = this.wave.who;
      this.wave.who = w.includes(key) ? w.filter((k) => k !== key) : [...w, key];
      this.render();
    },

    avatar(p, extra = "") {
      return p.avatar ? `<img class="sx-av ${extra}" src="${esc(p.avatar)}" alt="">`
        : `<span class="sx-av sx-av-letter ${extra}" aria-hidden="true">${esc((p.name || "?").trim()[0] || "?")}</span>`;
    },

    byline(p) {
      const who = this.person(p.author);
      if (p.account === "aita") return `<span class="sx-name">Anonymous</span> <span class="sx-tag sx-tag-aita">AITA</span>
        ${p.author === "user" ? `<span class="sx-muted">(you)</span>` : `<span class="sx-muted" title="Only you, and those who know, can tell">(${esc(who.name)})</span>`}`;
      return `<span class="sx-name">${esc(who.name)}</span> <span class="sx-handle">${p.account === "burner" ? "🔒 " + esc(who.burner) : esc(who.handle)}</span>`;
    },

    seenLine(p) {
      if (p.account === "main") return "";
      const names = (keys) => keys.map((k) => esc(this.person(k).name)).join(", ");
      const knows = Object.keys(p.knows || {});
      const parts = [];
      if (p.account === "burner") parts.push(p.followers.length ? `Followers: ${names(p.followers)}` : "No followers yet");
      if (knows.length) parts.push(`${p.account === "aita" ? "Know it's them" : "Know"}: ${names(knows)}`);
      if (p.account === "burner" && !p.you_see && p.author !== "user") parts.push("not you");
      return `<div class="sx-seen">${p.account === "burner" ? "🔒" : "🕶"} ${parts.join(" · ")}
        <button type="button" class="sx-link" onclick="SUBTEXT.whoKnows('${esc(p.id)}')">Who knows?</button></div>`;
    },

    card(p) {
      const who = this.person(p.author);
      const reacts = Object.entries(p.reactions || {});
      return `<article class="sx-post sx-${esc(p.account)}">
        ${p.account === "aita" ? `<span class="sx-av sx-av-letter" aria-hidden="true">?</span>` : this.avatar(who)}
        <div class="sx-post-body">
          <div class="sx-by">${this.byline(p)} <span class="sx-muted">· ${esc(p.when)}</span></div>
          ${p.title ? `<div class="sx-title">${esc(p.title)}</div>` : ""}
          <button type="button" class="sx-text" onclick="SUBTEXT.openPost('${esc(p.id)}')">${esc(p.text)}</button>
          ${this.photo(p)}
          ${p.account === "aita" ? this.votes(p) : ""}
          ${this.seenLine(p)}
          <div class="sx-actions">
            <button type="button" class="sx-act" onclick="SUBTEXT.openPost('${esc(p.id)}')" aria-label="Replies">💬 ${(p.comments || []).length}</button>
            ${reacts.map(([e, keys]) => `<button type="button" class="sx-act ${keys.includes("user") ? "is-on" : ""}" onclick="SUBTEXT.react('${esc(p.id)}', '${e}')"
              title="${esc(keys.map((k) => this.person(k).name).join(", "))}">${e} ${keys.length}</button>`).join("")}
            <button type="button" class="sx-act" onclick="SUBTEXT.reactMenu('${esc(p.id)}', this)" aria-label="React">＋</button>
            <button type="button" class="sx-act" onclick="SUBTEXT.forward('${esc(p.id)}')" title="Send it to someone in a DM">✈ Send</button>
            <button type="button" class="sx-act sx-act-end" onclick="SUBTEXT.remove('${esc(p.id)}')" aria-label="Delete post" title="Delete">🗑</button>
          </div>
        </div></article>`;
    },

    photo(p) {
      if (!p.photo) return "";
      if (p.photo.url) return `<img class="sx-photo" src="${esc(p.photo.url)}" alt="${esc(p.photo.prompt)}" loading="lazy" onclick="TG.viewImage?.(this.src)">`;
      return `<div class="sx-photo-wait"><span>📷 ${esc(p.photo.prompt)}</span>
        <button type="button" class="sx-btn" onclick="SUBTEXT.drawPhoto('${esc(p.id)}')" ${this.busy ? "disabled" : ""}>Draw it (1 picture)</button></div>`;
    },

    votes(p) {
      const v = p.votes || {};
      return `<div class="sx-votes">${["NTA", "YTA", "ESH"].map((k) => `<button type="button" class="sx-vote ${p.user_vote === k ? "is-on" : ""}"
        onclick="SUBTEXT.vote('${esc(p.id)}', '${k}')">${k} <b>${v[k.toLowerCase()] || 0}</b></button>`).join("")}</div>`;
    },

    threadView(p) {
      if (!p) {this.open = null; return this.feedView();}
      const replies = (p.comments || []).map((c) => {
        const who = this.person(c.author);
        return `<div class="sx-reply">${this.avatar(who)}<div><div class="sx-by"><span class="sx-name">${esc(who.name)}</span>
          <span class="sx-handle">${c.account === "burner" ? "🔒 " + esc(who.burner) : esc(who.handle)}</span>
          ${c.verdict ? `<span class="sx-tag">${esc(c.verdict)}</span>` : ""}</div><p>${esc(c.text)}</p></div></div>`;
      }).join("");
      const canReply = p.you_see;
      return `<button type="button" class="sx-btn sx-back" onclick="SUBTEXT.openPost(null)">← Feed</button>
        ${this.card(p)}
        <section class="sx-thread">${replies || `<p class="sx-muted">No replies yet.</p>`}</section>
        ${canReply ? `<section class="sx-compose sx-compose-reply">${this.avatar(this.person("user"))}<div class="sx-compose-body">
          <textarea class="sx-input" id="sxReply" rows="2" placeholder="Reply…">${esc(this.replyDraft || "")}</textarea>
          <div class="sx-row">
            ${p.account === "aita" ? `<select class="sx-select" id="sxVerdict" aria-label="Your verdict"><option value="">No verdict</option><option>NTA</option><option>YTA</option><option>ESH</option></select>` : "<span></span>"}
            <span class="sx-row-end"><button type="button" class="sx-btn" onclick="SUBTEXT.moreReplies('${esc(p.id)}')" ${this.busy ? "disabled" : ""}>Get replies</button>
            <button type="button" class="sx-btn sx-primary" onclick="SUBTEXT.reply('${esc(p.id)}')" ${this.busy ? "disabled" : ""}>Reply</button></span></div></div></section>`
          : `<p class="sx-note">You don't follow this locked account, so your character can't see it to reply. You can still read it, and get the followers' replies.
              <button type="button" class="sx-btn" onclick="SUBTEXT.moreReplies('${esc(p.id)}')" ${this.busy ? "disabled" : ""}>Get replies</button></p>`}`;
    },

    peopleView() {
      const everyone = [this.person("user"), ...this.characters()];
      return `<section class="sx-panel sx-people-intro"><h3>Locked accounts</h3>
          <p class="sx-muted">Each locked account is seen only by its followers. Characters bring up what they've seen in the phone chats; the rest they don't know about.</p></section>
        ${everyone.map((p) => {
          const fol = this.data.burners?.[p.key]?.followers || [];
          return `<section class="sx-person">
            <div class="sx-person-head">${this.avatar(p)}<div><b>${esc(p.name)}${p.key === "user" ? " (you)" : ""}</b>
              <div class="sx-muted">${esc(p.handle)} · 🔒 ${esc(p.burner)}</div></div></div>
            <div class="sx-field">Who follows ${esc(p.key === "user" ? "your" : p.name + "'s")} locked account
              <div class="sx-chips">${everyone.filter((o) => o.key !== p.key).map((o) => `<button type="button" class="sx-chip ${fol.includes(o.key) ? "is-on" : ""}"
                aria-pressed="${fol.includes(o.key)}" onclick="SUBTEXT.toggleFollower('${esc(p.key)}', '${esc(o.key)}')">${esc(o.key === "user" ? "You" : o.name)}</button>`).join("")}</div></div>
          </section>`;
        }).join("")}`;
    },

    /* ---------- actions ---------- */

    openPost(id) {this.keep(); this.open = id; this.replyDraft = ""; this.render(); this.root()?.querySelector(".sx-main")?.scrollTo?.(0, 0);},

    postIt() {
      this.keep();
      const c = this.compose;
      if (!c.text.trim()) {this.error = "Write something first."; this.render(); return;}
      return this.act({action: "create_post", text: c.text, account: c.account, title: c.title, ask_replies: c.replies}, "post",
        () => {this.compose = {...this.compose, text: "", title: ""};});
    },

    getWave() {this.keep(); return this.act({action: "generate_wave", character_slugs: this.wave.who, mode: this.wave.mode, topic: this.wave.topic}, "wave");},
    react(id, emoji) {return this.act({action: "react_post", post_id: id, emoji}, "");},
    vote(id, verdict) {return this.act({action: "vote_aita", post_id: id, verdict}, "");},
    drawPhoto(id) {return this.act({action: "generate_photo", post_id: id}, "photo");},
    moreReplies(id) {return this.act({action: "generate_replies", post_id: id}, "replies");},

    reply(id) {
      this.keep();
      const text = (this.replyDraft || "").trim();
      if (!text) return;
      const verdict = this.root().querySelector("#sxVerdict")?.value || "";
      return this.act({action: "add_comment", post_id: id, text, verdict}, "replies", () => {this.replyDraft = "";});
    },

    toggleFollower(owner, key) {
      const now = this.data.burners?.[owner]?.followers || [];
      const next = now.includes(key) ? now.filter((k) => k !== key) : [...now, key];
      return this.act({action: "set_followers", owner, followers: next}, "");
    },

    reactMenu(id, btn) {
      const pal = this.data.reactions || [];
      EpDialog.open({title: "React", html: `<div class="sx-react-pick">${pal.map((e) => `<button type="button" class="sx-act" data-e="${e}">${e}</button>`).join("")}</div>`,
        onMount: (box, close) => box.querySelectorAll("[data-e]").forEach((b) => b.addEventListener("click", () => {close?.(); this.react(id, b.dataset.e);}))});
    },

    async remove(id) {
      if (!(await EpDialog.confirm("Delete this post and its replies?", {ok: "Delete", danger: true}))) return;
      if (this.open === id) this.open = null;
      return this.act({action: "delete_post", post_id: id}, "");
    },

    /* Who knows: followers see it anyway; anyone else can be ticked as knowing because of the story. */
    whoKnows(id) {
      const p = this.post(id);
      if (!p) return;
      const rows = this.characters().filter((c) => c.key !== p.author).map((c) => {
        const follows = p.account === "burner" && p.followers.includes(c.key);
        const how = (p.knows || {})[c.key];
        return `<label class="sx-know"><input type="checkbox" data-k="${esc(c.key)}" ${follows || how !== undefined ? "checked" : ""} ${follows ? "disabled" : ""}>
          <span><b>${esc(c.name)}</b> ${follows ? `<span class="sx-muted">follows the account</span>` : ""}</span>
          ${follows ? "" : `<input class="sx-input" data-how="${esc(c.key)}" value="${esc(how || "")}" placeholder="How they found out (optional)">`}</label>`;
      }).join("");
      EpDialog.open({title: p.account === "aita" ? "Who knows it's them" : "Who knows about this post", wide: true,
        html: `<p class="ep-dialog-p">${p.account === "aita" ? "Everyone can read an AITA thread. Tick who knows who wrote it." : "Ticked characters count as having seen it, because of the story. They can bring it up in the phone chats and reply to it."}</p>
          <div class="sx-knows">${rows || "<p>No one else to tick.</p>"}</div>
          <div class="ep-dialog-actions"><button type="button" class="ep-btn ep-btn-primary" data-save>Save</button></div>`,
        onMount: (box, close) => box.querySelector("[data-save]").addEventListener("click", async () => {
          const wanted = [];
          box.querySelectorAll("[data-k]:not(:disabled)").forEach((cb) => {
            const before = (p.knows || {})[cb.dataset.k] !== undefined;
            const how = box.querySelector(`[data-how="${CSS.escape(cb.dataset.k)}"]`)?.value || "";
            if (cb.checked !== before || (cb.checked && how !== ((p.knows || {})[cb.dataset.k] || ""))) wanted.push({key: cb.dataset.k, knows: cb.checked, how});
          });
          close?.();
          for (const w of wanted) await this.act({action: "set_knows", post_id: id, ...w}, "");
        })});
    },

    forward(id) {
      const p = this.post(id);
      if (!p) return;
      EpDialog.open({title: "Send it in a DM", html: `<label class="ep-dialog-text">To
          <select class="sx-select" data-to>${this.characters().map((c) => `<option value="${esc(c.key)}" ${c.key === p.author ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
          <label class="ep-dialog-text">With a message <span class="sx-muted">(optional)</span><textarea class="sx-input" data-msg rows="2" placeholder="Care to explain?"></textarea></label>
          <p class="ep-dialog-p sx-muted">They'll see it in your chat with them, and count as knowing it from then on.</p>
          <div class="ep-dialog-actions"><button type="button" class="ep-btn ep-btn-primary" data-send>Send</button></div>`,
        onMount: (box, close) => box.querySelector("[data-send]").addEventListener("click", () => {
          const to = box.querySelector("[data-to]").value, msg = box.querySelector("[data-msg]").value;
          close?.();
          this.act({action: "forward_to_telechat", post_id: id, char_slug: to, comment: msg}, "forward", (data) => {
            if (data.threads) TG.state.threads = data.threads;
            if (data.thread) {TG.switchApp("messenger"); TG.selectThread?.(data.thread.id);}
          });
        })});
    },
  };

  window.SUBTEXT = SX;
  window.addEventListener("screen-app-changed", (e) => {if (e.detail?.app === "subtext") SX.init();});
})();
