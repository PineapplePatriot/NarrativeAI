from django.urls import path, re_path, register_converter
#from django.views.defaults import page_not_found

from . import views
#from . import converters
from mainapp.views import page_not_found

#register_converter(converters.FourDigitYearConverter, "year4")

urlpatterns = [
#path('worldbook/<slug:worldbook_slug>/', views.worldbooks_by_slug, name='worldbook'),
#path('characters/<slug:character_slug>/', views.ShowCharacter.as_view(), name='character'),
#path('edit/<slug:slug>/', views.UpdatePage.as_view(), name='edit_page'),
##path('new_about/', views.new_about, name='new_about'),
path('add_character/', views.AddCharacter.as_view(), name="add_character"),
path('character_edit/<slug:slug>', views.UpdateCharacter.as_view(), name="character"),
path('chat/<slug:slug>', views.chat, name="chat"),
path('characters_list/', views.CharactersList.as_view(), name="characters_list"),
#path('character_selection/', views.character_selection),
path('chat_settings/', views.chat_settings, name="chat_settings"),
path('worldbook_create/', views.worldbook_create, name='worldbook_create'),
path('worldbook_detail/<slug:slug>', views.worldbook_detail, name='worldbook_detail'),
path('worldbook_list/', views.worldbook_list, name='worldbook_list'),
    ]
#handler404 = page_not_found