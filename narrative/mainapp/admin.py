from django.contrib import admin
from django.utils.html import format_html
from .models import CharacterTemplate

@admin.register(CharacterTemplate)
class CharacterTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at', 'photos_preview')
    readonly_fields = ('created_at', 'updated_at', 'photos_preview')

    # Відображаємо всі фото емоцій
    def photos_preview(self, obj):
        photo_fields = [
            'photo_neutral', 'photo_happy', 'photo_sad', 'photo_angry',
            'photo_surprised', 'photo_scared', 'photo_confused',
            'photo_calm', 'photo_scheming'
        ]
        html = ""
        for field_name in photo_fields:
            photo = getattr(obj, field_name)
            if photo:
                html += f'<img src="{photo.url}" style="height:60px; margin:2px; border-radius:3px;" />'
        return format_html(html or "-")
    photos_preview.short_description = "Photos Preview"

    # Щоб фото відображалося також у формі редагування
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'scenario', 'initial_message')
        }),
        ('Photos', {
            'fields': (
                'photos_preview',  # прев’ю всіх фото
                'photo_neutral', 'photo_happy', 'photo_sad', 'photo_angry',
                'photo_surprised', 'photo_scared', 'photo_confused',
                'photo_calm', 'photo_scheming',
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
