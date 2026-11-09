"""Original research-derived baseline and scoped repair guidance for authored starters."""
import json
from functools import lru_cache
from pathlib import Path

BLOCK_ID = "narrative_writing_quality_v1"
BLOCK_NAME = "Writing quality"
COUNTER_ID = "narrative_model_counters_v1"
COUNTER_NAME = "Model pattern counters"


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "data/bulba/writing_quality.json").read_text(encoding="utf-8"))


def add_baseline(starter):
    """Materialize an ordinary editable/exportable block. Never rewrite a saved user preset."""
    if starter.get("experience") not in ("back_and_forth", "rich_scene", "director", "conversation", "drama", "storytelling"):
        return starter
    blocks = starter["preset"]["blocks"]
    if not any(b.get("id") == BLOCK_ID for b in blocks):
        index = next((i + 1 for i, b in enumerate(blocks) if b.get("name") == "Style"), 0)
        baseline = catalog()["baseline"]
        if (starter["preset"].get("extras") or {}).get("original_experience"):
            from mainapp import experiences
            baseline = experiences.catalog()["foundation"]
        blocks.insert(index, {"id": BLOCK_ID, "name": BLOCK_NAME, "kind": "prompt", "role": "system",
                              "enabled": True, "content": baseline})
    counter = catalog().get("default_counters", {}).get(starter.get("model"))
    if counter and not any(b.get("id") == COUNTER_ID for b in blocks):
        index = next(i + 1 for i, b in enumerate(blocks) if b.get("id") == BLOCK_ID)
        blocks.insert(index, {"id": COUNTER_ID, "name": COUNTER_NAME, "kind": "prompt", "role": "system",
                              "enabled": True, "content": counter})
    return starter


def guidance(model):
    data = catalog()
    selected = set(data["models"].get(model, []))
    lines = ["Writing quality: new authored starter variants include an editable Writing quality block. Older saved presets may not; inspect the active preset.",
             "Its safeguards concern recurring habits, not a ban on imagery, humor or interiority.",
             "Inspect it before adding rules. Baseline reference (do not append it automatically to an existing preset):",
             data["baseline"],
             "Default model counter (enabled in new authored starters, editable by the user):",
             data.get("default_counters", {}).get(model, ""),
             data.get("counter_evidence", ""),
             "Do not mistake an anti-fawning counter for an optional taste for hostility. Inspect model behavior and user intent before removing it.",
             "Phrase exclusions are user-selected and scoped. Never ban ordinary conjunctions, said, smile or silence by default. Preserve an explicit ban rather than weakening it to prefer variety.",
             "The following are diagnostic candidates, not established defects:"]
    for item in data["modules"]:
        if item["id"] in selected:
            lines += [f"- {item['problem']}: {item['instruction']}",
                      f"  Preserve: {item['exception']} Test: {item['test']}",
                      f"  Illustration (not a rewrite): {item['examples']['problem']} / {item['examples']['alternative']}"]
    return "\n".join(lines)
