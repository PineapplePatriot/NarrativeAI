from django.urls import path, re_path, register_converter

from . import views

urlpatterns = [
path('api/media-resources/', views.get_media_resources, name='media_resources'),
path('add_character/', views.AddCharacter.as_view(), name="add_character"),
path('character_edit/<slug:slug>', views.UpdateCharacter.as_view(), name="character"),
path('chat/<slug:slug>', views.chat, name="chat"),
path('characters_list/', views.CharactersList.as_view(), name="characters_list"),
path('samplers/', views.sampler_settings, name="samplers"),
path('presets/', views.preset_list, name="presets"),
path('bulba/', views.bulba_page, name="bulba"),
path('bulba/api/', views.bulba_api, name="bulba_api"),
path('presets/<int:preset_id>/export', views.preset_export, name="preset_export"),
path('trackers/<slug:slug>', views.tracker_setup, name="tracker_setup"),
path('worldbook_create/', views.worldbook_create, name='worldbook_create'),
path('worldbook_detail/<slug:slug>', views.worldbook_detail, name='worldbook_detail'),
path('worldbook_list/', views.worldbook_list, name='worldbook_list'),
path('worldbook_test/<slug:slug>', views.worldbook_test, name='worldbook_test'),
path('worldbook_export/<slug:slug>', views.worldbook_export, name='worldbook_export'),
path('worldbook_delete/<slug:slug>', views.worldbook_delete, name='worldbook_delete'),
    ]
#handler404 = page_not_found