import os
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
    """Non-chat service keys. AI chat keys live in ConnectionProfile."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="api_config"
    )
    eleven_key = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return f"API config for {self.user.username}"


class ConnectionProfile(models.Model):
    """One AI connection: where to send requests, with which key and model."""
    PROVIDER_OPENROUTER = "openrouter"
    PROVIDER_CUSTOM = "openai_compatible"
    PROVIDERS = [
        (PROVIDER_OPENROUTER, "OpenRouter"),
        (PROVIDER_CUSTOM, "OpenAI-compatible (custom URL)"),
    ]
    # NARRATIVE_OPENROUTER_URL points the app at a stand-in server for local testing; leave it unset normally
    OPENROUTER_URL = os.environ.get("NARRATIVE_OPENROUTER_URL") or "https://openrouter.ai/api/v1"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="connection_profiles")
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=32, choices=PROVIDERS, default=PROVIDER_OPENROUTER)
    base_url = models.CharField(max_length=512, blank=True, help_text="Only for custom providers")
    api_key = models.CharField(max_length=512, blank=True)
    model = models.CharField(max_length=256)
    time_create = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["time_create"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_profile_name_per_user")]

    def __str__(self):
        return f"{self.name} ({self.model})"

    @property
    def api_url(self):
        if self.provider == self.PROVIDER_OPENROUTER:
            return self.OPENROUTER_URL
        return self.base_url.rstrip("/")

    @property
    def key_hint(self):
        return f"…{self.api_key[-4:]}" if len(self.api_key) >= 8 else ("set" if self.api_key else "")


class TaskSetting(models.Model):
    """Which connection/model a task (chat, summary, ...) uses, and when it runs."""
    MODE_AUTO = "auto"
    MODE_MANUAL = "manual"
    MODES = [(MODE_AUTO, "Automatic"), (MODE_MANUAL, "Manual only")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_settings")
    task = models.CharField(max_length=32)
    # Empty profile = use the main chat connection
    profile = models.ForeignKey(ConnectionProfile, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="tasks")
    # Empty model = use the profile's model
    model = models.CharField(max_length=256, blank=True)
    enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=16, choices=MODES, default=MODE_MANUAL)
    interval = models.PositiveIntegerField(default=10, help_text="Run every N messages (automatic mode)")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "task"], name="unique_task_per_user")]

    def __str__(self):
        return f"{self.user} / {self.task}"
