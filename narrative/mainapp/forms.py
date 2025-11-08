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

    tags = forms.ModelMultipleChoiceField(
        queryset=TagPost.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tags",
    )

    class Meta:
        model = Character
        fields = [
            'name', 'description', 'scenario',
            'initial_message', 'creator_notes', 'worldbook', 'tags',
            'photo_neutral', 'photo_happy', 'photo_sad', 'photo_angry',
            'photo_surprised', 'photo_scared', 'photo_confused',
            'photo_calm', 'photo_scheming',
            'eleven_voice_char_name','eleven_voice_char_id',
            'eleven_voice_narr_name','eleven_voice_narr_id',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'scenario': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'initial_message': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'creator_notes': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'eleven_voice_char_name': forms.TextInput(attrs={'placeholder': "Введіть імʼя"}),
            'eleven_voice_char_id': forms.TextInput(attrs={'placeholder': "Введіть ID"}),
            'eleven_voice_narr_name': forms.TextInput(attrs={'placeholder': "Введіть імʼя"}),
            'eleven_voice_narr_id': forms.TextInput(attrs={'placeholder': "Введіть ID"}),
        }
        #labels = {'slug': "Slug"}

    def __init__(self, *args, **kwargs):
        # Отримуємо користувача, переданого з view
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['worldbook'].queryset = Worldbook.objects.filter(author=user)

            self.has_eleven_key = True if get_elevenlabs_key(user) else False

            voice_fields = [
                'eleven_voice_char_name', 'eleven_voice_char_id',
                'eleven_voice_narr_name', 'eleven_voice_narr_id',
            ]
            for fname in voice_fields:
                self.fields[fname].required = self.has_eleven_key



class UploadFileForm(forms.Form):
    file = forms.ImageField(label="Файл")