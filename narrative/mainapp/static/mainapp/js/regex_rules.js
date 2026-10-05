// Text rules that change only what's shown on screen ("display" mode; markdownOnly in SillyTavern).
// Same behaviour as mainapp/regex_rules.py, but with the browser's own regex engine, which is the one
// SillyTavern presets are written for. Rules and names come from the page (json_script "display-rules").
const TextRules = (() => {
    let rules = [], names = {};
    try {
        const data = JSON.parse(document.getElementById('display-rules')?.textContent || 'null');
        if (data) { rules = data.rules || []; names = data.names || {}; }
    } catch (e) { rules = []; }

    const compiled = new Map();
    const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
    const fill = t => t.replace(/\{\{\s*(char|user)\s*\}\}/gi, (m, k) => names[k.toLowerCase()] ?? m);

    function compile(rule) {
        if (compiled.has(rule.id)) return compiled.get(rule.id);
        let src = rule.find;
        if (rule.macros_in_find) {
            src = src.replace(/\{\{([^{}]+)\}\}/g, (m, k) => {
                const v = names[k.trim().toLowerCase()];
                if (v == null) return m;
                return rule.macros_in_find === 2 ? escapeRe(v) : v;
            });
        }
        const m = src.match(/^\/([\s\S]+)\/([a-z]*)$/);
        let re = null;
        try { re = m ? new RegExp(m[1], m[2]) : new RegExp(src); } catch (e) { re = null; }
        compiled.set(rule.id, re);
        return re;
    }

    function runRule(rule, text) {
        if (!rule.find) return text;
        const re = compile(rule);
        if (!re) return text;
        re.lastIndex = 0;
        const template = rule.replace.replace(/\{\{match\}\}/gi, '$0');
        const trims = (rule.trim || []).map(fill);
        return text.replace(re, (...args) => {
            const hasGroups = typeof args[args.length - 1] === 'object' && args[args.length - 1] !== null;
            const groups = hasGroups ? args[args.length - 1] : {};
            const numbered = args.slice(0, hasGroups ? -3 : -2);
            return fill(template.replace(/\$(\d+)|\$<([^>]+)>/g, (_, num, name) => {
                let v = num !== undefined ? numbered[Number(num)] : groups[name];
                if (!v) return '';
                for (const t of trims) v = v.split(t).join('');
                return v;
            }));
        });
    }

    // role: 'user' or 'assistant'; depth: 0 for the newest message
    function apply(text, role, depth) {
        const where = role === 'user' ? 1 : 2;
        for (const r of rules) {
            if (!r.placement.includes(where)) continue;
            if (depth != null && ((r.min_depth != null && depth < r.min_depth) ||
                                  (r.max_depth != null && depth > r.max_depth))) continue;
            text = runRule(r, text);
        }
        return text;
    }

    return {
        apply,
        any: () => rules.length > 0,
        usesDepth: () => rules.some(r => r.min_depth != null || r.max_depth != null),
    };
})();
