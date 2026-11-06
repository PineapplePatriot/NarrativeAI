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
        typed = (self.cleaned_data.get("username") or "").strip()
        if "@" in typed:  # their email instead of the login: emails are unique per account
            owner = get_user_model().objects.filter(email__iexact=typed).first()
            if owner:
                self.cleaned_data["username"] = owner.username
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
    username = forms.CharField(label="Login or email",
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
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={'class': 'form-input'}))  # required
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))

    class Meta:
        model = get_user_model()
        # Who they are in stories (the persona) is made with Bulba, or asked once in their first chat
        fields = ['username', 'email', 'first_name', 'password1', "password2"]
        labels = {'email': 'Email', 'first_name': "First name"}

    widgets = {
        'email': forms.TextInput(attrs={'class': 'form-input'}),
        'first_name': forms.TextInput(attrs={'class': 'form-input'}),
    }


    def clean_email(self):
        return unique_email(self.cleaned_data['email'])




class ProfileUserForm(forms.ModelForm):
    class Meta:
        model = User
        # The persona (who they are in stories): Bulba can make it, they can edit it here; each chat can still
        # have its own (the pen menu)
        fields = ['photo', 'first_name', 'date_birth', 'username', 'email', 'persona_name', 'persona_description']
        labels = {'username': "Login", 'email': "Email", 'persona_name': "Name in stories",
                  'persona_description': "About you in stories"}
        help_texts = {'username': "What you type to log in (your email works too)."}
        widgets = {
            'photo': forms.FileInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'date_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'persona_name': forms.TextInput(attrs={'class': 'form-input', 'maxlength': 100, 'placeholder': 'e.g. Wren'}),
            'persona_description': forms.Textarea(attrs={'class': 'form-input', 'rows': 5, 'maxlength': 8000,
                'placeholder': 'Your look, attitude, a habit or two. The AI reads this to know who it talks to.'}),
        }

    PERSONA = ('persona_name', 'persona_description')

    def account_fields(self):
        return [f for f in self if f.name != 'photo' and f.name not in self.PERSONA]

    def persona_fields(self):
        return [self[n] for n in self.PERSONA]

    def clean_email(self):
        return unique_email(self.cleaned_data.get('email'), self.instance)

    def clean(self):
        data = super().clean()
        for n in self.PERSONA:  # empty stays empty (not None), so the chat's "who are you?" hint reads it right
            data[n] = (data.get(n) or '').strip()
        return data

class UserPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(label="Old password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    new_password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput(attrs={'class': 'form-input'}))