/* Digital Screen Hub & Telegram Messenger Frontend (Phase F) */
(function () {
  var rawInit = document.getElementById("tgInitialData");
  var STATE = rawInit ? JSON.parse(rawInit.textContent) : {};
  STATE.threads = STATE.threads || [];
  STATE.characters = STATE.characters || [];
  STATE.user_profile = STATE.user_profile || {};
  STATE.wallpapers = STATE.wallpapers || {};
  STATE.reactions = STATE.reactions || ["❤️", "🔥", "👍", "😂", "😮", "😢", "👀", "🎉"];
  STATE.built_in_stickers = STATE.built_in_stickers || [];

  var replyToMsg = null;
  var currentDrawerTab = "char";
  var selectedDrawerCharSlug = "";
  window.selectedDrawerCharSlugSet = function (slug) { selectedDrawerCharSlug = slug; };  // (the card's Edit button)
  var activeAudio = null;
  var activeAudioMsgId = null;

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function apiPost(payload) {
    return fetch(window.TG_CFG.api, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.TG_CFG.csrf,
      },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok && !d.user_message) throw new Error(d.error || "Request failed");
        return d;
      });
    });
  }

  function updateClock() {
    var el = document.getElementById("dockClock");
    if (!el) return;
    var now = new Date();
    var hh = String(now.getHours()).padStart(2, "0");
    var mm = String(now.getMinutes()).padStart(2, "0");
    var day = now.toLocaleDateString("en-US", { weekday: "short" });
    el.innerHTML = "<strong>" + hh + ":" + mm + "</strong><br>" + esc(day);
  }
  setInterval(updateClock, 15000);
  updateClock();

  function isOnlyEmoji(str) {
    var s = (str || "").trim();
    if (!s || s.length > 10) return false;
    var stripped = s.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}\s]/gu, "");
    return stripped.length === 0;
  }

  // 📄 A text file as a document: markdown tables, headings, lists; the rest as chat formatting
  function renderDoc(text) {
    var lines = String(text || "").replace(/\r/g, "").split("\n"), out = [], i = 0;
    var cells = function (row) { return row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (c) { return c.trim(); }); };
    while (i < lines.length) {
      var ln = lines[i];
      if (/^\s*\|.*\|\s*$/.test(ln) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        var head = cells(ln), rows = [];
        i += 2;
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
        out.push('<table><thead><tr>' + head.map(function (h) { return "<th>" + formatMessageHtml(h) + "</th>"; }).join("") + "</tr></thead><tbody>" +
          rows.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + formatMessageHtml(c) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table>");
        continue;
      }
      var h = ln.match(/^(#{1,3})\s+(.*)$/);
      if (h) out.push("<h" + (h[1].length + 2) + ">" + formatMessageHtml(h[2]) + "</h" + (h[1].length + 2) + ">");
      else if (/^\s*[-*]\s+/.test(ln)) out.push('<div class="tg-doc-li">• ' + formatMessageHtml(ln.replace(/^\s*[-*]\s+/, "")) + "</div>");
      else if (!ln.trim()) out.push('<div class="tg-doc-gap"></div>');
      else out.push("<p>" + formatMessageHtml(ln) + "</p>");
      i++;
    }
    return out.join("");
  }

  function formatMessageHtml(raw) {
    if (!raw) return "";
    var s = esc(raw);
    // Blockquotes (> line)
    s = s.replace(/(^|\n)&gt;\s?([^\n]+)/g, '$1<blockquote>$2</blockquote>');
    // Monospace `code`
    s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    // Telegram Spoiler ||text||
    s = s.replace(/\|\|([^|\n]+)\|\|/g, '<span class="tg-spoiler" onclick="this.classList.toggle(\'revealed\')" title="Tap to reveal spoiler">$1</span>');
    // Bold **text**
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    // Strikethrough ~~text~~
    s = s.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    // Underline __text__
    s = s.replace(/__([^_\n]+)__/g, "<u>$1</u>");
    // Italic *text*
    s = s.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
    return s;
  }

  function avatarHtml(url, name, extraClass) {
    var initial = ((name || "?").trim()[0] || "?").toUpperCase();
    if (url) {
      return '<div class="' + (extraClass || "tg-avatar") + '"><img src="' + esc(url) + '" alt=""></div>';
    }
    return '<div class="' + (extraClass || "tg-avatar") + '">' + esc(initial) + "</div>";
  }

  // ✨ Statuses seen (this browser), for the rings
  function storySeen(id) { try { return (JSON.parse(localStorage.getItem("na-tg-seen-stories") || "[]")).indexOf(id) !== -1; } catch (e) { return false; } }
  function markStorySeen(id) {
    try { var a = JSON.parse(localStorage.getItem("na-tg-seen-stories") || "[]"); if (a.indexOf(id) === -1) { a.push(id); localStorage.setItem("na-tg-seen-stories", JSON.stringify(a.slice(-400))); } } catch (e) { /* no memory here */ }
  }

  function renderStoriesStrip() {
    var strip = document.getElementById("tgStoriesStrip");
    if (!strip) return;
    var u = STATE.user_profile || {};
    var uStories = u.stories || [];
    var html = [];
    html.push(
      '<div class="tg-story-item" onclick="TG.openStoryModal(\'user\')" title="Your Status / Story">' +
        '<div class="tg-story-ring ' + (uStories.length ? "" : "empty") + '">' +
          (u.avatar_url ? '<img src="' + esc(u.avatar_url) + '" alt="">' : '<div class="tg-avatar-fallback" style="display:flex;align-items:center;justify-content:center;background:#4b2a86;color:#fff;font-weight:700;">+</div>') +
          '<span class="tg-story-emoji-badge">' + esc(u.status_emoji || "✨") + "</span>" +
        "</div>" +
        '<span class="tg-story-label">My Status</span>' +
      "</div>"
    );

    (STATE.characters || []).forEach(function (c) {
      var hasStories = (c.stories || []).length > 0, unseen = (c.stories || []).some(function (s) { return !storySeen(s.id); });
      html.push(
        '<div class="tg-story-item" onclick="' + (hasStories ? "TG.viewStories(\'" + esc(c.slug) + "\')" : "") + '" title="' + esc(c.display_name) + ': ' + esc(c.bio || "No status yet") + '">' +
          '<div class="tg-story-ring ' + (hasStories ? (unseen ? "unseen" : "seen") : "empty") + '">' +
            (c.avatar_url
              ? '<img src="' + esc(c.avatar_url) + '" alt="">'
              : '<div class="tg-avatar-fallback" style="display:flex;align-items:center;justify-content:center;background:#2a2f4a;color:#fff;font-weight:700;">' + esc((c.display_name || "?")[0]) + "</div>") +
            '<span class="tg-story-emoji-badge">' + esc(c.status_emoji || "💬") + "</span>" +
          "</div>" +
          '<span class="tg-story-label">' + esc(c.display_name) + "</span>" +
        "</div>"
      );
    });
    strip.innerHTML = html.join("");
  }

  function renderSidebar() {
    renderStoriesStrip();
    var listEl = document.getElementById("tgThreadList");
    if (!listEl) return;
    var q = ((document.getElementById("tgSearchInput") || {}).value || "").trim().toLowerCase();
    var activeId = STATE.active_thread ? STATE.active_thread.id : null;
    var totalUnread = 0;

    var items = (STATE.threads || []).filter(function (t) {
      totalUnread += t.unread || 0;
      if (!q) return true;
      return (
        (t.title || "").toLowerCase().indexOf(q) !== -1 ||
        (t.handle || "").toLowerCase().indexOf(q) !== -1 ||
        (t.preview || "").toLowerCase().indexOf(q) !== -1
      );
    });

    var badge = document.getElementById("dockUnreadBadge");
    if (badge) {
      badge.style.display = totalUnread > 0 ? "inline-flex" : "none";
      badge.textContent = totalUnread;
    }

    if (!items.length) {
      listEl.innerHTML =
        '<div style="padding:24px 16px;text-align:center;color:var(--tg-muted);font-size:13px;">' +
        "No chats yet. Press <b>+ New / Group</b> above to start texting any of your characters!" +
        "</div>";
      return;
    }

    listEl.innerHTML = items
      .map(function (t) {
        var isAct = t.id === activeId;
        var modeBadge = "";
        if (t.is_group) {
          modeBadge = '<span class="tg-mode-pill group">Group</span>';
        } else if (t.mode === "modern_au") {
          modeBadge = '<span class="tg-mode-pill">Modern AU</span>';
        }
        return (
          '<div class="tg-thread-item ' + (isAct ? "active" : "") + '" onclick="TG.selectThread(' + t.id + ')">' +
            '<div class="tg-avatar">' +
              (t.avatar_url ? '<img src="' + esc(t.avatar_url) + '" alt="">' : esc(((t.title || "?")[0] || "?").toUpperCase())) +
              (t.is_group ? "" : '<span class="tg-online-dot ' + esc((t.presence || {}).state || "online") + '"></span>') +
            "</div>" +
            '<div class="tg-thread-meta">' +
              '<div class="tg-thread-row1">' +
                '<div class="tg-thread-name">' +
                  (t.pinned ? "📌 " : "") + (t.branch ? "⑂ " : "") +
                  esc(t.title) + " " + modeBadge +
                  (!t.is_group && t.chat_name && t.chat_name !== t.title ? '<small class="tg-chat-name">' + esc(t.chat_name) + "</small>" : "") +
                "</div>" +
                '<span class="tg-thread-time">' + esc(t.last_time || "") + "</span>" +
              "</div>" +
              '<div class="tg-thread-row2">' +
                '<div class="tg-thread-preview">' + esc(t.preview || "No messages yet") + "</div>" +
                (t.unread > 0 ? '<span class="tg-unread-pill">' + t.unread + "</span>" : "") +
              "</div>" +
            "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  var THEMES = { "": "Purple (the app's)", classic: "Telegram classic", forest: "Forest", rose: "Rose", sepia: "Sepia evening" };
  function applyWallpaper(thread) {
    var vp = document.getElementById("tgMessagesViewport");
    if (!vp || !thread) return;
    var main = document.getElementById("tgMain");  // 🎨 the chat's theme: bubbles, accent, background
    if (main) { Object.keys(THEMES).forEach(function (k) { if (k) main.classList.remove("tg-theme-" + k); }); if (thread.theme) main.classList.add("tg-theme-" + thread.theme); }
    vp.classList.toggle("tg-themed", !!thread.theme && (!thread.bg || thread.bg === "tg-night") && !thread.custom_bg_url);
    vp.classList.remove("light-wp");
    if (thread.custom_bg_url) {
      vp.style.backgroundImage = 'linear-gradient(rgba(10,15,26,0.55), rgba(10,15,26,0.55)), url("' + esc(thread.custom_bg_url) + '")';
      return;
    }
    var wpKey = thread.bg || (STATE.user_profile && STATE.user_profile.default_bg) || "tg-night";
    var wp = STATE.wallpapers[wpKey] || STATE.wallpapers["tg-night"] || {};
    vp.style.backgroundImage = wp.bg || "";
    if (wp.light) vp.classList.add("light-wp");
  }

  function memberMap(thread) {
    var map = {};
    ((thread && thread.members) || []).forEach(function (m) {
      map[m.slug] = m;
    });
    return map;
  }

  function renderWaveformBars(seedStr) {
    var bars = [];
    var s = seedStr || "voice";
    for (var i = 0; i < 24; i++) {
      var code = s.charCodeAt(i % s.length) || 70;
      var h = 25 + ((code * (i + 3)) % 70);
      bars.push('<span class="tg-wave-bar" style="height:' + h + '%"></span>');
    }
    return bars.join("");
  }

  function renderActiveThread() {
    var t = STATE.active_thread;
    var hdrTitle = document.getElementById("hdrTitle");
    var hdrSub = document.getElementById("hdrSub");
    var hdrAvatar = document.getElementById("hdrAvatar");
    var vp = document.getElementById("tgMessagesViewport");
    var pinBar = document.getElementById("tgPinnedBar");

    if (!t) {
      if (hdrTitle) hdrTitle.textContent = "No chat open";
      if (hdrSub) hdrSub.textContent = "Click + New / Group to start texting";
      if (vp) vp.innerHTML = '<div class="tg-sys-pill">Pick a character or create a group chat from the left sidebar.</div>';
      return;
    }

    applyWallpaper(t);
    var mMap = memberMap(t);

    if (hdrAvatar) {
      hdrAvatar.innerHTML = t.avatar_url
        ? '<img src="' + esc(t.avatar_url) + '" alt="">'
        : esc(((t.title || "?")[0] || "?").toUpperCase());
    }
    if (hdrTitle) {
      var badge = t.is_group
        ? '<span class="tg-mode-pill group">Group · ' + (t.members ? t.members.length : 1) + "</span>"
        : t.mode === "modern_au"
        ? '<span class="tg-mode-pill">✨ Modern AU</span>'
        : '<span class="tg-mode-pill">🏰 Canon</span>';
      hdrTitle.innerHTML = esc(t.title) + " " + badge;
    }
    if (hdrSub) {
      var rt = t.real_time || {};
      var subParts = [];
      if (!t.is_group && t.presence) subParts.push((t.presence.state === "online" ? "🟢 " : t.presence.state === "away" ? "🟡 " : t.presence.state === "busy" ? "🔴 " : "") + t.presence.label);
      if (t.handle) subParts.push(t.handle);
      if (t.subtitle) subParts.push(t.subtitle);
      if (rt.elapsed_text) subParts.push("Last text: " + rt.elapsed_text);
      hdrSub.textContent = subParts.join(" · ") || "online";
    }
    var am = (t && t.active_model) || STATE.active_model;
    var mdlLbl = document.getElementById("hdrModelLabel");
    var mdlBadge = document.getElementById("hdrModelBadge");
    if (mdlLbl && am) {
      mdlLbl.textContent = am.label || "Auto Rules";
      if (mdlBadge && am.rules) {
        mdlBadge.title = "Active Model Rules (" + (am.label || "") + "):\n" + am.rules;
      }
    }

    // Pinned message bar
    if (pinBar) {
      var pinnedMsg = t.pinned_id
        ? (t.messages || []).find(function (m) { return m.id === t.pinned_id; })
        : null;
      if (pinnedMsg) {
        pinBar.style.display = "flex";
        document.getElementById("tgPinnedText").textContent =
          (pinnedMsg.sender_name ? pinnedMsg.sender_name + ": " : "") + (pinnedMsg.text || "Pinned media");
      } else {
        pinBar.style.display = "none";
      }
    }

    // Render messages
    var msgs = t.messages || [];
    var out = [];
    var rtClock = (t.real_time && t.real_time.clock) ? t.real_time.clock : "Today";
    out.push('<div class="tg-sys-pill">🕒 ' + esc(rtClock) + "</div>");

    var setupCard = bulbaSetupCard(t);
    var groupCard = setupCard ? "" : groupScenarioCard(t);
    if (setupCard) out.push(setupCard);
    else if (groupCard) out.push(groupCard);
    else if (!t.started && !startSkipped[t.id]) out.push(startCard(t));

    if (!msgs.length) {
      out.push(
        '<div class="tg-sys-pill">No messages yet. Say hi, send a sticker, or click <b>🎲 Let them text</b> below!</div>'
      );
    }

    var lastUserId = null;
    msgs.forEach(function (m) { if (m.role === "user") lastUserId = m.id; });
    msgs.forEach(function (m) {
      if (m.role === "system") {
        out.push('<div class="tg-sys-pill" id="msg-' + esc(m.id) + '">' + esc(m.text) + "</div>");
        return;
      }
      var isUser = m.role === "user";
      var mem = mMap[m.sender_slug] || (t.members && t.members[0]) || {};
      var avUrl = isUser ? (STATE.user_profile.avatar_url || "") : (mem.avatar_url || t.avatar_url || "");
      var senderName = m.sender_name || (isUser ? STATE.user_profile.display_name : mem.display_name || t.title);
      var senderColor = isUser ? "#a78bfa" : (mem.color || "#f0abfc");

      var inner = [];
      if (!isUser && (t.is_group || (t.members && t.members.length > 1))) {
        inner.push(
          '<div class="tg-bubble-sender" style="color:' + esc(senderColor) + '" onclick="TG.openCharProfile(\'' + esc(m.sender_slug || "") + '\')">' +
            esc(senderName) + " <span style='opacity:0.65;font-weight:400;font-size:11px;'>" + esc(mem.handle || "") + "</span>" +
          "</div>"
        );
      }

      if (m.reply_to_text) {
        inner.push(
          '<div class="tg-reply-quote" onclick="TG.scrollToMsg(\'' + esc(m.reply_to_id || "") + '\')">' +
            '<div class="tg-reply-quote-name">' + esc(m.reply_to_sender || "Reply") + "</div>" +
            '<div class="tg-reply-quote-text">' + esc(m.reply_to_text) + "</div>" +
          "</div>"
        );
      }

      // Sticker
      if (m.sticker) {
        var st = m.sticker;
        if (st.url) {
          inner.push(
            '<div class="tg-sticker-card">' +
              (st.video || /\.webm$/i.test(st.url) ? '<video src="' + esc(st.url) + '" autoplay loop muted playsinline title="' + esc(st.name || "") + '"></video>'
                : '<img src="' + esc(st.url) + '" alt="' + esc(st.name || "Sticker") + '" title="' + esc(st.name || "") + '">') +
            "</div>"
          );
        } else {
          inner.push(
            '<div class="tg-sticker-emoji-art">' +
              '<span class="big">' + esc(st.emoji || "🥔") + "</span>" +
              '<span class="lbl">' + esc(st.label || st.name || "Sticker") + "</span>" +
            "</div>"
          );
        }
      }

      // Photo (Nano Banana or User Upload)
      if (m.photo) {
        var ph = m.photo;
        if (ph.url) {
          inner.push(
            '<div class="tg-photo-card">' +
              '<img src="' + esc(ph.url) + '" alt="Photo" onclick="TG.viewImage(this.src)">' +
              (ph.caption ? '<div class="tg-bubble-text">' + formatMessageHtml(ph.caption) + "</div>" : "") +
            "</div>"
          );
        } else {
          inner.push(
            '<div class="tg-photo-placeholder">' +
              '<div style="font-size:12px;font-weight:700;color:#fbbf24;">📸 ' +
                (ph.kind === "tease" ? "Tease Snapshot" : "Camera Snapshot") +
              "</div>" +
              '<div class="tg-photo-prompt-text">"' + esc(ph.prompt || "Candid photo") + '"</div>' +
              '<button type="button" class="tg-render-photo-btn" onclick="TG.renderBubblePhoto(\'' + esc(m.id) + '\', \'' + esc(ph.kind || "casual") + '\', this)">🍌 Show the photo</button>' +
            "</div>"
          );
        }
      }

      // File Attachment
      if (m.file) {
        var fl = m.file;
        inner.push(
          '<div class="tg-file-card" onclick="TG.openReadFileModal(\'' + esc(m.id) + '\')">' +
            '<div class="tg-file-icon">📄</div>' +
            '<div class="tg-file-info">' +
              '<div class="tg-file-name">' + esc(fl.name || "document.txt") + "</div>" +
              '<div class="tg-file-size">' + esc(fl.size || "Text file") + " · Tap to open</div>" +
            "</div>" +
          "</div>"
        );
      }

      // Voice Note Bubble with [ >A ] Transcript Button
      if (m.voice) {
        var vc = m.voice;
        var dur = vc.duration || 5;
        var durStr = "0:" + String(dur).padStart(2, "0");
        var isPlaying = activeAudioMsgId === m.id;
        inner.push(
          '<div class="tg-voice-card ' + (isPlaying ? "playing" : "") + '" id="voice-card-' + esc(m.id) + '">' +
            '<div class="tg-voice-controls">' +
              '<button type="button" class="tg-voice-play" onclick="TG.playVoiceBubble(\'' + esc(m.id) + '\', this)" title="Play / Synthesize ElevenLabs Voice Note">' +
                (isPlaying ? "⏸" : "▶") +
              "</button>" +
              '<div class="tg-voice-waveform">' + renderWaveformBars(vc.transcript || m.id) + "</div>" +
              '<span style="font-size:11px;color:var(--tg-muted);">' + esc(durStr) + "</span>" +
              '<button type="button" class="tg-voice-transcript-btn" onclick="TG.toggleTranscript(\'' + esc(m.id) + '\')" title="Show/hide text transcript">&gt;A</button>' +
            "</div>" +
            '<div class="tg-voice-transcript-box" id="transcript-' + esc(m.id) + '">' +
              formatMessageHtml(vc.transcript || m.text || "") +
            "</div>" +
          "</div>"
        );
      } else if (m.text && !(m.photo && m.photo.caption === m.text)) {
        var bigEmo = !m.sticker && !m.photo && !m.file && isOnlyEmoji(m.text);
        inner.push(
          '<div class="tg-bubble-text ' + (bigEmo ? "big-emoji" : "") + '">' +
            formatMessageHtml(m.text) +
          "</div>"
        );
      }

      // Reactions under bubble
      var reacts = m.reactions || {};
      var rKeys = Object.keys(reacts).filter(function (k) { return (reacts[k] || []).length > 0; });
      if (rKeys.length) {
        inner.push(
          '<div class="tg-reactions-bar">' +
            rKeys
              .map(function (emo) {
                var who = reacts[emo] || [];
                var mine = who.indexOf("You") !== -1;
                return (
                  '<button type="button" class="tg-react-pill ' + (mine ? "mine" : "") + '" onclick="TG.reactMessage(\'' + esc(m.id) + '\', \'' + esc(emo) + '\')" title="' + esc(who.join(", ")) + '">' +
                    esc(emo) + " <span>" + who.length + "</span>" +
                  "</button>"
                );
              })
              .join("") +
          "</div>"
        );
      }

      // Timestamp & Read ticks
      inner.push(
        '<div class="tg-bubble-meta">' +
          (m.edited ? "<span>edited</span>" : "") +
          "<span>" + esc(m.time || "") + "</span>" +
          (isUser ? '<span style="color:#a78bfa;font-weight:700;">✓✓</span>' : "") +
          (isUser && t.waiting && m.id === lastUserId ? '<span class="tg-seen">Seen</span>' : "") +
        "</div>"
      );

      // Hover Action Toolbar
      var quickEmojis = ["❤️", "🔥", "👍", "😂", "👀"]
        .map(function (e) {
          return '<button type="button" class="tg-act-btn" onclick="TG.reactMessage(\'' + esc(m.id) + '\', \'' + e + '\')">' + e + "</button>";
        })
        .join("");

      var actionsToolbar =
        '<div class="tg-msg-actions">' +
          quickEmojis +
          '<button type="button" class="tg-act-btn" onclick="TG.setReplyTo(\'' + esc(m.id) + '\')" title="Reply">↩</button>' +
          (!isUser ? '<button type="button" class="tg-act-btn" onclick="TG.playVoiceBubble(\'' + esc(m.id) + '\', this)" title="Voice with ElevenLabs">🔊</button>' : "") +
          (!isUser ? '<button type="button" class="tg-act-btn" onclick="TG.openRedo(\'' + esc(m.id) + '\')" title="Try this message again (a note optional)">↻</button>' : "") +
          '<button type="button" class="tg-act-btn" onclick="TG.branchFrom(\'' + esc(m.id) + '\')" title="Branch: a new chat from here (this one stays as it is)">⑂</button>' +
          '<button type="button" class="tg-act-btn" onclick="TG.pinMessage(\'' + esc(m.id) + '\')" title="Pin">📌</button>' +
          '<button type="button" class="tg-act-btn" onclick="TG.editMessagePrompt(\'' + esc(m.id) + '\')" title="Edit">✏️</button>' +
          '<button type="button" class="tg-act-btn" onclick="TG.deleteMessage(\'' + esc(m.id) + '\')" title="Delete">🗑</button>' +
        "</div>";

      var stickerOnly = m.sticker && !m.text && !m.voice && !m.photo && !m.file;
      out.push(
        '<div class="tg-msg-row ' + (isUser ? "user" : "assistant") + '" id="msg-' + esc(m.id) + '">' +
          (isUser ? avatarHtml(avUrl, senderName, "tg-msg-avatar")
                  : '<span class="tg-card-tap" onclick="TG.openCard(\'' + esc(m.sender_slug || "") + '\')" title="Their card">' + avatarHtml(avUrl, senderName, "tg-msg-avatar") + "</span>") +
          '<div class="tg-bubble ' + (stickerOnly ? "sticker-only" : "") + '">' +
            actionsToolbar +
            inner.join("") +
          "</div>" +
        "</div>"
      );
      if (redoFor === m.id && !isUser) out.push(redoBox(m));
    });

    // ↻ Under the characters' latest reply: try again, with an optional note ("as a voice note", "send a selfie")
    var lastUser = -1;
    msgs.forEach(function (m, i) { if (m.role === "user") lastUser = i; });
    if (msgs.slice(lastUser + 1).some(function (m) { return m.role === "assistant"; })) {
      var picks = [["🎤 As a voice note", "Say it as a voice note."], ["📸 With a photo", "Send a photo with it."],
                   ["✂️ Shorter", "Keep it shorter."], ["🔥 More feeling", "Let more feeling show."]];
      out.push(
        '<div class="tg-regen" id="tgRegen">' +
          '<button type="button" class="tg-regen-open" onclick="TG.toggleRegen()">↻ Try again…</button>' +
          '<div class="tg-regen-box" hidden>' +
            '<div class="tg-regen-picks">' + picks.map(function (p) {
              return '<button type="button" onclick="TG.regenPick(this)" data-note="' + esc(p[1]) + '">' + esc(p[0]) + "</button>";
            }).join("") + "</div>" +
            '<div class="tg-regen-row"><input type="text" id="tgRegenNote" maxlength="600" placeholder="A note for this take (optional): what should be different?" ' +
              'onkeydown="if (event.key === \'Enter\') { event.preventDefault(); TG.regenerate(); }">' +
            '<button type="button" class="tg-regen-go" onclick="TG.regenerate()">↻ Again</button></div>' +
          "</div>" +
        "</div>"
      );
    }

    // 🥔 Bulba Watch: something it noticed in their latest text, with a one-tap fix (Not now hides it)
    var wn = t.watch;
    var wnSkipped = function (id) { try { return localStorage.getItem("na-tg-watch-" + id) === "1"; } catch (e) { return false; } };
    if (wn && !wnSkipped(wn.message_id) && !(STATE.failed && STATE.failed.thread === t.id)) {
      out.push('<div class="tg-watch"><span>🥔 <b>Bulba noticed:</b> ' + esc(wn.text) + "</span>" +
        '<button type="button" class="tg-watch-fix" onclick="TG.watchFix()">↻ Rewrite without it</button>' +
        '<button type="button" class="tg-watch-x" onclick="TG.watchSkip()">Not now</button></div>');
    }

    // ⚠️ Their reply didn't arrive (an error): say so here, with a way to try again
    if (STATE.failed && STATE.failed.thread === t.id) {
      out.push('<div class="tg-failed"><span>⚠️ Their reply didn\'t arrive: ' + esc(STATE.failed.error || "something went wrong") + "</span>" +
        '<button type="button" onclick="TG.retryFailed()">↻ Try again</button></div>');
    }

    vp.innerHTML = out.join("");
    vp.scrollTop = vp.scrollHeight;
    renderStickerTray();
  }

  function renderStickerTray() {
    var grid = document.getElementById("tgStickerGrid");
    if (!grid) return;
    var t = STATE.active_thread;
    var list = (t && t.stickers) ? t.stickers : STATE.built_in_stickers;
    grid.innerHTML = list
      .map(function (s, idx) {
        if (s.url) {
          return (
            '<div class="tg-tray-item" onclick="TG.sendStickerByIndex(' + idx + ')">' +
              (s.video || /\.webm$/i.test(s.url) ? '<video src="' + esc(s.url) + '" autoplay loop muted playsinline></video>' : '<img src="' + esc(s.url) + '" alt="' + esc(s.name || "") + '">') +
              '<span class="nm">' + esc(s.name || s.mood || "Sticker") + "</span>" +
            "</div>"
          );
        }
        return (
          '<div class="tg-tray-item" onclick="TG.sendStickerByIndex(' + idx + ')">' +
            '<span class="emo">' + esc(s.emoji || "🥔") + "</span>" +
            '<span class="nm">' + esc(s.label || s.name || "Sticker") + "</span>" +
          "</div>"
        );
      })
      .join("");
  }

  // Drawer rendering
  function renderDrawer() {  // redrawn in place: the drawer keeps where they had scrolled to
    var drw = document.getElementById("tgDrawer"), keep = drw ? drw.scrollTop : 0;
    renderDrawerNow();
    if (drw) drw.scrollTop = keep;
  }
  function renderDrawerNow() {
    var body = document.getElementById("tgDrawerBody");
    if (!body) return;
    var t = STATE.active_thread;

    if (currentDrawerTab === "char") {
      var members = (t && t.members) || STATE.characters || [];
      if (!members.length) {
        body.innerHTML =
          '<p style="color:var(--tg-muted);font-size:13px;">No characters available yet.</p>' +
          '<button type="button" class="tg-bulba-btn" onclick="TG.openCreateCharModal()">🥔 Create Messenger Character with Bulba</button>';
        return;
      }
      var cur = members.find(function (m) { return m.slug === selectedDrawerCharSlug; }) || members[0];
      selectedDrawerCharSlug = cur.slug;

      var charPicker = "";
      if (members.length > 1) {
        charPicker =
          '<div class="tg-field-group">' +
            "<label>Character in this chat</label>" +
            '<select class="tg-select" onchange="TG.selectDrawerChar(this.value)">' +
              members
                .map(function (m) {
                  return '<option value="' + esc(m.slug) + '" ' + (m.slug === cur.slug ? "selected" : "") + ">" + esc(m.name) + "</option>";
                })
                .join("") +
            "</select>" +
          "</div>";
      }

      var voices = STATE.voices || [];
      var curVoice = cur.voice_id || "";
      var isKnownVoice = voices.some(function (v) { return v.id.toLowerCase() === curVoice.toLowerCase(); });
      var voiceOptions = voices
        .map(function (v) {
          var sel = v.id.toLowerCase() === curVoice.toLowerCase() ? "selected" : "";
          var badge = v.source === "elevenlabs" ? " [My ElevenLabs]" : "";
          var info = [v.gender, v.accent, v.description].filter(Boolean).join(" · ");
          return '<option value="' + esc(v.id) + '" ' + sel + ">" + esc(v.name) + " (" + esc(info) + ")" + esc(badge) + "</option>";
        })
        .join("");

      var ttsModels = STATE.tts_models || ["elevenlabs/eleven-v4-turbo", "elevenlabs/eleven-v4", "elevenlabs/eleven-v3"];
      var curVoiceModel = cur.voice_model || "elevenlabs/eleven-v4-turbo";
      var ttsModelOptions = ttsModels
        .map(function (m) {
          return '<option value="' + esc(m) + '" ' + (m === curVoiceModel ? "selected" : "") + ">" + esc(m) + "</option>";
        })
        .join("");

      var neutralUrl = cur.neutral_url || cur.avatar_url || "";
      var extraRefs = (cur.extra_refs || []).slice(0, 4);
      var refSlotsHtml = [];
      // Slot 0: Neutral Portrait
      refSlotsHtml.push(
        '<div style="border:1px solid var(--tg-border);border-radius:10px;padding:8px;display:flex;flex-direction:column;align-items:center;gap:6px;background:rgba(255,255,255,0.03);">' +
          '<div style="font-size:11px;font-weight:700;color:#93c5fd;">1. Neutral Ref</div>' +
          (neutralUrl
            ? '<img class="tg-ref-img" src="' + esc(neutralUrl) + '" alt="Neutral" title="Tap to see it big" onclick="TG.viewImage(this.src)">'
            : '<div class="tg-ref-empty" style="background:rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;font-size:20px;">👤</div>') +
          '<div style="display:flex;gap:3px;"><button type="button" class="tg-fmt-btn" style="font-size:10.5px;padding:3px 7px;" onclick="TG.triggerRefUpload(\'char_neutral\', -1)">Upload</button>' +
          '<button type="button" class="tg-fmt-btn" style="font-size:10.5px;padding:3px 6px;" onclick="TG.makeOneRef(-1, this)" title="' + (neutralUrl ? "Draw it again" : "Draw it") + ', just this one">' + (neutralUrl ? "↻" : "✨") + "</button></div>" +
        "</div>"
      );
      // Slots 1..4: Up to 4 Extra References
      for (var rIdx = 0; rIdx < 4; rIdx++) {
        var rUrl = extraRefs[rIdx] || "";
        refSlotsHtml.push(
          '<div style="border:1px solid var(--tg-border);border-radius:10px;padding:8px;display:flex;flex-direction:column;align-items:center;gap:6px;background:rgba(255,255,255,0.02);">' +
            '<div style="font-size:11px;color:var(--tg-muted);">Ref #' + (rIdx + 2) + "</div>" +
            (rUrl
              ? '<img class="tg-ref-img" src="' + esc(rUrl) + '" alt="Ref" title="Tap to see it big" onclick="TG.viewImage(this.src)">'
              : '<div class="tg-ref-empty" style="background:rgba(255,255,255,0.04);display:flex;align-items:center;justify-content:center;font-size:18px;color:var(--tg-muted);">+</div>') +
            '<div style="display:flex;gap:3px;">' +
              '<button type="button" class="tg-fmt-btn" style="font-size:10.5px;padding:3px 6px;" onclick="TG.triggerRefUpload(\'char_extra_ref\', ' + rIdx + ')">' + (rUrl ? "Swap" : "Add") + "</button>" +
              '<button type="button" class="tg-fmt-btn" style="font-size:10.5px;padding:3px 6px;" onclick="TG.makeOneRef(' + rIdx + ', this)" title="' + (rUrl ? "Draw it again" : "Draw it") + ', just this one">' + (rUrl ? "↻" : "✨") + "</button>" +
              (rUrl ? '<button type="button" class="tg-fmt-btn" style="font-size:10.5px;padding:3px 5px;color:#f87171;" onclick="TG.removeExtraRef(' + rIdx + ')">✕</button>' : "") +
            "</div>" +
          "</div>"
        );
      }

      body.innerHTML =
        charPicker +
        '<div class="tg-bulba-box">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;">' +
            '<div style="font-weight:700;font-size:13px;">🥔 Automatic Setup with Bulba</div>' +
            '<button type="button" class="tg-fmt-btn" style="font-size:11px;" onclick="TG.openCreateCharModal()">+ New Character</button>' +
          "</div>" +
          '<div style="font-size:12px;color:#cbd5e1;">Modernize ' + esc(cur.name) + " into a Modern AU or draft a texting setup without touching their main roleplay card.</div>" +
          '<input type="text" class="tg-input" id="drwBulbaHint" placeholder="Optional note (e.g. rival barista, late-night lab boss)…">' +
          '<div style="display:flex;gap:6px;">' +
            '<button type="button" class="tg-bulba-btn" style="flex:1" onclick="TG.runBulbaModernize(\'modern_au\', this)">✨ Modernize (Modern AU)</button>' +
            '<button type="button" class="tg-fmt-btn" onclick="TG.runBulbaModernize(\'canon\', this)">🏰 Canon Texting</button>' +
          "</div>" +
        "</div>" +
        '<div class="tg-bulba-box" style="background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.25);">' +
          '<div style="font-weight:700;font-size:13px;">🖼️ 1 Neutral + Up to 4 Reference Pictures</div>' +
          '<div style="font-size:11.5px;color:#cbd5e1;">Nano Banana uses these to lock face, outfit & art style across varied-angle selfies, food shots, and scenery. For OCs without art yet, generate them from description below!</div>' +
          '<div class="tg-ref-grid">' + refSlotsHtml.join("") + "</div>" +
          '<input type="file" id="drwRefUploadInput" accept="image/*" style="display:none" onchange="TG.handleRefUploadFile(this)">' +
          '<div class="tg-field-group" style="margin-top:4px;">' +
            "<label>Appearance Description (used for photos & OC reference generation)</label>" +
            '<textarea class="tg-textarea" id="drwCharAppearance" style="min-height:54px;" placeholder="Face, hair, eyes, build, signature outfit…">' + esc(cur.appearance_notes || "") + "</textarea>" +
          "</div>" +
          '<div class="tg-field-group">' +
            "<label>Visual Art Style Lock (kept consistent on selfies, food & scenery photos)</label>" +
            '<input type="text" class="tg-input" id="drwCharArtStyle" value="' + esc(cur.art_style_notes || "") + '" placeholder="e.g. semi-realistic painted anime illustration, warm cinematic light">' +
          "</div>" +
          '<button type="button" class="tg-bulba-btn" onclick="TG.generateCharRefsFromDesc(this)">🍌 Generate Neutral + Reference Pics from Description</button>' +
        "</div>" +
        '<div class="tg-bulba-box" style="background:rgba(167,139,250,0.06);border-color:rgba(167,139,250,0.25);">' +
          '<div style="font-weight:700;font-size:13px;">🎤 ElevenLabs Voice (on OpenRouter or Direct Key)</div>' +
          '<div class="tg-field-group">' +
            "<label>Premade Voice (21 OpenRouter ElevenLabs Voices + Your Account Voices)</label>" +
            '<select class="tg-select" id="drwCharVoicePreset" onchange="document.getElementById(\'drwCharVoiceCustom\').value = this.value;">' +
              voiceOptions +
            "</select>" +
          "</div>" +
          '<div style="display:grid;grid-template-columns:1fr auto;gap:6px;align-items:end;">' +
            '<div class="tg-field-group">' +
              "<label>Active Voice Name or Custom 20-char ElevenLabs Voice ID</label>" +
              '<small style="display:block;color:var(--tg-muted);font-size:11.5px;margin:-2px 0 4px;">Through OpenRouter only the 21 voices in the list above work. Your own ElevenLabs voice ids need your ElevenLabs key (Extras → Voices).</small>' +
              '<input type="text" class="tg-input" id="drwCharVoiceCustom" value="' + esc(curVoice || (voices[0] ? voices[0].id : "sarah")) + '" placeholder="e.g. george, sarah, or JBFqnCBsd6RMkjVDRZzb">' +
            "</div>" +
            '<button type="button" class="tg-fmt-btn" style="height:36px;padding:0 12px;" onclick="TG.previewSelectedVoice(this)">🔊 Preview</button>' +
          "</div>" +
          '<div class="tg-field-group">' +
            "<label>OpenRouter ElevenLabs TTS Model</label>" +
            '<select class="tg-select" id="drwCharVoiceModel">' + ttsModelOptions + "</select>" +
          "</div>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Messenger Mode</label>" +
          '<select class="tg-select" id="drwCharMode">' +
            '<option value="canon" ' + (cur.mode === "canon" ? "selected" : "") + ">🏰 Original Setting (Canon world)</option>" +
            '<option value="modern_au" ' + (cur.mode === "modern_au" ? "selected" : "") + ">✨ Modern AU (Modernized for Messenger)</option>" +
          "</select>" +
        "</div>" +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">' +
          '<div class="tg-field-group">' +
            "<label>Display Name</label>" +
            '<input type="text" class="tg-input" id="drwCharName" value="' + esc(cur.display_name || cur.name) + '">' +
          "</div>" +
          '<div class="tg-field-group">' +
            "<label>@Handle & Emoji</label>" +
            '<div style="display:flex;gap:4px;">' +
              '<input type="text" class="tg-input" id="drwCharEmoji" style="width:46px;text-align:center;" value="' + esc(cur.status_emoji || "💬") + '">' +
              '<input type="text" class="tg-input" id="drwCharHandle" value="' + esc(cur.handle || "") + '">' +
            "</div>" +
          "</div>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Telegram Bio / Status Line</label>" +
          '<input type="text" class="tg-input" id="drwCharBio" value="' + esc(cur.bio || "") + '" placeholder="In the lab. Do not disturb.">' +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Modern AU / Messenger Persona (separate from RP card)</label>" +
          '<textarea class="tg-textarea" id="drwCharPersona" placeholder="Who they are in this modern/texting setup…">' + esc(cur.modern_persona || "") + "</textarea>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Texting Fingerprint & Habits (Frankenstein voice guard)</label>" +
          '<textarea class="tg-textarea" id="drwCharStyle" style="min-height:60px;" placeholder="How they punctuate, capitalize, emoji habits, reply length…">' + esc(cur.texting_style || "") + "</textarea>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Texting Scenario</label>" +
          '<textarea class="tg-textarea" id="drwCharScenario" style="min-height:60px;">' + esc(cur.scenario || "") + "</textarea>" +
        "</div>" +
        '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
          '<input type="checkbox" id="drwCharMemory" ' + (cur.share_memory !== false ? "checked" : "") + ">" +
          "Share Story Memory with their main roleplay chats" +
        "</label>" +
        '<div class="tg-save-bar">' +
          '<button type="button" class="tg-send-btn" style="flex:1;justify-content:center;" onclick="TG.saving(this, TG.saveCharProfile)">💾 Save Character Setup</button>' +
          '<button type="button" class="tg-fmt-btn" onclick="TG.openStoryModal(\'' + esc(cur.slug) + '\')">+ Post Status</button>' +
        "</div>";
      return;
    }

    if (currentDrawerTab === "clock") {
      if (!t) {
        body.innerHTML = '<p style="color:var(--tg-muted);">Open a chat first.</p>';
        return;
      }
      var rt = t.real_time || {};
      var wpOptions = Object.keys(STATE.wallpapers)
        .map(function (k) {
          return '<option value="' + esc(k) + '" ' + (t.bg === k ? "selected" : "") + ">" + esc(STATE.wallpapers[k].name) + "</option>";
        })
        .join("");

      var evHtml = ((t.events || []).map(function (ev, idx) {
        return (
          '<div style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.04);padding:6px 10px;border-radius:8px;font-size:12px;">' +
            "<div><strong>" + esc(ev.title) + "</strong>" + (ev.notes ? " — " + esc(ev.notes) : "") + "</div>" +
            '<button type="button" class="tg-fmt-btn" onclick="TG.removeEvent(' + idx + ')">✕</button>' +
          "</div>"
        );
      })).join("");

      body.innerHTML =
        '<div class="tg-bulba-box">' +
          '<div style="font-weight:700;font-size:13px;">🕒 Real-Time Clock Awareness</div>' +
          '<div style="font-size:12px;color:#e2e8f0;">Current time: <b>' + esc(rt.clock || "Now") + "</b></div>" +
          '<div style="font-size:12px;color:#94a3b8;">Time since last text: <b>' + esc(rt.elapsed_text || "just now") + "</b></div>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Scheduled Real-Time Events / Deadlines</label>" +
          '<div style="display:flex;flex-direction:column;gap:6px;">' + (evHtml || '<span style="font-size:12px;color:var(--tg-muted);">No active events yet.</span>') + "</div>" +
          '<div style="display:flex;gap:6px;margin-top:6px;">' +
            '<input type="text" class="tg-input" id="drwNewEventTitle" placeholder="e.g. Friday 20:00 — Dinner at the pier">' +
            '<button type="button" class="tg-fmt-btn" onclick="TG.addEvent()">+ Add</button>' +
          "</div>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Chat Wallpaper</label>" +
          '<select class="tg-select" id="drwThreadBg">' + wpOptions + "</select>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Custom Background Image URL (optional)</label>" +
          '<input type="url" class="tg-input" id="drwThreadCustomBg" value="' + esc(t.custom_bg_url || "") + '" placeholder="https://…">' +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Chat / Group Title</label>" +
          '<input type="text" class="tg-input" id="drwThreadTitle" value="' + esc(t.title || "") + '">' +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>This Chat's Scenario Override (optional)</label>" +
          '<textarea class="tg-textarea" id="drwThreadScenario">' + esc(t.scenario_override || "") + "</textarea>" +
        "</div>" +
        '<div class="tg-field-group">' +
          '<label style="display:flex;align-items:flex-start;gap:8px;font-size:13px;cursor:pointer;">' +
            '<input type="checkbox" id="drwThreadLeaveOnRead" ' + (t.leave_on_read ? "checked" : "") + ' style="margin-top:3px">' +
            "<span>🙈 <b>They can leave me on read</b><br><small style=\"color:var(--tg-muted)\">Now and then, when it fits (they were busy, " +
            "or teasing, annoyed, petty), they answer up to 5 real minutes later. Your message shows as Seen meanwhile.</small></span>" +
          "</label>" +
          '<label style="display:flex;align-items:flex-start;gap:8px;font-size:13px;cursor:pointer;margin-top:8px;">' +
            '<input type="checkbox" id="drwThreadShare" ' + (t.share_memory !== false ? "checked" : "") + ' style="margin-top:3px">' +
            "<span>🧠 <b>Share story memory with the roleplay chats</b></span></label>" +
        "</div>" +
        '<div class="tg-field-group"><label>🕰️ The chat\'s clock</label>' +
          '<div style="font-size:13px;margin-bottom:6px;">' + (t.clock_offset ? "Set: it's <b>" + esc((t.real_time || {}).clock || "") + "</b> in this chat (it runs on from there)."
            : "Real time: <b>" + esc((t.real_time || {}).clock || "") + "</b>.") + "</div>" +
          '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">' +
            '<button type="button" class="tg-fmt-btn" onclick="TG.setClock(\'resume\')" title="The clock jumps back to just after the last message">🌙 Continue where we left off</button>' +
            '<input type="datetime-local" class="tg-input" id="drwClockAt" style="width:auto">' +
            '<button type="button" class="tg-fmt-btn" onclick="TG.setClock(document.getElementById(\'drwClockAt\').value)">Set</button>' +
            (t.clock_offset ? '<button type="button" class="tg-fmt-btn" onclick="TG.setClock(\'real\')">⏱ Back to real time</button>' : "") +
          "</div></div>" +
        '<div class="tg-field-group"><label>🎨 Theme</label><select class="tg-select" id="drwThreadTheme">' +
          Object.keys(THEMES).map(function (k) { return '<option value="' + k + '"' + ((t.theme || "") === k ? " selected" : "") + ">" + esc(THEMES[k]) + "</option>"; }).join("") +
        "</select></div>" +
        '<div class="tg-field-group">' +
          "<label>🧠 Memory of this chat <small style=\"font-weight:400;color:var(--tg-muted)\">(what happened before the recent messages; kept up to date as the chat grows; edit freely)</small></label>" +
          '<textarea class="tg-textarea" id="drwThreadMemory" style="min-height:90px" placeholder="Nothing yet: it starts once older messages fall out of view.">' + esc(t.memory || "") + "</textarea>" +
          '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;">' +
            '<button type="button" class="tg-fmt-btn" onclick="TG.updateMemory(this)">🧠 Update it now</button>' +
            '<label style="font-size:12.5px;">Recent messages the model reads <select class="tg-select" id="drwThreadContext" style="width:auto;display:inline-block">' +
              [20, 30, 60, 100].map(function (n) { return '<option value="' + n + '"' + ((t.context_size || 30) === n ? " selected" : "") + ">" + n + "</option>"; }).join("") +
            "</select></label></div>" +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>🎭 Who you are in this chat (empty: your usual persona" + (t.usual_persona ? ", " + esc(t.usual_persona) : "") + ")</label>" +
          '<input type="text" class="tg-input" id="drwThreadPersonaName" placeholder="Name" value="' + esc((t.persona || {}).name || "") + '">' +
          '<textarea class="tg-textarea" id="drwThreadPersonaDesc" placeholder="Who you are here">' + esc((t.persona || {}).description || "") + "</textarea>" +
        "</div>" +
        '<div class="tg-save-bar">' +
          '<button type="button" class="tg-send-btn" style="flex:1;justify-content:center;" onclick="TG.saving(this, TG.saveThreadSettings)">💾 Save Chat & Look</button>' +
          '<button type="button" class="tg-fmt-btn" onclick="TG.pinCurrentThread()">📌 Pin Chat</button>' +
          '<button type="button" class="tg-fmt-btn" style="color:#f87171;" onclick="TG.deleteCurrentThread()">🗑</button>' +
        "</div>";
      return;
    }

    // Tab "me": User Profile & Notifications
    var u = STATE.user_profile || {};
    body.innerHTML =
      '<div class="tg-field-group">' +
        "<label>Your Telegram Display Name</label>" +
        '<input type="text" class="tg-input" id="drwMeName" value="' + esc(u.display_name || "") + '">' +
      "</div>" +
      '<div style="display:grid;grid-template-columns:64px 1fr;gap:8px;">' +
        '<div class="tg-field-group">' +
          "<label>Emoji</label>" +
          '<input type="text" class="tg-input" id="drwMeEmoji" value="' + esc(u.status_emoji || "✨") + '">' +
        "</div>" +
        '<div class="tg-field-group">' +
          "<label>Your @Handle</label>" +
          '<input type="text" class="tg-input" id="drwMeHandle" value="' + esc(u.handle || "") + '">' +
        "</div>" +
      "</div>" +
      '<div class="tg-field-group">' +
        "<label>Your Bio / Status (characters see when you change this!)</label>" +
        '<input type="text" class="tg-input" id="drwMeBio" value="' + esc(u.bio || "") + '" placeholder="Coffee first, questions later.">' +
      "</div>" +
      "<hr style='border:none;border-top:1px solid var(--tg-border);width:100%;'>" +
      '<div style="font-weight:700;font-size:13px;">🔔 Notifications & Rich Media</div>' +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeToast" ' + (u.in_app_toasts !== false ? "checked" : "") + ">" +
        "In-app toast alerts when you are on another page" +
      "</label>" +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeBrowserNotif" ' + (u.browser_notifications ? "checked" : "") + ' onchange="TG.requestBrowserNotifPermission(this)">' +
        "Browser / system notifications when in another tab or outside site" +
      "</label>" +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeSpontaneous" ' + (u.spontaneous_texts ? "checked" : "") + ">" +
        "Characters can text you first when you're on another page" +
      "</label>" +
      '<div class="tg-field-group">' +
        "<label>Quiet time before a spontaneous check-in (minutes)</label>" +
        '<input type="number" class="tg-input" id="drwMeSpontMins" min="2" max="1440" value="' + (u.spontaneous_minutes || 15) + '">' +
      "</div>" +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeAutoPhoto" ' + (u.auto_photos ? "checked" : "") + ">" +
        "Automatically make the picture when characters send a photo" +
      "</label>" +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeAutoStatuses" ' + (u.auto_statuses !== false ? "checked" : "") + ">" +
        "Characters post statuses on their own now and then" +
      "</label>" +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer;">' +
        '<input type="checkbox" id="drwMeAutoVoice" ' + (u.auto_voice ? "checked" : "") + ">" +
        "Automatically synthesize ElevenLabs audio when characters send [VOICE]" +
      "</label>" +
      '<div class="tg-field-group"><label>🖼️ Picture model (photos, selfies and reference pictures in the messenger)</label>' +
        '<select class="tg-select" id="drwMeImageModel">' +
          [["", "Nano Banana (Google): the app's default"],
           ["microsoft/mai-image-2.7", "MAI-Image-2.7 (Microsoft): precise, consistent"],
           ["microsoft/mai-image-2.7-flash", "MAI-Image-2.7 Flash (Microsoft): faster, cheaper"]].map(function (o) {
            return '<option value="' + o[0] + '"' + ((u.image_model || "") === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>";
          }).join("") +
        "</select><small style=\"color:var(--tg-muted);font-size:11.5px;\">All three keep faces from the reference pictures. Through your OpenRouter key.</small></div>" +
      '<div class="tg-save-bar"><button type="button" class="tg-send-btn" style="flex:1;justify-content:center;" onclick="TG.saving(this, TG.saveUserProfile)">💾 Save My Profile & Alerts</button></div>';
  }

  function renderMomentsFeed() {
    var box = document.getElementById("momentsFeedList");
    if (!box) return;
    var items = [];
    var u = STATE.user_profile || {};
    (u.stories || []).forEach(function (s) {
      items.push({
        owner: u.display_name || "You",
        handle: u.handle || "@you",
        avatar: u.avatar_url || "",
        emoji: s.emoji || u.status_emoji || "✨",
        text: s.text,
        at: s.at || "",
        ts: s.ts || 0,
      });
    });
    (STATE.characters || []).forEach(function (c) {
      (c.stories || []).forEach(function (s) {
        items.push({
          owner: c.display_name || c.name,
          handle: c.handle || "",
          avatar: c.avatar_url || "",
          emoji: s.emoji || c.status_emoji || "💬",
          text: s.text,
          at: s.at || "",
          ts: s.ts || 0,
        });
      });
    });
    items.sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); });

    if (!items.length) {
      box.innerHTML =
        '<div class="moment-card"><div style="color:var(--tg-muted);font-size:13.5px;">No status updates yet. Click <b>+ Post My Status</b> above or chat with your characters!</div></div>';
      return;
    }
    box.innerHTML = items
      .map(function (it) {
        return (
          '<div class="moment-card">' +
            avatarHtml(it.avatar, it.owner, "tg-avatar") +
            '<div style="flex:1;">' +
              '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                '<div><strong>' + esc(it.owner) + '</strong> <span style="color:var(--tg-muted);font-size:12px;">' + esc(it.handle) + "</span></div>" +
                '<span style="color:var(--tg-muted);font-size:12px;">' + esc(it.at) + "</span>" +
              "</div>" +
              '<div style="margin-top:6px;font-size:14.5px;">' + esc(it.emoji) + " " + formatMessageHtml(it.text) + "</div>" +
            "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  function renderHubFilesAndNotes() {
    var box = document.getElementById("hubFilesContainer");
    if (!box) return;
    var t = STATE.active_thread;
    var sharedFiles = [];
    if (t && t.messages) {
      t.messages.forEach(function (m) {
        if (m.file) {
          sharedFiles.push({ sender: m.sender_name, time: m.time, file: m.file, msgId: m.id });
        }
      });
    }
    var notes = (STATE.user_profile && STATE.user_profile.notes) || [];

    var html = [];
    html.push("<h3 style='margin:0;font-size:15px;'>📎 Files in Current Chat</h3>");
    if (!sharedFiles.length) {
      html.push('<div style="color:var(--tg-muted);font-size:13px;">No files sent in this chat yet. Use the <b>📄 Note File</b> button in the chat composer to send one, or ask a character for a document!</div>');
    } else {
      html.push(
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;">' +
          sharedFiles
            .map(function (sf) {
              return (
                '<div class="tg-file-card" onclick="TG.openReadFileModal(\'' + esc(sf.msgId) + '\')">' +
                  '<div class="tg-file-icon">📄</div>' +
                  '<div class="tg-file-info">' +
                    '<div class="tg-file-name">' + esc(sf.file.name) + "</div>" +
                    '<div class="tg-file-size">From ' + esc(sf.sender) + " · " + esc(sf.file.size || "") + "</div>" +
                  "</div>" +
                "</div>"
              );
            })
            .join("") +
        "</div>"
      );
    }

    html.push("<h3 style='margin:12px 0 0;font-size:15px;'>📝 Personal Scratchpad Notes</h3>");
    if (!notes.length) {
      html.push('<div style="color:var(--tg-muted);font-size:13px;">No personal notes yet. Click <b>+ New Note</b> above to jot something down.</div>');
    } else {
      html.push(
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;">' +
          notes
            .map(function (n, idx) {
              return (
                '<div class="moment-card" style="flex-direction:column;gap:8px;">' +
                  '<div style="display:flex;justify-content:space-between;width:100%;align-items:center;">' +
                    "<strong>" + esc(n.title || "Note") + "</strong>" +
                    '<button type="button" class="tg-fmt-btn" onclick="TG.deletePersonalNote(' + idx + ')">🗑</button>' +
                  "</div>" +
                  '<div style="font-size:13px;white-space:pre-wrap;color:#cbd5e1;">' + esc(n.text || "") + "</div>" +
                "</div>"
              );
            })
            .join("") +
        "</div>"
      );
    }
    box.innerHTML = html.join("");
  }

  // --- ↻ One message again: its text (or a voice note's words) rewritten, or its photo redrawn, with a note ---
  var redoFor = null;
  function redoBox(m) {
    var hasText = !!((m.voice && m.voice.transcript) || m.text), hasPhoto = !!m.photo;
    var picks = hasPhoto && !hasText ? [["🎨 Other angle", "A different camera angle."], ["😏 Cheekier", "More playful."], ["🌙 Moodier light", "Moodier lighting."]]
      : [["✂️ Shorter", "Shorter."], ["🔥 More feeling", "Let more feeling show."], ["😏 Teasing", "More teasing."], ["🧊 Colder", "Colder, more distant."]];
    return '<div class="tg-regen tg-redo" id="tgRedo"><div class="tg-regen-box">' +
      '<div class="tg-regen-picks">' + picks.map(function (p) {
        return '<button type="button" onclick="TG.redoPick(this)" data-note="' + esc(p[1]) + '">' + esc(p[0]) + "</button>";
      }).join("") + "</div>" +
      '<div class="tg-regen-row"><input type="text" id="tgRedoNote" maxlength="600" placeholder="What should be different? (optional)">' +
      (hasText ? '<button type="button" class="tg-regen-go" onclick="TG.redoMessage(\'' + esc(m.id) + '\')">↻ ' + (m.voice ? "New words" : "Rewrite") + "</button>" : "") +
      (hasPhoto ? '<button type="button" class="tg-regen-go" onclick="TG.redoPhoto(\'' + esc(m.id) + '\')">🖼️ New picture</button>' : "") +
      '<button type="button" class="tg-regen-x" onclick="TG.openRedo(null)" aria-label="Close">✕</button></div></div></div>';
  }

  // --- 🥔 A group chat's shared scenario, once everyone is set up for texting ---
  var groupState = {};
  function groupScenarioCard(t) {
    if (!t.is_group) return "";
    var gs = groupState[t.id];
    if (!gs && (t.scenario_override || setupSkipped("group-" + t.id))) return "";
    gs = gs || (groupState[t.id] = { step: "offer", hint: "" });
    if (gs.step === "done") return "";
    var err = gs.error ? '<p class="tg-setup-err">' + esc(gs.error) + "</p>" : "", body;
    if (gs.step === "offer") {
      body = "<p>Everyone's set up. Want me to write how you all ended up in one group chat, and what's going on as it starts?</p>" +
        '<textarea rows="2" oninput="TG.groupType(' + t.id + ', this.value)" placeholder="Steer it (optional): how you all know each other, what the group is for… Empty: I\'ll suggest one.">' + esc(gs.hint) + "</textarea>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.groupWrite(' + t.id + ')">🥔 Write it</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.groupSkip(' + t.id + ')">Not now</button></div>';
    } else if (gs.step === "busy") {
      body = "<p>Working out how you all know each other… 🥔</p>";
    } else {
      body = "<p><b>" + esc(t.title) + "</b>: " + esc(t.scenario_override || "") + "</p>" +
        '<textarea rows="2" oninput="TG.groupFixType(' + t.id + ', this.value)" placeholder="What\'s off? Tell me and I\'ll fix it">' + esc(gs.fix || "") + "</textarea>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.groupDone(' + t.id + ')">👍 Keep it</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.groupFix(' + t.id + ')">↻ Fix what I said / another take</button></div>';
    }
    return '<div class="tg-setup"><div class="tg-setup-head">🥔 <b>Bulba</b> · the group</div>' + body + err + "</div>";
  }

  // --- 🧭 Before you start: memory, leave-on-read, who you are in this chat (once per chat) ---
  var startSkipped = {}, startState = {};
  function startCard(t) {
    var st = startState[t.id] || (startState[t.id] = { share: t.share_memory !== false, lor: !!t.leave_on_read,
      own: !!(t.persona && (t.persona.name || t.persona.description)), name: (t.persona || {}).name || "", desc: (t.persona || {}).description || "" });
    var who = t.is_group ? "them" : esc((t.members && t.members[0] && t.members[0].name) || "them");
    var radio = function (name, val, on, label) {
      return '<label class="tg-start-opt' + (on ? " on" : "") + '"><input type="radio" name="' + name + '" ' + (on ? "checked" : "") +
        ' onchange="TG.startSet(' + t.id + ', \'' + name + '\', ' + val + ')">' + label + "</label>";
    };
    return '<div class="tg-setup tg-start" id="tgStart"><div class="tg-setup-head">🧭 <b>Before you start</b></div>' +
      "<p><b>🧠 Memory.</b> Should " + who + " remember what happened in your roleplay chats?</p>" +
      '<div class="tg-start-row">' + radio("share", "true", st.share, "Yes, share story memory") + radio("share", "false", !st.share, "No, texting stands apart") + "</div>" +
      "<p><b>🙈 Realism.</b></p>" +
      '<label class="tg-start-opt' + (st.lor ? " on" : "") + '"><input type="checkbox" ' + (st.lor ? "checked" : "") +
        ' onchange="TG.startSet(' + t.id + ', \'lor\', this.checked)">They can leave me on read now and then (up to 5 minutes, when it fits: busy, teasing, annoyed, petty)</label>' +
      "<p><b>🎭 Who are you here?</b></p>" +
      '<div class="tg-start-row">' + radio("own", "false", !st.own, "My usual persona" + (t.usual_persona ? " (" + esc(t.usual_persona) + ")" : "")) +
        radio("own", "true", st.own, "Someone else, for this chat only") + "</div>" +
      (st.own ? '<input type="text" class="tg-input" placeholder="Name" value="' + esc(st.name) + '" oninput="TG.startSet(' + t.id + ', \'name\', this.value, true)">' +
        '<textarea rows="3" placeholder="Who you are in this chat: age, job, how you know them, anything they should know" oninput="TG.startSet(' + t.id + ', \'desc\', this.value, true)">' + esc(st.desc) + "</textarea>" : "") +
      '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.startSave(' + t.id + ')">Start texting</button>' +
      '<button type="button" class="tg-setup-ghost" onclick="TG.startLater(' + t.id + ')">Later</button></div>' +
      '<p class="tg-card-small">All of it can be changed later in Time & Look.</p></div>';
  }

  // --- 🥔 Bulba's setup: a character who isn't set up for texting yet gets an offer at the top of the chat ---
  var setupState = {};  // slug → {step: offer|busy|review|look|drawing|done, mode, hint, outfit, error}
  function setupSkipped(slug) { try { return localStorage.getItem("na-tg-setup-skip-" + slug) === "1"; } catch (e) { return false; } }
  function bulbaSetupCard(t) {
    var m = (t.members || []).find(function (x) { return !x.set_up && !setupSkipped(x.slug); }) ||
            (t.members || []).find(function (x) { return setupState[x.slug] && setupState[x.slug].step !== "done"; });
    if (!m) return "";
    var st = setupState[m.slug] || (setupState[m.slug] = { step: (m.card_people || []).length > 1 && !t.is_group ? "split" : "offer",
                                                          mode: "modern_au", hint: "", outfit: "" });
    var n = esc(m.name), slug = esc(m.slug), body = "";
    var err = st.error ? '<p class="tg-setup-err">' + esc(st.error) + "</p>" : "";
    if (st.step === "split") {  // ✂️ one contact, one person
      var ppl = m.card_people.map(esc);
      body = "<p><b>" + n + "</b> is a card with " + ppl.length + " people (" + ppl.join(", ") + "). On a phone each of them " +
        "would be their own contact. Want me to split them into " + ppl.length + " characters and start a group chat with all of " +
        "them? Each keeps their own sections; your card stays exactly as it is.</p>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.splitCard(\'' + slug + '\')">✂️ Split into ' + ppl.length + " + a group chat</button>" +
        '<button type="button" class="tg-setup-ghost" onclick="TG.setupStep(\'' + slug + '\', \'offer\')">Keep them as one contact</button></div>';
    } else if (st.step === "splitting") {
      body = "<p>Splitting them up… ✂️</p>";
    } else if (st.step === "offer") {
      body = "<p><b>" + n + "</b> isn't set up for texting yet. Want me to bring them onto a phone? I'll write their @handle, bio, " +
        "how they text, and why you two have each other's number. Their roleplay card stays exactly as it is.</p>" +
        '<div class="tg-setup-modes">' +
          '<button type="button" class="' + (st.mode === "modern_au" ? "on" : "") + '" onclick="TG.setupMode(\'' + slug + '\', \'modern_au\')">🌆 Modern AU<small>today\'s world, a modern job</small></button>' +
          '<button type="button" class="' + (st.mode === "canon" ? "on" : "") + '" onclick="TG.setupMode(\'' + slug + '\', \'canon\')">🏰 Keep their world<small>a phone or communicator there</small></button>' +
        "</div>" +
        '<textarea id="tgSetupHint" rows="2" oninput="TG.setupType(\'' + slug + '\', \'hint\', this.value)" placeholder="Steer it (optional): a scenario, their job now, how you two know each other… Leave it empty and I\'ll suggest one.">' + esc(st.hint) + "</textarea>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.setupRun(\'' + slug + '\')">🥔 Set them up</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.setupSkip(\'' + slug + '\')">Not now</button></div>';
    } else if (st.step === "busy") {
      body = "<p>Thinking about who " + n + " is on a phone… 🥔</p>";
    } else if (st.step === "review") {
      body = "<p>Here's " + n + " for texting:</p><dl class=\"tg-setup-draft\">" +
        "<dt>Handle & bio</dt><dd>" + esc(m.handle || "") + " · " + esc(m.bio || "") + "</dd>" +
        "<dt>Why you text</dt><dd>" + esc(m.scenario || "") + "</dd>" +
        "<dt>Who they are here</dt><dd>" + esc(m.modern_persona || "") + "</dd>" +
        "<dt>How they text</dt><dd>" + esc(m.texting_style || "") + "</dd>" +
        "<dt>How they look</dt><dd>" + esc(m.appearance_notes || "") + "</dd></dl>" +
        (st.notes && st.notes.changes && st.notes.changes.length ? '<p class="tg-setup-sub">Changed from the roleplay card:</p><ul class="tg-setup-list">' +
          st.notes.changes.map(function (c) { return "<li>" + esc(c) + "</li>"; }).join("") + "</ul>" : "") +
        (st.notes && st.notes.questions && st.notes.questions.length ? '<p class="tg-setup-sub">🥔 Your call (answer below, or keep my choice):</p><ul class="tg-setup-list">' +
          st.notes.questions.map(function (q) { return "<li>" + esc(q) + "</li>"; }).join("") + "</ul>" : "") +
        '<textarea id="tgSetupFix" rows="2" oninput="TG.setupType(\'' + slug + '\', \'fix\', this.value)" placeholder="What\'s off? Tell me and I\'ll fix it, e.g. we met at a night pharmacy, not at work">' + esc(st.fix || "") + "</textarea>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.setupKeep(\'' + slug + '\')">👍 Keep it</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.setupFix(\'' + slug + '\')">↻ Fix what I said / another take</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.openBulba()">🥔 Talk it through</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.openDrawer(\'char\')">✏️ Adjust by hand</button></div>';
    } else if (st.step === "look") {
      body = (m.neutral_url
        ? "<p>Now their pictures: the ones they have show their old look. Want me to draw " + n + " for this setup? I'll keep their face from the pictures they have.</p>"
        : "<p>Now their pictures: " + n + " doesn't have any for texting yet. Want me to draw them for this setup, from their description?</p>") +
        '<textarea id="tgSetupOutfit" rows="2" oninput="TG.setupType(\'' + slug + '\', \'outfit\', this.value)" placeholder="Their outfit now (optional), e.g. black turtleneck, a lab coat over it, silver rings">' + esc(st.outfit) + "</textarea>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" onclick="TG.setupDraw(\'' + slug + '\')">🍌 Draw them (2 pictures)</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="TG.setupDone(\'' + slug + '\')">Keep the old pictures</button></div>';
    } else if (st.step === "drawing") {
      body = "<p>Drawing " + n + " in their new look… this takes a minute. 🍌</p>";
    } else if (st.step === "done") {
      body = "<p>All set! " + (m.neutral_url ? '<img class="tg-setup-pic" src="' + esc(m.neutral_url) + '" alt="">' : "") +
        "Say hi, or press 🎲 <b>Let them text</b> and " + n + " goes first.</p>" +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-ghost" onclick="TG.setupClose(\'' + slug + '\')">Close</button></div>';
    }
    return '<div class="tg-setup" id="tgSetup"><div class="tg-setup-head">🥔 <b>Bulba</b></div>' + body + err + "</div>";
  }

  function syncCharCatalog(charSlug, updatedProf) {
    STATE.characters = (STATE.characters || []).map(function (c) {
      return c.slug === charSlug ? Object.assign({}, c, updatedProf) : c;
    });
    if (STATE.active_thread && STATE.active_thread.members) {
      STATE.active_thread.members = STATE.active_thread.members.map(function (m) {
        return m.slug === charSlug ? Object.assign({}, m, updatedProf) : m;
      });
      if (!STATE.active_thread.is_group && STATE.active_thread.members[0] && STATE.active_thread.members[0].slug === charSlug) {
        STATE.active_thread.title = updatedProf.display_name || STATE.active_thread.title;
        STATE.active_thread.subtitle = updatedProf.bio || STATE.active_thread.subtitle;
        STATE.active_thread.handle = updatedProf.handle || STATE.active_thread.handle;
        STATE.active_thread.mode = updatedProf.mode || STATE.active_thread.mode;
      }
    }
  }

  // Expose public handlers on window.TG
  window.TG = {
    switchApp: function (appName) {
      document.querySelectorAll(".dock-app-btn[data-app]").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-app") === appName);
      });
      document.querySelectorAll(".screen-app-view").forEach(function (v) {
        v.classList.toggle("active", v.id === "app-" + appName);
      });
      if (appName === "moments") renderMomentsFeed();
      if (appName === "files") renderHubFilesAndNotes();
    },

    selectThread: function (threadId) {
      apiPost({ action: "load_thread", thread_id: threadId }).then(function (res) {
        STATE.active_thread = res.thread;
        STATE.threads = (STATE.threads || []).map(function (t) {
          return t.id === threadId ? Object.assign({}, t, { unread: 0 }) : t;
        });
        renderSidebar();
        renderActiveThread();
        if (document.getElementById("tgDrawer").classList.contains("open")) {
          renderDrawer();
        }
        document.getElementById("tgSidebar").classList.add("mobile-hidden");
        document.getElementById("tgMain").classList.remove("mobile-hidden");
        if (res.thread.waiting) TG.showTurn(res, (res.thread.messages || []).map(function (m) { return m.id; }));  // 🙈 a late reply on its way
      });
    },

    showMobileSidebar: function () {
      document.getElementById("tgSidebar").classList.remove("mobile-hidden");
      document.getElementById("tgMain").classList.add("mobile-hidden");
    },

    openDrawer: function (tab) {
      currentDrawerTab = tab || "char";
      document.querySelectorAll(".tg-drawer-tab").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-tab") === currentDrawerTab);
      });
      TG.closeBulba();  // one side panel at a time: both squeezed the chat into a sliver
      document.getElementById("tgDrawer").classList.add("open");
      renderDrawerNow();
      document.getElementById("tgDrawer").scrollTop = 0;  // a tab opens at its top
    },

    closeDrawer: function () {
      document.getElementById("tgDrawer").classList.remove("open");
    },

    switchDrawerTab: function (tab) {
      currentDrawerTab = tab;
      document.querySelectorAll(".tg-drawer-tab").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-tab") === tab);
      });
      renderDrawer();
    },

    selectDrawerChar: function (slug) {
      selectedDrawerCharSlug = slug;
      renderDrawer();
    },

    openCharProfile: function (slug) {
      selectedDrawerCharSlug = slug;
      TG.openDrawer("char");
    },

    wrapFormat: function (prefix, suffix) {
      var inp = document.getElementById("tgMessageInput");
      if (!inp) return;
      var start = inp.selectionStart || 0;
      var end = inp.selectionEnd || 0;
      var val = inp.value;
      var selected = val.substring(start, end) || "text";
      inp.value = val.substring(0, start) + prefix + selected + suffix + val.substring(end);
      inp.focus();
    },

    onInputKey: function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        TG.sendUserMessage();
      }
    },

    setReplyTo: function (msgId) {
      var t = STATE.active_thread;
      if (!t) return;
      var m = (t.messages || []).find(function (x) { return x.id === msgId; });
      if (!m) return;
      replyToMsg = m;
      var bar = document.getElementById("tgReplyPreview");
      document.getElementById("tgReplyPreviewSender").textContent = m.sender_name || "Message";
      document.getElementById("tgReplyPreviewText").textContent = (m.text || "Media").substring(0, 90);
      bar.classList.add("visible");
      document.getElementById("tgMessageInput").focus();
    },

    clearReplyTo: function () {
      replyToMsg = null;
      document.getElementById("tgReplyPreview").classList.remove("visible");
    },

    sendUserMessage: function (extraPayload) {
      var t = STATE.active_thread;
      if (!t) return;
      var inp = document.getElementById("tgMessageInput");
      var text = inp ? inp.value.trim() : "";
      var payload = Object.assign(
        {
          action: "send_user_message",
          thread_id: t.id,
          text: text,
          reply_to_id: replyToMsg ? replyToMsg.id : null,
          generate: false,
        },
        extraPayload || {}
      );
      if (!payload.text && !payload.sticker && !payload.file && !payload.photo && !payload.voice) return;
      if (inp && !extraPayload) inp.value = "";
      TG.clearReplyTo();
      TG.toggleStickerTray(false);

      apiPost(payload)
        .then(function (res) {
          STATE.active_thread = res.thread;
          renderActiveThread();
          return TG.triggerAiTurn();
        })
        .catch(function (err) {
          alert(err.message);
        });
    },

    setupMode: function (slug, mode) {
      var st = setupState[slug]; if (!st) return;
      var h = document.getElementById("tgSetupHint"); if (h) st.hint = h.value;
      st.mode = mode; renderActiveThread();
    },
    // 🥔 Bulba for this chat, in a side panel (mainapp/bulba/texting.py); what's applied there shows here at once
    openBulba: function () {
      var t = STATE.active_thread;
      if (!t) return;
      var panel = document.getElementById("tgBulbaPanel"), frame = document.getElementById("tgBulbaFrame");
      var url = window.TG_CFG.bulba.replace(/\/0\/$/, "/" + t.id + "/");
      if (frame.getAttribute("data-thread") !== String(t.id)) { frame.src = url; frame.setAttribute("data-thread", String(t.id)); }
      TG.closeDrawer();  // one side panel at a time
      panel.hidden = false;
      document.body.classList.add("tg-bulba-open");
    },
    closeBulba: function () {
      document.getElementById("tgBulbaPanel").hidden = true;
      document.body.classList.remove("tg-bulba-open");
    },
    // 💾 A save button says how it went: Saving… → ✓ Saved (or the error), and stays where it is
    saving: function (btn, save) {
      var label = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = "Saving…";
      var done = function (ok, msg) {
        var b = document.querySelector('[onclick="' + btn.getAttribute("onclick") + '"]') || btn;  // (the drawer may have redrawn)
        b.disabled = false;
        b.innerHTML = ok ? "✓ Saved" : label;
        b.classList.toggle("tg-saved", ok);
        if (ok) setTimeout(function () { b.innerHTML = label; b.classList.remove("tg-saved"); }, 1800);
        else alert(msg || "That didn't save. Try again.");
      };
      var p;
      try { p = save(); } catch (e) { done(false, e.message); return; }
      if (p && p.then) p.then(function (res) {
        if (res && res.error) done(false, res.error); else done(true);
      }, function (e) { done(false, e && e.message); });
      else done(true);
    },
    // 🔍 Any picture, big: tap (or Esc) to close
    viewImage: function (src) {
      if (!src) return;
      var box = document.getElementById("tgLightbox");
      if (!box) {
        box = document.createElement("div");
        box.id = "tgLightbox";
        box.className = "tg-lightbox";
        box.setAttribute("role", "dialog");
        box.setAttribute("aria-label", "Picture");
        box.innerHTML = '<img alt=""><button type="button" aria-label="Close">✕</button>';
        box.addEventListener("click", function () { box.classList.remove("open"); });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") box.classList.remove("open"); });
        document.body.appendChild(box);
      }
      box.querySelector("img").src = src;
      box.classList.add("open");
    },
    // 📇 Their card: the texting profile on top, the roleplay card at a glance below (character_quick)
    openCard: function (slug) {
      var t = STATE.active_thread; if (!t) return;
      var m = (t.members || []).find(function (x) { return x.slug === slug; }) || (t.members || [])[0];
      if (!m) return;
      var box = document.getElementById("tgCard");
      if (!box) {
        box = document.createElement("div");
        box.id = "tgCard"; box.className = "tg-card-shade";
        box.addEventListener("click", function (e) { if (e.target === box) box.classList.remove("open"); });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") box.classList.remove("open"); });
        document.body.appendChild(box);
      }
      var you = (STATE.user_profile && STATE.user_profile.display_name) || "you";
      var fill = function (x) { return String(x || "").replace(/\{\{user\}\}/gi, you).replace(/\{\{char\}\}/gi, m.name); };
      var row = function (label, text) { return text ? "<dt>" + esc(label) + "</dt><dd>" + esc(fill(text)) + "</dd>" : ""; };
      var pics = [m.neutral_url].concat(m.extra_refs || []).filter(Boolean);
      box.innerHTML = '<div class="tg-card" role="dialog" aria-label="' + esc(m.name) + '">' +
        '<button type="button" class="tg-card-x" onclick="document.getElementById(\'tgCard\').classList.remove(\'open\')" aria-label="Close">✕</button>' +
        '<div class="tg-card-top">' + (m.avatar_url || m.neutral_url ? '<img src="' + esc(m.avatar_url || m.neutral_url) + '" alt="" onclick="TG.viewImage(this.src)">' : '<div class="tg-card-noimg">' + esc((m.name || "?")[0]) + "</div>") +
          '<div><h3>' + esc(m.display_name || m.name) + " " + esc(m.status_emoji || "") + "</h3>" +
          '<div class="tg-card-handle">' + esc(m.handle || "") + ' · <span class="tg-card-mode">' + (m.mode === "modern_au" ? "🌆 Modern AU" : "🏰 Their own world") + "</span>" +
          (m.set_up ? "" : ' · <span class="tg-card-warn">not set up for texting yet</span>') + "</div>" +
          (m.bio ? '<p class="tg-card-bio">' + esc(m.bio) + "</p>" : "") + "</div></div>" +
        '<h4>📱 On the phone</h4><dl class="tg-card-dl">' +
          row("Why you text", m.scenario) + row("Who they are here", m.modern_persona) + row("How they text", m.texting_style) +
          row("How they look", m.appearance_notes) + row("Voice", m.voice_id) + "</dl>" +
        (pics.length ? '<div class="tg-card-pics">' + pics.map(function (u) { return '<img src="' + esc(u) + '" alt="" onclick="TG.viewImage(this.src)">'; }).join("") + "</div>" : "") +
        '<h4>📖 Their roleplay card</h4><div id="tgCardRp" class="tg-card-rp">Loading…</div>' +
        '<div class="tg-card-actions"><button type="button" class="tg-setup-go" onclick="document.getElementById(\'tgCard\').classList.remove(\'open\'); selectedDrawerCharSlugSet(\'' + esc(m.slug) + '\'); TG.openDrawer(\'char\')">⚙️ Edit texting setup</button>' +
        '<button type="button" class="tg-setup-ghost" onclick="document.getElementById(\'tgCard\').classList.remove(\'open\'); TG.openBulba()">🥔 Ask Bulba</button></div>' +
        "</div>";
      box.classList.add("open");
      fetch(window.TG_CFG.quick.replace("__slug__", encodeURIComponent(m.slug)), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (q) {
          var el = document.getElementById("tgCardRp"); if (!el) return;
          if (!q) { el.textContent = "Couldn't load the card."; return; }
          var people = (q.people || []).map(function (p) {
            return "<p><b>" + esc(p.name) + "</b>" + (p.identity ? ": " + esc(p.identity) : "") + "</p>" + (p.temperament ? '<p class="tg-card-small">' + esc(p.temperament) + "</p>" : "");
          }).join("");
          el.innerHTML = (q.tagline ? '<p class="tg-card-bio">' + esc(q.tagline) + "</p>" : "") + people +
            (q.about ? "<p>" + esc(q.about) + "</p>" : "") +
            '<a class="tg-card-link" href="' + esc(q.edit_url) + '" target="_blank" rel="noopener">Open the full card ↗</a>';
        })
        .catch(function () { var el = document.getElementById("tgCardRp"); if (el) el.textContent = "Couldn't load the card."; });
    },

    // 💬 Chat files: every chat with the same character(s), a new one, branches, rename, delete
    openChats: function () {
      var t = STATE.active_thread; if (!t) return;
      var key = (t.members || []).map(function (m) { return m.slug; }).sort().join("|");
      var same = (STATE.threads || []).filter(function (x) { return (x.member_slugs || []).slice().sort().join("|") === key; });
      var box = document.getElementById("tgChats");
      if (!box) {
        box = document.createElement("div");
        box.id = "tgChats"; box.className = "tg-card-shade";
        box.addEventListener("click", function (e) { if (e.target === box) box.classList.remove("open"); });
        document.body.appendChild(box);
      }
      box.innerHTML = '<div class="tg-card tg-chats" role="dialog" aria-label="Chats">' +
        '<button type="button" class="tg-card-x" onclick="document.getElementById(\'tgChats\').classList.remove(\'open\')" aria-label="Close">✕</button>' +
        "<h3>💬 Chats with " + esc(t.is_group ? t.title : (t.members && t.members[0] ? t.members[0].name : t.title)) + "</h3>" +
        '<button type="button" class="tg-setup-go" onclick="TG.newChat()">+ New chat</button>' +
        '<p class="tg-card-small">A new chat starts fresh (their first text again). ⑂ on any message makes a branch: a new chat from that point; the old one stays as it is.</p>' +
        '<div class="tg-chat-files">' + same.map(function (x) {
          return '<div class="tg-chat-file' + (x.id === t.id ? " on" : "") + '">' +
            '<div class="tg-chat-file-main" onclick="document.getElementById(\'tgChats\').classList.remove(\'open\'); TG.selectThread(' + x.id + ')">' +
              "<b>" + (x.branch ? "⑂ " : "") + esc(x.chat_name || x.title) + "</b>" + (x.id === t.id ? ' <span class="tg-card-mode">· open now</span>' : "") +
              "<small>" + esc(x.preview || "") + "</small>" +
              '<small class="tg-card-small">' + esc(x.updated || "") + " · " + (x.count || 0) + " messages</small></div>" +
            '<button type="button" class="tg-fmt-btn" onclick="TG.renameChat(' + x.id + ')" title="Rename">✏️</button>' +
            '<button type="button" class="tg-fmt-btn" style="color:#f87171" onclick="TG.deleteChat(' + x.id + ')" title="Delete">🗑</button></div>';
        }).join("") + "</div></div>";
      box.classList.add("open");
    },
    newChat: function () {
      var t = STATE.active_thread; if (!t) return;
      apiPost({ action: "new_chat", thread_id: t.id }).then(function (res) {
        var box = document.getElementById("tgChats"); if (box) box.classList.remove("open");
        STATE.threads = res.threads; STATE.active_thread = res.thread; renderSidebar(); renderActiveThread();
      }).catch(function (e) { alert(e.message); });
    },
    branchFrom: function (msgId) {
      var t = STATE.active_thread; if (!t) return;
      apiPost({ action: "branch_chat", thread_id: t.id, message_id: msgId }).then(function (res) {
        STATE.threads = res.threads; STATE.active_thread = res.thread; renderSidebar(); renderActiveThread();
      }).catch(function (e) { alert(e.message); });
    },
    renameChat: function (id) {
      var x = (STATE.threads || []).find(function (y) { return y.id === id; }); if (!x) return;
      var name = prompt("A name for this chat:", x.chat_name || x.title);
      if (!name || !name.trim()) return;
      apiPost({ action: "rename_chat", thread_id: id, title: name.trim() }).then(function (res) {
        STATE.threads = res.threads;
        if (STATE.active_thread && STATE.active_thread.id === id) STATE.active_thread = res.thread;
        renderSidebar(); renderActiveThread(); TG.openChats();
      }).catch(function (e) { alert(e.message); });
    },

    startSet: function (id, key, value, quiet) {
      var st = startState[id]; if (!st) return;
      st[key] = value;
      if (!quiet) renderActiveThread();
    },
    startLater: function (id) { startSkipped[id] = true; renderActiveThread(); },
    startSave: function (id) {
      var st = startState[id]; if (!st) return;
      apiPost({ action: "thread_settings", thread_id: id, started: true, share_memory: st.share, leave_on_read: st.lor,
                persona: st.own ? { name: st.name, description: st.desc } : {} })
        .then(function (res) { STATE.active_thread = res.thread; renderActiveThread(); })
        .catch(function (e) { alert(e.message); });
    },
    groupType: function (id, v) { if (groupState[id]) groupState[id].hint = v; },
    groupFixType: function (id, v) { if (groupState[id]) groupState[id].fix = v; },
    groupSkip: function (id) {
      try { localStorage.setItem("na-tg-setup-skip-group-" + id, "1"); } catch (e) { /* this visit */ }
      if (groupState[id]) groupState[id].step = "done";
      renderActiveThread();
    },
    groupDone: function (id) { if (groupState[id]) groupState[id].step = "done"; renderActiveThread(); },
    groupFix: function (id) {
      var gs = groupState[id]; if (!gs) return;
      if ((gs.fix || "").trim()) gs.hint = (gs.hint ? gs.hint + "\n" : "") + "Correction to the last draft: " + gs.fix.trim();
      gs.fix = ""; TG.groupWrite(id);
    },
    groupWrite: function (id) {
      var gs = groupState[id]; if (!gs) return;
      gs.step = "busy"; gs.error = ""; renderActiveThread();
      apiPost({ action: "group_scenario", thread_id: id, hint: gs.hint }).then(function (res) {
        gs.step = "review"; STATE.threads = res.threads; STATE.active_thread = res.thread; renderSidebar(); renderActiveThread();
      }).catch(function (e) { gs.step = "offer"; gs.error = e.message; renderActiveThread(); });
    },
    setupStep: function (slug, step) { var st = setupState[slug]; if (st) { st.step = step; renderActiveThread(); } },
    splitCard: function (slug) {
      var st = setupState[slug]; if (!st) return;
      st.step = "splitting"; st.error = ""; renderActiveThread();
      apiPost({ action: "split_card", char_slug: slug }).then(function (res) {
        delete setupState[slug];
        STATE.threads = res.threads; STATE.active_thread = res.thread; renderSidebar(); renderActiveThread();
      }).catch(function (e) { st.step = "split"; st.error = e.message; renderActiveThread(); });
    },
    // ✨ A character's statuses, like Telegram stories: the picture (made on first view), the text over it; tap
    // the right side for the next one, the left for the one before
    viewStories: function (slug) {
      var c = (STATE.characters || []).find(function (x) { return x.slug === slug; }); if (!c) return;
      var stories = (c.stories || []).slice().reverse();  // oldest first, like a story
      if (!stories.length) return;
      var i = Math.max(0, stories.findIndex(function (s) { return !storySeen(s.id); }));
      var box = document.getElementById("tgStories");
      if (!box) { box = document.createElement("div"); box.id = "tgStories"; box.className = "tg-stories"; document.body.appendChild(box); }
      var show = function () {
        var s = stories[i]; markStorySeen(s.id);
        box.innerHTML = '<div class="tg-stories-bars">' + stories.map(function (x, j) { return '<i class="' + (j < i ? "done" : j === i ? "now" : "") + '"></i>'; }).join("") + "</div>" +
          '<div class="tg-stories-head"><img src="' + esc(c.avatar_url || "") + '" alt=""><b>' + esc(c.display_name || c.name) + "</b><small>" + esc(s.at || "") + "</small>" +
          '<button type="button" aria-label="Close" data-x>✕</button></div>' +
          '<div class="tg-stories-pic">' + (s.image_url ? '<img src="' + esc(s.image_url) + '" alt="">'
            : s.photo_prompt ? '<button type="button" class="tg-setup-go" data-pic>🖼️ Show the picture</button>' : '<div class="tg-stories-emoji">' + esc(s.emoji || "✨") + "</div>") + "</div>" +
          (s.text ? '<div class="tg-stories-text">' + esc(s.emoji || "") + " " + formatMessageHtml(s.text) + "</div>" : "") +
          '<div class="tg-stories-tap prev" data-prev></div><div class="tg-stories-tap next" data-next></div>';
        box.classList.add("open");
        renderStoriesStrip();
      };
      box.onclick = function (e) {
        if (e.target.closest("[data-x]")) { box.classList.remove("open"); return; }
        if (e.target.closest("[data-pic]")) {
          var b = e.target.closest("[data-pic]"); b.disabled = true; b.textContent = "📸 Making the picture…";
          apiPost({ action: "story_picture", owner: slug, story_id: stories[i].id }).then(function (res) {
            stories[i].image_url = res.story.image_url; syncCharCatalog(slug, res.profile); show();
          }).catch(function (err) { b.disabled = false; b.textContent = "🖼️ Show the picture"; alert(err.message); });
          return;
        }
        if (e.target.closest("[data-next]")) { if (i < stories.length - 1) { i++; show(); } else box.classList.remove("open"); }
        else if (e.target.closest("[data-prev]")) { if (i > 0) { i--; show(); } }
      };
      show();
    },

    // 🎨 A picture to send: a photo of you (your persona picture as the reference) or of anything; up to 5
    // references; make it again as often as you like, then send it with a caption
    openMakePicture: function () {
      var t = STATE.active_thread; if (!t) return;
      var mk = TG._mk = TG._mk && TG._mk.thread === t.id ? TG._mk : { thread: t.id, withMe: !!STATE.persona_photo, refs: [], url: "", seen: "", busy: false };
      var box = document.getElementById("tgMake");
      if (!box) {
        box = document.createElement("div"); box.id = "tgMake"; box.className = "tg-card-shade";
        box.addEventListener("click", function (e) { if (e.target === box) box.classList.remove("open"); });
        document.body.appendChild(box);
      }
      var options = [];
      (t.members || []).forEach(function (m) {
        [m.neutral_url].concat(m.extra_refs || []).filter(Boolean).forEach(function (u) { options.push({ url: u, label: m.name }); });
      });
      mk.uploads = mk.uploads || [];
      mk.uploads.forEach(function (u) { options.push({ url: u, label: "yours" }); });
      var count = mk.refs.length + (mk.withMe && STATE.persona_photo ? 1 : 0);
      box.innerHTML = '<div class="tg-card tg-make" role="dialog" aria-label="Make a picture">' +
        '<button type="button" class="tg-card-x" data-x aria-label="Close">✕</button>' +
        "<h3>🎨 Make a picture to send</h3>" +
        '<textarea id="tgMakeDesc" rows="3" placeholder="What the photo shows: me at the bus stop in the rain, holding the umbrella you lent me…">' + esc(mk.desc || "") + "</textarea>" +
        (STATE.persona_photo ? '<label class="tg-start-opt' + (mk.withMe ? " on" : "") + '"><input type="checkbox" data-me ' + (mk.withMe ? "checked" : "") + '> I\'m in it (my persona picture as the reference)</label>'
          : '<p class="tg-card-small">No persona picture yet: add one in your Profile to be in your photos.</p>') +
        '<p class="tg-card-small">References (' + count + " of 5): tap to use. A character's picture puts them in it too.</p>" +
        '<div class="tg-make-refs">' + options.map(function (o) {
          var on = mk.refs.indexOf(o.url) !== -1;
          return '<button type="button" class="tg-make-ref' + (on ? " on" : "") + '" data-ref="' + esc(o.url) + '" title="' + esc(o.label) + '"><img src="' + esc(o.url) + '" alt=""></button>';
        }).join("") +
        '<label class="tg-make-ref tg-make-add" title="Upload a reference">＋<input type="file" accept="image/*" hidden data-up></label></div>' +
        '<div class="tg-make-preview">' + (mk.busy ? "<p>📸 Making the picture…</p>" : mk.url ? '<img src="' + esc(mk.url) + '" alt="" onclick="TG.viewImage(this.src)">' : "") + "</div>" +
        (mk.url ? '<input type="text" class="tg-input" id="tgMakeCaption" placeholder="A caption (optional)" value="' + esc(mk.caption || "") + '">' : "") +
        '<div class="tg-setup-row"><button type="button" class="tg-setup-go" data-make ' + (mk.busy ? "disabled" : "") + ">" + (mk.url ? "↻ Make it again" : "🎨 Make it") + "</button>" +
        (mk.url ? '<button type="button" class="tg-setup-go" data-send>Send ➤</button>' : "") + "</div></div>";
      box.classList.add("open");
      box.onclick = function (e) {
        var d = document.getElementById("tgMakeDesc"); if (d) mk.desc = d.value;
        var c = document.getElementById("tgMakeCaption"); if (c) mk.caption = c.value;
        if (e.target === box || e.target.closest("[data-x]")) { box.classList.remove("open"); return; }
        var r = e.target.closest("[data-ref]");
        if (r) {
          var u = r.getAttribute("data-ref"), at = mk.refs.indexOf(u);
          if (at !== -1) mk.refs.splice(at, 1); else if (count < 5) mk.refs.push(u);
          return TG.openMakePicture();
        }
        if (e.target.closest("[data-make]")) {
          if (!(mk.desc || "").trim()) return alert("Describe the picture first.");
          mk.busy = true; TG.openMakePicture();
          apiPost({ action: "user_picture", thread_id: t.id, prompt: mk.desc, refs: mk.refs, with_me: mk.withMe })
            .then(function (res) { mk.busy = false; mk.url = res.url; mk.seen = res.seen; TG.openMakePicture(); })
            .catch(function (err) { mk.busy = false; TG.openMakePicture(); alert(err.message); });
          return;
        }
        if (e.target.closest("[data-send]")) {
          box.classList.remove("open");
          TG.sendUserMessage({ text: "", photo: { kind: "generated", url: mk.url, caption: mk.caption || "", seen: mk.seen, prompt: mk.desc } });
          TG._mk = null;
        }
      };
      box.onchange = function (e) {
        if (e.target.matches("[data-me]")) { mk.withMe = e.target.checked; return TG.openMakePicture(); }
        if (e.target.matches("[data-up]") && e.target.files[0]) {
          var fd = new FormData(); fd.append("kind", "image"); fd.append("file", e.target.files[0]);
          fetch(window.TG_CFG.api, { method: "POST", headers: { "X-CSRFToken": window.TG_CFG.csrf }, body: fd })
            .then(function (r) { return r.json(); })
            .then(function (res) { if (res.error) throw new Error(res.error); mk.uploads.push(res.url); if (count < 5) mk.refs.push(res.url); TG.openMakePicture(); })
            .catch(function (err) { alert(err.message); });
        }
      };
    },

    makeOneRef: function (slot, btn) {
      var slug = selectedDrawerCharSlug; if (!slug) return;
      if (btn) { btn.disabled = true; btn.textContent = "⏳"; }
      apiPost({ action: "one_reference", char_slug: slug, slot: slot }).then(function (res) {
        syncCharCatalog(res.char_slug, res.profile); renderSidebar(); renderActiveThread(); renderDrawer();
      }).catch(function (e) { if (btn) { btn.disabled = false; btn.textContent = slot < 0 ? "✨" : "✨"; } alert(e.message); });
    },
    // 🎨 A sticker pack in their texting look, one sticker at a time (stoppable; a sticker can be redone)
    makeStickerPack: function () {
      var t = STATE.active_thread; if (!t) return;
      var m = (t.members || [])[0]; if (!m) return;
      if (TG._packBusy) { TG._packBusy = false; return; }  // a second press stops it
      var moods = ["happy", "smug", "angry", "sleepy", "shocked", "love", "crying", "thumbs up"];
      var have = (m.sticker_pack || []).map(function (s) { return s.mood; });
      var todo = moods.filter(function (x) { return have.indexOf(x) === -1; });
      if (!todo.length) {
        var redo = prompt("Their pack is complete. Redo one? Type its mood (" + moods.join(", ") + "):", "");
        if (!redo) return; todo = [redo.trim().toLowerCase()];
      } else if (!confirm("Draw " + todo.length + " stickers of " + m.name + " in their texting look? About a few cents each. Press 🎨 again to stop.")) return;
      var st = document.getElementById("tgStickerStatus"); st.hidden = false;
      TG._packBusy = true;
      var i = 0;
      (function next() {
        if (!TG._packBusy || i >= todo.length) { TG._packBusy = false; st.textContent = "🎨 Done: " + i + " sticker" + (i === 1 ? "" : "s") + "."; return; }
        st.textContent = "🎨 Drawing “" + todo[i] + "” (" + (i + 1) + " of " + todo.length + ")… press 🎨 to stop";
        apiPost({ action: "make_sticker", char_slug: m.slug, mood: todo[i] }).then(function (res) {
          syncCharCatalog(res.char_slug, res.profile);
          t.stickers = (t.stickers || []).filter(function (s) { return s.char_slug !== res.char_slug; }).concat(res.stickers);
          renderStickerTray(); i++; next();
        }).catch(function (e) { TG._packBusy = false; st.textContent = "Stopped at “" + todo[i] + "”: " + e.message; });
      })();
    },
    importTelegramPack: function () {
      var link = prompt("A Telegram sticker pack link (t.me/addstickers/…):", "");
      if (!link || !link.trim()) return;
      var st = document.getElementById("tgStickerStatus"); st.hidden = false; st.textContent = "📥 Fetching the pack…";
      apiPost({ action: "telegram_pack", link: link.trim() }).then(function (res) {
        STATE.user_profile = res.user_profile;
        var mine = res.user_profile.custom_stickers || [];
        if (STATE.active_thread) STATE.active_thread.stickers = (STATE.active_thread.stickers || []).filter(function (s) { return !/^custom_|^tg_/.test(s.id || ""); }).concat(mine);
        renderStickerTray();
        st.textContent = "📥 “" + res.title + "”: " + res.added + " stickers added" + (res.skipped ? ", " + res.skipped + " animated ones skipped (they need a special player)" : "") + ".";
      }).catch(function (e) { st.textContent = "📥 " + e.message; });
    },
    watchSkip: function () {
      var t = STATE.active_thread; if (!t || !t.watch) return;
      try { localStorage.setItem("na-tg-watch-" + t.watch.message_id, "1"); } catch (e) { /* this view */ }
      t.watch = null; renderActiveThread();
    },
    watchFix: function () {
      var t = STATE.active_thread; if (!t || !t.watch) return;
      var wn = t.watch; t.watch = null; renderActiveThread();
      apiPost({ action: "redo_message", thread_id: t.id, message_id: wn.message_id, note: wn.note })
        .then(function (res) { STATE.active_thread = res.thread; renderActiveThread(); })
        .catch(function (e) { alert(e.message); });
    },
    updateMemory: function (btn) {
      var t = STATE.active_thread; if (!t) return;
      if (btn) { btn.disabled = true; btn.textContent = "🧠 Updating…"; }
      apiPost({ action: "update_memory", thread_id: t.id, now: true }).then(function (res) {
        STATE.active_thread = res.thread;
        var box = document.getElementById("drwThreadMemory"); if (box) box.value = res.memory || "";
        if (btn) { btn.disabled = false; btn.textContent = "✓ Updated"; }
      }).catch(function (e) { if (btn) { btn.disabled = false; btn.textContent = "🧠 Update it now"; } alert(e.message); });
    },
    setClock: function (how) {
      var t = STATE.active_thread; if (!t || !how) return;
      apiPost({ action: "thread_settings", thread_id: t.id, clock: how }).then(function (res) {
        STATE.active_thread = res.thread; renderActiveThread(); renderDrawer();
      }).catch(function (e) { alert(e.message); });
    },
    setupType: function (slug, key, value) { if (setupState[slug]) setupState[slug][key] = value; },
    setupSkip: function (slug) {
      try { localStorage.setItem("na-tg-setup-skip-" + slug, "1"); } catch (e) { /* this visit only */ }
      delete setupState[slug]; renderActiveThread();
    },
    setupRun: function (slug) {
      var st = setupState[slug]; if (!st) return;
      var h = document.getElementById("tgSetupHint"); if (h) st.hint = h.value;
      st.step = "busy"; st.error = ""; renderActiveThread();
      apiPost({ action: "modernize_bulba", char_slug: slug, mode: st.mode, hint: st.hint })
        .then(function (res) {
          if (res.error) throw new Error(res.error);
          st.notes = res.profile.setup_notes || {};
          syncCharCatalog(res.char_slug, Object.assign({}, res.profile, { set_up: true }));
          st.step = "review"; renderSidebar(); renderActiveThread();
        })
        .catch(function (e) { st.step = "offer"; st.error = e.message; renderActiveThread(); });
    },
    setupFix: function (slug) {  // what they said is off joins their directions, then Bulba writes it again
      var st = setupState[slug]; if (!st) return;
      var f = document.getElementById("tgSetupFix"), fix = (f ? f.value : st.fix || "").trim();
      if (fix) st.hint = (st.hint ? st.hint + "\n" : "") + "Correction to the last draft: " + fix;
      st.fix = "";
      TG.setupRun(slug);
    },
    setupKeep: function (slug) { var st = setupState[slug]; if (st) { st.step = "look"; renderActiveThread(); } },
    setupDraw: function (slug) {
      var st = setupState[slug]; if (!st) return;
      var o = document.getElementById("tgSetupOutfit"); if (o) st.outfit = o.value;
      st.step = "drawing"; st.error = ""; renderActiveThread();
      apiPost({ action: "setup_look", char_slug: slug, outfit: st.outfit })
        .then(function (res) {
          if (res.error) throw new Error(res.error);
          syncCharCatalog(res.char_slug, res.profile);
          st.step = "done"; renderSidebar(); renderActiveThread();
        })
        .catch(function (e) { st.step = "look"; st.error = e.message; renderActiveThread(); });
    },
    setupDone: function (slug) { var st = setupState[slug]; if (st) { st.step = "done"; renderActiveThread(); } },
    setupClose: function (slug) { delete setupState[slug]; renderActiveThread(); },

    openRedo: function (msgId) {
      redoFor = redoFor === msgId ? null : msgId;
      renderActiveThread();
      var box = document.getElementById("tgRedo");
      if (box) { box.scrollIntoView({ block: "nearest" }); var i = document.getElementById("tgRedoNote"); if (i) i.focus(); }
    },
    redoPick: function (btn) {
      var inp = document.getElementById("tgRedoNote");
      if (inp) { inp.value = inp.value.trim() ? inp.value.trim() + " " + btn.getAttribute("data-note") : btn.getAttribute("data-note"); inp.focus(); }
    },
    redoMessage: function (msgId) {
      var t = STATE.active_thread; if (!t) return;
      var inp = document.getElementById("tgRedoNote"), box = document.getElementById("tgRedo");
      if (box) box.classList.add("busy");
      apiPost({ action: "redo_message", thread_id: t.id, message_id: msgId, note: inp ? inp.value.trim() : "" })
        .then(function (res) { redoFor = null; STATE.active_thread = res.thread; renderActiveThread(); })
        .catch(function (e) { if (box) box.classList.remove("busy"); alert(e.message); });
    },
    redoPhoto: function (msgId) {
      var t = STATE.active_thread; if (!t) return;
      var m = (t.messages || []).find(function (x) { return x.id === msgId; }); if (!m || !m.photo) return;
      var inp = document.getElementById("tgRedoNote"), note = inp ? inp.value.trim() : "", box = document.getElementById("tgRedo");
      if (box) box.classList.add("busy");
      var prompt = (m.photo.prompt || "") + (note ? " " + note : "");
      apiPost({ action: "photo_bubble", thread_id: t.id, message_id: msgId, kind: m.photo.kind || "casual", prompt: prompt })
        .then(function (res) {
          var idx = t.messages.findIndex(function (x) { return x.id === msgId; });
          if (idx !== -1 && res.message) t.messages[idx] = res.message;
          redoFor = null; renderActiveThread();
        })
        .catch(function (e) { if (box) box.classList.remove("busy"); alert(e.message); });
    },

    toggleRegen: function () {
      var box = document.querySelector("#tgRegen .tg-regen-box");
      if (!box) return;
      box.hidden = !box.hidden;
      if (!box.hidden) { var inp = document.getElementById("tgRegenNote"); if (inp) inp.focus(); }
      box.scrollIntoView({ block: "nearest" });
    },

    regenPick: function (btn) {
      var inp = document.getElementById("tgRegenNote");
      if (!inp) return;
      var add = btn.getAttribute("data-note");
      inp.value = inp.value.trim() ? inp.value.trim() + " " + add : add;
      inp.focus();
    },

    regenerate: function () {
      var t = STATE.active_thread;
      if (!t) return;
      var inp = document.getElementById("tgRegenNote"), note = inp ? inp.value.trim() : "";
      var typRow = document.getElementById("tgTypingRow"), typTxt = document.getElementById("tgTypingText");
      if (typRow) { typTxt.textContent = t.title + " is typing again…"; typRow.classList.add("visible"); }
      var box = document.getElementById("tgRegen");
      if (box) box.classList.add("busy");
      var keep = (t.messages || []).map(function (m) { return m.id; });
      return apiPost({ action: "regenerate", thread_id: t.id, note: note })
        .then(function (res) {
          if (typRow) typRow.classList.remove("visible");
          return TG.showTurn(res, keep);
        })
        .catch(function (err) {
          if (typRow) typRow.classList.remove("visible");
          if (box) box.classList.remove("busy");
          STATE.failed = { thread: t.id, error: err.message, regen: true };
          renderActiveThread();
        });
    },

    // 💬 A turn's new messages arrive one by one (typing… → message → a pause), and a reply left on read later
    showTurn: function (res, oldIds) {
      if (res.thread && res.thread.memory_due) {  // 🧠 quietly bring the chat's memory up to date
        apiPost({ action: "update_memory", thread_id: res.thread.id }).catch(function () { /* next time */ });
      }
      var full = res.thread, fresh = (full.messages || []).filter(function (m) { return m.role !== "user" && oldIds.indexOf(m.id) === -1; });
      if (res.threads) STATE.threads = res.threads;
      clearTimeout(TG._waitTimer);
      if (full.waiting) {  // 🙈 left on read: their reply arrives on its own (we look again when it's due)
        var tid = full.id;
        TG._waitTimer = setTimeout(function () {
          if (!STATE.active_thread || STATE.active_thread.id !== tid) return;
          var before = (STATE.active_thread.messages || []).map(function (m) { return m.id; });
          apiPost({ action: "load_thread", thread_id: tid }).then(function (r) { TG.showTurn(r, before); });
        }, full.waiting * 1000 + 500);
      }
      var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (fresh.length < 2 || calm) {
        STATE.active_thread = full; renderSidebar(); renderActiveThread(); return Promise.resolve();
      }
      var shown = (full.messages || []).filter(function (m) { return fresh.indexOf(m) === -1; });
      STATE.active_thread = Object.assign({}, full, { messages: shown.slice() });
      renderSidebar(); renderActiveThread();
      var typRow = document.getElementById("tgTypingRow"), typTxt = document.getElementById("tgTypingText");
      var i = 0;
      return new Promise(function (done) {
        (function next() {
          if (!STATE.active_thread || STATE.active_thread.id !== full.id) return done();
          if (i >= fresh.length) { if (typRow) typRow.classList.remove("visible"); STATE.active_thread = full; renderActiveThread(); return done(); }
          var m = fresh[i], len = ((m.voice && m.voice.transcript) || m.text || "").length;
          var typing = i === 0 ? 250 : Math.min(3200, 600 + len * 32);
          if (typRow && i > 0) { typTxt.textContent = (m.voice ? "🎤 recording a voice note…" : m.photo ? "📷 sending a photo…" : (m.sender_name || full.title) + " is typing…"); typRow.classList.add("visible"); }
          setTimeout(function () {
            if (typRow) typRow.classList.remove("visible");
            STATE.active_thread.messages.push(m);
            renderActiveThread();
            i += 1;
            setTimeout(next, 350 + Math.random() * 500);  // a breath before the next one
          }, typing);
        })();
      });
    },

    triggerAiTurn: function (instruction) {
      var t = STATE.active_thread;
      if (!t) return;
      var typRow = document.getElementById("tgTypingRow");
      var typTxt = document.getElementById("tgTypingText");
      if (typRow) {
        typTxt.textContent = t.title + " is typing…";
        typRow.classList.add("visible");
      }
      var oldIds = (t.messages || []).map(function (m) { return m.id; });
      return apiPost({
        action: "generate_reply",
        thread_id: t.id,
        instruction: instruction || "",
      })
        .then(function (res) {
          if (typRow) typRow.classList.remove("visible");
          STATE.failed = null;
          return TG.showTurn(res, oldIds);
        })
        .catch(function (err) {
          if (typRow) typRow.classList.remove("visible");
          STATE.failed = { thread: t.id, error: err.message, instruction: instruction || "" };
          renderActiveThread();
        });
    },

    retryFailed: function () {
      var f = STATE.failed; if (!f) return;
      STATE.failed = null;
      renderActiveThread();
      if (f.regen) return TG.regenerate();
      return TG.triggerAiTurn(f.instruction);
    },

    toggleStickerTray: function (force) {
      var tray = document.getElementById("tgStickerTray");
      if (!tray) return;
      if (typeof force === "boolean") {
        tray.classList.toggle("open", force);
      } else {
        tray.classList.toggle("open");
      }
    },

    sendStickerByIndex: function (idx) {
      var t = STATE.active_thread;
      if (!t) return;
      var list = t.stickers || STATE.built_in_stickers;
      var st = list[idx];
      if (!st) return;
      TG.sendUserMessage({ text: "", sticker: st });
    },

    uploadCustomSticker: function (input) {
      if (!input.files || !input.files[0]) return;
      var fd = new FormData();
      fd.append("kind", "sticker");
      fd.append("file", input.files[0]);
      fetch(window.TG_CFG.api, {
        method: "POST",
        headers: { "X-CSRFToken": window.TG_CFG.csrf },
        body: fd,
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.error) throw new Error(res.error);
          STATE.user_profile.custom_stickers = STATE.user_profile.custom_stickers || [];
          STATE.user_profile.custom_stickers.push(res.sticker);
          if (STATE.active_thread) {
            STATE.active_thread.stickers = STATE.active_thread.stickers || [];
            STATE.active_thread.stickers.push(res.sticker);
          }
          renderStickerTray();
        })
        .catch(function (e) { alert(e.message); });
    },

    handleMediaUpload: function (input) {
      if (!input.files || !input.files[0]) return;
      var f = input.files[0];
      var isImg = f.type.indexOf("image/") === 0;
      var fd = new FormData();
      fd.append("kind", isImg ? "image" : "file");
      fd.append("file", f);
      fetch(window.TG_CFG.api, {
        method: "POST",
        headers: { "X-CSRFToken": window.TG_CFG.csrf },
        body: fd,
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.error) throw new Error(res.error);
          if (isImg) {
            TG.sendUserMessage({
              text: "",
              photo: { kind: "upload", url: res.url, caption: document.getElementById("tgMessageInput").value.trim(), prompt: f.name },
            });
            document.getElementById("tgMessageInput").value = "";
          } else {
            var said = document.getElementById("tgMessageInput").value.trim();  // what they typed goes with it
            TG.sendUserMessage({
              text: said,
              file: { name: res.name, size: res.size, content: res.content || "Uploaded file: " + res.url },
            });
            document.getElementById("tgMessageInput").value = "";
          }
        })
        .catch(function (e) { alert(e.message); });
    },

    // 🎤 A real voice note: tap to record, tap again to send. It's turned into words (Scribe) so the character
    // can read it; the recording plays in the chat. No microphone (blocked, or none): typed instead.
    toggleRecording: function () {
      var btn = document.getElementById("tgMicBtn");
      if (TG._rec && TG._rec.state === "recording") { TG._rec.stop(); return; }
      if (!navigator.mediaDevices || !window.MediaRecorder) return TG.sendVoiceNotePrompt();
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        var chunks = [], started = Date.now(), rec = new MediaRecorder(stream);
        TG._rec = rec;
        rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        rec.onstop = function () {
          stream.getTracks().forEach(function (tr) { tr.stop(); });
          btn.classList.remove("recording"); btn.textContent = "🎤";
          var secs = Math.round((Date.now() - started) / 1000);
          if (secs < 1 || !chunks.length) return;
          var type = rec.mimeType || "audio/webm", ext = type.indexOf("mp4") !== -1 ? "m4a" : type.indexOf("ogg") !== -1 ? "ogg" : "webm";
          var fd = new FormData();
          fd.append("kind", "voice_rec");
          fd.append("file", new Blob(chunks, { type: type }), "voice." + ext);
          btn.disabled = true; btn.textContent = "⏳";
          fetch(window.TG_CFG.api, { method: "POST", headers: { "X-CSRFToken": window.TG_CFG.csrf }, body: fd })
            .then(function (r) { return r.json(); })
            .then(function (res) {
              btn.disabled = false; btn.textContent = "🎤";
              if (res.error) throw new Error(res.error);
              TG.sendUserMessage({ text: res.transcript, voice: { transcript: res.transcript, audio_url: res.url, duration: Math.max(1, secs) } });
            })
            .catch(function (e) { btn.disabled = false; btn.textContent = "🎤"; alert(e.message); });
        };
        rec.start();
        btn.classList.add("recording"); btn.textContent = "⏹";
        btn.title = "Recording… tap to send";
      }).catch(function () { TG.sendVoiceNotePrompt(); });
    },

    sendVoiceNotePrompt: function () {
      var transcript = prompt("Speak / type your voice message transcript:");
      if (!transcript || !transcript.trim()) return;
      TG.sendUserMessage({
        text: transcript.trim(),
        voice: {
          transcript: transcript.trim(),
          audio_url: "",
          duration: Math.max(2, Math.min(45, Math.ceil(transcript.trim().split(/\s+/).length / 2))),
        },
      });
    },

    toggleTranscript: function (msgId) {
      var box = document.getElementById("transcript-" + msgId);
      if (!box) return;
      box.style.display = box.style.display === "none" ? "block" : "none";
    },

    playVoiceBubble: function (msgId, btn) {
      var t = STATE.active_thread;
      if (!t) return;
      var m = (t.messages || []).find(function (x) { return x.id === msgId; });
      if (!m) return;

      if (activeAudio && activeAudioMsgId === msgId) {
        activeAudio.pause();
        activeAudio = null;
        activeAudioMsgId = null;
        renderActiveThread();
        return;
      }

      var playUrl = function (url) {
        if (activeAudio) activeAudio.pause();
        activeAudio = new Audio(url);
        activeAudioMsgId = msgId;
        renderActiveThread();
        activeAudio.onended = function () {
          activeAudio = null;
          activeAudioMsgId = null;
          renderActiveThread();
        };
        activeAudio.play().catch(function (e) {
          activeAudio = null;
          activeAudioMsgId = null;
          alert("Couldn't play audio: " + e.message);
        });
      };

      if (m.voice && m.voice.audio_url) {
        playUrl(m.voice.audio_url);
        return;
      }

      var origText = btn ? btn.textContent : "";
      if (btn) btn.textContent = "⏳";
      apiPost({ action: "voice_bubble", thread_id: t.id, message_id: msgId })
        .then(function (res) {
          m.voice = res.message.voice;
          playUrl(res.audio_url);
        })
        .catch(function (e) {
          if (btn) btn.textContent = origText;
          alert(e.message);
        });
    },

    renderBubblePhoto: function (msgId, kind, btn) {
      var t = STATE.active_thread;
      if (!t) return;
      var orig = btn ? btn.textContent : "";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "📸 Making the picture…";
      }
      apiPost({ action: "photo_bubble", thread_id: t.id, message_id: msgId, kind: kind || "casual" })
        .then(function (res) {
          var idx = (t.messages || []).findIndex(function (x) { return x.id === msgId; });
          if (idx !== -1) t.messages[idx] = res.message;
          renderActiveThread();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    reactMessage: function (msgId, emoji) {
      var t = STATE.active_thread;
      if (!t) return;
      apiPost({ action: "react", thread_id: t.id, message_id: msgId, emoji: emoji }).then(function (res) {
        var m = (t.messages || []).find(function (x) { return x.id === msgId; });
        if (m) m.reactions = res.reactions;
        renderActiveThread();
      });
    },

    pinMessage: function (msgId) {
      var t = STATE.active_thread;
      if (!t) return;
      apiPost({ action: "pin_message", thread_id: t.id, message_id: msgId }).then(function (res) {
        t.pinned_id = res.pinned_id;
        renderActiveThread();
      });
    },

    unpinMessage: function () {
      var t = STATE.active_thread;
      if (!t || !t.pinned_id) return;
      TG.pinMessage(t.pinned_id);
    },

    scrollToPinned: function () {
      var t = STATE.active_thread;
      if (t && t.pinned_id) TG.scrollToMsg(t.pinned_id);
    },

    scrollToMsg: function (msgId) {
      var el = document.getElementById("msg-" + msgId);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    },

    editMessagePrompt: function (msgId) {
      var t = STATE.active_thread;
      if (!t) return;
      var m = (t.messages || []).find(function (x) { return x.id === msgId; });
      if (!m) return;
      var next = prompt("Edit message:", m.text || "");
      if (next == null || !next.trim()) return;
      apiPost({ action: "edit_message", thread_id: t.id, message_id: msgId, text: next.trim() }).then(function (res) {
        var idx = t.messages.findIndex(function (x) { return x.id === msgId; });
        if (idx !== -1) t.messages[idx] = res.message;
        renderActiveThread();
      });
    },

    deleteMessage: function (msgId) {
      var t = STATE.active_thread;
      if (!t) return;
      apiPost({ action: "delete_message", thread_id: t.id, message_id: msgId }).then(function (res) {
        t.messages = (t.messages || []).filter(function (x) { return x.id !== msgId; });
        t.pinned_id = res.pinned_id;
        renderActiveThread();
      });
    },

    runBulbaModernize: function (mode, btn) {
      var slug = selectedDrawerCharSlug || (STATE.active_thread && STATE.active_thread.members && STATE.active_thread.members[0] && STATE.active_thread.members[0].slug);
      if (!slug) return;
      var hint = (document.getElementById("drwBulbaHint") || {}).value || "";
      var orig = btn ? btn.textContent : "";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "🥔 Bulba is writing…";
      }
      apiPost({
        action: "modernize_bulba",
        char_slug: slug,
        mode: mode,
        hint: hint,
        save: true,
      })
        .then(function (res) {
          syncCharCatalog(slug, res.profile);
          renderSidebar();
          renderActiveThread();
          renderDrawer();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    saveCharProfile: function () {  // (returns the request: saving() shows how it went)
      var slug = selectedDrawerCharSlug;
      if (!slug) return;
      var voiceInp = document.getElementById("drwCharVoiceCustom");
      var voicePreset = document.getElementById("drwCharVoicePreset");
      var chosenVoice = (voiceInp && voiceInp.value.trim()) || (voicePreset && voicePreset.value) || "";
      var profile = {
        mode: document.getElementById("drwCharMode").value,
        display_name: document.getElementById("drwCharName").value,
        status_emoji: document.getElementById("drwCharEmoji").value,
        handle: document.getElementById("drwCharHandle").value,
        bio: document.getElementById("drwCharBio").value,
        modern_persona: document.getElementById("drwCharPersona").value,
        texting_style: document.getElementById("drwCharStyle").value,
        scenario: document.getElementById("drwCharScenario").value,
        appearance_notes: (document.getElementById("drwCharAppearance") || {}).value || "",
        art_style_notes: (document.getElementById("drwCharArtStyle") || {}).value || "",
        voice_id: chosenVoice,
        voice_model: (document.getElementById("drwCharVoiceModel") || {}).value || "elevenlabs/eleven-v4-turbo",
        share_memory: document.getElementById("drwCharMemory").checked,
      };
      return apiPost({
        action: "char_profile",
        char_slug: slug,
        thread_id: STATE.active_thread ? STATE.active_thread.id : null,
        profile: profile,
      }).then(function (res) {
        syncCharCatalog(slug, res.profile);
        renderSidebar();
        renderActiveThread();
        renderDrawer();
      });
    },

    triggerRefUpload: function (kind, slot) {
      var inp = document.getElementById("drwRefUploadInput");
      if (!inp) return;
      inp.setAttribute("data-kind", kind);
      inp.setAttribute("data-slot", String(slot));
      inp.value = "";
      inp.click();
    },

    handleRefUploadFile: function (input) {
      if (!input.files || !input.files[0] || !selectedDrawerCharSlug) return;
      var fd = new FormData();
      fd.append("kind", input.getAttribute("data-kind") || "char_extra_ref");
      fd.append("char_slug", selectedDrawerCharSlug);
      fd.append("slot", input.getAttribute("data-slot") || "-1");
      fd.append("file", input.files[0]);
      fetch(window.TG_CFG.api, {
        method: "POST",
        headers: { "X-CSRFToken": window.TG_CFG.csrf },
        body: fd,
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res.error) throw new Error(res.error);
          syncCharCatalog(res.char_slug, res.profile);
          renderSidebar();
          renderActiveThread();
          renderDrawer();
        })
        .catch(function (e) { alert(e.message); });
    },

    removeExtraRef: function (slotIdx) {
      var slug = selectedDrawerCharSlug;
      if (!slug) return;
      var cur = (STATE.characters || []).find(function (c) { return c.slug === slug; });
      if (!cur) return;
      var nextRefs = (cur.extra_refs || []).slice();
      nextRefs.splice(slotIdx, 1);
      apiPost({
        action: "char_profile",
        char_slug: slug,
        profile: { extra_refs: nextRefs },
      }).then(function (res) {
        syncCharCatalog(slug, res.profile);
        renderDrawer();
      });
    },

    generateCharRefsFromDesc: function (btn) {
      var slug = selectedDrawerCharSlug;
      if (!slug) return;
      var appNotes = (document.getElementById("drwCharAppearance") || {}).value || "";
      var styleNotes = (document.getElementById("drwCharArtStyle") || {}).value || "";
      var orig = btn ? btn.textContent : "";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "🍌 Generating Neutral + Reference Pics…";
      }
      apiPost({
        action: "generate_char_refs",
        char_slug: slug,
        count: 2,
        profile: {
          appearance_notes: appNotes,
          art_style_notes: styleNotes,
        },
      })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          syncCharCatalog(slug, res.profile);
          renderSidebar();
          renderActiveThread();
          renderDrawer();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    previewSelectedVoice: function (btn) {
      var voiceInp = document.getElementById("drwCharVoiceCustom");
      var voicePreset = document.getElementById("drwCharVoicePreset");
      var vid = (voiceInp && voiceInp.value.trim()) || (voicePreset && voicePreset.value) || "sarah";
      var vModel = (document.getElementById("drwCharVoiceModel") || {}).value || "elevenlabs/eleven-v4-turbo";
      var orig = btn ? btn.textContent : "🔊 Preview";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳…";
      }
      apiPost({
        action: "preview_voice",
        voice_id: vid,
        voice_model: vModel,
      })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          if (activeAudio) activeAudio.pause();
          activeAudio = new Audio(res.audio_url);
          activeAudio.play().catch(function (e) {
            alert("Could not play voice preview: " + e.message);
          });
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    openCreateCharModal: function () {
      document.getElementById("createCharName").value = "";
      document.getElementById("createCharIdea").value = "";
      document.getElementById("createCharGenPics").checked = false;
      document.getElementById("modalCreateChar").classList.add("open");
    },

    submitCreateCharBulba: function () {
      var name = document.getElementById("createCharName").value.trim();
      var mode = document.getElementById("createCharMode").value;
      var idea = document.getElementById("createCharIdea").value.trim();
      var genPics = document.getElementById("createCharGenPics").checked;
      if (!name && !idea) {
        alert("Give Bulba at least a character name or concept description.");
        return;
      }
      var btn = document.getElementById("createCharSubmitBtn");
      var orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = genPics ? "🥔 Bulba + 🍌 Nano Banana working…" : "🥔 Bulba is creating character…";
      apiPost({
        action: "create_char_bulba",
        name: name,
        mode: mode,
        idea: idea,
        generate_pics: genPics,
      })
        .then(function (res) {
          btn.disabled = false;
          btn.textContent = orig;
          STATE.characters = STATE.characters || [];
          STATE.characters.unshift(res.character);
          STATE.threads = res.threads;
          STATE.active_thread = res.thread;
          selectedDrawerCharSlug = res.character.slug;
          TG.closeModals();
          renderSidebar();
          renderActiveThread();
          if (document.getElementById("tgDrawer").classList.contains("open")) {
            renderDrawer();
          }
        })
        .catch(function (e) {
          btn.disabled = false;
          btn.textContent = orig;
          alert(e.message);
        });
    },

    saveThreadSettings: function () {  // (returns the request: saving() shows how it went)
      var t = STATE.active_thread;
      if (!t) return;
      return apiPost({
        action: "thread_settings",
        thread_id: t.id,
        bg: document.getElementById("drwThreadBg").value,
        custom_bg_url: document.getElementById("drwThreadCustomBg").value,
        title: document.getElementById("drwThreadTitle").value,
        scenario_override: document.getElementById("drwThreadScenario").value,
        leave_on_read: !!(document.getElementById("drwThreadLeaveOnRead") || {}).checked,
        share_memory: !!(document.getElementById("drwThreadShare") || {}).checked,
        memory: (document.getElementById("drwThreadMemory") || {}).value || "",
        context_size: parseInt((document.getElementById("drwThreadContext") || {}).value || "30", 10),
        theme: (document.getElementById("drwThreadTheme") || {}).value || "",
        persona: { name: (document.getElementById("drwThreadPersonaName") || {}).value || "",
                   description: (document.getElementById("drwThreadPersonaDesc") || {}).value || "" },
        events: t.events || [],
      }).then(function (res) {
        STATE.active_thread = res.thread;
        STATE.threads = (STATE.threads || []).map(function (x) {
          return x.id === t.id ? Object.assign({}, x, { title: res.thread.title }) : x;
        });
        renderSidebar();
        renderActiveThread();
      });
    },

    addEvent: function () {
      var t = STATE.active_thread;
      if (!t) return;
      var inp = document.getElementById("drwNewEventTitle");
      var val = inp ? inp.value.trim() : "";
      if (!val) return;
      t.events = t.events || [];
      t.events.push({ id: String(Date.now()), title: val, when: val, notes: "", done: false });
      inp.value = "";
      TG.saveThreadSettings();
      renderDrawer();
    },

    removeEvent: function (idx) {
      var t = STATE.active_thread;
      if (!t || !t.events) return;
      t.events.splice(idx, 1);
      TG.saveThreadSettings();
      renderDrawer();
    },

    pinCurrentThread: function () {
      var t = STATE.active_thread;
      if (!t) return;
      apiPost({ action: "pin_thread", thread_id: t.id }).then(function (res) {
        t.pinned = res.pinned;
        STATE.threads = res.threads;
        renderSidebar();
      });
    },

    deleteCurrentThread: function () {
      var t = STATE.active_thread;
      if (t) TG.deleteChat(t.id);
    },
    deleteChat: function (id) {
      var t = (STATE.threads || []).find(function (x) { return x.id === id; }) || STATE.active_thread;
      if (!t || !confirm("Delete “" + (t.chat_name || t.title) + "”? Its messages are gone for good (branches made from it stay).")) return;
      apiPost({ action: "delete_thread", thread_id: id }).then(function (res) {
        var box = document.getElementById("tgChats"); if (box) box.classList.remove("open");
        STATE.threads = res.threads || [];
        STATE.active_thread = res.active_thread || null;
        TG.closeDrawer();
        renderSidebar();
        renderActiveThread();
      });
    },

    requestBrowserNotifPermission: function (checkbox) {
      if (checkbox.checked && "Notification" in window && Notification.permission !== "granted") {
        Notification.requestPermission();
      }
    },

    saveUserProfile: function () {  // (returns the request: saving() shows how it went)
      var profile = {
        display_name: document.getElementById("drwMeName").value,
        status_emoji: document.getElementById("drwMeEmoji").value,
        handle: document.getElementById("drwMeHandle").value,
        bio: document.getElementById("drwMeBio").value,
        in_app_toasts: document.getElementById("drwMeToast").checked,
        browser_notifications: document.getElementById("drwMeBrowserNotif").checked,
        spontaneous_texts: document.getElementById("drwMeSpontaneous").checked,
        spontaneous_minutes: parseInt(document.getElementById("drwMeSpontMins").value || "15", 10),
        auto_photos: document.getElementById("drwMeAutoPhoto").checked,
        auto_voice: document.getElementById("drwMeAutoVoice").checked,
        auto_statuses: !!(document.getElementById("drwMeAutoStatuses") || {}).checked,
        image_model: (document.getElementById("drwMeImageModel") || {}).value || "",
      };
      return apiPost({
        action: "user_profile",
        thread_id: STATE.active_thread ? STATE.active_thread.id : null,
        profile: profile,
      }).then(function (res) {
        STATE.user_profile = res.user_profile;
        renderSidebar();
        if (STATE.active_thread) TG.selectThread(STATE.active_thread.id);
      });
    },

    // Modals
    closeModals: function () {
      document.querySelectorAll(".tg-modal-backdrop").forEach(function (m) {
        m.classList.remove("open");
      });
    },

    openNewChatModal: function () {
      var listEl = document.getElementById("newChatCharList");
      var chars = STATE.characters || [];
      if (!chars.length) {
        listEl.innerHTML = '<div style="color:var(--tg-muted);">Create a character first on the Characters page.</div>';
      } else {
        listEl.innerHTML = chars
          .map(function (c) {
            return (
              '<label class="tg-char-pick-row">' +
                '<input type="checkbox" name="newChatChar" value="' + esc(c.slug) + '">' +
                avatarHtml(c.avatar_url, c.display_name || c.name, "tg-msg-avatar") +
                "<div>" +
                  '<div style="font-weight:600;font-size:13.5px;">' + esc(c.display_name || c.name) + "</div>" +
                  '<div style="font-size:11.5px;color:var(--tg-muted);">' + esc(c.handle || "") + " · " + esc(c.bio || "") + "</div>" +
                "</div>" +
              "</label>"
            );
          })
          .join("");
      }
      document.getElementById("newChatTitle").value = "";
      document.getElementById("newChatScenario").value = "";
      document.getElementById("modalNewChat").classList.add("open");
    },

    submitNewChat: function () {
      var checked = Array.from(document.querySelectorAll('input[name="newChatChar"]:checked')).map(function (el) {
        return el.value;
      });
      if (!checked.length) {
        alert("Tick at least one character.");
        return;
      }
      var title = document.getElementById("newChatTitle").value.trim();
      var scenario = document.getElementById("newChatScenario").value.trim();
      apiPost({
        action: "create_thread",
        character_slugs: checked,
        is_group: checked.length > 1 || Boolean(title),
        force_new: checked.length > 1 || Boolean(title) || Boolean(scenario),
        title: title,
        scenario_override: scenario,
      }).then(function (res) {
        STATE.threads = res.threads;
        STATE.active_thread = res.thread;
        TG.closeModals();
        renderSidebar();
        renderActiveThread();
      });
    },

    openPhotoModal: function () {
      var t = STATE.active_thread;
      if (!t) return;
      var sel = document.getElementById("photoModalChar");
      sel.innerHTML = (t.members || [])
        .map(function (m) {
          return '<option value="' + esc(m.slug) + '">' + esc(m.display_name || m.name) + "</option>";
        })
        .join("");
      document.getElementById("photoModalPrompt").value = "";
      document.getElementById("modalPhoto").classList.add("open");
    },

    submitPhotoRequest: function () {
      var t = STATE.active_thread;
      if (!t) return;
      var btn = document.getElementById("photoModalSubmitBtn");
      var orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = "📸 Making the picture…";
      apiPost({
        action: "photo_bubble",
        thread_id: t.id,
        char_slug: document.getElementById("photoModalChar").value,
        kind: document.getElementById("photoModalKind").value,
        subject: (document.getElementById("photoModalSubject") || {}).value || "",
        prompt: document.getElementById("photoModalPrompt").value,
      })
        .then(function (res) {
          btn.disabled = false;
          btn.textContent = orig;
          t.messages.push(res.message);
          TG.closeModals();
          renderActiveThread();
        })
        .catch(function (e) {
          btn.disabled = false;
          btn.textContent = orig;
          alert(e.message);
        });
    },

    openWriteFileModal: function () {
      document.getElementById("fileModalHeading").textContent = "📄 Send a Note or Document File";
      document.getElementById("fileModalName").value = "note.txt";
      document.getElementById("fileModalName").readOnly = false;
      document.getElementById("fileModalContent").value = "";
      document.getElementById("fileModalContent").readOnly = false;
      document.getElementById("fileModalContent").hidden = false;
      var doc = document.getElementById("fileModalRendered"); if (doc) doc.hidden = true;
      document.getElementById("fileModalSendBtn").style.display = "inline-flex";
      document.getElementById("modalFile").classList.add("open");
    },

    openReadFileModal: function (msgId) {
      var t = STATE.active_thread;
      if (!t) return;
      var m = (t.messages || []).find(function (x) { return x.id === msgId; });
      if (!m || !m.file) return;
      document.getElementById("fileModalHeading").textContent = "📄 " + (m.file.name || "File");
      document.getElementById("fileModalName").value = m.file.name || "document.txt";
      document.getElementById("fileModalName").readOnly = true;
      document.getElementById("fileModalContent").value = m.file.content || "";
      document.getElementById("fileModalContent").readOnly = true;
      document.getElementById("fileModalContent").hidden = true;  // read as a document (tables and all)
      var doc = document.getElementById("fileModalRendered");
      if (doc) { doc.hidden = false; doc.innerHTML = renderDoc(m.file.content || ""); }
      document.getElementById("fileModalSendBtn").style.display = "none";
      document.getElementById("modalFile").classList.add("open");
    },

    submitFileMessage: function () {
      var name = document.getElementById("fileModalName").value.trim() || "note.txt";
      var content = document.getElementById("fileModalContent").value;
      if (!content.trim()) return;
      TG.closeModals();
      TG.sendUserMessage({
        text: "",
        file: {
          name: name,
          content: content,
          size: Math.max(1, content.length) + " B",
        },
      });
    },

    openStoryModal: function (owner) {
      var box = document.getElementById("modalStoryBody");
      var isUser = owner === "user";
      var target = isUser
        ? STATE.user_profile
        : (STATE.characters || []).find(function (c) { return c.slug === owner; });
      if (!target) return;

      var stories = target.stories || [];
      var stHtml = stories
        .map(function (s) {
          return (
            '<div style="background:rgba(255,255,255,0.05);padding:10px 12px;border-radius:10px;font-size:13.5px;">' +
              '<div style="display:flex;justify-content:space-between;color:var(--tg-muted);font-size:11px;margin-bottom:4px;">' +
                "<span>Status Update</span><span>" + esc(s.at || "") + "</span>" +
              "</div>" +
              "<div>" + esc(s.emoji || "✨") + " " + formatMessageHtml(s.text || "") + "</div>" +
            "</div>"
          );
        })
        .join("");

      box.innerHTML =
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
          '<h3 style="margin:0;">' + esc(target.display_name || target.name || "Profile") + " · Status & Stories</h3>" +
          '<button type="button" class="tg-fmt-btn" onclick="TG.closeModals()">✕</button>' +
        "</div>" +
        '<div style="font-size:12.5px;color:var(--tg-muted);">' + esc(target.handle || "") + " — " + esc(target.bio || "No bio set") + "</div>" +
        '<div style="display:flex;flex-direction:column;gap:8px;max-height:220px;overflow-y:auto;">' +
          (stHtml || '<div style="color:var(--tg-muted);font-size:13px;">No status stories posted yet.</div>') +
        "</div>" +
        '<div style="border-top:1px solid var(--tg-border);padding-top:10px;display:flex;flex-direction:column;gap:8px;">' +
          "<label style='font-size:12px;font-weight:600;color:var(--tg-muted);'>Post a new Status Update</label>" +
          '<div style="display:flex;gap:6px;">' +
            '<input type="text" class="tg-input" id="storyModalEmoji" style="width:52px;text-align:center;" value="' + esc(target.status_emoji || "✨") + '">' +
            '<input type="text" class="tg-input" id="storyModalText" placeholder="What\'s happening right now?">' +
          "</div>" +
          '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">' +
            '<label class="tg-fmt-btn" style="cursor:pointer;">🖼️ <span id="storyModalPicLabel">Add a picture</span>' +
              '<input type="file" accept="image/*" id="storyModalPic" hidden onchange="document.getElementById(\'storyModalPicLabel\').textContent = this.files[0] ? this.files[0].name : \'Add a picture\'"></label>' +
            '<button type="button" class="tg-send-btn" onclick="TG.submitStory(\'' + esc(owner) + '\')">Post Status</button>' +
          "</div>" +
        "</div>";
      document.getElementById("modalStory").classList.add("open");
    },

    submitStory: function (owner) {
      var emoji = document.getElementById("storyModalEmoji").value.trim() || "✨";
      var text = document.getElementById("storyModalText").value.trim();
      var pic = document.getElementById("storyModalPic"), file = pic && pic.files && pic.files[0];
      if (!text && !file) return;
      var upload = file ? (function () {  // the picture first (as any upload), then the status with it
        var fd = new FormData(); fd.append("kind", "image"); fd.append("file", file);
        return fetch(window.TG_CFG.api, { method: "POST", headers: { "X-CSRFToken": window.TG_CFG.csrf }, body: fd })
          .then(function (r) { return r.json(); }).then(function (r) { if (r.error) throw new Error(r.error); return r.url; });
      })() : Promise.resolve("");
      upload.then(function (url) { return apiPost({ action: "post_story", owner: owner, emoji: emoji, text: text, image_url: url }); }).then(function (res) {
        if (owner === "user") {
          STATE.user_profile = res.user_profile;
        } else {
          syncCharCatalog(owner, res.profile);
        }
        TG.closeModals();
        renderSidebar();
        renderMomentsFeed();
      });
    },

    addPersonalNote: function () {
      var title = prompt("Note title:");
      if (!title) return;
      var text = prompt("Note text:");
      if (text == null) return;
      var notes = (STATE.user_profile.notes || []).slice();
      notes.unshift({ id: String(Date.now()), title: title.trim(), text: text.trim() });
      apiPost({ action: "user_profile", profile: { notes: notes } }).then(function (res) {
        STATE.user_profile = res.user_profile;
        renderHubFilesAndNotes();
      });
    },

    deletePersonalNote: function (idx) {
      var notes = (STATE.user_profile.notes || []).slice();
      notes.splice(idx, 1);
      apiPost({ action: "user_profile", profile: { notes: notes } }).then(function (res) {
        STATE.user_profile = res.user_profile;
        renderHubFilesAndNotes();
      });
    },

    renderSidebar: renderSidebar,
  };

  renderSidebar();
  renderActiveThread();

  // Touch screens have no hover: tapping a message shows its actions (reply, ↻, pin, edit, delete); tap again hides
  var vpEl = document.getElementById("tgMessagesViewport");
  if (vpEl) vpEl.addEventListener("click", function (e) {
    if (e.target.closest("button, a, input, textarea, img, .tg-regen, .tg-setup, .tg-spoiler")) return;
    var row = e.target.closest(".tg-msg-row");
    vpEl.querySelectorAll(".tg-msg-row.show-actions").forEach(function (r) { if (r !== row) r.classList.remove("show-actions"); });
    if (row) row.classList.toggle("show-actions");
  });

  // Bulba's panel tells us when something changed (a card applied, a reply retried): reload this chat
  window.addEventListener("message", function (e) {
    if (e.origin !== window.location.origin || !e.data) return;
    if (e.data.quickBulba === "close") { TG.closeBulba(); return; }
    if ((e.data.bulba || e.data.quickBulba === "changed") && STATE.active_thread) TG.selectThread(STATE.active_thread.id);
  });
})();
