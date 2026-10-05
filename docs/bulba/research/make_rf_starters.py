# Builds the two Realistic Frankenstein starters from the shipped Gemini BOLT file:
#   gemini-frankenstein: the file as shipped (Mature toggles off, as in every starter)
#   mimo-frankenstein:   MiMo V2.6 Pro BOLT, from the authors' MiMo V2.6 Pro file
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "narrative"))
from mainapp import presets

SRC = os.path.join(HERE, "Realistic_Frankenstein_2.2.1.2.json")  # the shipped Gemini BOLT file (not in the repo)
MIMO_FILE = os.path.join(HERE, "Realistic_Frankenstein_2.2.1.2_Mimo_V2_6_Pro.json")  # the authors' MiMo V2.6 Pro file (not in the repo)
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

# --- MiMo V2.6 Pro BOLT ------------------------------------------------------------------------------
# Starts from the authors' own MiMo V2.6 Pro file (their pico setup: native thinking off), then switches
# what their README says differs in BOLT: the BOLT chain of thought instead of pico, native thinking on
# with the MiMo thinking leash and Fate Ledger, and the reasoning-leak cleanup rules on.
mimo = presets.from_sillytavern(json.load(open(MIMO_FILE)))
toggle(mimo, MATURE, False)
toggle(mimo, ["🤏 pico CoT: Mimo V2.6 Edition (native reasoning OFF) 🪶"], False)
toggle(mimo, ["⚡️ BOLT Chain of Thought 🧠", "🐉🪢 Chinese LLM Thinking Leash: Mimo V2.6 Pro Edition 📱",
              "📱🧮 Fate Ledger: Mimo V2.6 Pro Edition"], True)
rules(mimo, [r["name"] for r in mimo["regex"] if r["name"].startswith(("RF2.2.1 — MiMo V2.6 leak", "RF2.2.1 — Strip leaked CoT checklist"))], True)
# Thinking on. MiMo uses its own temperature / top-p while thinking (the authors' 0.7 / 0.8 belong to the
# pico setup, where thinking is off), so they're left unset here.
mimo["samplers"]["temperature"] = {"on": False, "value": 0.7}
mimo["samplers"]["top_p"] = {"on": False, "value": 0.8}
mimo["samplers"]["reasoning_effort"] = {"on": True, "value": "medium"}
mimo["extras"]["starter_note"] = ("MiMo V2.6 Pro BOLT: the authors' MiMo V2.6 Pro file with the BOLT chain of thought, "
                                  "native thinking, thinking leash, Fate Ledger and leak cleanups switched on, as their "
                                  "README describes. Mature toggles off.")

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
      "The whole preset: the authors' MiMo V2.6 Pro configuration, switched to BOLT as their README describes "
      "(BOLT chain of thought, native thinking, thinking leash, Fate Ledger, leak cleanups). Mature toggles off.")
