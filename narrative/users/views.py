# --- Django auth ---
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView

# --- Django core ---
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, UpdateView

# --- Local imports ---
from narrative import settings
from .forms import (
    LoginUserForm, RegisterUserForm,
    ProfileUserForm, UserPasswordChangeForm,
    ApiConfigForm
)
from .models import ApiConfig


class LoginUser(LoginView):
    #form_class = AuthenticationForm
    form_class = LoginUserForm
    template_name = 'users/login.html'
    extra_context = {'title': "Авторизація"}


class RegisterUser(CreateView):
    form_class = RegisterUserForm
    template_name = 'users/register.html'
    extra_context = {'title' : "Реєстрація"}
    #success_url =  reverse_lazy('users:login')
    success_url = reverse_lazy('users:api_config')  # після успішної реєстрації

    def form_valid(self, form):
        user = form.save()
        # (необов’язково) автоматичний логін:
        # from django.contrib.auth import login
        # login(self.request, user)
        return super().form_valid(form)


class ProfileUser(LoginRequiredMixin, UpdateView):
    model = get_user_model()
    form_class = ProfileUserForm
    template_name = 'users/profile.html'
    extra_context = {
        'title': 'Profile',
        'default_image': settings.DEFAULT_USER_IMAGE,             }

    def get_success_url(self):
        return reverse_lazy('users:profile')

    def get_object(self, queryset=None):
        return self.request.user

class UserPasswordChange(PasswordChangeView):
    form_class = UserPasswordChangeForm
    success_url = reverse_lazy("users:password_change_done")
    template_name = "users/password_change_form.html"



@method_decorator(login_required, name="dispatch")
class ApiConfigView(UpdateView):
    model = ApiConfig
    form_class = ApiConfigForm
    template_name = "users/api_config.html"
    success_url = reverse_lazy("home")

    def get_object(self, queryset=None):
        # отримати або створити ApiConfig користувача
        obj, created = ApiConfig.objects.get_or_create(user=self.request.user)
        return obj

    def form_valid(self, form):
        # переконаємось, що user завжди присвоєно
        form.instance.user = self.request.user
        return super().form_valid(form)


class MyLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect(reverse_lazy('users:login'))
