"""
Dice and inventory kept by the app (function calling).

The chat model doesn't make up rolls or keep the inventory in its head: it calls tools, the app
rolls the dice and changes the inventory, and the model narrates what really happened.

- Mode (per character, Character.tracker_config["game"]; "default" follows the user's Extras choice):
  "off", "dice" (rolls only) or "full" (rolls, inventory and conditions).
- Every change a reply makes is an "op" stored on that reply (chats.with_game), per swipe. The
  inventory is the starting point plus the ops of the replies currently shown, replayed in order, so
  swiping, deleting or regenerating can never count the same key twice.
- In "full" mode the Inventory and Conditions trackers show this state, and the background tracker
  AI leaves them alone.
"""
import json
import random
import re

from mainapp import chats

MODES = ("off", "dice", "full")
MODE_LABELS = {"off": "Off", "dice": "Dice only", "full": "Dice and inventory"}
OWNED_TRACKERS = ("inventory", "conditions")   # in "full" mode, the app keeps these
MAX_TOOL_ROUNDS = 4
DICE = re.compile(r"^\s*(\d{0,2})d(\d{1,3})\s*([+-]\s*\d{1,3})?\s*$", re.I)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def user_default(user):
    from mainapp.models import ChatSettings
    s = ChatSettings.objects.filter(author=user).first()
    mode = ((s.appearance or {}).get("game") if s else None) or "off"
    return mode if mode in MODES else "off"


def set_user_default(user, mode):
    from mainapp.models import ChatSettings
    if mode not in MODES:
        raise ValueError("Unknown mode.")
    s, _ = ChatSettings.objects.get_or_create(author=user)
    s.appearance = {**(s.appearance or {}), "game": mode}
    s.save(update_fields=["appearance"])


def character_choice(character):
    choice = (character.tracker_config or {}).get("game", "default")
    return choice if choice in MODES else "default"


def mode_for(user, character):
    choice = character_choice(character)
    return user_default(user) if choice == "default" else choice


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def empty_state():
    return {"inventory": [], "conditions": []}


def _clean_state(raw):
    raw = raw if isinstance(raw, dict) else {}
    inv = []
    for i in raw.get("inventory") or []:
        if isinstance(i, dict) and str(i.get("name") or "").strip():
            try:
                qty = int(float(i.get("qty", 1)))
            except (TypeError, ValueError):
                qty = 1
            if qty > 0:
                inv.append({"name": str(i["name"]).strip()[:80], "qty": qty, "group": str(i.get("group") or "")[:40]})
    cond = [{"name": str(c["name"]).strip()[:80], "effect": str(c.get("effect") or "")[:200],
             "duration": str(c.get("duration") or "")[:80]}
            for c in raw.get("conditions") or [] if isinstance(c, dict) and str(c.get("name") or "").strip()]
    return {"inventory": inv, "conditions": cond}


def _find(items, name):
    key = name.strip().lower()
    return next((i for i in items if i["name"].lower() == key), None)


def apply_op(state, op):
    """Apply one recorded op to a state (in place). Ops were validated when they were made."""
    if op.get("type") == "item":
        item = _find(state["inventory"], op["item"])
        if item is None and op["change"] > 0:
            state["inventory"].append({"name": op["item"], "qty": op["change"], "group": op.get("group", "")})
        elif item is not None:
            item["qty"] += op["change"]
            if item["qty"] <= 0:
                state["inventory"].remove(item)
    elif op.get("type") == "condition":
        existing = _find(state["conditions"], op["name"])
        if op["action"] == "add" and existing is None:
            state["conditions"].append({"name": op["name"], "effect": op.get("effect", ""),
                                        "duration": op.get("duration", "")})
        elif op["action"] == "remove" and existing is not None:
            state["conditions"].remove(existing)


def current_state(chat_state, messages):
    """The starting point plus the ops of the replies currently shown (after the last manual edit)."""
    game = chat_state.get("game") if isinstance(chat_state.get("game"), dict) else {}
    state = _clean_state(game.get("base"))
    for m in list(messages)[game.get("base_upto") or 0:]:
        for op in chats.game_of(m):
            apply_op(state, op)
    return state


def set_base(chat_state, state, message_count):
    """A manual edit: this is the truth now; earlier replies' changes are already in it."""
    chat_state["game"] = {"base": _clean_state(state), "base_upto": message_count}


# ---------------------------------------------------------------------------
# Tools the chat model can call
# ---------------------------------------------------------------------------

def _fn(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": list(required)}}}


STR = {"type": "string"}
TOOLS = {
    "roll_dice": _fn(
        "roll_dice", "Roll dice for an uncertain action that matters. The app rolls; narrate the result you get.",
        {"action": {"type": "string", "description": "Who tries what, e.g. 'Mira picks the lock'"},
         "dice": {"type": "string", "description": "Dice to roll, e.g. 1d20 (default), 2d6, 1d100"},
         "modifier": {"type": "integer", "description": "Bonus or penalty from skill, tools or conditions, -5..5"},
         "difficulty": {"type": "integer", "description": "Number to reach: 5 easy, 10 moderate, 15 hard, 20 very hard"}},
        ["action"]),
    "change_inventory": _fn(
        "change_inventory", "Add or remove items when they are found, bought, used up, lost or given away.",
        {"changes": {"type": "array", "items": {"type": "object", "properties": {
            "item": STR, "change": {"type": "integer", "description": "+ gained, - used or lost"},
            "group": {"type": "string", "description": "Optional: currency, equipped or carried"}},
            "required": ["item", "change"]}}}, ["changes"]),
    "change_conditions": _fn(
        "change_conditions", "Add or remove a temporary condition of the user's character (injured, poisoned, "
        "exhausted...).",
        {"add": {"type": "array", "items": {"type": "object", "properties": {
            "name": STR, "effect": STR, "duration": STR}, "required": ["name"]}},
         "remove": {"type": "array", "items": STR}}),
}


def tools_for(mode):
    if mode == "dice":
        return [TOOLS["roll_dice"]]
    if mode == "full":
        return list(TOOLS.values())
    return []


def roll(dice="1d20", modifier=0, difficulty=None, rng=None):
    rng = rng or random.SystemRandom()
    m = DICE.match(dice or "1d20") or DICE.match("1d20")
    count, sides = int(m.group(1) or 1), int(m.group(2))
    count, sides = max(1, min(count, 20)), max(2, min(sides, 1000))
    bonus = int(re.sub(r"\s", "", m.group(3))) if m.group(3) else 0
    modifier = max(-10, min(10, int(modifier or 0))) + bonus
    rolls = [rng.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    op = {"type": "roll", "dice": f"{count}d{sides}", "rolls": rolls, "modifier": modifier, "total": total}
    if difficulty is not None:
        op["difficulty"] = int(difficulty)
        if count == 1 and sides == 20 and rolls[0] == 20:
            op["outcome"] = "critical success"
        elif count == 1 and sides == 20 and rolls[0] == 1:
            op["outcome"] = "critical failure"
        else:
            op["outcome"] = "success" if total >= op["difficulty"] else "failure"
    return op


def run_tool(state, name, args, rng=None):
    """Carry out one tool call against the reply's working state. Returns (result for the model, ops)."""
    from mainapp import extras
    if name in extras.TOOL_KIND:
        return extras.run_tool(name, args)
    if name == "roll_dice":
        try:
            difficulty = int(args["difficulty"]) if args.get("difficulty") is not None else None
            op = roll(str(args.get("dice") or "1d20"), args.get("modifier") or 0, difficulty, rng)
        except (TypeError, ValueError):
            return {"error": "Bad numbers; use dice like 1d20 and whole numbers."}, []
        op["action"] = str(args.get("action") or "")[:120]
        result = {k: op[k] for k in ("dice", "rolls", "modifier", "total", "difficulty", "outcome") if k in op}
        return result, [op]
    if name == "change_inventory":
        ops, results = [], []
        for c in (args.get("changes") or [])[:10]:
            if not isinstance(c, dict) or not str(c.get("item") or "").strip():
                continue
            item_name = str(c["item"]).strip()[:80]
            try:
                change = int(c.get("change", 0))
            except (TypeError, ValueError):
                change = 0
            have = _find(state["inventory"], item_name)
            if change == 0:
                continue
            if change < 0 and (have is None or have["qty"] < -change):
                results.append({"item": item_name, "error": f"Not enough: has {have['qty'] if have else 0}."})
                continue
            op = {"type": "item", "item": have["name"] if have else item_name, "change": change,
                  "group": str(c.get("group") or "")[:40]}
            apply_op(state, op)
            ops.append(op)
            now = _find(state["inventory"], op["item"])
            results.append({"item": op["item"], "now": now["qty"] if now else 0})
        return {"results": results}, ops
    if name == "change_conditions":
        ops = []
        for c in (args.get("add") or [])[:5]:
            if isinstance(c, dict) and str(c.get("name") or "").strip() and not _find(state["conditions"], c["name"]):
                ops.append({"type": "condition", "action": "add", "name": str(c["name"]).strip()[:80],
                            "effect": str(c.get("effect") or "")[:200], "duration": str(c.get("duration") or "")[:80]})
        for n in (args.get("remove") or [])[:5]:
            have = _find(state["conditions"], str(n))
            if have:
                ops.append({"type": "condition", "action": "remove", "name": have["name"]})
        for op in ops:
            apply_op(state, op)
        return {"conditions": [c["name"] for c in state["conditions"]]}, ops
    return {"error": f"No tool called {name}."}, []


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

DICE_RULES = (
    "Dice (kept by the app): when {{user}} or another character tries something whose outcome is "
    "uncertain and matters, call roll_dice before you write the outcome, then write the result you got: "
    "a failure fails, a critical success is remarkable. Set the difficulty from how hard it really is "
    "(5 easy, 10 moderate, 15 hard, 20 very hard) and a modifier from skill, tools and conditions. Don't "
    "roll for trivial or certain actions, and never make up a roll. Keep numbers out of the story: the "
    "app shows the roll. Roll for {{user}}'s attempts; what {{user}} decides to try stays theirs.")
INVENTORY_RULES = (
    "Inventory and conditions (kept by the app): call change_inventory when an item is gained, bought, "
    "used up, lost or given away, and change_conditions when {{user}}'s character is hurt, poisoned, "
    "exhausted or recovers. {{user}} can only use what is listed; if they reach for something they don't "
    "have, the story notices. Mention items and conditions in the story when they matter, without numbers.")


def prompt_block(mode, state):
    if mode == "off":
        return ""
    parts = [DICE_RULES]
    if mode == "full":
        inv = ", ".join(f"{i['name']} ×{i['qty']}" if i["qty"] != 1 else i["name"] for i in state["inventory"])
        cond = ", ".join(c["name"] + (f" ({c['effect']})" if c["effect"] else "") for c in state["conditions"])
        parts += [INVENTORY_RULES, f"{{{{user}}}}'s inventory now: {inv or 'nothing'}.",
                  f"{{{{user}}}}'s conditions now: {cond or 'none'}."]
    return "\n\n".join(parts)


def add_to_request(built, mode, state, names, extra_kinds=()):
    """Tools and rules (dice, inventory and story extras) into an assembled request; the rules go just before
    the last message, to keep the start of the prompt cacheable."""
    from mainapp import extras
    tools = tools_for(mode) + extras.tools_for(extra_kinds)
    if not tools:
        return built
    text = "\n\n".join(t for t in (prompt_block(mode, state), extras.rules_for(extra_kinds)) if t)
    text = text.replace("{{user}}", names.get("user", "the user")).replace("{{char}}", names.get("char", ""))
    messages = list(built["messages"])
    messages.insert(max(len(messages) - 1, 0), {"role": "system", "content": text})
    return {**built, "messages": messages, "params": {**built["params"], "tools": tools}}


# ---------------------------------------------------------------------------
# Running a reply with tools
# ---------------------------------------------------------------------------

class GameEvent(dict):
    """Something that happened while the reply was written (a roll, an item), for the page."""


def stream_reply(user, messages, params, state, rng=None):
    """Like ai_client.stream, but carries out tool calls and asks again, up to MAX_TOOL_ROUNDS.
    Yields text, ai_client.Reasoning and GameEvent pieces. `state` is changed as the reply goes."""
    from mainapp import ai_client
    from mainapp import extras
    messages = list(messages)
    written = []  # the reply's text so far, over all rounds
    shown = 0     # story extras so far (numbered for their markers)
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        if round_no == MAX_TOOL_ROUNDS:  # enough tools: just write
            params = {k: v for k, v in params.items() if k != "tools"}
        calls, text = None, []
        try:
            pieces = list_first(ai_client.stream(user, "chat", messages, **params))
        except ai_client.AIError as e:
            # Some models or providers can't take tools at all: write without them, and say so once
            if round_no or "tool" not in str(e).lower() or "tools" not in params:
                raise
            params = {k: v for k, v in params.items() if k != "tools"}
            yield GameEvent({"type": "notice", "text": "This model can't use the app's tools (dice, inventory, story extras), so "
                                                        "this reply was written without them."})
            pieces = list_first(ai_client.stream(user, "chat", messages, **params))
        for piece in pieces:
            if isinstance(piece, ai_client.ToolCalls):
                calls = piece
                continue
            if not isinstance(piece, ai_client.Reasoning):
                if not text and written and not written[-1][-1:].isspace() and not piece[:1].isspace():
                    written.append("\n\n")
                    yield "\n\n"  # a new round starts a new paragraph
                text.append(piece)
                written.append(piece)
            yield piece
        if not calls:
            return
        assistant = {"role": "assistant", "content": "".join(text) or None, "tool_calls": list(calls)}
        if calls.reasoning_details:
            assistant["reasoning_details"] = calls.reasoning_details
        messages.append(assistant)
        for call in calls:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            result, ops = run_tool(state, fn.get("name"), args if isinstance(args, dict) else {}, rng)
            for op in ops:
                if extras.is_extra(op):  # the model places it in its text with a marker (see extras.place)
                    shown += 1
                    op.update(n=shown, at=len("".join(written)))
                    result = {**result, "place": f"Put {extras.marker(shown)} on its own line in your reply, "
                                                 "where it appears in the story."}
                yield GameEvent(op)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result)})


def list_first(generator):
    """Start a generator now (so a request error is raised here), then hand over its pieces."""
    first = next(generator, None)

    def rest():
        if first is not None:
            yield first
        yield from generator
    return rest()


def describe(op):
    """One line for the page and for exports."""
    if op.get("type") == "roll":
        mod = f"{op['modifier']:+d}" if op.get("modifier") else ""
        line = f"🎲 {op.get('action') or 'Roll'}: {op['dice']}{mod} = {op['total']}"
        if "difficulty" in op:
            line += f" vs {op['difficulty']}: {op['outcome']}"
        return line
    if op.get("type") == "item":
        return f"🎒 {op['change']:+d} {op['item']}"
    if op.get("type") == "condition":
        return f"🩹 {'+' if op['action'] == 'add' else '−'} {op['name']}"
    if op.get("type") == "notice":
        return f"ℹ️ {op['text']}"
    return ""
