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
