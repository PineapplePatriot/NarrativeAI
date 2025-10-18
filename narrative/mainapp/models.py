from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse

# Create your models here.

class Character(models.Model):

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)

    photo_neutral = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                              blank=True, null=True, verbose_name="Neutral emotion")
    photo_happy = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Happy emotion")
    photo_sad = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Sad emotion")
    photo_angry = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Angry emotion")
    photo_surprised = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Surprised emotion")
    photo_scared = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Scared emotion")
    photo_confused = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Confused emotion")
    photo_calm = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Calm emotion")
    photo_scheming = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None,
                                      blank=True, null=True, verbose_name="Scheming emotion")


    description = models.TextField(blank=True) # було поле  content
    scenario = models.TextField(blank=True) #нове
    initial_message = models.TextField(blank=True) #нове
    chat_log_file = models.FileField(
        upload_to="chat_logs/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name="Chat log file")

    is_default = models.BooleanField(default=False, verbose_name="Default character")  # <- нове поле


    creator_notes = models.TextField(blank=True) #нове
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)

    worldbook = models.ForeignKey('Worldbook', on_delete=models.PROTECT, null=True, blank=True, related_name="characters")
    tags = models.ManyToManyField('TagPost', blank=True, related_name='tags')

    author=models.ForeignKey(get_user_model(), on_delete=models.SET_NULL,
                             related_name='characters', null=True, default=None)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-time_create']
        indexes = [
            models.Index(fields=["-time_create"])
        ]

    def get_absolute_url(self):
        return reverse('character', kwargs={'slug': self.slug})


class TagPost(models.Model):
    tag = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)

    def __str__(self):
        return self.tag

    def get_absolute_url(self):
        return reverse('tag', kwargs={'tag_slug': self.slug})

class Worldbook(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    description = models.TextField(blank=True)
    json_file = models.FileField(upload_to='worldbooks_json/', blank=True, null=True)  # нове поле
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL,
                               related_name='worldbooks', null=True, default=None)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-time_create']
        indexes = [
            models.Index(fields=["-time_create"])
        ]

    def get_absolute_url(self):
        return reverse('worldbook_detail', kwargs={'slug': self.slug})

class UploadsFiles(models.Model):
    file = models.FileField(upload_to='uploads_model')



from django.db import models
from django.contrib.auth import get_user_model

class ChatSettings(models.Model):
    json_file = models.FileField(upload_to='settings_json/', blank=True, null=True)
    author = models.OneToOneField(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='settings',
        null=True,
        default=None
    )

    def __str__(self):
        return f"Settings for {self.author}" if self.author else "Orphaned settings"


from django.db import models

class CharacterTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    scenario = models.TextField(blank=True)
    initial_message = models.TextField(blank=True)

    photo_neutral = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_happy = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_sad = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_angry = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_surprised = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_scared = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_confused = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_calm = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)
    photo_scheming = models.ImageField(upload_to="templates/%Y/%m/%d/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
