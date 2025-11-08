from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from .models import User, ApiConfig

class LoginUserForm(AuthenticationForm):
    username = forms.CharField(label="Login",
        widget=forms.TextInput(attrs={'class': 'form-input'}))
    password = forms.CharField(label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-input'}))

    class Meta:
        model = get_user_model()
        fields = ['username', 'password']



class RegisterUserForm(UserCreationForm):
    username = forms.CharField(label="Login", widget=forms.TextInput(attrs={'class': 'form-input'}))
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', "last_name", 'password1', "password2", "persona_name", "persona_description"]
        labels = {
            'email': 'E-mail',
            'first_name': "First name",
            'last_name': "Last name",
            'persona_name': "Persona name",
            'persona_description': "Persona description"
        }

    widgets = {
        'email': forms.TextInput(attrs={'class': 'form-input'}),
        'first_name': forms.TextInput(attrs={'class': 'form-input'}),
        'last_name': forms.TextInput(attrs={'class': 'form-input'}),
    }


    def clean_email(self):
        email = self.cleaned_data['email']
        if get_user_model().objects.filter(email=email).exists():
            raise forms.ValidationError("Such an email already exists.")
        return email




class ProfileUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['photo', 'first_name', 'last_name', 'date_birth', 'username', 'email','persona_name','persona_description']
        widgets = {
            'photo': forms.FileInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'date_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'persona_name': forms.TextInput(attrs={'class': 'form-input'}),
            'persona_description': forms.TextInput(attrs={'class': 'form-input'}),
        }

class ApiConfigForm(forms.ModelForm):
    class Meta:
        model = ApiConfig
        fields = ["chat_key", "eleven_key", "or_model"]

        widgets = {
            "chat_key": forms.PasswordInput(attrs={"class": "form-input", "placeholder": "sk-or-v1-..."}),
            "eleven_key": forms.PasswordInput(attrs={"class": "form-input", "placeholder": "sk_..."}),
            "or_model": forms.TextInput(attrs={"class": "form-input", "placeholder": "Default model"}),
        }

class UserPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(label="Old password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))