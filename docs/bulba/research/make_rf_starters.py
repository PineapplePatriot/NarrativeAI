# Builds the two Realistic Frankenstein starters from the shipped Gemini BOLT file:
#   gemini-frankenstein: the file as shipped (Mature toggles off, as in every starter)
#   mimo-frankenstein:   MiMo V2.6 Pro BOLT, rebuilt from the per-block notes (the authors ship it as a
#                        separate file we don't have yet)
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "narrative"))
from mainapp import presets

SRC = os.path.join(HERE, "Realistic_Frankenstein_2.2.1.2.json")  # the shipped Gemini BOLT file (not in the repo)
OUT = os.path.join(ROOT, "narrative", "mainapp", "data", "starters") + os.sep
st = json.load(open(SRC))
base = presets.from_sillytavern(st)

MATURE = ["🔞Realism Mode / Jailbreak ❤️💋", "🔞 NSFW Anti-Slop Register 💋 (pair with NSFW modes)"]

def toggle(preset, names, on):
    found = set()
    for b in preset["blocks"]:
        if b["name"].strip() in [n.strip() for n in names]:
            b["enabled"] = on
            found.add(b["name"].strip())
    missing = [n for n in names if n.strip() not in found]
    assert not missing, missing

def rules(preset, names, on):
    found = set()
    for r in preset["regex"]:
        if r["name"] in names:
            r["enabled"] = on
            found.add(r["name"])
    assert found == set(names), set(names) - found

CREDIT = {"name": "Realistic Frankenstein 2.2.1.2 — Limitless Realism (SillyTavern preset)",
          "author": "dptgreg and TheAestheticFur", "version": "2.2.1.2",
          "url": "https://www.reddit.com/r/SillyTavernAI/search/?q=Realistic+Frankenstein"}

# --- Gemini: as shipped ---------------------------------------------------------------------------
gemini = copy.deepcopy(base)
toggle(gemini, MATURE, False)
gemini["extras"]["starter_note"] = "Realistic Gemini BOLT configuration, as shipped; Mature toggles off."

# --- MiMo V2.6 Pro BOLT, from the notes -------------------------------------------------------------
mimo = copy.deepcopy(base)
toggle(mimo, MATURE, False)
GEMINI_ONLY = [
    "🌠😡 Gemini, Don't Speak Like a Therapist!",
    "🌌🔎 Scene Detail & Evidence: Cosmos Edition, Realistic Gemini",
    "👃🌌 Scent Killswitch: Cosmos Edition 🚫",
    "🌌🎤 NPC Voice + Dialogue Output: Cosmos Edition 🗣️",
    "🌌⏱️ Pacing: Cosmos Edition",
    "🌌🚫 Banned Word List: Cosmos Edition 📝",
    "🌌⚖️ Anti-Comparative Emphasis: Cosmos Edition 🚫",
    "🌌🧰 Occupational Monomania Killswitch: Cosmos Edition 🚫",
    "🚪 Last-Mile Contrast Gate: Cosmos Edition 🌌⚖️ (Keep ON w/ Killswitch)",
    "🚪 Last-Mile Vocation Gate: Cosmos Edition 🌌🧰 (keep ON w/ Killswitch)",
    "🚪 Last-Mile Gemini Banned Vocab Check 🌠",
    "🚪 Last-Mile Scent Gate: Cosmos Edition 🌌👃 (Keep ON w/ Killswitch)",
    "🫢'Really Did It' Restatement Fix for Western Models ✨",   # Western models only
    "🧘Anti-Omniscient NPCs and Thoughts 💥🧠",                  # replaced by the MiMo V2.6 edition
]
# Names in the file may differ slightly (trailing text); match by prefix where needed
def names_like(preset, prefixes):
    out = []
    for p in prefixes:
        hits = [b["name"] for b in preset["blocks"] if b["name"].strip().startswith(p.strip()[:40])]
        assert hits, p
        out.append(hits[0])
    return out

toggle(mimo, names_like(mimo, GEMINI_ONLY), False)
MIMO_ON = [
    "👃 Smell & Taste Rules 👅 (OFF for Gemini)",
    "🎤NPC Voice + Dialogue Output🗣️",
    "🚫Banned Word List📝",
    "⚖️ Comparative Emphasis Killswitch 🚫",
    "🚪 Last-Mile Contrast Gate ⚖️ (keep ON w/ Killswitch)",
    "🧰 Occupational Monomania Killswitch 🚫",
    "🚪 Last-Mile Vocation Gate 🧰 (keep ON w/ Killswitch)",
    "🚪 Last-Mile Legato Gate 🗣️ (keep ON w/ Chop Killswitch)",
    "📱🧘 Anti-Omniscient NPCs and Thoughts: Mimo V2.6 Edition 💥🧠",
    "📱🧮 Fate Ledger: Mimo V2.6 Pro Edition",
    "🐉🪢 Chinese LLM Thinking Leash: Mimo V2.6 Pro Edition 📱",
    "📱🗣️ Language Hold: Mimo V2.6 Edition",
]
toggle(mimo, names_like(mimo, MIMO_ON), True)
# The native-reasoning MiMo configurations run the reasoning-leak cleanups
rules(mimo, [r["name"] for r in mimo["regex"] if r["name"].startswith(("RF2.2.1 — MiMo V2.6 leak", "RF2.2.1 — Strip leaked CoT checklist"))], True)
# The authors ship MiMo V2.6 Pro at temperature 0.7 / top-p 0.8 with thinking on. Our MiMo profile says
# MiMo fixes both while thinking (so they wouldn't be sent); until that's settled, thinking is simply on
# and temperature / top-p are left to MiMo. (Thinking is on/off for MiMo; "medium" means on.)
mimo["samplers"]["temperature"] = {"on": False, "value": 0.7}
mimo["samplers"]["top_p"] = {"on": False, "value": 0.8}
mimo["samplers"]["reasoning_effort"] = {"on": True, "value": "medium"}
mimo["extras"]["starter_note"] = ("MiMo V2.6 Pro BOLT, rebuilt from the preset's own toggle notes: MiMo editions on, "
                                  "Gemini-only blocks off, MiMo leak-cleanup rules on, thinking on. The authors also set temperature 0.7 / "
                                  "top-p 0.8, which MiMo ignores while thinking (see its model profile). "
                                  "Mature toggles off.")

def write(sid, model, preset, tagline, description, used):
    data = {"id": sid, "model": model, "experience": "full_preset", "title": "Realistic Frankenstein",
            "tagline": tagline, "description": description,
            "based_on": [{**CREDIT, "used": used}], "status": "community", "preset": preset}
    with open(OUT + sid + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    on = [b for b in preset["blocks"] if b["enabled"] and b["kind"] == "prompt"]
    print(sid, "blocks on:", len(on), "rules on:", sum(r["enabled"] for r in preset["regex"]),
          "~tokens on:", sum(len(b["content"]) for b in on) // 4)

write("gemini-frankenstein", "gemini-3-8-flash", gemini,
      "The big one: strict realism for chaotic models.",
      "A large community preset (dozens of switchable modules: story engines, NPC agendas, relationship "
      "tracking, anti-cliché gates) that holds Gemini to the rules very firmly. Heavy on tokens; "
      "its panels and cleanups rely on its text rules.",
      "The whole preset, as shipped in its Realistic Gemini BOLT configuration. Only its Mature toggles are "
      "switched off, as in every starter.")
write("mimo-frankenstein", "mimo-v2-6-pro", mimo,
      "The big one: strict realism, with MiMo's own fixes.",
      "A large community preset with MiMo V2.6 editions of its rules: a thinking leash, a language hold, "
      "and cleanups for reasoning that leaks into replies. Heavy on tokens; its panels and cleanups rely on "
      "its text rules.",
      "The whole preset, set up as its MiMo V2.6 Pro BOLT configuration from the preset's own notes (MiMo "
      "editions on, Gemini-only blocks off, MiMo leak cleanups on, thinking on). Mature toggles off.")
