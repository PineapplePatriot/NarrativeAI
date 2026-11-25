/* Subtext / Chirp — Public Timeline, Locked Burners, AITA Threads & TeleChat DM Bridge */
(function () {
  var rawInit = document.getElementById("tgInitialData");
  var INIT = rawInit ? JSON.parse(rawInit.textContent) : {};
  var SUB = INIT.subtext || { posts: [], burner_handles: {}, reactions_palette: ["❤️", "🔥", "💀", "👀", "🤡", "💔"] };
  var CHARS = INIT.characters || [];
  var USER_PROF = INIT.user_profile || {};
  var currentTab = "all"; // "all" | "burner" | "aita" | "public"

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function formatBody(raw) {
    var s = esc(raw || "");
    s = s.replace(/\|\|([^|\n]+)\|\|/g, '<span class="tg-spoiler" onclick="this.classList.toggle(\'revealed\')" title="Tap to reveal spoiler">$1</span>');
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
    s = s.replace(/(^|\s)(@[a-zA-Z0-9_]+)/g, '$1<span style="color:#60a5fa;font-weight:600;">$2</span>');
    return s;
  }

  function avatarHtml(url, name) {
    var initial = ((name || "?").trim()[0] || "?").toUpperCase();
    if (url) {
      return '<div class="tg-avatar" style="width:38px;height:38px;"><img src="' + esc(url) + '" alt=""></div>';
    }
    return '<div class="tg-avatar" style="width:38px;height:38px;">' + esc(initial) + "</div>";
  }

  function subApiPost(payload) {
    var url = (window.TG_CFG && window.TG_CFG.subtext_api) || "/main/screen/subtext/api/";
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": (window.TG_CFG && window.TG_CFG.csrf) || "",
      },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(d.error || "Subtext request failed");
        return d;
      });
    });
  }

  function renderSubtextFeed() {
    var listEl = document.getElementById("subtextFeedList");
    if (!listEl) return;

    var posts = (SUB.posts || []).filter(function (p) {
      if (currentTab === "burner") return p.visibility === "burner";
      if (currentTab === "aita") return p.visibility === "aita";
      if (currentTab === "public") return p.visibility === "public";
      return true;
    });

    if (!posts.length) {
      listEl.innerHTML =
        '<div class="subtext-post-card" style="text-align:center;padding:30px 18px;color:var(--tg-muted);">' +
          '<div style="font-size:28px;margin-bottom:6px;">🌐</div>' +
          '<div>No posts in this tab yet. Click <b>🎲 Generate Wave</b> on the right or write a post above!</div>' +
        "</div>";
      return;
    }

    var palette = SUB.reactions_palette || ["❤️", "🔥", "💀", "👀", "🤡", "💔"];

    listEl.innerHTML = posts
      .map(function (p) {
        var vis = p.visibility || "public";
        var cardCls = "subtext-post-card" + (vis === "burner" ? " is-burner" : vis === "aita" ? " is-aita" : "");
        var badgeHtml = "";
        if (vis === "burner") {
          badgeHtml = '<span class="subtext-badge burner">🔒 ' + esc(p.subtweet_note || "Locked Burner") + "</span>";
        } else if (vis === "aita") {
          badgeHtml = '<span class="subtext-badge aita">⚖️ ' + esc(p.subtweet_note || "AITA Thread") + "</span>";
        } else {
          badgeHtml = '<span class="subtext-badge public">🌐 ' + esc(p.subtweet_note || "Public Main") + "</span>";
        }

        var titleHtml = p.title ? '<h4 class="subtext-post-title">' + esc(p.title) + "</h4>" : "";

        var photoHtml = "";
        if (p.photo) {
          if (p.photo.url) {
            photoHtml =
              '<div class="subtext-photo-box">' +
                '<img src="' + esc(p.photo.url) + '" alt="Subtext snapshot">' +
              "</div>";
          } else if (p.photo.prompt) {
            photoHtml =
              '<div class="subtext-photo-box" style="padding:10px 12px;display:flex;align-items:center;justify-content:space-between;gap:10px;">' +
                '<div style="font-size:12px;color:#94a3b8;">📷 <i>' + esc(p.photo.prompt) + "</i></div>" +
                '<button type="button" class="tg-bulba-btn" style="padding:5px 10px;font-size:11.5px;white-space:nowrap;" onclick="SUBTEXT.generatePhoto(\'' + esc(p.id) + '\', this)">🍌 Render Photo</button>' +
              "</div>";
          }
        }

        var aitaBarHtml = "";
        if (vis === "aita") {
          var v = p.aita_votes || { nta: 0, yta: 0, esh: 0, user_vote: "" };
          var uVote = v.user_vote || "";
          aitaBarHtml =
            '<div class="subtext-aita-bar">' +
              '<span style="font-size:12px;font-weight:700;color:#fdba74;">⚖️ Community Verdict:</span>' +
              '<button type="button" class="subtext-vote-btn ' + (uVote === "NTA" ? "voted-nta" : "") + '" onclick="SUBTEXT.voteAita(\'' + esc(p.id) + '\', \'NTA\')">🟢 NTA (' + (v.nta || 0) + ")</button>" +
              '<button type="button" class="subtext-vote-btn ' + (uVote === "YTA" ? "voted-yta" : "") + '" onclick="SUBTEXT.voteAita(\'' + esc(p.id) + '\', \'YTA\')">🔴 YTA (' + (v.yta || 0) + ")</button>" +
              '<button type="button" class="subtext-vote-btn ' + (uVote === "ESH" ? "voted-esh" : "") + '" onclick="SUBTEXT.voteAita(\'' + esc(p.id) + '\', \'ESH\')">🟡 ESH (' + (v.esh || 0) + ")</button>" +
            "</div>";
        }

        var reacts = p.reactions || {};
        var reactPills = palette
          .map(function (emo) {
            var users = reacts[emo] || [];
            var cnt = users.length;
            return (
              '<button type="button" class="subtext-react-pill" title="' + esc(users.join(", ")) + '" onclick="SUBTEXT.reactPost(\'' + esc(p.id) + "', '" + esc(emo) + '\')">' +
                emo + (cnt ? " <b>" + cnt + "</b>" : "") +
              "</button>"
            );
          })
          .join("");

        var comments = p.comments || [];
        var commentsHtml = comments
          .map(function (c) {
            var vTag = c.verdict ? '<span class="subtext-verdict-tag ' + esc(c.verdict) + '">' + esc(c.verdict) + "</span>" : "";
            var burnerTag = c.is_burner ? ' <span style="color:#d8b4fe;font-size:11px;">🔒</span>' : "";
            return (
              '<div class="subtext-comment-item">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">' +
                  '<div><strong>' + esc(c.author_name) + '</strong> <span style="color:#94a3b8;font-size:11.5px;">' + esc(c.handle) + "</span>" + burnerTag + "</div>" +
                  '<span style="color:#64748b;font-size:11px;">' + esc(c.time || "") + "</span>" +
                "</div>" +
                '<div style="color:#e2e8f0;line-height:1.42;">' + vTag + formatBody(c.text) + "</div>" +
              "</div>"
            );
          })
          .join("");

        var verdictSelectHtml =
          vis === "aita"
            ? '<select class="tg-select" id="stCommentVerdict-' + esc(p.id) + '" style="width:92px;padding:5px 8px;font-size:12px;">' +
                '<option value="">Verdict…</option>' +
                '<option value="NTA">NTA</option>' +
                '<option value="YTA">YTA</option>' +
                '<option value="ESH">ESH</option>' +
              "</select>"
            : "";

        return (
          '<article class="' + cardCls + '" id="st-post-' + esc(p.id) + '">' +
            '<div class="subtext-post-top">' +
              '<div class="subtext-author-row">' +
                avatarHtml(p.author_avatar, p.author_name) +
                "<div>" +
                  '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">' +
                    '<strong style="font-size:14.5px;color:#fff;">' + esc(p.author_name) + "</strong>" +
                    '<span style="font-size:12.5px;color:#94a3b8;">' + esc(p.handle) + "</span>" +
                    '<span style="font-size:12px;color:#64748b;">· ' + esc(p.time || "") + "</span>" +
                  "</div>" +
                  '<div style="margin-top:3px;">' + badgeHtml + "</div>" +
                "</div>" +
              "</div>" +
              '<div style="display:flex;gap:6px;align-items:center;">' +
                (p.author_slug !== "user"
                  ? '<button type="button" class="subtext-dm-btn" onclick="SUBTEXT.forwardToTeleChat(\'' + esc(p.id) + '\')" title="Forward this post or burner subtweet straight into your TeleChat DM with this character!">✈️ DM in TeleChat</button>'
                  : "") +
                '<button type="button" class="tg-fmt-btn" onclick="SUBTEXT.deletePost(\'' + esc(p.id) + '\')" title="Delete post">✕</button>' +
              "</div>" +
            "</div>" +
            titleHtml +
            '<div class="subtext-post-body">' + formatBody(p.text) + "</div>" +
            photoHtml +
            aitaBarHtml +
            '<div class="subtext-actions-row">' +
              '<div class="subtext-react-strip">' + reactPills + "</div>" +
              '<div style="display:flex;gap:6px;">' +
                '<button type="button" class="tg-fmt-btn" onclick="SUBTEXT.summonReplies(\'' + esc(p.id) + '\', this)" title="Have characters jump into the comments and react">💬 Summon Replies (' + comments.length + ")</button>" +
              "</div>" +
            "</div>" +
            '<div class="subtext-comments-box">' +
              commentsHtml +
              '<div style="display:flex;gap:6px;margin-top:4px;align-items:center;">' +
                verdictSelectHtml +
                '<input type="text" class="tg-input" id="stCommentInput-' + esc(p.id) + '" placeholder="Reply to ' + esc(p.handle) + '… (characters will respond)" style="flex:1;padding:6px 10px;font-size:12.5px;" onkeydown="if(event.key===\'Enter\')SUBTEXT.submitComment(\'' + esc(p.id) + '\')">' +
                '<button type="button" class="tg-fmt-btn" onclick="SUBTEXT.submitComment(\'' + esc(p.id) + '\')">Reply</button>' +
              "</div>" +
            "</div>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderSubtextSidebar() {
    var rosterEl = document.getElementById("subtextCharRoster");
    if (!rosterEl) return;
    if (!CHARS.length) {
      rosterEl.innerHTML = '<div style="color:var(--tg-muted);font-size:12.5px;">Create a character first using <b>🥔 + Character</b> in TeleChat!</div>';
      return;
    }
    var bMap = SUB.burner_handles || {};
    rosterEl.innerHTML = CHARS.map(function (c) {
      var bHandle = c.burner_handle || bMap[c.slug] || ("@" + (c.handle || c.slug).replace(/^@/, "") + "_priv");
      return (
        '<label style="display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:10px;background:rgba(255,255,255,0.03);cursor:pointer;font-size:12.5px;">' +
          '<input type="checkbox" class="subtext-wave-char-cb" value="' + esc(c.slug) + '" checked>' +
          avatarHtml(c.avatar_url, c.display_name || c.name) +
          '<div style="flex:1;min-width:0;">' +
            '<div style="font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(c.display_name || c.name) + "</div>" +
            '<div style="font-size:11px;color:#94a3b8;">🌐 ' + esc(c.handle || "") + " · <span style='color:#d8b4fe;'>🔒 " + esc(bHandle) + "</span></div>" +
          "</div>" +
        "</label>"
      );
    }).join("");
  }

  function selectedWaveCharSlugs() {
    var slugs = [];
    document.querySelectorAll(".subtext-wave-char-cb:checked").forEach(function (cb) {
      slugs.push(cb.value);
    });
    return slugs;
  }

  window.SUBTEXT = {
    init: function () {
      renderSubtextSidebar();
      renderSubtextFeed();
    },

    switchTab: function (tab) {
      currentTab = tab || "all";
      document.querySelectorAll(".subtext-tab-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-st-tab") === currentTab);
      });
      renderSubtextFeed();
    },

    onVisChange: function (sel) {
      var titleRow = document.getElementById("stUserPostTitleWrap");
      if (titleRow) {
        titleRow.style.display = sel.value === "aita" ? "block" : "none";
      }
    },

    submitUserPost: function (btn) {
      var txtEl = document.getElementById("stUserPostText");
      var visEl = document.getElementById("stUserPostVis");
      var titleEl = document.getElementById("stUserPostTitle");
      var askEl = document.getElementById("stUserPostAskReplies");
      var text = txtEl ? txtEl.value.trim() : "";
      if (!text) {
        alert("Write something for your post first.");
        return;
      }
      var orig = btn ? btn.textContent : "Post";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ Posting…";
      }
      subApiPost({
        action: "create_post",
        text: text,
        visibility: visEl ? visEl.value : "public",
        title: titleEl ? titleEl.value.trim() : "",
        ask_replies: askEl ? askEl.checked : true,
        character_slugs: selectedWaveCharSlugs(),
      })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          if (txtEl) txtEl.value = "";
          if (titleEl) titleEl.value = "";
          SUB = res.subtext;
          renderSubtextFeed();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    generateWave: function (mode, btn) {
      var topicEl = document.getElementById("stWaveTopicInput");
      var topic = topicEl ? topicEl.value.trim() : "";
      var orig = btn ? btn.textContent : "🎲 Generate";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ Characters posting…";
      }
      subApiPost({
        action: "generate_wave",
        mode: mode || "mix",
        topic: topic,
        character_slugs: selectedWaveCharSlugs(),
      })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          SUB = res.subtext;
          renderSubtextFeed();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    submitComment: function (postId) {
      var inp = document.getElementById("stCommentInput-" + postId);
      var vSel = document.getElementById("stCommentVerdict-" + postId);
      var text = inp ? inp.value.trim() : "";
      if (!text) return;
      inp.disabled = true;
      subApiPost({
        action: "add_comment",
        post_id: postId,
        text: text,
        verdict: vSel ? vSel.value : "",
        ask_replies: true,
      })
        .then(function (res) {
          SUB = res.subtext;
          renderSubtextFeed();
        })
        .catch(function (e) {
          inp.disabled = false;
          alert(e.message);
        });
    },

    summonReplies: function (postId, btn) {
      var orig = btn ? btn.textContent : "💬 Summon Replies";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ Replying…";
      }
      subApiPost({
        action: "generate_replies",
        post_id: postId,
        character_slugs: selectedWaveCharSlugs(),
      })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          SUB = res.subtext;
          renderSubtextFeed();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    reactPost: function (postId, emoji) {
      subApiPost({ action: "react_post", post_id: postId, emoji: emoji }).then(function (res) {
        SUB.posts = (SUB.posts || []).map(function (p) {
          return p.id === postId ? res.post : p;
        });
        renderSubtextFeed();
      });
    },

    voteAita: function (postId, verdict) {
      subApiPost({ action: "vote_aita", post_id: postId, verdict: verdict }).then(function (res) {
        SUB.posts = (SUB.posts || []).map(function (p) {
          return p.id === postId ? res.post : p;
        });
        renderSubtextFeed();
      });
    },

    generatePhoto: function (postId, btn) {
      var orig = btn ? btn.textContent : "🍌 Render Photo";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "🍌 Rendering…";
      }
      subApiPost({ action: "generate_photo", post_id: postId })
        .then(function (res) {
          SUB.posts = (SUB.posts || []).map(function (p) {
            return p.id === postId ? res.post : p;
          });
          renderSubtextFeed();
        })
        .catch(function (e) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = orig;
          }
          alert(e.message);
        });
    },

    forwardToTeleChat: function (postId) {
      var post = (SUB.posts || []).find(function (p) { return p.id === postId; });
      if (!post) return;
      var defaultPrompt =
        post.visibility === "burner"
          ? "Care to explain what you just posted on " + post.handle + "?"
          : post.visibility === "aita"
          ? "I know this 'anonymous' AITA thread is yours."
          : "Just saw your post on Subtext.";
      var comment = prompt("Slide into " + post.author_name + "'s TeleChat DMs with this post:", defaultPrompt);
      if (comment === null) return;
      subApiPost({
        action: "forward_to_telechat",
        post_id: postId,
        comment: comment,
      })
        .then(function (res) {
          if (window.TG && res.thread) {
            window.TG.switchApp("messenger");
            window.TG.selectThread(res.thread.id);
          }
        })
        .catch(function (e) {
          alert(e.message);
        });
    },

    deletePost: function (postId) {
      subApiPost({ action: "delete_post", post_id: postId }).then(function (res) {
        SUB = res.subtext;
        renderSubtextFeed();
      });
    },
  };

  // Hook into TG.switchApp so switching to "subtext" initializes/refreshes the feed
  document.addEventListener("DOMContentLoaded", function () {
    if (window.TG && typeof window.TG.switchApp === "function") {
      var origSwitch = window.TG.switchApp;
      window.TG.switchApp = function (appName) {
        origSwitch(appName);
        if (appName === "subtext") {
          window.SUBTEXT.init();
        }
      };
    }
    window.SUBTEXT.init();
  });
})();
