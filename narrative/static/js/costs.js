/* Cost estimates for the chat's memory (context size), summaries and trackers: Bulba's setup forms and the Extras
   page. Prices are OpenRouter's per-token rates ([input, output]), passed in by the page; none means no estimate,
   never a guess. A chat message rereads the whole memory once the chat fills it and gets ~800 tokens back. */
window.NACosts = (function () {
    const STEPS = [8000, 16000, 32000, 48000, 64000, 96000, 128000, 200000, 256000, 500000, 1000000];
    const REPLY = 800, AVG_MESSAGE = 450;  // a reply, and a chat message on average (theirs are shorter)
    const money = usd => usd < 0.001 ? 'under $0.001' : '≈ ' + (usd < 0.01 ? `$${usd.toFixed(3)}` : `$${usd.toFixed(2)}`);
    const kTokens = n => n >= 1000000 ? `${n / 1000000}M` : `${Math.round(n / 1000)}k`;
    const cost = (p, tin, tout) => p ? tin * p[0] + tout * p[1] : null;

    function steps(max) { const s = STEPS.filter(n => n <= max); return s.length ? s : [max]; }
    function nearest(list, value) {
        return list.reduce((best, n, i) => Math.abs(n - (value || 0)) < Math.abs(list[best] - (value || 0)) ? i : best, 0);
    }
    function memory(size) { return `${kTokens(size)} tokens · about ${Math.round(size / AVG_MESSAGE).toLocaleString()} messages remembered`; }
    function chat(price, size) {
        const each = cost(price, size, REPLY);
        return each == null ? 'No price to show: OpenRouter’s price list couldn’t be read.'
            : `${money(each)} a message once the chat fills it, ${money(each * 100)} for 100 messages. At most: less before `
              + 'the chat fills it, and less where the provider caches the repeated part; thinking adds a little.';
    }
    // task: "summary" (the messages since the last one) or "trackers" (the latest 4 to 16 messages plus the trackers)
    function job(task, price, size, mode, every) {
        const usd = task === 'summary' ? cost(price, Math.min(every * AVG_MESSAGE, size) + 300, 400)
                                        : cost(price, Math.min(16, Math.max(4, every)) * AVG_MESSAGE + 1500, 500);
        if (usd == null) return '';
        return mode === 'auto' ? `${money(usd)} each time, every ${every} messages (${money(usd / every)} a message)`
                               : `${money(usd)} each time you ask`;
    }
    return { steps, nearest, memory, chat, job };
})();
