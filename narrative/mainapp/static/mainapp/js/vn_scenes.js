/* ==========================================================================
   Visual Novel Meet-Up Scene Mode & Event CG Gallery (Digital Screen Hub)
   ========================================================================== */

(function () {
  const VN_SCENES = {
    tab: "stage", // 'stage' | 'gallery'
    beatIndex: 0,
    autoGenSprites: false,
    musicPlaying: false,
    lastFinaleEntry: null,

    init() {
      if (!window.TG || !TG.state) return;
      if (!TG.state.vn_scenes) {
        TG.state.vn_scenes = { active_scene: null, gallery: [], music_tracks: [], backgrounds: [], meetup_cue: { ready: false, reason: "" } };
      }
      const sc = TG.state.vn_scenes.active_scene;
      if (sc && Array.isArray(sc.beats) && sc.beats.length) {
        this.beatIndex = Math.max(0, sc.beats.length - 1);
      }

      const origSwitchApp = TG.switchApp.bind(TG);
      TG.switchApp = (appName) => {
        origSwitchApp(appName);
        if (appName === "scenes") {
          this.render();
        }
      };

      const origRenderMainChat = TG.renderMainChat ? TG.renderMainChat.bind(TG) : null;
      if (origRenderMainChat) {
        TG.renderMainChat = () => {
          origRenderMainChat();
          this.checkAndRenderMeetupBanner();
        };
      }

      this.render();
      this.checkAndRenderMeetupBanner();
    },

    async apiPost(payload) {
      const url = (window.TG_CFG && window.TG_CFG.vn_scenes_api) || "/main/screen/scenes/api/";
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": (window.TG_CFG && window.TG_CFG.csrf) || "",
        },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      return data;
    },

    switchTab(tab) {
      this.tab = tab;
      document.querySelectorAll(".vn-tab-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.vnTab === tab);
      });
      this.render();
    },

    /* ----------------------------------------------------------------------
       Meet-Up Cue Detection & Banner in TeleChat
       ---------------------------------------------------------------------- */
    checkAndRenderMeetupBanner() {
      const banner = document.getElementById("tgMeetupBanner");
      const textEl = document.getElementById("tgMeetupBannerText");
      if (!banner || !TG.state || !TG.state.active_thread) {
        if (banner) banner.style.display = "none";
        return;
      }
      const msgs = TG.state.active_thread.messages || [];
      const recent = msgs.slice(-4);
      const cueRe = /\b(meet\s+up|see\s+you|on\s+my\s+way|omw|outside\s+your|at\s+the\s+door|come\s+over|coming\s+over|heading\s+over|grab\s+coffee|grab\s+a\s+drink|grab\s+dinner|hang\s+out|meet\s+me\s+at|waiting\s+for\s+you|i'?m\s+here|pulling\s+up|be\s+there\s+in)\b/i;
      let hit = null;
      for (let i = recent.length - 1; i >= 0; i--) {
        const m = recent[i];
        if (m.role !== "system" && cueRe.test(m.text || "")) {
          hit = m;
          break;
        }
      }
      if (hit) {
        const who = hit.sender_name || "Chat";
        const snippet = (hit.text || "").slice(0, 85);
        if (textEl) {
          textEl.innerHTML = `🎬 <strong>Meet-Up Cue Detected:</strong> ${TG.esc(who)}: <em>"${TG.esc(snippet)}"</em> — Ready to switch to Visual Novel scene mode?`;
        }
        banner.style.display = "flex";
      } else {
        banner.style.display = "none";
      }
    },

    openLaunchModalFromChat() {
      const t = TG.state.active_thread;
      const hintInput = document.getElementById("vnLocationHintInput");
      TG.switchApp("scenes");
      this.switchTab("stage");
      if (!TG.state.vn_scenes.active_scene) {
        if (hintInput) hintInput.focus();
      }
    },

    async launchFromActiveThread(btnEl) {
      const t = TG.state.active_thread;
      if (!t) {
        TG.toast("Select a TeleChat conversation first.");
        return;
      }
      const hintEl = document.getElementById("vnLocationHintInput");
      const hint = hintEl ? hintEl.value.trim() : "";
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = "🎬 Setting the stage…";
      }
      try {
        TG.switchApp("scenes");
        this.tab = "stage";
        const data = await this.apiPost({
          action: "start_scene",
          thread_id: t.id,
          location_hint: hint,
          auto_generate_sprites: this.autoGenSprites,
        });
        TG.state.vn_scenes = data.vn_scenes;
        if (data.char_sprites) {
          this.mergeCharSprites(data.char_sprites);
        }
        this.beatIndex = 0;
        this.lastFinaleEntry = null;
        this.render();
        this.syncAudioTrack(true);
        TG.toast(`🎬 Scene started: ${data.scene.title}`);
      } catch (e) {
        TG.toast(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    mergeCharSprites(charSpritesMap) {
      if (!charSpritesMap || !Array.isArray(TG.state.characters)) return;
      TG.state.characters.forEach((c) => {
        if (charSpritesMap[c.slug]) {
          c.sprites = charSpritesMap[c.slug];
        }
      });
    },

    /* ----------------------------------------------------------------------
       Beat Navigation & Turn Progression
       ---------------------------------------------------------------------- */
    activeScene() {
      return (TG.state.vn_scenes && TG.state.vn_scenes.active_scene) || null;
    },

    currentBeat() {
      const sc = this.activeScene();
      if (!sc || !Array.isArray(sc.beats) || !sc.beats.length) return null;
      const idx = Math.max(0, Math.min(this.beatIndex, sc.beats.length - 1));
      return sc.beats[idx];
    },

    activeSpriteBeat() {
      const sc = this.activeScene();
      if (!sc || !Array.isArray(sc.beats) || !sc.beats.length) return null;
      const idx = Math.max(0, Math.min(this.beatIndex, sc.beats.length - 1));
      for (let i = idx; i >= 0; i--) {
        const b = sc.beats[i];
        if (b && b.speaker && b.speaker !== "narrator" && b.speaker !== "user") {
          return b;
        }
      }
      const firstCharSlug = (sc.character_slugs || [])[0];
      if (!firstCharSlug) return null;
      const c = (TG.state.characters || []).find((x) => x.slug === firstCharSlug);
      if (!c) return null;
      return {
        id: "default",
        speaker: c.slug,
        speaker_name: c.display_name || c.name,
        emotion: "neutral",
        sprite_url: (c.sprites && c.sprites.neutral) || c.neutral_url || c.avatar_url || "",
        needs_sprite_gen: false,
      };
    },

    prevBeat() {
      if (this.beatIndex > 0) {
        this.beatIndex--;
        this.renderStageOnly();
      }
    },

    nextBeat() {
      const sc = this.activeScene();
      if (!sc || !Array.isArray(sc.beats)) return;
      if (this.beatIndex < sc.beats.length - 1) {
        this.beatIndex++;
        this.renderStageOnly();
      }
    },

    async stepScene(userInput, btnEl) {
      const sc = this.activeScene();
      if (!sc) return;
      const prevLen = (sc.beats || []).length;
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = "⏳ Directing next beats…";
      }
      try {
        const data = await this.apiPost({
          action: "step_scene",
          user_input: userInput || "",
          auto_generate_sprites: this.autoGenSprites,
        });
        TG.state.vn_scenes = data.vn_scenes;
        if (data.char_sprites) {
          this.mergeCharSprites(data.char_sprites);
        }
        const newBeats = (data.scene && data.scene.beats) || [];
        this.beatIndex = Math.min(prevLen, Math.max(0, newBeats.length - 1));
        this.renderStageOnly();
      } catch (e) {
        TG.toast(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    submitUserBeatInput(btnEl) {
      const inp = document.getElementById("vnShortInput");
      const val = inp ? inp.value.trim() : "";
      if (!val) {
        TG.toast("Write a short action or dialogue line, or click Continue Scene.");
        return;
      }
      this.stepScene(val, btnEl);
    },

    async generateSpriteForCurrentBeat(customEmotion, btnEl) {
      const spBeat = this.activeSpriteBeat();
      if (!spBeat || !spBeat.speaker) return;
      const emotion = customEmotion || spBeat.emotion || "neutral";
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = `🎨 Painting '${emotion}' sprite…`;
      }
      try {
        const data = await this.apiPost({
          action: "generate_sprite",
          beat_id: spBeat.id || "",
          char_slug: spBeat.speaker,
          emotion: emotion,
        });
        if (TG.state.vn_scenes) {
          TG.state.vn_scenes.active_scene = data.scene;
        }
        if (data.char_slug && data.sprites) {
          this.mergeCharSprites({ [data.char_slug]: data.sprites });
        }
        this.renderStageOnly();
        TG.toast(`🎨 Saved '${data.emotion}' sprite permanently for ${spBeat.speaker_name}!`);
      } catch (e) {
        TG.toast(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    promptCustomMoodSprite(btnEl) {
      const spBeat = this.activeSpriteBeat();
      if (!spBeat) return;
      const mood = window.prompt(
        `Enter an expression mood to generate & store permanently for ${spBeat.speaker_name} (e.g. flustered, smug, blushing, laughing, surprised, scheming):`,
        spBeat.emotion || "flustered"
      );
      if (!mood || !mood.trim()) return;
      this.generateSpriteForCurrentBeat(mood.trim().toLowerCase(), btnEl);
    },

    async changeStageSetting(kind, val) {
      const payload = { action: "set_stage" };
      if (kind === "music") payload.music_id = val;
      if (kind === "bg") payload.background_id = val;
      try {
        const data = await this.apiPost(payload);
        if (TG.state.vn_scenes) {
          TG.state.vn_scenes.active_scene = data.scene;
        }
        this.renderStageOnly();
        if (kind === "music") this.syncAudioTrack(true);
      } catch (e) {
        TG.toast(e.message, true);
      }
    },

    syncAudioTrack(autoPlay) {
      const sc = this.activeScene();
      const audio = document.getElementById("vnAudioPlayer");
      if (!audio) return;
      const url = sc && sc.music ? sc.music.url : "";
      if (!url) {
        audio.pause();
        this.musicPlaying = false;
        return;
      }
      if (audio.getAttribute("data-src") !== url) {
        audio.src = url;
        audio.setAttribute("data-src", url);
      }
      if (autoPlay) {
        audio.volume = 0.45;
        audio.play().then(() => {
          this.musicPlaying = true;
          this.updateMusicBtnLabel();
        }).catch(() => {
          this.musicPlaying = false;
          this.updateMusicBtnLabel();
        });
      }
    },

    toggleMusic() {
      const audio = document.getElementById("vnAudioPlayer");
      if (!audio) return;
      if (audio.paused) {
        audio.volume = 0.45;
        audio.play().then(() => {
          this.musicPlaying = true;
          this.updateMusicBtnLabel();
        }).catch(() => {});
      } else {
        audio.pause();
        this.musicPlaying = false;
        this.updateMusicBtnLabel();
      }
    },

    updateMusicBtnLabel() {
      const btn = document.getElementById("vnMusicToggleBtn");
      const sc = this.activeScene();
      if (!btn || !sc || !sc.music) return;
      btn.textContent = `${this.musicPlaying ? "🔊 Pause" : "🔈 Play"} · ${sc.music.name}`;
    },

    /* ----------------------------------------------------------------------
       Finale Event CG Generation & Scene Completion
       ---------------------------------------------------------------------- */
    async finishScene(btnEl) {
      const sc = this.activeScene();
      if (!sc) return;
      const hintEl = document.getElementById("vnShortInput");
      const cgHint = hintEl ? hintEl.value.trim() : "";
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = "🖼️ Painting Finale Event CG…";
      }
      try {
        const data = await this.apiPost({
          action: "finish_scene",
          cg_hint: cgHint,
        });
        TG.state.vn_scenes = data.vn_scenes;
        if (data.threads) {
          TG.state.threads = data.threads;
        }
        if (data.thread) {
          TG.state.active_thread = data.thread;
          TG.renderSidebar();
          TG.renderMainChat();
        }
        this.lastFinaleEntry = data.gallery_entry;
        this.render();
        TG.toast("🖼️ Finale Event CG saved to Gallery & shared in TeleChat!");
      } catch (e) {
        TG.toast(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    returnToPhone() {
      this.lastFinaleEntry = null;
      const audio = document.getElementById("vnAudioPlayer");
      if (audio) audio.pause();
      this.musicPlaying = false;
      TG.switchApp("messenger");
      TG.renderMainChat();
    },

    startAnotherScene() {
      this.lastFinaleEntry = null;
      this.render();
    },

    async deleteGalleryItem(id) {
      try {
        const data = await this.apiPost({ action: "delete_gallery_item", id });
        TG.state.vn_scenes = data.vn_scenes;
        this.render();
      } catch (e) {
        TG.toast(e.message, true);
      }
    },

    viewGalleryTranscript(id) {
      const gallery = (TG.state.vn_scenes && TG.state.vn_scenes.gallery) || [];
      const item = gallery.find((g) => g.id === id);
      if (!item) return;
      const modal = document.getElementById("modalStory");
      const body = document.getElementById("modalStoryBody");
      if (!modal || !body) return;

      const beatsHtml = (item.beats || []).map((b) => {
        if (b.kind === "narration" || b.speaker === "narrator") {
          return `<div style="font-style:italic; color:#94a3b8; padding:6px 0;">${TG.esc(b.text)}</div>`;
        }
        const emo = b.emotion ? ` <span style="font-size:11px; color:#f472b6;">(${TG.esc(b.emotion)})</span>` : "";
        return `<div style="padding:6px 0;"><strong style="color:#f8fafc;">${TG.esc(b.speaker_name || b.speaker)}</strong>${emo}: <span style="color:#e2e8f0;">${TG.esc(b.text)}</span></div>`;
      }).join("");

      body.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
          <div>
            <h3 style="margin:0;">🎬 ${TG.esc(item.title)}</h3>
            <div style="font-size:12px; color:var(--tg-muted);">📍 ${TG.esc(item.location)} · 🎵 ${TG.esc((item.music && item.music.name) || "BGM")} · ${TG.esc(item.finished_at || "")}</div>
          </div>
          <button type="button" class="tg-fmt-btn" onclick="TG.closeModals()">✕</button>
        </div>
        ${item.cg_url ? `<img src="${TG.esc(item.cg_url)}" alt="Finale CG" style="width:100%; max-height:320px; object-fit:cover; border-radius:12px; border:1px solid rgba(255,255,255,0.14);">` : ""}
        <div style="font-size:13px; color:#fbcfe8; background:rgba(219,39,119,0.12); padding:10px 12px; border-radius:10px;">
          <strong>Summary:</strong> ${TG.esc(item.summary || "")}
        </div>
        <div style="max-height:280px; overflow-y:auto; padding:10px 12px; background:rgba(15,23,42,0.75); border-radius:10px; font-size:13px; border:1px solid rgba(255,255,255,0.08);">
          ${beatsHtml}
        </div>
      `;
      modal.classList.add("open");
    },

    /* ----------------------------------------------------------------------
       Main Renderers
       ---------------------------------------------------------------------- */
    render() {
      const root = document.getElementById("vnScenesRoot");
      if (!root) return;
      const galleryCount = ((TG.state.vn_scenes && TG.state.vn_scenes.gallery) || []).length;
      const badgeEl = document.getElementById("vnGalleryCountBadge");
      if (badgeEl) badgeEl.textContent = galleryCount;

      if (this.tab === "gallery") {
        this.renderGallery(root);
      } else {
        this.renderStageOnly();
      }
    },

    renderStageOnly() {
      const root = document.getElementById("vnScenesRoot");
      if (!root || this.tab !== "stage") return;

      // 1. If a Finale CG was just generated, display the Finale Event CG Showcase
      if (this.lastFinaleEntry) {
        const e = this.lastFinaleEntry;
        root.innerHTML = `
          <div class="vn-gallery-pane" style="display:flex; align-items:center; justify-content:center;">
            <div style="max-width:760px; width:100%; background:rgba(15,23,42,0.92); border:1.5px solid rgba(236,72,153,0.45); border-radius:20px; padding:22px; box-shadow:0 24px 60px rgba(0,0,0,0.75); display:flex; flex-direction:column; gap:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                  <span style="font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; color:#f472b6;">🌟 Scene Complete · Saved to CG Gallery</span>
                  <h2 style="margin:3px 0 0; font-size:21px;">${TG.esc(e.title)}</h2>
                </div>
                <span style="font-size:12px; color:#94a3b8;">📍 ${TG.esc(e.location)}</span>
              </div>
              ${e.cg_url ? `
                <div style="position:relative; border-radius:14px; overflow:hidden; border:1px solid rgba(255,255,255,0.16); background:#090d16;">
                  <img src="${TG.esc(e.cg_url)}" alt="Finale Event CG" style="width:100%; max-height:420px; object-fit:contain; display:block;">
                </div>
              ` : ""}
              ${e.quote ? `<div style="font-size:15px; font-style:italic; color:#fbcfe8; text-align:center;">"${TG.esc(e.quote)}"</div>` : ""}
              <div style="font-size:13.5px; color:#e2e8f0; background:rgba(30,41,59,0.65); padding:11px 14px; border-radius:12px;">
                ${TG.esc(e.summary || "")}
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; padding-top:4px;">
                <button type="button" class="tg-fmt-btn" onclick="VN_SCENES.switchTab('gallery')">🖼️ View in CG Gallery</button>
                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                  <button type="button" class="tg-bulba-btn" onclick="VN_SCENES.startAnotherScene()">🎬 Start Next Scene</button>
                  <button type="button" class="tg-send-btn" onclick="VN_SCENES.returnToPhone()">📱 Back to TeleChat Phone ➤</button>
                </div>
              </div>
            </div>
          </div>
        `;
        return;
      }

      const sc = this.activeScene();
      // 2. If no active scene yet, show the Scene Launcher card
      if (!sc) {
        const t = TG.state.active_thread;
        const threadTitle = t ? t.title : "your active chat";
        const cue = (TG.state.vn_scenes && TG.state.vn_scenes.meetup_cue) || {};
        root.innerHTML = `
          <div class="vn-gallery-pane" style="display:flex; align-items:center; justify-content:center;">
            <div style="max-width:620px; width:100%; background:rgba(15,23,42,0.9); border:1px solid rgba(255,255,255,0.12); border-radius:20px; padding:26px; display:flex; flex-direction:column; gap:16px; box-shadow:0 20px 50px rgba(0,0,0,0.6);">
              <div>
                <span style="font-size:11.5px; font-weight:700; color:#f472b6; text-transform:uppercase; letter-spacing:0.05em;">🎬 Visual Novel Meet-Up Engine</span>
                <h2 style="margin:4px 0 6px; font-size:22px;">Step Out of the Phone & Meet In Person</h2>
                <p style="margin:0; font-size:13.5px; color:#94a3b8; line-height:1.55;">
                  Transition from texting in <strong>${TG.esc(threadTitle)}</strong> into a full Visual Novel stage: central character expression sprites, background music & scenery chosen by the model, dynamic new sprite generation, and a widescreen Finale Event CG saved to your gallery.
                </p>
              </div>
              ${cue.ready ? `
                <div style="padding:10px 13px; border-radius:12px; background:rgba(219,39,119,0.16); border:1px solid rgba(236,72,153,0.4); font-size:12.5px; color:#fbcfe8;">
                  ✨ <strong>Recent chat cue:</strong> <em>"${TG.esc(cue.reason)}"</em>
                </div>
              ` : ""}
              <div class="tg-field-group">
                <label>Where are you meeting up? (optional — leave blank for the model to pick from your chat)</label>
                <input type="text" class="tg-input" id="vnLocationHintInput" placeholder="e.g. Rainy neon coffee shop at 11 PM, rooftop balcony, quiet library corner…">
              </div>
              <label style="display:flex; align-items:center; gap:8px; font-size:12.5px; color:#cbd5e1; cursor:pointer;">
                <input type="checkbox" ${this.autoGenSprites ? "checked" : ""} onchange="VN_SCENES.autoGenSprites = this.checked">
                <span>🎨 Automatically generate & permanently save new expression sprites whenever a scene calls for a mood the character doesn't have yet</span>
              </label>
              <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
                <button type="button" class="tg-fmt-btn" onclick="TG.switchApp('messenger')">← Back to TeleChat</button>
                <button type="button" class="tg-send-btn" style="background:linear-gradient(135deg,#db2777,#7c3aed);" onclick="VN_SCENES.launchFromActiveThread(this)">🎬 Launch Meet-Up Scene ➤</button>
              </div>
            </div>
          </div>
        `;
        return;
      }

      // 3. Active Visual Novel Stage
      const beats = sc.beats || [];
      const idx = Math.max(0, Math.min(this.beatIndex, Math.max(0, beats.length - 1)));
      const beat = beats[idx] || { speaker: "narrator", speaker_name: "Narrator", kind: "narration", text: "…" };
      const spBeat = this.activeSpriteBeat();
      const isLastBeat = idx >= beats.length - 1;
      const bgUrl = (sc.background && sc.background.url) || "";

      const tracks = (TG.state.vn_scenes && TG.state.vn_scenes.music_tracks) || [];
      const bgs = (TG.state.vn_scenes && TG.state.vn_scenes.backgrounds) || [];

      const musicOpts = tracks.map((t) =>
        `<option value="${TG.esc(t.id)}" ${sc.music && sc.music.id === t.id ? "selected" : ""}>🎵 ${TG.esc(t.name)}</option>`
      ).join("");

      const bgOpts = bgs.map((b) =>
        `<option value="${TG.esc(b.id)}" ${sc.background && sc.background.id === b.id ? "selected" : ""}>🖼️ ${TG.esc(b.name)}</option>`
      ).join("");

      const isNarrator = beat.kind === "narration" || beat.speaker === "narrator";
      const handoff = sc.handoff || "user_turn";
      const choices = Array.isArray(sc.choices) ? sc.choices : [];

      root.innerHTML = `
        <div class="vn-stage-wrap" style="${bgUrl ? `background-image:url('${TG.esc(bgUrl)}');` : ""}">
          <div class="vn-stage-overlay"></div>

          <!-- Top Stage HUD -->
          <div class="vn-stage-hud">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span class="vn-hud-pill">📍 ${TG.esc(sc.location || sc.title || "Meet-Up Scene")}</span>
              <button type="button" class="vn-hud-pill" id="vnMusicToggleBtn" style="cursor:pointer;" onclick="VN_SCENES.toggleMusic()">
                ${this.musicPlaying ? "🔊 Pause" : "🔈 Play"} · ${TG.esc((sc.music && sc.music.name) || "BGM")}
              </button>
              <select class="tg-select" style="width:auto; padding:4px 9px; font-size:11.5px; background:rgba(11,17,30,0.82);" onchange="VN_SCENES.changeStageSetting('music', this.value)" title="Switch background music">
                ${musicOpts}
              </select>
              <select class="tg-select" style="width:auto; padding:4px 9px; font-size:11.5px; background:rgba(11,17,30,0.82);" onchange="VN_SCENES.changeStageSetting('bg', this.value)" title="Switch stage backdrop">
                ${bgOpts}
              </select>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              <label class="vn-hud-pill" style="cursor:pointer; font-weight:500;">
                <input type="checkbox" ${this.autoGenSprites ? "checked" : ""} onchange="VN_SCENES.autoGenSprites = this.checked">
                <span>🎨 Auto-gen missing sprites</span>
              </label>
              <button type="button" class="vn-hud-pill" style="cursor:pointer;" onclick="VN_SCENES.returnToPhone()" title="Minimize scene and return to TeleChat">
                📱 Phone
              </button>
            </div>
          </div>

          <!-- Central Character Sprite Stage -->
          <div class="vn-sprite-stage">
            ${spBeat ? `
              <div class="vn-central-sprite-card">
                ${spBeat.sprite_url ? `
                  <img class="vn-central-sprite-img" src="${TG.esc(spBeat.sprite_url)}" alt="${TG.esc(spBeat.speaker_name)}">
                ` : `
                  <div style="width:220px; height:280px; border-radius:18px; background:rgba(15,23,42,0.85); border:1px dashed rgba(244,114,182,0.45); display:flex; align-items:center; justify-content:center; flex-direction:column; gap:8px; color:#fbcfe8;">
                    <span style="font-size:42px;">🎭</span>
                    <strong>${TG.esc(spBeat.speaker_name)}</strong>
                  </div>
                `}
                <div class="vn-sprite-mood-bar">
                  <span class="vn-mood-badge">🎭 ${TG.esc(spBeat.speaker_name)} · ${TG.esc(spBeat.emotion || "neutral")}</span>
                  ${spBeat.needs_sprite_gen ? `
                    <button type="button" class="vn-gen-sprite-btn" onclick="VN_SCENES.generateSpriteForCurrentBeat('${TG.esc(spBeat.emotion)}', this)" title="Generate and permanently store this '${TG.esc(spBeat.emotion)}' expression sprite on ${TG.esc(spBeat.speaker_name)}">
                      🎨 Generate & Save '${TG.esc(spBeat.emotion)}' Sprite
                    </button>
                  ` : `
                    <button type="button" class="vn-gen-sprite-btn" style="opacity:0.86; font-size:11px;" onclick="VN_SCENES.promptCustomMoodSprite(this)" title="Dynamically generate & store a new expression sprite for ${TG.esc(spBeat.speaker_name)}">
                      🎨 + New Mood Sprite
                    </button>
                  `}
                </div>
              </div>
            ` : ""}
          </div>

          <!-- Classic Visual Novel Dialogue Box -->
          <div class="vn-dialogue-dock">
            <div class="vn-dialogue-box">
              <div class="vn-speaker-plate ${isNarrator ? "narrator" : ""}">
                <span>${isNarrator ? "📖 Narration" : `💬 ${TG.esc(beat.speaker_name || beat.speaker)}`}</span>
                ${!isNarrator && beat.emotion ? `<span style="font-weight:500; opacity:0.88; font-size:11.5px;">· ${TG.esc(beat.emotion)}</span>` : ""}
              </div>
              <div class="vn-beat-counter">Beat ${idx + 1} / ${beats.length}</div>

              <div class="vn-beat-text ${isNarrator ? "narration-line" : ""}">
                ${TG.formatText ? TG.formatText(beat.text || "") : TG.esc(beat.text || "")}
              </div>

              <div class="vn-beat-nav-row">
                <div style="display:flex; gap:8px; align-items:center;">
                  <button type="button" class="tg-fmt-btn" ${idx <= 0 ? "disabled style='opacity:0.4'" : ""} onclick="VN_SCENES.prevBeat()">◀ Prev Beat</button>
                  ${!isLastBeat ? `
                    <button type="button" class="tg-send-btn" onclick="VN_SCENES.nextBeat()">Next Beat ▶ (${idx + 2}/${beats.length})</button>
                  ` : `
                    <span style="font-size:12px; color:#fbcfe8; font-weight:600;">
                      ${handoff === "climax_ready"
                        ? "🌟 Scene climax reached — ready to capture Finale Event CG or keep going!"
                        : handoff === "auto_continue"
                        ? "🎬 Characters are in the middle of the moment — click Continue Scene or jump in!"
                        : "✍️ Characters paused for your action or dialogue:"}
                    </span>
                  `}
                </div>
                ${!isLastBeat ? `
                  <button type="button" class="tg-fmt-btn" onclick="VN_SCENES.beatIndex = ${beats.length - 1}; VN_SCENES.renderStageOnly();">Skip to Turn End ⏭</button>
                ` : ""}
              </div>

              ${isLastBeat ? `
                <div class="vn-turn-director">
                  ${choices.length ? `
                    <div class="vn-choices-row">
                      ${choices.map((c) => `
                        <button type="button" class="vn-choice-chip" onclick="VN_SCENES.stepScene(${JSON.stringify(c)}, this)">
                          ✨ ${TG.esc(c)}
                        </button>
                      `).join("")}
                    </div>
                  ` : ""}
                  <div class="vn-input-row">
                    <input type="text" class="vn-short-input" id="vnShortInput" placeholder="Short action or dialogue (e.g. *smiles and takes the cup* &quot;Thanks for meeting me.&quot;)…" onkeydown="if(event.key==='Enter'){event.preventDefault(); VN_SCENES.submitUserBeatInput();}">
                    <button type="button" class="tg-send-btn" onclick="VN_SCENES.submitUserBeatInput(this)">Act / Speak ➤</button>
                    <button type="button" class="tg-bulba-btn" style="${handoff === "auto_continue" ? "box-shadow:0 0 14px rgba(168,85,247,0.65);" : ""}" onclick="VN_SCENES.stepScene('', this)" title="Let the characters continue the scene without user input">
                      Continue Scene ▶▶
                    </button>
                    <button type="button" class="vn-climax-btn ${handoff === "climax_ready" ? "pulse" : ""}" onclick="VN_SCENES.finishScene(this)" title="End the scene on a full widescreen generated Event CG and save it to your Gallery">
                      🖼️ End & Capture Finale CG
                    </button>
                  </div>
                </div>
              ` : ""}
            </div>
          </div>
        </div>
      `;
    },

    renderGallery(root) {
      const gallery = (TG.state.vn_scenes && TG.state.vn_scenes.gallery) || [];
      if (!gallery.length) {
        root.innerHTML = `
          <div class="vn-gallery-pane">
            <div style="max-width:560px; margin:40px auto; text-align:center; padding:28px; background:rgba(15,23,42,0.85); border:1px solid rgba(255,255,255,0.1); border-radius:18px;">
              <div style="font-size:40px; margin-bottom:8px;">🖼️</div>
              <h3 style="margin:0 0 6px;">Your Event CG & Scene Gallery is Empty</h3>
              <p style="margin:0 0 16px; font-size:13px; color:#94a3b8;">
                Launch a Meet-Up Scene from TeleChat and click <strong>"🖼️ End & Capture Finale CG"</strong> when the scene peaks to save widescreen Event CG artwork and replayable scene transcripts here.
              </p>
              <button type="button" class="tg-send-btn" onclick="VN_SCENES.switchTab('stage')">🎬 Go to Visual Novel Stage</button>
            </div>
          </div>
        `;
        return;
      }

      const cardsHtml = gallery.map((item) => `
        <article class="vn-cg-card">
          ${item.cg_url ? `
            <img class="vn-cg-thumb" src="${TG.esc(item.cg_url)}" alt="${TG.esc(item.title)}" onclick="VN_SCENES.viewGalleryTranscript('${TG.esc(item.id)}')">
          ` : `
            <div class="vn-cg-thumb" style="display:flex; align-items:center; justify-content:center; font-size:32px;" onclick="VN_SCENES.viewGalleryTranscript('${TG.esc(item.id)}')">🎬</div>
          `}
          <div class="vn-cg-body">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
              <strong style="font-size:14.5px; color:#f8fafc;">${TG.esc(item.title)}</strong>
              <span style="font-size:11px; color:#94a3b8; white-space:nowrap;">${TG.esc(item.finished_at || "")}</span>
            </div>
            <div style="font-size:11.5px; color:#f472b6;">
              📍 ${TG.esc(item.location || "Meet-Up")} · 🎵 ${TG.esc((item.music && item.music.name) || "BGM")}
            </div>
            ${item.quote ? `<div style="font-size:12px; font-style:italic; color:#fbcfe8;">"${TG.esc(item.quote)}"</div>` : ""}
            <p style="margin:0; font-size:12.5px; color:#cbd5e1; line-height:1.45;">${TG.esc(item.summary || "")}</p>
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:6px;">
              <button type="button" class="tg-fmt-btn" onclick="VN_SCENES.viewGalleryTranscript('${TG.esc(item.id)}')">📖 Replay Scene (${(item.beats || []).length} beats)</button>
              <button type="button" class="tg-fmt-btn" style="color:#f87171;" onclick="VN_SCENES.deleteGalleryItem('${TG.esc(item.id)}')" title="Remove from gallery">🗑</button>
            </div>
          </div>
        </article>
      `).join("");

      root.innerHTML = `
        <div class="vn-gallery-pane">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <h2 style="margin:0 0 3px; font-size:19px;">🖼️ Visual Novel Event CG & Scene Gallery</h2>
              <p style="margin:0; font-size:12.5px; color:#94a3b8;">Every completed in-person meet-up scene, its widescreen Finale Event CG, and full replayable transcript.</p>
            </div>
            <button type="button" class="tg-send-btn" onclick="VN_SCENES.switchTab('stage')">🎬 Back to VN Stage</button>
          </div>
          <div class="vn-gallery-grid">${cardsHtml}</div>
        </div>
      `;
    },
  };

  window.VN_SCENES = VN_SCENES;
  document.addEventListener("DOMContentLoaded", () => {
    VN_SCENES.init();
  });
})();
