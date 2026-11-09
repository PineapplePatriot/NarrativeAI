"""
Experience presets, built from parts (all in mainapp/data/bulba/experience_presets.json):

  Roleplay            the base for the model's family: story-led (Claude, Gemini, MiMo; adapted from the user's
                      modified Pura) or rule-led (Kimi, GLM, DeepSeek; adapted from Sola's organisation), with the
                      never-write list and the out-of-character rule
  Presentation        follow the story's tense/POV unless the Basics block chooses otherwise
  Reply length        short / medium / long / flexible (the forms' choice)
  Style               the experience: Conversation & Chemistry, Character Drama or Immersive Storytelling
  Your character      exactly one authorship contract: roleplay, shared authorship or directing
  Writing quality     shared safeguards (writing_quality.py) and the model's pattern counters
  modules             Friction, No therapy talk, Busy world (on); Kindness guard, OOC co-author,
                      Explicit intimacy (off); extensions Adventure & Ensemble, Continuity & Simulation (off)
  Mature content      the app's own 18+ rule, off until switched on (mature.py)
  story slots, then the Reply reminder at the very end (a user message, never an assistant prefill)

Legacy starters supply only technical settings (samplers, story slots). Nothing is copied from community presets.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

EXPERIENCES = ('conversation', 'drama', 'storytelling')
CONTRACTS = {
    'dont': "Write the other characters and world. Do not write {{user}}'s new dialogue, voluntary actions, decisions or private thoughts. Respond to actions already established and apply external consequences within the agreed scene rules. Stop where the player's next contribution is needed.",
    'write': "Write the cast and world, including {{user}} as a scene character with dialogue, actions and thoughts. Treat the participant's corrections and stated character choices as authoritative. Do not expand these shared-authorship permissions into instructions about the real participant.",
    'director': "The participant directs the story from outside it. Write all characters present, including {{user}} when the scene includes that character. Treat the participant's messages as directions, not in-world dialogue. Never address the director as a character. Develop the requested scene until further direction is useful."
}
REMINDER = "Reply reminder"
LENGTH_BLOCK = "Reply length"


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'data/bulba/experience_presets.json').read_text(encoding='utf-8'))


def base_of(model_id):
    """'narrative' or 'structured': which family base a model profile gets."""
    data = catalog()
    return data['model_foundations'].get(model_id, data['default_base'])


def length_text(key):
    lengths = catalog()['lengths']
    return lengths.get(key, lengths[catalog()['default_length']])['content']


def set_length(preset, key):
    """The preset's Reply length block set to `key` (added before the story slots if missing). True if it has one."""
    from mainapp import presets
    if key not in catalog()['lengths']:
        return False
    block = next((b for b in preset['blocks'] if b.get('name') == LENGTH_BLOCK and b.get('kind') == 'prompt'), None)
    if block is None:
        if not (preset.get('extras') or {}).get('original_experience'):
            return False
        block = presets.normalize_block({'name': LENGTH_BLOCK, 'kind': 'prompt', 'content': ''})
        at = next((i for i, b in enumerate(preset['blocks']) if b.get('kind') == 'marker'), len(preset['blocks']))
        preset['blocks'].insert(at, block)
    block['content'] = length_text(key)
    block['enabled'] = True
    return True


def generate(template, profile, feel):
    from mainapp import mature, writing_quality
    data = catalog()
    experience = data['experiences'][feel]
    preset = copy.deepcopy(template['preset'])
    markers = [b for b in preset['blocks'] if b.get('kind') == 'marker']
    director_note = [b for b in markers if b.get('marker') == 'director_note']
    markers = [b for b in markers if b.get('marker') != 'director_note']

    def prompt(name, content, **extra):
        return {'name': name, 'kind': 'prompt', 'role': 'system', 'enabled': True, 'content': content, **extra}

    def module(key, m):
        return prompt(m['title'], m.get('variants', {}).get(profile['id'], m['content']), enabled=m['default'])

    base = base_of(profile['id'])
    preset['blocks'] = [
        prompt('Roleplay', data['bases'][base]),
        prompt('Presentation', data['presentation']),
        prompt(LENGTH_BLOCK, length_text(data['default_length'])),
        prompt('Style', experience['content']),
        prompt('Your character', CONTRACTS['dont']),
        *[module(k, m) for k, m in data['modules'].items()],
        *[prompt(e['title'], e['content'], enabled=False) for e in data['extensions'].values()],
        prompt('Mature content (optional)', mature.BLOCK_TEXT, enabled=False),
        *markers,
        prompt(REMINDER, data['reminders']['dont'], role='user', position='in_chat', depth=0),
        *director_note,
    ]
    preset.setdefault('extras', {})['original_experience'] = {'id': feel, 'foundation': base}
    starter = {'id': profile['starters'][feel], 'model': profile['id'], 'experience': feel,
               'title': experience['title'], 'tagline': experience['description'],
               'description': experience['description'], 'status': 'research-informed', 'based_on': [], 'preset': preset}
    return writing_quality.add_baseline(starter)


def configure(preset, mode='dont', extensions=()):
    """Exactly one authorship contract (and its matching reply reminder) and the chosen extensions."""
    from mainapp import presets
    if mode not in CONTRACTS:
        raise ValueError('Choose roleplay, shared authorship or directing.')
    if not isinstance(extensions, (list, tuple)) or any(not isinstance(e, str) or e not in catalog()['extensions'] for e in extensions):
        raise ValueError('Unknown experience extension.')
    result = copy.deepcopy(preset)
    old = next((i for i, b in enumerate(result['blocks']) if b.get('name') == 'Your character'), None)
    contract = presets.normalize_block({'name': 'Your character', 'kind': 'prompt', 'content': CONTRACTS[mode]})
    if old is None:
        result['blocks'].insert(0, contract)
    else:
        result['blocks'][old] = contract
    selected = {catalog()['extensions'][e]['title'] for e in extensions}
    for block in result['blocks']:
        if block.get('name') in {e['title'] for e in catalog()['extensions'].values()}:
            block['enabled'] = block['name'] in selected
    reminder = next((b for b in result['blocks'] if b.get('name') == REMINDER and b.get('position') == 'in_chat'), None)
    if reminder is not None:  # keep anything added to it (the 18+ line), swap only the contract's own line
        known = set(catalog()['reminders'].values())
        lines = [l for l in reminder['content'].split('\n') if l.strip() not in known]
        reminder['content'] = '\n'.join([catalog()['reminders'][mode], *[l for l in lines if l.strip()]])
    return result


GROUP_LABELS = {'characters': 'Characters', 'world': 'World', 'story': 'Story drive', 'prose': 'Prose',
                'collaboration': 'Talking to the AI', 'mature': 'Fights and 18+', 'voice': 'Narration voice'}
ADULT = {'slow_burn', 'dark_themes', 'explicit_intimacy', 'intense_explicit'}


def module_states(preset):
    """Every module with whether this preset has it on (a preset without the block counts as its default, off
    for presets that aren't experience presets)."""
    names = {b.get('name'): b for b in preset.get('blocks', []) if b.get('kind') == 'prompt'}
    experience = bool((preset.get('extras') or {}).get('original_experience'))
    out = []
    for key, m in catalog()['modules'].items():
        block = names.get(m['title'])
        on = block['enabled'] if block else (m['default'] and experience)
        out.append({'key': key, 'title': m['title'], 'about': m['about'], 'group': m.get('group', 'story'),
                    'adult': key in ADULT, 'on': bool(on)})
    return out


def set_modules(preset, wanted, model_id=''):
    """A copy with modules switched on or off ({key: bool}); missing blocks are added before the story slots.
    One narration voice at a time."""
    from mainapp import presets
    cat = catalog()['modules']
    wanted = {k: bool(v) for k, v in wanted.items() if k in cat}
    if sum(1 for k, v in wanted.items() if v and k.startswith('voice_')) > 1:
        raise ValueError('One narration voice at a time.')
    if any(v for k, v in wanted.items() if k.startswith('voice_')):  # picking a voice switches the others off
        for k in cat:
            if k.startswith('voice_') and not wanted.get(k):
                wanted[k] = False
    result = copy.deepcopy(preset)
    for key, on in wanted.items():
        m = cat[key]
        block = next((b for b in result['blocks'] if b.get('name') == m['title'] and b.get('kind') == 'prompt'), None)
        if block is None:
            if not on:
                continue
            block = presets.normalize_block({'name': m['title'], 'kind': 'prompt',
                                             'content': m.get('variants', {}).get(model_id, m['content'])})
            at = next((i for i, b in enumerate(result['blocks']) if b.get('kind') == 'marker'), len(result['blocks']))
            result['blocks'].insert(at, block)
        block['enabled'] = on
    return result
