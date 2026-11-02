from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from .models import User, ApiConfig

class LoginLock:
    """Mixed into a login form (the app's own, and the admin's when it's switched on)."""

    def clean(self):
        """Wrong passwords are counted per username and per address; past the limit, logging in waits
        (settings.LOGIN_MAX_FAILURES / LOGIN_LOCK_SECONDS). An address gets more tries: people share them."""
        from django.conf import settings
        from django.core.cache import cache
        limits = _failure_keys(self.request, self.cleaned_data.get("username"))
        if any(cache.get(key, 0) >= limit for key, limit in limits):
            raise forms.ValidationError(f"Too many wrong passwords. Try again in "
                                        f"{settings.LOGIN_LOCK_SECONDS // 60} minutes.", code="locked")
        try:
            data = super().clean()
        except forms.ValidationError:
            for key, _ in limits:
                cache.add(key, 0, settings.LOGIN_LOCK_SECONDS)  # the window starts at the first failure
                try:
                    cache.incr(key)
                except ValueError:  # expired in between
                    cache.set(key, 1, settings.LOGIN_LOCK_SECONDS)
            raise
        cache.delete(limits[0][0])
        return data


class LoginUserForm(LoginLock, AuthenticationForm):
    username = forms.CharField(label="Login",
        widget=forms.TextInput(attrs={'class': 'form-input'}))
    password = forms.CharField(label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-input'}))

    class Meta:
        model = get_user_model()
        fields = ['username', 'password']


class AdminLoginForm(LoginLock, AdminAuthenticationForm):
    pass


def _failure_keys(request, username):
    from django.conf import settings
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() if request else ""
    address = forwarded or (request.META.get("REMOTE_ADDR", "") if request else "")
    return [(f"login-fail:user:{(username or '').strip().lower()}", settings.LOGIN_MAX_FAILURES),
            (f"login-fail:ip:{address}", settings.LOGIN_MAX_FAILURES * 3)]



def unique_email(email, user=None):
    """An address no other account uses (whatever the letter case), stored in lower case."""
    email = (email or "").strip().lower()
    others = get_user_model().objects.filter(email__iexact=email)
    if user is not None and user.pk:
        others = others.exclude(pk=user.pk)
    if email and others.exists():
        raise forms.ValidationError("An account with this email already exists.")
    return email


class RegisterUserForm(UserCreationForm):
    username = forms.CharField(label="Login", widget=forms.TextInput(attrs={'class': 'form-input'}))
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={'class': 'form-input'}))  # required
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
        return unique_email(self.cleaned_data['email'])




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
            'persona_description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4,
                                                         'placeholder': 'Who you are in the story: look, personality, background.'}),
        }

    def clean_email(self):
        return unique_email(self.cleaned_data.get('email'), self.instance)

class UserPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(label="Old password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))