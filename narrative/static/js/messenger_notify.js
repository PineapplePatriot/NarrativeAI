/* Global Messenger Notification Poller (In-App Toast + Outside-Site Browser Notification) */
(function () {
  var scriptEl = document.currentScript;
  if (!scriptEl) return;
  var pollUrl = scriptEl.getAttribute("data-poll");
  var screenUrl = scriptEl.getAttribute("data-screen");
  if (!pollUrl || !screenUrl) return;

  // Do not run toast popups while already inside the Screen Hub page
  var onScreenPage = window.location.pathname.indexOf("/screen/") !== -1;
  var seenKey = "na_messenger_last_seen_id";

  function showInAppToast(item) {
    if (onScreenPage) return;
    var existing = document.getElementById("naMessengerToast");
    if (existing) existing.remove();

    var toast = document.createElement("a");
    toast.id = "naMessengerToast";
    toast.href = screenUrl + "?thread=" + encodeURIComponent(item.thread_id || "");
    toast.style.cssText =
      "position:fixed;bottom:20px;right:20px;z-index:9999;background:#17212b;color:#f1f5f9;" +
      "border:1px solid rgba(56,189,248,0.5);border-radius:14px;padding:12px 16px;max-width:320px;" +
      "box-shadow:0 12px 32px rgba(0,0,0,0.55);text-decoration:none;display:flex;gap:12px;align-items:center;" +
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;transition: opacity 0.25s ease;";
    toast.innerHTML =
      '<div style="width:38px;height:38px;border-radius:50%;background:#0284c7;color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;">💬</div>' +
      '<div style="min-width:0;flex:1;">' +
        '<div style="font-size:13px;font-weight:700;color:#38bdf8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
          (item.sender_name || "Messenger") +
        "</div>" +
        '<div style="font-size:12.5px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
          (item.text || "New message") +
        "</div>" +
      "</div>";
    document.body.appendChild(toast);
    setTimeout(function () {
      if (toast && toast.parentNode) toast.remove();
    }, 8000);
  }

  function showBrowserNotification(item) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    try {
      var n = new Notification("💬 " + (item.sender_name || "TeleChat"), {
        body: item.text || "Sent you a message",
        tag: "na-messenger-" + (item.id || "latest"),
      });
      n.onclick = function () {
        window.focus();
        window.location.href = screenUrl + "?thread=" + encodeURIComponent(item.thread_id || "");
      };
    } catch (e) {}
  }

  function poll(allowSpontaneous) {
    var url = pollUrl + (allowSpontaneous && !onScreenPage ? "&allow_spontaneous=1" : "");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var badge = document.getElementById("naScreenUnreadBadge");
        if (badge) {
          var cnt = data.total_unread || 0;
          badge.style.display = cnt > 0 ? "inline-flex" : "none";
          badge.textContent = cnt;
        }
        var latest = data.latest_unread;
        if (latest && latest.id) {
          var lastId = "";
          try { lastId = sessionStorage.getItem(seenKey) || ""; } catch (e) {}
          if (latest.id !== lastId) {
            try { sessionStorage.setItem(seenKey, latest.id); } catch (e) {}
            if (data.in_app_toasts !== false && !onScreenPage) {
              showInAppToast(latest);
            }
            if (data.browser_notifications && (document.hidden || !onScreenPage)) {
              showBrowserNotification(latest);
            }
          }
        }
      })
      .catch(function () {});
  }

  setTimeout(function () { poll(false); }, 1500);
  setInterval(function () { poll(true); }, 45000);
})();
