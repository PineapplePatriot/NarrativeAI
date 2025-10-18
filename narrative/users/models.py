from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class User(AbstractUser):
    name = models.CharField(max_length=30, blank=True, verbose_name="First name")
    date_birth = models.DateTimeField(blank=True, null=True, verbose_name="Date of birth")
    photo = models.ImageField(
        upload_to="users/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name="Photo"
    )
    persona_name = models.CharField(max_length=256, blank=True, default=None, null=True, verbose_name="Persona name")
    persona_description = models.TextField(blank=True, default=None, null=True)

    def __str__(self):
        return self.username


class ApiConfig(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="api_config"
    )
    eleven_key = models.CharField(max_length=256, blank=True)
    chat_key = models.CharField(max_length=256, blank=False)
    or_model = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return f"API config for {self.user.username}"

