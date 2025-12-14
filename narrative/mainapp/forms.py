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

class AddCharacterForm(forms.ModelForm):

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

            'photo_neutral', 'photo_happy', 'photo_sad',
            'photo_angry', 'photo_surprised', 'photo_scared',
            'photo_confused', 'photo_calm', 'photo_scheming',

            'photo_second_neutral', 'photo_second_happy', 'photo_second_sad',
            'photo_second_angry', 'photo_second_surprised', 'photo_second_scared',
            'photo_second_confused', 'photo_second_calm', 'photo_second_scheming',

            'eleven_voice_char_id', 'eleven_voice_narr_id',
        ]
        widgets = {
            'is_mult': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'scenario': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'initial_message': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'creator_notes': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'eleven_voice_char_id': forms.TextInput(attrs={'placeholder': "Введіть ID"}),
            'eleven_voice_narr_id': forms.TextInput(attrs={'placeholder': "Введіть ID"}),
        }
        labels = {'is_mult': 'Contains 2 characters',}

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
            ]
            for fname in voice_fields:
                self.fields[fname].required = self.has_eleven_key



class UploadFileForm(forms.Form):
    file = forms.ImageField(label="Файл")