from django import forms
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.utils.deconstruct import deconstructible
from django.core.exceptions import ValidationError


from .models import Character, Worldbook, TagPost

#ВСЕ, що нижче, треба повністю змінювати!!!!!!!!!!!!!!!
emotions = [
        "neutral", "happy", "sad", "angry", "surprised",
        "scared", "confused", "calm", "scheming"
    ]

class AddCharacterForm(forms.ModelForm):
    worldbook = forms.ModelChoiceField(
        queryset=Worldbook.objects.all(),
        empty_label="Worldbook is not chosen",
        label="Worldbook"
    )

    tags = forms.ModelMultipleChoiceField(
        queryset=TagPost.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,  # або SelectMultiple, якщо хочеш список
        label="Tags"
    )

    class Meta:
        model = Character
        fields = [
            'name', 'slug', 'description', 'scenario',
            'initial_message', 'creator_notes', 'worldbook', 'tags',
            'photo_neutral', 'photo_happy', 'photo_sad', 'photo_angry',
            'photo_surprised', 'photo_scared', 'photo_confused',
            'photo_calm', 'photo_scheming',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'scenario': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'initial_message': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
            'creator_notes': forms.Textarea(attrs={'cols': 50, 'rows': 5}),
        }
        labels = {'slug': "Slug"}

    # def clean_title(self):
    #     title = self.cleaned_data['title']
    #     print(title)
    #     if len(title) > 50:
    #         raise ValidationError("Заголовок не більше 50 символів")

# class AddPostForm(forms.Form):
#     title = forms.CharField(max_length=255, min_length=5,
#                             label="Заголовок",
#                             widget=forms.TextInput(attrs={'class': 'form-input'}),
#                             validators=[
#                                 UkrainianValidator()
#                             ],
#                             error_messages={
#                                 'min_length': "Занадто коротки йзаголовок",
#                                 'reqired': "Без назви ніяк",
#                             })
#     slug = forms.SlugField(max_length=255, label="Slug",
#                            validators=[
#                                MinLengthValidator(5, "Мінімум 5 символів"),
#                                MaxLengthValidator(100, "Максимум 100 символів"),
#                            ])
#     content = forms.CharField(widget=forms.Textarea(attrs={'cols':50, 'rows':5}), required=False, label="Контент")
#     is_published = forms.BooleanField(required=False, initial=True,label="Статус")
#     cat = forms.ModelChoiceField(queryset=Category.objects.all(), empty_label="Категорія не вибрана", label="Категорія")
#     doi = forms.ModelChoiceField(queryset=Doi.objects.all(), empty_label="Doi не присвоєний", required=False, label="DOI")
#
#     def clean_title(self):
#         title = self.cleaned_data['title']
#         ALLOWED_CHARS = "абвгдеєжзиіїйклмнопрстяює"
#
#         if not (set(title) <= set(self.ALLOWED_CHARS)):
#             raise ValidationError(self.message, code=self.code)


class UploadFileForm(forms.Form):
    file = forms.ImageField(label="Файл")