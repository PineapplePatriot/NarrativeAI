/* The cut-out engine: a picture drawn on a flat colour, with that colour taken away in the browser (flood fill from
 * the border, closed-off pockets, spill removal on the edge band), so the server never runs a background remover.
 * Used by episode looks, chat sprites (character and persona pages) and Screen stickers. Cutout.review shows a
 * before/after with three strengths and resolves to the cut PNG, or null.
 */
(function () {

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


  function toBlob(canvas) {
    return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("The browser couldn't make the cut-out."))), "image/png"));
  }

  /* Cut a picture by its url; resolves to a PNG blob. */
  async function cutUrl(url, strength = "normal", size = null) {
    return toBlob(cutCanvas(await loadImage(url), strength, size));
  }

  /* A before/after with Keep more edge / Normal / Remove more background; resolves to the chosen PNG blob or null. */
  function review(url, {title = "Cut out the background", note = ""} = {}) {
    return new Promise((resolve) => {
      const back = document.createElement("div");
      back.className = "cutout-back";
      back.innerHTML = `<div class="cutout-box" role="dialog" aria-modal="true" aria-label="${title}">
          <strong>${title}</strong>
          ${note ? `<p class="cutout-note">${note}</p>` : ""}
          <div class="cutout-pair"><figure><img data-before alt=""><figcaption>Now</figcaption></figure>
            <figure class="cutout-checker"><canvas data-after></canvas><figcaption>Cut out</figcaption></figure></div>
          <div class="cutout-strength">
            <button type="button" data-s="tight">Keep more edge</button><button type="button" data-s="normal" class="is-on">Normal</button>
            <button type="button" data-s="loose">Remove more background</button></div>
          <p class="cutout-note">Works best on a plain background. Edges look wrong? Try another strength.</p>
          <div class="cutout-actions"><button type="button" data-no>Cancel</button><button type="button" data-yes class="is-primary">Keep the cut-out</button></div>
        </div>`;
      document.body.append(back);
      let canvas = null;
      const done = async (keep) => {
        let blob = null;
        if (keep && canvas) {
          try {blob = await toBlob(canvas);} catch (_) {blob = null;}
        }
        back.remove();
        resolve(blob);
      };
      const draw = async (strength) => {
        back.querySelectorAll("[data-s]").forEach((b) => b.classList.toggle("is-on", b.dataset.s === strength));
        try {
          const img = await loadImage(url);
          canvas = cutCanvas(img, strength);
          const shown = back.querySelector("[data-after]");
          shown.width = canvas.width; shown.height = canvas.height;
          shown.getContext("2d").drawImage(canvas, 0, 0);
        } catch (e) {
          back.querySelector(".cutout-note").textContent = e.message;
        }
      };
      back.querySelector("[data-before]").src = url;
      back.querySelectorAll("[data-s]").forEach((b) => b.addEventListener("click", () => draw(b.dataset.s)));
      back.querySelector("[data-yes]").addEventListener("click", () => done(true));
      back.querySelector("[data-no]").addEventListener("click", () => done(false));
      back.addEventListener("click", (e) => {if (e.target === back) done(false);});
      draw("normal");
    });
  }

  window.Cutout = {loadImage, cutCanvas, outline, outlineChange, cutUrl, toBlob, review};
})();
