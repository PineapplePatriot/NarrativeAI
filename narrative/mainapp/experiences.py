"""Original experience family. Legacy artifacts supply technical settings/slots only."""
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


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'data/bulba/experience_presets.json').read_text(encoding='utf-8'))


def generate(template, profile, feel):
    from mainapp import writing_quality
    data = catalog()
    experience = data['experiences'][feel]
    preset = copy.deepcopy(template['preset'])
    # Keep supported settings and application context markers; never copy community prompt text.
    markers = [b for b in preset['blocks'] if b.get('kind') == 'marker']
    def prompt(name, content, **extra):
        return {'name': name, 'kind': 'prompt', 'role': 'system', 'enabled': True, 'content': content, **extra}
    preset['blocks'] = [
        prompt('Roleplay', "Write {{char}} and the other scene characters within the separate Your character authorship contract. Continue from accepted events and follow the selected experience and viewpoint. The Writing quality block supplies the shared narrative foundation; do not output checks or a repeated turn procedure."),
        prompt('Presentation defaults', 'Unless the participant selects otherwise, use present tense, third-person narration, a discreet narrator and textured prose. Enter the thoughts of model-controlled characters when useful, within the authorship contract. Develop the current contribution to a natural stopping point; no fixed word or paragraph quota is required. Add plausible details consistent with supplied canon, the card and accepted events. Explicit preferences for tense, viewpoint, texture, scope or invention override these defaults.'),
        prompt('Model foundation', data['foundations'][data['model_foundations'][profile['id']]]),
        prompt('Style', experience['content']),
        prompt('Your character', CONTRACTS['dont']),
        prompt('Mature content (optional)', 'Adult themes may appear when enabled and appropriate to the established story. Preserve characterization, context and the agreed boundaries rather than imposing a separate generic tone.', enabled=False),
    ] + markers + [prompt(e['title'], e['content'], enabled=False) for e in data['extensions'].values()]
    # Experiences impose neither a length nor a new generation/translation language policy.
    preset.setdefault('extras', {})['original_experience'] = {'id': feel, 'foundation': data['model_foundations'][profile['id']]}
    starter = {'id': profile['starters'][feel], 'model': profile['id'], 'experience': feel,
               'title': experience['title'], 'tagline': experience['description'],
               'description': experience['description'], 'status': 'research-informed', 'based_on': [], 'preset': preset}
    return writing_quality.add_baseline(starter)


def configure(preset, mode='dont', extensions=()):
    from mainapp import presets
    if mode not in CONTRACTS:
        raise ValueError('Choose roleplay, shared authorship or directing.')
    if not isinstance(extensions, (list, tuple)) or any(not isinstance(e, str) or e not in catalog()['extensions'] for e in extensions):
        raise ValueError('Unknown experience extension.')
    result = copy.deepcopy(preset)
    result['blocks'] = [b for b in result['blocks'] if b.get('name') != 'Your character']
    result['blocks'].insert(0, presets.normalize_block({'name': 'Your character', 'kind': 'prompt', 'content': CONTRACTS[mode]}))
    selected = {catalog()['extensions'][e]['title'] for e in extensions}
    for block in result['blocks']:
        if block.get('name') in {e['title'] for e in catalog()['extensions'].values()}:
            block['enabled'] = block['name'] in selected
    return result
