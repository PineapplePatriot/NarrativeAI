from django.urls import path, re_path, register_converter

from . import views

urlpatterns = [
path('add_character/', views.AddCharacter.as_view(), name="add_character"),
path('character_edit/<slug:slug>', views.UpdateCharacter.as_view(), name="character"),
path('chat/<slug:slug>', views.chat, name="chat"),
path('characters_list/', views.CharactersList.as_view(), name="characters_list"),
path('chat_settings/', views.chat_settings, name="chat_settings"),
path('worldbook_create/', views.worldbook_create, name='worldbook_create'),
path('worldbook_detail/<slug:slug>', views.worldbook_detail, name='worldbook_detail'),
path('worldbook_list/', views.worldbook_list, name='worldbook_list'),
    ]
#handler404 = page_not_found