from django import forms
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.utils.deconstruct import deconstructible
from django.core.exceptions import ValidationError

from .utils import get_elevenlabs_key
from .models import Character, Worldbook, TagPost

#ВСЕ, що нижче, треба повністю змінювати!!!!!!!!!!!!!!!
emotions = [
        "neutral", "happy", "sad", "angry", "surprised",
        "scared", "confused", "calm", "scheming"
    ]

GREETING_SEPARATOR = "<NEXT>"


class GreetingsField(forms.CharField):
    """Alternate greetings, one textarea; each greeting separated by a line with just <NEXT>."""
    widget = forms.Textarea

    def prepare_value(self, value):
        if isinstance(value, list):
            return f"\n{GREETING_SEPARATOR}\n".join(value)
        return value

    def to_python(self, value):
        text = super().to_python(value) or ""
        parts = [p.strip() for p in text.replace("\r\n", "\n").split(GREETING_SEPARATOR)]
        return [p for p in parts if p]


class AddCharacterForm(forms.ModelForm):
    # Shown under "Card details" instead of the main list
    card_fields = ('personality', 'example_dialogue', 'alternate_greetings', 'system_prompt',
                   'post_history_instructions', 'card_creator', 'card_version')

    alternate_greetings = GreetingsField(
        required=False, label="Alternate greetings",
        help_text=f"Other first messages to swipe between. Put a line with just {GREETING_SEPARATOR} between them.")

    worldbook = forms.ModelChoiceField(
        queryset=Worldbook.objects.none(),
        empty_label="Worldbook is not chosen",
        label="Worldbook",
        required=False
    )

    class Meta:
        model = Character
        fields = [
            'is_mult', 'name', 'description', 'scenario',
            'initial_message', 'creator_notes', 'worldbook',
            'personality', 'example_dialogue', 'alternate_greetings', 'system_prompt',
            'post_history_instructions', 'card_creator', 'card_version',

            'photo_neutral', 'photo_happy', 'photo_sad',
            'photo_angry', 'photo_surprised', 'photo_scared',
            'photo_confused', 'photo_calm', 'photo_scheming',

            'photo_second_neutral', 'photo_second_happy', 'photo_second_sad',
            'photo_second_angry', 'photo_second_surprised', 'photo_second_scared',
            'photo_second_confused', 'photo_second_calm', 'photo_second_scheming',

            'eleven_voice_char_id', 'eleven_voice_narr_id', 'eleven_voice_second_id', 'voice_cast'
        ]
        widgets = {
            'is_mult': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'scenario': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'initial_message': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'creator_notes': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
            'personality': forms.Textarea(attrs={'rows': 3}),
            'example_dialogue': forms.Textarea(attrs={'rows': 6, 'placeholder':
                '<START>\n{{user}}: "You could have asked for help."\n{{char}}: "I could have." '
                'He pushes the repaired lamp toward you. "It works now."'}),
            'system_prompt': forms.Textarea(attrs={'rows': 4}),
            'post_history_instructions': forms.Textarea(attrs={'rows': 3}),
            'eleven_voice_char_id': forms.TextInput(attrs={'placeholder': "Paste an ElevenLabs voice ID"}),
            'eleven_voice_narr_id': forms.TextInput(attrs={'placeholder': "Paste an ElevenLabs voice ID"}),
            'eleven_voice_second_id': forms.TextInput(attrs={'placeholder': "Paste an ElevenLabs voice ID"}),
            'voice_cast': forms.HiddenInput(),
        }
        labels = {'is_mult': 'Contains 2 characters', 'initial_message': 'First message',
                  'creator_notes': "Creator's notes"}
        help_texts = {
            'creator_notes': "For people reading the card. Never sent to the AI.",
            'personality': "Optional short reminder of who they are. Sent with the description.",
            'example_dialogue': "A few short exchanges in their voice, each starting with <START>.",
            'system_prompt': "Replaces your preset's main prompt for this character. "
                             "Write {{original}} to keep the preset's text. Leave empty normally.",
            'post_history_instructions': "Sent after the latest message. Leave empty normally.",
        }

    def __init__(self, *args, **kwargs):
        # Отримуємо користувача, переданого з view
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['worldbook'].queryset = Worldbook.objects.filter(author=user)

            self.has_eleven_key = True if get_elevenlabs_key(user) else False

            voice_fields = [
                'eleven_voice_char_id',
                'eleven_voice_narr_id',
                'eleven_voice_second_id'
            ]
            # Voices are optional per character, even with a key (an empty ID means no voice)
            for fname in voice_fields:
                self.fields[fname].required = False
            self.fields['voice_cast'].required = False

    def clean_voice_cast(self):
        cast = self.cleaned_data.get('voice_cast') or {}
        if not isinstance(cast, dict):
            return {}
        return {str(k).strip()[:60]: str(v).strip()[:64] for k, v in cast.items() if str(k).strip() and str(v).strip()}



class UploadFileForm(forms.Form):
    file = forms.ImageField(label="File")