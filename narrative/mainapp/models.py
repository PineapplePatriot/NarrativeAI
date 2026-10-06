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
    # Character Card V2/V3 fields (see mainapp/cards.py), so imported cards keep everything
    personality = models.TextField(blank=True, verbose_name="Personality summary")
    example_dialogue = models.TextField(blank=True, verbose_name="Example dialogue")
    alternate_greetings = models.JSONField(default=list, blank=True)
    system_prompt = models.TextField(blank=True, verbose_name="Card's system prompt")
    post_history_instructions = models.TextField(blank=True, verbose_name="Card's post-history instructions")
    card_creator = models.CharField(max_length=255, blank=True, verbose_name="Card author")
    card_version = models.CharField(max_length=64, blank=True, verbose_name="Card version")
    # Whatever else the card carried (extensions, tags, source...), kept for export
    card_data = models.JSONField(default=dict, blank=True)
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)

    worldbook = models.ForeignKey('Worldbook', on_delete=models.PROTECT, null=True, blank=True, related_name="characters")
    tags = models.ManyToManyField('TagPost', blank=True, related_name='tags')

    author=models.ForeignKey(get_user_model(), on_delete=models.SET_NULL,
                             related_name='characters', null=True, default=None)

    eleven_voice_char_id = models.CharField(max_length=128, blank=True)
    eleven_voice_narr_id = models.CharField(max_length=128, blank=True)
    eleven_voice_second_id = models.CharField(max_length=128, blank=True, verbose_name="2nd Character Voice ID")

    is_mult = models.BooleanField(default=False, verbose_name="Multi-Character Mode")
    # Which story trackers are on for this character, custom fields and layout (see mainapp/trackers.py)
    tracker_config = models.JSONField(default=dict, blank=True)
    # The character's look: {"bg": url, "music": {"url", "name"}, "dialogue_color": "#rrggbb" or "preset"}.
    # A chat opens with these unless it picked its own background or music.
    theme = models.JSONField(default=dict, blank=True)

    photo_second_neutral = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_happy = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_sad = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_angry = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_surprised = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_scared = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_confused = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_calm = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)
    photo_second_scheming = models.ImageField(upload_to="photos/%Y/%m/%d/", default=None, blank=True, null=True)

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
    # Sampler on/off switches and values for the main chat (see mainapp/samplers.py)
    samplers = models.JSONField(default=dict, blank=True)
    # How chats look: {"dialogue_color": "#e594f2" or "preset" (leave colouring to the preset)}
    appearance = models.JSONField(default=dict, blank=True)
    # The user's own text rules, run with every preset (see mainapp/regex_rules.py)
    regex = models.JSONField(default=list, blank=True)
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


class Preset(models.Model):
    """A prompt preset (blocks, samplers, utility prompts). One per user is active. See mainapp/presets.py."""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name="presets")
    name = models.CharField(max_length=200)
    data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_preset_name_per_user")]

    def __str__(self):
        return self.name


class Chat(models.Model):
    """One conversation with a character. A character can have many; branches point to their parent."""
    character = models.ForeignKey('Character', on_delete=models.CASCADE, related_name="chats")
    title = models.CharField(max_length=200, default="Chat")
    log_file = models.FileField(upload_to="chat_logs/", blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name="branches")
    branch_point = models.PositiveIntegerField(null=True, blank=True, help_text="Messages copied from the parent")
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-time_update"]

    def __str__(self):
        return f"{self.character.name}: {self.title}"


class BulbaSession(models.Model):
    """One conversation with Bulba, the setup assistant (see mainapp/bulba/)."""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name="bulba_sessions")
    target_model = models.CharField(max_length=64, help_text="Model profile id the user will chat with")
    # "setup": the first-run setup; "chat": helping with one chat (opened from the chat page)
    mode = models.CharField(max_length=16, default="setup")
    chat = models.ForeignKey("Chat", on_delete=models.CASCADE, null=True, blank=True, related_name="bulba_sessions")
    # In setup: an existing character the user asked Bulba to work on (its card and lorebook)
    focus = models.ForeignKey("Character", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    stage = models.CharField(max_length=32, default="extras")
    messages = models.JSONField(default=list, blank=True, help_text="Conversation as sent to Bulba's model")
    events = models.JSONField(default=list, blank=True, help_text="What the page shows")
    preferences = models.JSONField(default=list, blank=True)
    proposals = models.JSONField(default=list, blank=True)
    spent = models.FloatField(default=0.0, help_text="USD, as reported by OpenRouter")
    budget = models.FloatField(default=5.0, help_text="USD per session")
    activity = models.CharField(max_length=200, blank=True, help_text="What Bulba is doing right now, for the page")
    active = models.BooleanField(default=True)
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-time_update"]
