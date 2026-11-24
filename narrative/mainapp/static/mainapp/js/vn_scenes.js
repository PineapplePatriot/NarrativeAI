/* ==========================================================================
   Visual Novel Meet-Up Scene Mode & Event CG Gallery (Digital Screen Hub)
   ========================================================================== */

(function () {
  const VN_SCENES = {
    tab: "stage", // 'stage' | 'gallery'
    beatIndex: 0,
    musicPlaying: false,
    lastFinaleEntry: null,
    busy: false,

    attr(value) {return TG.esc(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');},

    setBusy(value) {
      this.busy = value;
      const root = document.getElementById('vnScenesRoot');
      if (root) root.setAttribute('aria-busy', String(value));
      document.querySelectorAll('#vnScenesRoot button, #vnScenesRoot input, #vnScenesRoot textarea, #vnScenesRoot select, [data-vn-mutation]').forEach(control => {
        if (value && !control.disabled) {control.dataset.vnBusyDisabled = 'true'; control.disabled = true;}
        else if (!value && control.dataset.vnBusyDisabled) {delete control.dataset.vnBusyDisabled; control.disabled = false;}
      });
    },

    bindDrafts(root, key) {
      if (key.startsWith('vn:') && this.activeScene()) window.ScreenDrafts?.put(key, {...window.ScreenDrafts.get(key), title: this.activeScene().title});
      window.ScreenDrafts?.bind(root, key);
      this.setBusy(this.busy);
    },

    stopMusic() {
      document.getElementById('vnAudioPlayer')?.pause();
      this.musicPlaying = false;
    },

    async reloadScene() {
      if (this.busy) {this.notify('Wait for the current request before reloading.'); return;}
      const id = this.currentBeat()?.id;
      this.setBusy(true);
      try {
        const response = await fetch(TG_CFG.vn_scenes_api);
        const data = await response.json();
        if (!response.ok) throw Error(data.error || 'Could not reload this episode.');
        TG.state.vn_scenes = data.vn_scenes;
        const scene = this.activeScene();
        this.beatIndex = Math.max(0, scene?.beats?.findIndex(b => b.id === id) ?? 0);
        this.lastFinaleEntry = null; this.render();
        this.notify('Episode reloaded. Unsent replies are available under Versions.');
      } catch (error) {this.notify(error.message, true);} finally {this.setBusy(false);}
    },

    init() {
      if (!window.TG || !TG.state) return;
      if (!TG.state.vn_scenes) {
        TG.state.vn_scenes = { active_scene: null, gallery: [], music_tracks: [], backgrounds: [], meetup_cue: { ready: false, reason: "" } };
      }
      const sc = TG.state.vn_scenes.active_scene;
      if (sc && Array.isArray(sc.beats) && sc.beats.length) {
        let saved;
        try {saved = localStorage.getItem("vn-cursor-" + sc.id);} catch (_) {saved = this.savedCursor?.[sc.id];}
        const index = sc.beats.findIndex((b) => b.id === saved);
        this.beatIndex = index >= 0 ? index : Math.max(0, sc.beats.length - ((sc.current_beats || []).length || 1));
      }

      if (!this.initialized) {
      this.initialized = true;
      const origSwitchApp = TG.switchApp.bind(TG);
      TG.switchApp = (appName) => {
        origSwitchApp(appName);
        if (appName === "scenes") {
          this.render();
        } else this.stopMusic();
      };

      window.addEventListener("telechat-rendered", () => this.checkAndRenderMeetupBanner());
      }

      this.render();
      this.checkAndRenderMeetupBanner();
    },

    notify(message, isError = false) {
      const notice = document.getElementById("vnNotice");
      if (!notice) return;
      notice.textContent = message;
      notice.setAttribute('role', isError ? 'alert' : 'status');
      notice.dataset.error = String(isError);
      notice.hidden = false;
    },

    async apiPost(payload) {
      if (this.busy) throw new Error("The episode is still working on your previous request.");
      if (this.watchPromise) await this.watchPromise.catch(() => {});  // let Bulba's check save first
      this.setBusy(true);
      try {
      const url = (window.TG_CFG && window.TG_CFG.vn_scenes_api) || "/main/screen/scenes/api/";
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": (window.TG_CFG && window.TG_CFG.csrf) || "",
        },
        body: JSON.stringify({scene_id: this.activeScene()?.id, revision: this.activeScene()?.revision, ...payload}),
      });
      let data;
      try {data = await resp.json();} catch (_) {throw new Error(`The server returned an unreadable response (HTTP ${resp.status}). Your unsent text is preserved.`);}
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('The server returned an unexpected response. Your unsent text is preserved.');
      if (!resp.ok || data.error) {
        const error = new Error(data.error || `HTTP ${resp.status}`); error.status = resp.status; throw error;
      }
      return data;
      } finally {
        this.setBusy(false);
      }
    },

    switchTab(tab) {
      if (tab !== 'stage') this.stopMusic();
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
          textEl.innerHTML = `🎬 <strong>Meet-Up Cue Detected:</strong> ${this.attr(who)}: <em>"${this.attr(snippet)}"</em> — Ready to switch to Visual Novel scene mode?`;
        }
        banner.style.display = "flex";
      } else {
        banner.style.display = "none";
      }
    },

    openLaunchModalFromChat() {
      this.pendingPulse = null;
      const t = TG.state.active_thread;
      const existing = this.activeScene();
      TG.switchApp("scenes");
      this.switchTab("stage");
      if (existing && t && existing.thread_id !== t.id) this.notify(`An episode with ${(existing.character_names || []).join(', ')} is already open. Save it as unfinished under Episode preferences before starting another chat's episode.`);
      if (!TG.state.vn_scenes.active_scene) {
        document.getElementById("vnLocationHintInput")?.focus();
      }
    },

    async preparePulse(seed) {
      if(this.busy || this.activeScene()) throw new Error('Save or finish the open episode before preparing a Pulse scene.');
      const selected=await TG.selectThread(seed.thread_id);
      if(selected===false) throw new Error('Chat selection changed. Reopen the plan from Pulse.');
      if(this.busy || this.activeScene()) throw new Error('An episode is already open. Save or finish it first.');
      this.pendingPulse=seed;
      const key='launch:'+seed.thread_id;
      ScreenDrafts.put(key,{...ScreenDrafts.get(key),location:seed.location,auto_images:false});
      this.tab='stage';TG.switchApp('scenes');this.render();
    },

    /* The wait while the opening is written: what is happening, step by step, over the place's backdrop. */
    showLaunchTransition(visible, drawing = false) {
      const transition = document.getElementById('vnLaunchTransition');
      const root = document.getElementById('vnScenesRoot');
      clearTimeout(this.launchStepTimer);
      if (visible) {
        document.getElementById('vnNotice').hidden = true;
        const steps = ['Reading the casting sheet', 'Writing the opening', ...(drawing ? ['Drawing the backdrop'] : []), 'Putting everyone on stage'];
        document.getElementById('vnLaunchDetail').innerHTML = `<ol class="ep-wait-steps">${steps.map((s, i) =>
          `<li data-step="${i}" class="${i === 0 ? 'is-now' : ''}">${s}</li>`).join('')}</ol>`;
        let at = 0;
        const tick = () => {
          const items = transition.querySelectorAll('[data-step]');
          if (at >= items.length - 1) return;
          items[at].className = 'is-done'; at += 1; items[at].className = 'is-now';
          this.launchStepTimer = setTimeout(tick, at === 1 ? 9000 : 7000);
        };
        this.launchStepTimer = setTimeout(tick, 1200);
      }
      root.hidden = visible;
      transition.hidden = !visible;
    },

    async launchFromActiveThread() {
      if (this.busy) return;
      const t = TG.state.active_thread;
      if (!t) {
        this.notify("Select a TeleChat conversation first.");
        return;
      }
      if (window.CASTING?.pending() && !window.confirm("Some of Bulba's suggestions aren't applied yet, so they won't be used. Start anyway?")) return;
      const casting = window.CASTING?.payload() || null;
      const hintEl = document.getElementById("vnLocationHintInput");
      const hint = hintEl ? hintEl.value.trim() : "";
      const direction = (document.getElementById("vnWritingDirection") || {}).value || "";
      const polishEnabled = !!(document.getElementById("vnPolishEnabled") || {}).checked;
      const interactionMode = (document.getElementById("vnInteractionMode") || {}).value || "mixed";
      const authoringMode = (document.getElementById("vnAuthoringMode") || {}).value || "roleplay";
      this.tab = "stage";
      if (!document.getElementById('app-scenes').classList.contains('active')) TG.switchApp("scenes");
      const drawPlace = !!(casting && casting.place && !casting.place.background_id);
      this.showLaunchTransition(true, drawPlace || !!document.getElementById("vnGenerateBackground")?.checked);
      try {
        const data = await this.apiPost({
          action: "start_scene",
          thread_id: t.id,
          ...(this.pendingPulse?.thread_id === t.id ? {pulse_event_id:this.pendingPulse.id,pulse_event_revision:this.pendingPulse.revision}:{}),
          location_hint: hint,
          looks: window.EPISODE_LOOKS?.chosen() || {},
          casting,
          ...(casting?.cast?.length ? {character_slugs: casting.cast} : {}),
          generate_background: drawPlace || !!document.getElementById("vnGenerateBackground")?.checked,
          direction,
          polish_enabled: polishEnabled,
          interaction_mode: interactionMode, authoring_mode: authoringMode,
        });
        TG.state.vn_scenes = data.vn_scenes;
        this.pendingPulse = null;
        window.ScreenDrafts?.clear('launch:' + t.id);
        window.CASTING?.clear(t.id);
        this.beatIndex = 0;
        this.lastFinaleEntry = null;
        this.render();
        this.syncAudioTrack(!!document.getElementById('app-scenes')?.classList.contains('active'));
        if (TG.state.vn_scenes?.watch_on) this.runWatch();
        this.notify(data.scene.background_error || data.scene.polish_error || `🎬 Scene started: ${data.scene.title}`, !!(data.scene.background_error || data.scene.polish_error));
      } catch (e) {
        this.notify(e.message, true);
      } finally {
        this.showLaunchTransition(false);
        const notice = document.getElementById('vnNotice');
        if (notice.dataset.error === 'true' && document.getElementById('app-scenes').classList.contains('active')) {
          notice.scrollIntoView({block: 'nearest'});
        }
      }
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
        if (b?.hide_sprite) return null;
        if (b && b.character_slug && (b.character_slug !== "user" || sc.authoring_mode === "director")) {
          // The camera may show the listener while somebody else is speaking.
          return { ...b, speaker: b.character_slug, speaker_name: b.character_name || b.speaker_name };
        }
      }
      const firstCharSlug = (sc.character_slugs || [])[0];
      if (!firstCharSlug) return null;
      const c = (TG.state.characters || []).find((x) => x.slug === firstCharSlug);
      if (!c) return null;
      const look = (TG.state.vn_scenes?.looks || {})[c.slug];
      return {
        id: "default",
        speaker: c.slug,
        speaker_name: c.display_name || c.name,
        emotion: "neutral",
        look_id: look?.id || null,
        sprite_url: look?.moods?.neutral?.url || "",
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
        btnEl.textContent = "Writing the next part…";
      }
      try {
        const data = await this.apiPost({
          action: "step_scene",
          user_input: userInput || "",
        });
        TG.state.vn_scenes = data.vn_scenes;
        window.ScreenDrafts?.clear('vn:' + sc.id, ['reply']);
        const newBeats = (data.scene && data.scene.beats) || [];
        this.beatIndex = data.new_beats && data.new_beats.length
          ? newBeats.findIndex((b) => b.id === data.new_beats[0].id)
          : Math.min(prevLen, Math.max(0, newBeats.length - 1));
        this.renderStageOnly();
        this.syncAudioTrack(this.musicPlaying);
        if (data.scene.polish_error) this.notify(data.scene.polish_error, true);
        if (TG.state.vn_scenes?.watch_on) this.runWatch();
      } catch (e) {
        this.notify(e.message, true);
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
        this.notify("Write a short action or dialogue line, or click Continue Scene.");
        return;
      }
      this.stepScene(val, btnEl);
    },

    async suggestChoices() {
      try {
        this.notify('Suggesting options without advancing the scene…');
        const data = await this.apiPost({action: 'suggest_choices'});
        TG.state.vn_scenes = data.vn_scenes;
        this.renderStageOnly(); this.notify('Options ready.');
      } catch (error) {this.notify(error.message, true);}
    },

    async drawLookMood(customEmotion, btnEl) {
      const spBeat = this.activeSpriteBeat();
      if (!spBeat || !spBeat.look_id) return;
      const emotion = customEmotion || spBeat.asked_emotion || spBeat.emotion || "neutral";
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = `Drawing “${emotion}”…`;
      }
      try {
        const data = await this.apiPost({action: "add_look_mood", beat_id: spBeat.id || "", emotion});
        if (TG.state.vn_scenes) {
          TG.state.vn_scenes.active_scene = data.scene;
          TG.state.vn_scenes.looks = data.looks || TG.state.vn_scenes.looks;
        }
        this.renderStageOnly();
        this.notify(`“${emotion}” added to ${spBeat.speaker_name}'s look. Cutting it out…`);
        await window.EPISODE_LOOKS?.cutLook(data.look);
        const fresh = await fetch(TG_CFG.vn_scenes_api).then(r => r.json()).catch(() => null);
        if (fresh?.vn_scenes) TG.state.vn_scenes = fresh.vn_scenes;
        this.renderStageOnly();
        this.notify(`“${emotion}” is ready for ${spBeat.speaker_name}.`);
      } catch (e) {
        this.notify(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    promptLookMood(btnEl) {
      const spBeat = this.activeSpriteBeat();
      if (!spBeat || !spBeat.look_id) return;
      const mood = window.prompt(`Which mood should ${spBeat.speaker_name}'s current look get? (one picture, edited from their neutral one)`,
        spBeat.asked_emotion || "thoughtful");
      if (!mood || !mood.trim()) return;
      this.drawLookMood(mood.trim().toLowerCase(), btnEl);
    },

    async loadLookChoices() {
      const sc = this.activeScene();
      if (!sc || this.lookChoicesFor === sc.id) return;
      try {
        const data = await this.apiPost({action: "episode_looks", character_slugs: sc.character_slugs || []});
        this.lookChoices = data.cast || [];
        this.lookChoicesFor = sc.id;
        this.renderStageOnly();
      } catch (e) {this.notify(e.message, true);}
    },

    async changeLook(beatId, key, how, el) {
      const orig = el && el.tagName === "BUTTON" ? el.textContent : "";
      if (el) el.disabled = true;
      if (orig) el.textContent = how.outfit ? "Drawing the new look…" : "Saving…";
      try {
        const data = await this.apiPost({action: "change_look", beat_id: beatId, key, ...how});
        TG.state.vn_scenes = data.vn_scenes;
        if (how.outfit) {
          const look = (data.vn_scenes.looks || {})[key];
          this.notify("New look drawn. Cutting it out in your browser…");
          await window.EPISODE_LOOKS?.cutLook(look);
          const fresh = await fetch(TG_CFG.vn_scenes_api).then((r) => r.json()).catch(() => null);
          if (fresh?.vn_scenes) TG.state.vn_scenes = fresh.vn_scenes;
          this.lookChoicesFor = null;
        }
        this.renderStageOnly();
        this.notify(data.errors?.length ? `Some moods failed: ${data.errors.join("; ")}` : how.keep ? "Kept the current picture." : "Look changed from this passage on.", !!data.errors?.length);
      } catch (e) {
        this.notify(e.message, true);
        this.renderStageOnly();
      } finally {
        if (el && el.isConnected) {el.disabled = false; if (orig) el.textContent = orig;}
      }
    },

    editOutfitThenDraw(beatId, key, outfit, el) {
      const edited = window.prompt("The new outfit, item by item. This is what every picture of the new look will show.", outfit);
      if (!edited || !edited.trim()) return;
      this.changeLook(beatId, key, {outfit: edited.trim()}, el);
    },

    async changeStageSetting(kind, val) {
      const payload = { action: "set_stage", beat_id: this.currentBeat()?.id };
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
        this.notify(e.message, true);
      }
    },

    syncAudioTrack(autoPlay) {
      const sc = this.activeScene();
      const audio = document.getElementById("vnAudioPlayer");
      if (!audio) return;
      const music = this.currentBeat()?.stage?.music || sc?.music;
      const url = music?.url || "";
      if (!url) {
        audio.pause();
        audio.removeAttribute("src");
        audio.removeAttribute("data-src");
        this.musicPlaying = false;
        this.updateMusicBtnLabel();
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
      const music = this.currentBeat()?.stage?.music || this.activeScene()?.music;
      if (!music?.url) { this.notify("This passage has no music selected."); return; }
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
      const music = this.currentBeat()?.stage?.music || sc?.music;
      if (!btn || !music) return;
      btn.disabled = this.busy || !music.url;
      btn.textContent = music.url ? `${this.musicPlaying ? "🔊 Pause" : "🔈 Play"} · ${music.name}` : 'Silence';
    },

    /* ----------------------------------------------------------------------
       Finale Event CG Generation & Scene Completion
       ---------------------------------------------------------------------- */
    async finishScene(btnEl, captureImage = false) {
      const sc = this.activeScene();
      if (!sc) return;
      const previousPhone = TG.state.active_thread?.id;
      if (document.getElementById('vnShortInput')?.value.trim() || String(window.ScreenDrafts?.get('vn:' + sc.id)?.reply || "").trim()) {
        this.notify(sc.interaction_mode === 'choices' ? 'You have an unsent writing draft. Switch to writing mode to send or clear it before finishing.' : 'Your reply has not been sent. Send it before finishing, or clear the reply box to finish without it.', true);
        return;
      }
      const hintEl = document.getElementById("vnIllustrationHint");
      const cgHint = hintEl ? hintEl.value.trim() : "";
      const orig = btnEl ? btnEl.textContent : "";
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = captureImage ? 'Creating illustration…' : 'Saving episode…';
      }
      try {
        const data = await this.apiPost({
          action: "finish_scene",
          cg_hint: cgHint,
          capture_image: captureImage,
        });
        TG.state.vn_scenes = data.vn_scenes;
        if (data.threads) {
          TG.state.threads = data.threads;
        }
        if (data.thread && TG.state.active_thread?.id === previousPhone) {
          TG.state.active_thread = data.thread;
          TG.renderSidebar();
          TG.renderMainChat();
        }
        this.lastFinaleEntry = data.gallery_entry;
        this.stopMusic();
        this.render();
        this.notify(data.gallery_entry.image_error
          ? "Episode saved. The illustration failed: " + data.gallery_entry.image_error
          : "Episode saved and remembered in TeleChat.", !!data.gallery_entry.image_error);
      } catch (e) {
        this.notify(e.message, true);
      } finally {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = orig;
        }
      }
    },

    returnToPhone() {
      const tid = this.activeScene()?.thread_id || this.lastFinaleEntry?.thread_id;
      this.lastFinaleEntry = null;
      this.stopMusic();
      TG.switchApp("messenger");
      if (tid && TG.selectThread) TG.selectThread(tid);
      else TG.renderMainChat();
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
        this.notify(e.message, true);
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
          return `<div style="font-style:italic; color:#94a3b8; padding:6px 0;">${this.attr(b.text)}</div>`;
        }
        const emo = b.emotion ? ` <span style="font-size:11px; color:#f472b6;">(${this.attr(b.emotion)})</span>` : "";
        return `<div style="padding:6px 0;"><strong style="color:#f8fafc;">${this.attr(b.speaker_name || b.speaker)}</strong>${emo}: <span style="color:#e2e8f0;">${this.attr(b.text)}</span></div>`;
      }).join("");

      body.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
          <div>
            <h3 style="margin:0;">🎬 ${this.attr(item.title)}</h3>
            <div style="font-size:12px; color:var(--tg-muted);">📍 ${this.attr(item.location)} · 🎵 ${this.attr((item.music && item.music.name) || "BGM")} · ${this.attr(item.finished_at || "")}</div>
          </div>
          <button type="button" class="tg-fmt-btn" onclick="TG.closeModals()">✕</button>
        </div>
        ${item.cg_url ? `<img src="${this.attr(item.cg_url)}" alt="Finale CG" style="width:100%; max-height:320px; object-fit:cover; border-radius:12px; border:1px solid rgba(255,255,255,0.14);">` : ""}
        <div style="font-size:13px; color:#fbcfe8; background:rgba(219,39,119,0.12); padding:10px 12px; border-radius:10px;">
          <strong>Summary:</strong> ${this.attr(item.summary || "")}
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
        document.getElementById("app-scenes")?.classList.remove("ep-playing");
        this.renderGallery(root);
      } else {
        this.renderStageOnly();
      }
    },

    renderStageOnly() {
      const root = document.getElementById("vnScenesRoot");
      if (!root || this.tab !== "stage") return;
      document.getElementById("app-scenes")?.classList.remove("ep-playing");
      this.seenBeats = this.seenBeats || new Set();

      // 1. If a Finale CG was just generated, display the Finale Event CG Showcase
      if (this.lastFinaleEntry) {
        const e = this.lastFinaleEntry;
        root.innerHTML = `
          <div class="vn-gallery-pane" style="display:flex; align-items:center; justify-content:center;">
            <div style="max-width:760px; width:100%; background:rgba(15,23,42,0.92); border:1.5px solid rgba(236,72,153,0.45); border-radius:20px; padding:22px; box-shadow:0 24px 60px rgba(0,0,0,0.75); display:flex; flex-direction:column; gap:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                  <span style="font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; color:#f472b6;">Episode saved</span>
                  <h2 style="margin:3px 0 0; font-size:21px;">${this.attr(e.title)}</h2>
                </div>
                <span style="font-size:12px; color:#94a3b8;">📍 ${this.attr(e.location)}</span>
              </div>
              ${e.cg_url ? `
                <div style="position:relative; border-radius:14px; overflow:hidden; border:1px solid rgba(255,255,255,0.16); background:#090d16;">
                  <img src="${this.attr(e.cg_url)}" alt="Finale Event CG" style="width:100%; max-height:420px; object-fit:contain; display:block;">
                </div>
              ` : ""}
              ${e.quote ? `<div style="font-size:15px; font-style:italic; color:#fbcfe8; text-align:center;">"${this.attr(e.quote)}"</div>` : ""}
              <div style="font-size:13.5px; color:#e2e8f0; background:rgba(30,41,59,0.65); padding:11px 14px; border-radius:12px;">
                ${this.attr(e.summary || "")}
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; padding-top:4px;">
                <button type="button" class="tg-fmt-btn" onclick="VN_SCENES.switchTab('gallery')">Saved episodes</button>
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
      // 2. No episode open: the casting sheet it will start from.
      if (!sc) {
        const t = TG.state.active_thread;
        document.getElementById("app-scenes")?.classList.add("ep-playing");
        window.CASTING.render(root, t);
        this.bindDrafts(root, "launch:" + (t?.id || "none"));
        window.EPISODE_LOOKS?.mount(document.getElementById("vnLooksPanel"), t);
        return;
      }

      // 3. The stage: one frame with the backdrop, the cast standing on its floor and the text box.
      const beats = sc.beats || [];
      const idx = Math.max(0, Math.min(this.beatIndex, Math.max(0, beats.length - 1)));
      const beat = beats[idx] || { speaker: "narrator", speaker_name: "Narrator", kind: "narration", text: "…" };
      if (beat.id) {
        this.savedCursor = {...this.savedCursor, [sc.id]: beat.id};
        try {localStorage.setItem("vn-cursor-" + sc.id, beat.id);} catch (_) {}
      }
      const isLastBeat = idx >= beats.length - 1;
      const visual = beat.stage || sc;
      const bgUrl = (visual.background && visual.background.url) || "";
      const tracks = (TG.state.vn_scenes && TG.state.vn_scenes.music_tracks) || [];
      const bgs = (TG.state.vn_scenes && TG.state.vn_scenes.backgrounds) || [];
      const musicOpts = [{id: "none", name: "Silence"}, ...tracks].map((t) =>
        `<option value="${this.attr(t.id)}" ${visual.music && visual.music.id === t.id ? "selected" : ""}>${this.attr(t.name)}</option>`).join("");
      const bgOpts = [{id: "none", name: "No backdrop"}, ...bgs].map((b) =>
        `<option value="${this.attr(b.id)}" ${visual.background && visual.background.id === b.id ? "selected" : ""}>${this.attr(b.name)}</option>`).join("");

      const blockFirst = beats.find((b) => (b.block_id || b.id) === (beat.block_id || beat.id)) || beat;
      const cast = this.castOnStage(sc, beat);
      const spBeat = this.activeSpriteBeat();
      const isDirection = beat.kind === "direction";
      const isNarrator = beat.kind === "narration" || beat.speaker === "narrator";
      const handoff = sc.handoff || "user_turn";
      const choices = sc.interaction_mode === "write" ? [] : Array.isArray(sc.choices) ? sc.choices : [];
      const fresh = !this.seenBeats.has(beat.id) && !this.cutNext;
      this.cutNext = false;
      if (beat.id) this.seenBeats.add(beat.id);

      const outfitNotes = (blockFirst.outfit_change || []).map((c) => {
        const worn = (TG.state.vn_scenes?.looks || {})[c.slug];
        const count = worn ? Object.keys(worn.moods || {}).length : 0;
        return `<div class="ep-note" role="status">
            <strong>${this.attr(c.name)}'s clothes change</strong>
            <p>${this.attr(c.outfit)}</p>
            <div class="ep-note-actions">
              ${worn ? `<button type="button" class="ep-btn ep-btn-primary" onclick="VN_SCENES.changeLook('${this.attr(blockFirst.id)}', '${this.attr(c.slug)}', {outfit: ${this.attr(JSON.stringify(c.outfit))}}, this)">Draw the new look · ${count} pictures</button>
              <button type="button" class="ep-btn" onclick="VN_SCENES.editOutfitThenDraw('${this.attr(blockFirst.id)}', '${this.attr(c.slug)}', ${this.attr(JSON.stringify(c.outfit))}, this)">Edit the outfit first</button>` : ""}
              <button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.changeLook('${this.attr(blockFirst.id)}', '${this.attr(c.slug)}', {keep: true}, this)">Keep the picture</button>
            </div>
          </div>`;
      }).join("");
      const moodChip = spBeat && spBeat.look_id && spBeat.asked_emotion && spBeat.asked_emotion !== spBeat.emotion
        ? `<button type="button" class="ep-chip" onclick="VN_SCENES.drawLookMood(null, this)">Showing “${this.attr(spBeat.emotion)}” for “${this.attr(spBeat.asked_emotion)}” · draw it, 1 picture</button>` : "";
      const lookPickers = (this.lookChoices || []).filter((m) => m.looks.length && (m.key !== "user" || sc.authoring_mode === "director")).map((m) => {
        const wornId = ((beat.stage || {}).looks || {})[m.key];
        return `<label>${this.attr(m.name)}<select class="tg-select" onchange="VN_SCENES.changeLook('${this.attr(blockFirst.id)}', '${this.attr(m.key)}', {look_id: Number(this.value)}, this)">
            ${wornId ? "" : `<option value="" selected>No look</option>`}
            ${m.looks.map((l) => `<option value="${l.id}" ${l.id === wornId ? "selected" : ""}>${this.attr(l.name)}</option>`).join("")}
          </select></label>`;
      }).join("");

      const name = isDirection ? "Direction" : isNarrator ? "" : (beat.speaker_name || beat.speaker);
      const turnEnd = isLastBeat ? `
        ${choices.length ? `<div class="ep-choices" role="group" aria-label="Choices">${choices.map((c, i) =>
          `<button type="button" class="ep-choice" data-choice-index="${i}">${this.attr(c)}</button>`).join("")}</div>` : ""}
        <div class="ep-well">
          ${sc.interaction_mode !== "choices" ? `
            <textarea class="ep-input" id="vnShortInput" rows="1" data-screen-field="reply"
              placeholder="${sc.authoring_mode === "director" ? "Direct the cast…" : "What you do or say…"}"
              onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault(); VN_SCENES.submitUserBeatInput(this.nextElementSibling);}"></textarea>
            <button type="button" class="ep-btn ep-btn-primary" onclick="VN_SCENES.submitUserBeatInput(this)">${sc.authoring_mode === "director" ? "Direct" : "Send"}</button>` : ""}
          <button type="button" class="ep-btn ${handoff === "auto_continue" ? "ep-btn-primary" : ""}" onclick="VN_SCENES.stepScene('', this)" title="Let the scene go on without you">Continue</button>
          ${!choices.length && sc.interaction_mode !== "write" ? `<button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.suggestChoices()">Suggest options</button>` : ""}
          ${handoff === "climax_ready" ? `<button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.openSheet('finish')">A good place to end</button>` : ""}
        </div>` : "";

      root.innerHTML = `
        <div class="ep-stage ${this.chromeHidden ? "ep-chrome-off" : ""}" id="epStage">
          <div class="ep-frame" id="epFrame">
            <div class="ep-bg" id="epBg"></div>
            <div class="ep-cast" aria-hidden="true">
              ${cast.map((f, i) => `<img class="ep-figure ${f.speaking ? "is-speaking" : cast.some((o) => o.speaking) ? "is-listening" : ""}" src="${this.attr(f.url)}" alt=""
                  style="--x:${this.castX(i, cast.length)}%; --z:${f.speaking ? 3 : 1}" data-name="${this.attr(f.name)}">`).join("")}
            </div>
            <div class="ep-top">
              <span class="ep-where" title="${this.attr(visual.location || sc.title || "Episode")}">${this.attr(visual.location || sc.title || "Episode")}</span>
              <div class="ep-icons">
                ${this.watchChip(sc)}
                <button type="button" class="ep-icon" onclick="VN_SCENES.toggleMusic()" aria-label="${this.musicPlaying ? "Pause music" : "Play music"}" title="${this.attr(visual.music?.name || "Silence")}">${this.icon(this.musicPlaying ? "music" : "mute")}</button>
                <button type="button" class="ep-icon" onclick="VN_SCENES.openLog()" aria-label="Backlog" title="Backlog">${this.icon("log")}</button>
                <button type="button" class="ep-icon ${this.autoPlay ? "is-on" : ""}" onclick="VN_SCENES.toggleAuto()" aria-label="Auto" title="Auto">${this.icon("auto")}</button>
                <button type="button" class="ep-icon" onclick="VN_SCENES.toggleChrome()" aria-label="Hide the interface (H)" title="Hide (H)">${this.icon("hide")}</button>
                <button type="button" class="ep-icon" onclick="VN_SCENES.openSheet()" aria-label="Menu" title="Menu">${this.icon("menu")}</button>
              </div>
            </div>
            <div class="ep-asides">${this.slipNotes(sc, blockFirst)}${outfitNotes}${moodChip}</div>
            <div class="ep-dock">
              <div class="ep-box ${isNarrator ? "is-narration" : ""} ${isDirection ? "is-direction" : ""}">
                ${name ? `<div class="ep-name">${this.attr(name)}</div>` : ""}
                <div class="ep-text" id="epText">${TG.formatText ? TG.formatText(beat.text || "") : this.attr(beat.text || "")}</div>
                <div class="ep-box-foot">
                  <button type="button" class="ep-step" onclick="VN_SCENES.prevBeat()" ${idx <= 0 ? "disabled" : ""} aria-label="Back">${this.icon("back")}</button>
                  <span class="ep-count">${idx + 1} / ${beats.length}</span>
                  ${!isLastBeat ? `<button type="button" class="ep-step" onclick="VN_SCENES.nextBeat()" aria-label="Next">${this.icon("next")}</button>
                    <button type="button" class="ep-step ep-skip" onclick="VN_SCENES.cutNext = true; VN_SCENES.beatIndex = ${beats.length - 1}; VN_SCENES.renderStageOnly();" aria-label="Skip to your turn" title="Skip to your turn">${this.icon("skip")}</button>` : ""}
                </div>
                ${turnEnd}
              </div>
            </div>
          </div>
          <aside class="ep-sheet" id="epSheet" ${this.sheetOpen ? "" : "hidden"} aria-label="Episode menu">
            <div class="ep-sheet-head"><strong>${this.attr(sc.title || "Episode")}</strong>
              <button type="button" class="ep-icon" onclick="VN_SCENES.closeSheet()" aria-label="Close">${this.icon("close")}</button></div>
            <section class="ep-sheet-part" id="epSheetPassage"><h4>This passage</h4>
              ${beat.original_text ? `<details class="vn-original"><summary>Before Bulba's edits</summary><div style="white-space:pre-wrap;">${this.attr(beat.original_text)}</div></details>` : ""}
              ${spBeat && spBeat.look_id ? `<button type="button" class="ep-btn" onclick="VN_SCENES.promptLookMood(this)">Add a mood to ${this.attr(spBeat.speaker_name)}'s look · 1 picture</button>` : ""}
            </section>
            <section class="ep-sheet-part"><h4>Scene</h4>
              <details ontoggle="this.open && VN_SCENES.loadLookChoices()" data-screen-field="visuals_open"><summary>Looks, music and backdrop</summary>
                <div class="vn-editor-content">
                  ${lookPickers ? `<p class="ep-looks-note">Looks change from this passage on.</p>${lookPickers}` : ""}
                  <label>Music<select class="tg-select" onchange="VN_SCENES.changeStageSetting('music', this.value)">${musicOpts}</select></label>
                  <label>Backdrop<select class="tg-select" onchange="VN_SCENES.changeStageSetting('bg', this.value)">${bgOpts}</select></label>
                </div>
              </details>
            </section>
            <section class="ep-sheet-part" id="epSheetEpisode"><h4>Episode</h4>
              <button type="button" class="ep-btn" onclick="VN_SCENES.closeSheet(); VN_SCENES.runWatch(true)">🥔 Check this turn for slips</button>
            </section>
            <section class="ep-sheet-part" id="epSheetFinish"><h4>Finish</h4>
              <button type="button" class="ep-btn" onclick="VN_SCENES.finishScene(this)">Finish and save</button>
              <details class="vn-illustration-options"><summary>Illustration hint (optional)</summary><textarea class="tg-textarea" id="vnIllustrationHint" data-screen-field="illustration_hint" placeholder="What should the illustration show?"></textarea></details>
              <button type="button" class="ep-btn ep-btn-primary" onclick="VN_SCENES.finishScene(this, true)">Finish with an illustration</button>
            </section>
            <section class="ep-sheet-part">
              <button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.closeSheet(); VN_SCENES.switchTab('gallery')">Saved episodes</button>
              <button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.closeSheet(); VN_SCENES.returnToPhone()">Back to the phone</button>
            </section>
          </aside>
          <div class="ep-log" id="epLog" hidden role="dialog" aria-label="Backlog"></div>
        </div>
      `;
      document.getElementById("app-scenes")?.classList.add("ep-playing");
      this.paintBackground(bgUrl);
      root.querySelectorAll(".ep-figure").forEach((img) => img.addEventListener("error", () => img.remove(), {once: true}));
      this.typeText(document.getElementById("epText"), fresh);
      this.bindDrafts(root, "vn:" + sc.id);
      this.syncAudioTrack(this.musicPlaying);
      root.querySelectorAll("[data-choice-index]").forEach((button) => {
        button.addEventListener("click", () => this.stepScene(choices[Number(button.dataset.choiceIndex)], button));
      });
      this.bindStage();
    },

    /* ---------- Bulba's Watch: continuity slips in the latest turn ---------- */

    runWatch(asked = false) {
      if (this.watching) return this.watchPromise;
      this.watchPromise = this.watchTurn(asked).finally(() => {this.watchPromise = null;});
      return this.watchPromise;
    },

    async watchTurn(asked) {
      const sc = this.activeScene();
      if (!sc) return;
      this.watching = true;
      this.renderStageOnly();
      try {
        const resp = await fetch(TG_CFG.vn_scenes_api, {method: "POST",
          headers: {"Content-Type": "application/json", "X-CSRFToken": TG_CFG.csrf || ""},
          body: JSON.stringify({action: "episode_watch", scene_id: sc.id, revision: sc.revision})});
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
        if (this.activeScene()?.id === sc.id) TG.state.vn_scenes = data.vn_scenes;
        const slips = this.activeScene()?.watch?.slips || [];
        if (asked || slips.length) this.notify(slips.length ? `Bulba noticed ${slips.length === 1 ? "a slip" : slips.length + " slips"} in this turn.` : "Bulba checked this turn: nothing contradicts what's established.");
      } catch (e) {
        // A turn written in the meantime makes the check stale; it simply runs again after that turn.
        if (asked || !/changed in another tab/.test(e.message)) this.notify("Bulba couldn't check this turn: " + e.message, true);
      } finally {
        this.watching = false;
        this.renderStageOnly();
      }
    },

    watchChip(sc) {
      if (this.watching) return `<span class="ep-watch is-busy" role="status">🥔 checking…</span>`;
      const slips = sc.watch?.slips || [];
      if (!slips.length) return "";
      return `<button type="button" class="ep-watch" onclick="VN_SCENES.jumpToSlip()" aria-label="Show the slips Bulba found">🥔 ${slips.length} ${slips.length === 1 ? "slip" : "slips"}</button>`;
    },

    jumpToSlip() {
      const sc = this.activeScene(), first = sc?.watch?.slips?.[0];
      if (!first) return;
      this.cutNext = true;
      this.beatIndex = Math.max(0, (sc.beats || []).findIndex((b) => b.id === first.beat_id));
      this.renderStageOnly();
    },

    slipNotes(sc, blockFirst) {
      return (sc.watch?.slips || []).filter((s) => s.beat_id === blockFirst.id).map((s) => `
        <div class="ep-note ep-slip" role="status">
          <strong>🥔 Bulba noticed a slip</strong>
          <p>${this.attr(s.what)}${s.fact ? `<br><span class="ep-slip-fact">Established: ${this.attr(s.fact)}</span>` : ""}</p>
          ${s.fix ? `<details><summary>Bulba's fix</summary><p class="ep-slip-fix">${this.attr(s.fix)}</p></details>` : ""}
          <div class="ep-note-actions">
            ${s.fix ? `<button type="button" class="ep-btn ep-btn-primary" onclick="VN_SCENES.useSlipFix('${this.attr(s.beat_id)}')">Use Bulba's fix</button>` : ""}
            <button type="button" class="ep-btn" onclick="VN_SCENES.regenerateSlip('${this.attr(s.beat_id)}')">Regenerate from here</button>
            <button type="button" class="ep-btn ep-btn-quiet" onclick="VN_SCENES.dismissSlip('${this.attr(s.beat_id)}')">Ignore</button>
          </div>
        </div>`).join("");
    },

    slipOf(beatId) {return (this.activeScene()?.watch?.slips || []).find((s) => s.beat_id === beatId);},

    async useSlipFix(beatId) {
      const slip = this.slipOf(beatId);
      if (slip?.fix) await this.passageChange?.("edit_passage", {beat_id: beatId, text: slip.fix});
    },

    async regenerateSlip(beatId) {
      const slip = this.slipOf(beatId);
      if (!slip) return;
      const ok = await this.passageChange?.("regenerate_passage", {beat_id: beatId,
        direction: `Fix this continuity slip: ${slip.what}${slip.fact ? ` Established: ${slip.fact}` : ""}`});
      if (ok && TG.state.vn_scenes?.watch_on) this.runWatch();
    },

    async dismissSlip(beatId) {
      try {
        const data = await this.apiPost({action: "watch_dismiss", beat_id: beatId});
        TG.state.vn_scenes = data.vn_scenes;
        this.renderStageOnly();
      } catch (e) {this.notify(e.message, true);}
    },

    /* Everyone standing on stage at this passage: their look's picture for the face they show, the one on
       camera in front. Older episodes without per-passage looks show only the one on camera. */
    castOnStage(sc, beat) {
      const stage = beat.stage || {};
      const packs = TG.state.vn_scenes?.look_packs || {};
      const current = TG.state.vn_scenes?.looks || {};
      const camera = (this.activeSpriteBeat() || {}).speaker;
      const talking = beat.kind === "dialogue" && beat.speaker !== "narrator" ? camera : null;
      const keys = [...(sc.character_slugs || []), ...(sc.authoring_mode === "director" ? ["user"] : [])];
      const out = [];
      keys.forEach((key) => {
        const lookId = (stage.looks || {})[key];
        const pack = lookId ? packs[String(lookId)] || Object.values(current).find((l) => l.id === lookId) : null;
        let url = "";
        if (pack) {
          const mood = (stage.faces || {})[key] || "neutral";
          url = (pack.moods[mood] || pack.moods.neutral || {}).url || "";
        }
        if (key === camera && beat.character_slug === key && beat.sprite_url) url = beat.sprite_url;
        if (!url && key === camera) url = (this.activeSpriteBeat() || {}).sprite_url || "";
        if (!url) return;
        const person = (TG.state.characters || []).find((c) => c.slug === key);
        out.push({key, url, speaking: key === talking, name: key === "user" ? (sc.user_participant?.name || "You") : (person?.display_name || person?.name || key)});
      });
      return out;
    },

    castX(i, n) {
      if (n <= 1) return 50;
      const span = n === 2 ? 40 : Math.min(76, 24 * (n - 1));
      return 50 - span / 2 + (span / (n - 1)) * i;
    },

    icon(name) {
      const paths = {
        music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
        mute: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><path d="M3 3l18 18"/>',
        log: '<path d="M4 6h16M4 12h16M4 18h10"/>',
        auto: '<path d="M5 4l10 8-10 8z"/><path d="M19 5v14"/>',
        hide: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><path d="M3 3l18 18"/>',
        menu: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
        close: '<path d="M6 6l12 12M18 6L6 18"/>',
        back: '<path d="M15 18l-6-6 6-6"/>',
        next: '<path d="M9 18l6-6-6-6"/>',
        skip: '<path d="M5 18l6-6-6-6M13 18l6-6-6-6"/>',
      };
      return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ""}</svg>`;
    },

    /* The backdrop crossfades when it changes and cuts when it doesn't. */
    paintBackground(url) {
      const bg = document.getElementById("epBg");
      if (!bg) return;
      const before = this.lastBgUrl;
      bg.style.backgroundImage = url ? `url(${JSON.stringify(url)})` : "none";
      if (before !== undefined && before !== url) {
        bg.classList.remove("ep-bg-in"); void bg.offsetWidth; bg.classList.add("ep-bg-in");
      }
      this.lastBgUrl = url;
    },

    /* New text arrives word by word; a passage read before, or a rewind, is shown whole. */
    typeText(el, fresh) {
      clearTimeout(this.autoTimer);
      if (!el) return;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      this.typing = false;
      if (!fresh || reduce) {this.afterTyped(); return;}
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      let n = 0;
      nodes.forEach((node) => {
        const frag = document.createDocumentFragment();
        node.textContent.split(/(\s+)/).forEach((part) => {
          if (!part) return;
          if (/^\s+$/.test(part)) {frag.append(part); return;}
          const span = document.createElement("span");
          span.className = "ep-word"; span.textContent = part; span.style.animationDelay = `${n++ * 38}ms`;
          frag.append(span);
        });
        node.replaceWith(frag);
      });
      el.classList.add("ep-typing");
      this.typing = true;
      this.typeTimer = setTimeout(() => this.finishTyping(), n * 38 + 260);
    },

    finishTyping() {
      clearTimeout(this.typeTimer);
      const el = document.getElementById("epText");
      el?.classList.remove("ep-typing");
      el?.querySelectorAll(".ep-word").forEach((w) => {w.style.animation = "none"; w.style.opacity = "1";});
      this.typing = false;
      this.afterTyped();
    },

    afterTyped() {
      clearTimeout(this.autoTimer);
      const sc = this.activeScene();
      if (!this.autoPlay || !sc || this.beatIndex >= (sc.beats || []).length - 1) return;
      const words = (document.getElementById("epText")?.textContent || "").split(/\s+/).length;
      this.autoTimer = setTimeout(() => this.nextBeat(), 1400 + words * 160);
    },

    toggleAuto() {
      this.autoPlay = !this.autoPlay;
      this.renderStageOnly();
    },

    toggleChrome() {
      this.chromeHidden = !this.chromeHidden;
      document.getElementById("epStage")?.classList.toggle("ep-chrome-off", this.chromeHidden);
    },

    openSheet(part) {
      this.sheetOpen = true;
      const sheet = document.getElementById("epSheet");
      if (sheet) sheet.hidden = false;
      if (part === "finish") document.getElementById("epSheetFinish")?.scrollIntoView({block: "start"});
    },

    closeSheet() {
      this.sheetOpen = false;
      const sheet = document.getElementById("epSheet");
      if (sheet) sheet.hidden = true;
    },

    openLog() {
      const sc = this.activeScene(), log = document.getElementById("epLog");
      if (!sc || !log) return;
      const upto = (sc.beats || []).slice(0, this.beatIndex + 1);
      log.innerHTML = `<div class="ep-log-head"><strong>Backlog</strong>
          <button type="button" class="ep-icon" onclick="document.getElementById('epLog').hidden = true" aria-label="Close">${this.icon("close")}</button></div>
        <ol class="ep-log-list">${upto.map((b, i) => `<li><button type="button" data-log-index="${i}">
          ${b.kind === "narration" || b.speaker === "narrator" ? "" : `<strong>${this.attr(b.speaker_name || b.speaker)}</strong>`}
          <span>${this.attr(b.text)}</span></button></li>`).join("")}</ol>`;
      log.hidden = false;
      log.querySelectorAll("[data-log-index]").forEach((btn) => btn.addEventListener("click", () => {
        this.cutNext = true; this.beatIndex = Number(btn.dataset.logIndex); this.renderStageOnly();
      }));
      log.querySelector(".ep-log-list li:last-child")?.scrollIntoView({block: "end"});
    },

    /* A click or tap on the bare stage finishes the words first, then turns the page. Keys: Space, Enter and
       the right arrow go on; the left arrow steps back; H hides the interface; Escape closes what's open. */
    bindStage() {
      const frame = document.getElementById("epFrame");
      const box = frame?.querySelector(".ep-box"), picks = frame?.querySelector(".ep-choices");
      if (frame && box) frame.style.setProperty("--ep-box-h", `${box.offsetHeight + 14 + (picks ? picks.offsetHeight + 16 : 0)}px`);
      frame?.addEventListener("click", (event) => {
        if (event.target.closest("button, a, input, textarea, select, label, details, .ep-choices, .ep-well, .ep-note")) return;
        if (this.chromeHidden) {this.toggleChrome(); return;}
        this.advance();
      });
      if (this.keysBound) return;
      this.keysBound = true;
      document.addEventListener("keydown", (event) => {
        if (!document.getElementById("app-scenes")?.classList.contains("active") || this.tab !== "stage" || !this.activeScene()) return;
        if (event.target.closest?.("input, textarea, select, [contenteditable]") || event.ctrlKey || event.metaKey || event.altKey) return;
        const log = document.getElementById("epLog");
        if (event.key === "Escape") {if (log) log.hidden = true; this.closeSheet(); return;}
        if (this.chromeHidden && event.key.length) {this.toggleChrome(); event.preventDefault(); return;}
        if (event.key === "h" || event.key === "H") {this.toggleChrome(); event.preventDefault();}
        else if (event.key === " " || event.key === "Enter" || event.key === "ArrowRight") {
          if (event.target.closest?.("button") && event.key !== "ArrowRight") return;
          this.advance(); event.preventDefault();
        } else if (event.key === "ArrowLeft") {this.cutNext = true; this.prevBeat(); event.preventDefault();}
      });
    },

    advance() {
      if (this.typing) {this.finishTyping(); return;}
      const sc = this.activeScene();
      if (sc && this.beatIndex < (sc.beats || []).length - 1) this.nextBeat();
      else document.getElementById("vnShortInput")?.focus();
    },


    renderGallery(root) {
      const gallery = (TG.state.vn_scenes && TG.state.vn_scenes.gallery) || [];
      if (!gallery.length) {
        root.innerHTML = `
          <div class="vn-gallery-pane">
            <div style="max-width:560px; margin:40px auto; text-align:center; padding:28px; background:rgba(15,23,42,0.85); border:1px solid rgba(255,255,255,0.1); border-radius:18px;">
              <div style="font-size:40px; margin-bottom:8px;">🖼️</div>
              <h3 style="margin:0 0 6px;">No completed episodes yet</h3>
              <p style="margin:0 0 16px; font-size:13px; color:#94a3b8;">
                Launch a scene from TeleChat and finish it to save a replayable transcript here. You can optionally generate an illustration when finishing.
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
            <img class="vn-cg-thumb" src="${this.attr(item.cg_url)}" alt="${this.attr(item.title)}" onclick="VN_SCENES.viewGalleryTranscript('${this.attr(item.id)}')">
          ` : `
            <div class="vn-cg-thumb" style="display:flex; align-items:center; justify-content:center; font-size:32px;" onclick="VN_SCENES.viewGalleryTranscript('${this.attr(item.id)}')">🎬</div>
          `}
          <div class="vn-cg-body">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
              <strong style="font-size:14.5px; color:#f8fafc;">${this.attr(item.title)}</strong>
              <span style="font-size:11px; color:#94a3b8; white-space:nowrap;">${this.attr(item.finished_at || "")}</span>
            </div>
            <div style="font-size:11.5px; color:#f472b6;">
              📍 ${this.attr(item.location || "Meet-Up")} · 🎵 ${this.attr((item.music && item.music.name) || "BGM")}
            </div>
            ${item.quote ? `<div style="font-size:12px; font-style:italic; color:#fbcfe8;">"${this.attr(item.quote)}"</div>` : ""}
            <p style="margin:0; font-size:12.5px; color:#cbd5e1; line-height:1.45;">${this.attr(item.summary || "")}</p>
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:6px;">
              <button type="button" class="tg-fmt-btn" onclick="VN_SCENES.viewGalleryTranscript('${this.attr(item.id)}')">📖 Read episode (${(item.beats || []).length} pages)</button>
              <button type="button" class="tg-fmt-btn" style="color:#f87171;" onclick="VN_SCENES.deleteGalleryItem('${this.attr(item.id)}')" title="Remove from gallery">🗑</button>
            </div>
          </div>
        </article>
      `).join("");

      root.innerHTML = `
        <div class="vn-gallery-pane">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <h2 style="margin:0 0 3px; font-size:19px;">🖼️ Visual Novel Event CG & Scene Gallery</h2>
              <p style="margin:0; font-size:12.5px; color:#94a3b8;">Your completed episodes, illustrations and full transcripts.</p>
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
