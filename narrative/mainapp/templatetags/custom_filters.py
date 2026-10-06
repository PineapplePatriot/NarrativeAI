from django import template

register = template.Library()

@register.filter
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False


@register.filter
def names(text, character):
    """Shows {{char}}/{{user}} in card text as the character's and the owner's names."""
    from mainapp.cards import fill_names, user_name
    return fill_names(text, character.name, user_name(character.author))



@register.filter
def tagline(text):
    """A card description as a one-line preview: drops label-only lines like "Identity:" and labels at the start."""
    import re
    text = re.sub(r"(?m)^\s*[\w'{} ]{1,40}:\s*$", "", text or "")
    text = re.sub(r"^\s*(Identity|Description|Summary)\s*:\s*", "", text.strip(), flags=re.I)
    return " ".join(text.split())


@register.filter
def split(text, sep=","):
    return str(text or "").split(sep)
