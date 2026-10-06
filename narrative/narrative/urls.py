"""
URL configuration for narrative project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import posixpath

from django.contrib import admin
from django.http import Http404
from django.urls import path, include, re_path
from narrative import settings
from django.views.static import serve
from mainapp.views import index_page


PRIVATE_MEDIA = ("chat_logs", "worldbooks_json", "settings_json", "chat_settings2")


def media(request, path):
    """Uploaded files, except the private folders (chats, lorebooks, settings), which only the app reads."""
    clean = posixpath.normpath(path).lstrip("/")
    if clean.split("/", 1)[0] in PRIVATE_MEDIA or clean.startswith(".."):
        raise Http404()
    return serve(request, clean, document_root=settings.MEDIA_ROOT)

urlpatterns = [
    path("admin/", admin.site.urls),
    path('', index_page, name='home'),
    path('users/', include('users.urls', namespace="users")),
    path('main/', include('mainapp.urls')),

]
# Private files live in media too (chat logs, lorebooks, old settings). They are only read by the app itself,
# so never hand them out by URL; everything else (sprites, backgrounds, music, voice clips) is served for the
# pages that show it. On a server Django serves them itself: fine for a small site with a few users.
urlpatterns += [re_path(r"^media/(?P<path>.*)$", media)]
