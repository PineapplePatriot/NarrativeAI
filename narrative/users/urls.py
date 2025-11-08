from django.urls import path
from django.contrib.auth.views import LogoutView, PasswordChangeView, PasswordChangeDoneView
from . import views

app_name = "users"

urlpatterns = [
    path('login/', views.LoginUser.as_view(), name ='login'),
    path('logout/', views.MyLogoutView.as_view(), name='logout'),

    path('password-change/', views.UserPasswordChange.as_view(), name="password_change"),
    path('password-change/done/', PasswordChangeDoneView.as_view(template_name="users/password_change_done.html"), name="password_change_done"),

    path('register/', views.RegisterUser.as_view(), name='register'),
    path('profile/', views.ProfileUser.as_view(), name='profile'),
    path("api-config/", views.ApiConfigView.as_view(), name="api_config"),
]