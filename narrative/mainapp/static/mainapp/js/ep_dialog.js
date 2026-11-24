/* The episodes' own dialogs, in the stage's style, instead of the browser's confirm and prompt boxes (which take the
 * browser's language and look). EpDialog.confirm / prompt return promises; EpDialog.open shows any content. */
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  function open({title = "", html = "", wide = false, onMount = null} = {}) {
    let done;
    const result = new Promise((resolve) => {done = resolve;});
    const back = document.createElement("div");
    back.className = "ep-dialog-back";
    back.innerHTML = `<div class="ep-dialog ${wide ? "is-wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        ${title ? `<div class="ep-dialog-head"><strong>${esc(title)}</strong>
          <button type="button" class="ep-icon" data-close aria-label="Close">✕</button></div>` : ""}
        <div class="ep-dialog-body">${html}</div></div>`;
    const before = document.activeElement;
    const close = (value) => {
      back.remove();
      document.removeEventListener("keydown", onKey, true);
      try {before?.focus?.();} catch (_) { /* nothing to return to */ }
      done(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {event.stopPropagation(); close(null);}
    };
    back.addEventListener("click", (event) => {if (event.target === back) close(null);});
    back.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => close(null)));
    document.addEventListener("keydown", onKey, true);
    document.body.append(back);
    const body = back.querySelector(".ep-dialog-body");
    if (onMount) onMount(body, close);
    (back.querySelector("[autofocus]") || back.querySelector("textarea, input, button:not([data-close])"))?.focus();
    return result;
  }

  function confirm(message, {ok = "OK", cancel = "Cancel", danger = false, title = ""} = {}) {
    return open({title, html: `<p class="ep-dialog-p">${esc(message)}</p>
        <div class="ep-dialog-actions">
          <button type="button" class="ep-btn ep-btn-quiet" data-no>${esc(cancel)}</button>
          <button type="button" class="ep-btn ${danger ? "ep-btn-danger" : "ep-btn-primary"}" data-yes autofocus>${esc(ok)}</button>
        </div>`,
      onMount: (body, close) => {
        body.querySelector("[data-yes]").addEventListener("click", () => close(true));
        body.querySelector("[data-no]").addEventListener("click", () => close(false));
      }}).then((v) => v === true);
  }

  function prompt(message, value = "", {ok = "OK", cancel = "Cancel", title = "", multiline = false, placeholder = ""} = {}) {
    const field = multiline
      ? `<textarea class="ep-input" data-field rows="4" placeholder="${esc(placeholder)}">${esc(value)}</textarea>`
      : `<input class="ep-input" data-field value="${esc(value)}" placeholder="${esc(placeholder)}">`;
    return open({title, html: `<label class="ep-dialog-text">${esc(message)}${field}</label>
        <div class="ep-dialog-actions">
          <button type="button" class="ep-btn ep-btn-quiet" data-no>${esc(cancel)}</button>
          <button type="button" class="ep-btn ep-btn-primary" data-yes>${esc(ok)}</button>
        </div>`,
      onMount: (body, close) => {
        const input = body.querySelector("[data-field]");
        const submit = () => close(input.value);
        body.querySelector("[data-yes]").addEventListener("click", submit);
        body.querySelector("[data-no]").addEventListener("click", () => close(null));
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter" && (!multiline || event.ctrlKey || event.metaKey)) {event.preventDefault(); submit();}
        });
        setTimeout(() => {input.focus(); input.select?.();}, 0);
      }}).then((v) => (typeof v === "string" ? v : null));
  }

  window.EpDialog = {open, confirm, prompt};
})();
