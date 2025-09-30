from django.db import models

# Create your models here.

class SettingsModel(models.Model):
    openai_key = models.CharField(max_length=512)
    google_api_key = models.CharField(max_length=512, blank=True, null=True)
    anthropic_api_key = models.CharField(max_length=512, blank=True, null=True)
    # Number of parallel workers/displays to run. Must be between 1 and 5.
    num_workers = models.PositiveIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Settings at {self.created_at}"


def set_api_keys_from_settings():
    import os
    latest_settings = SettingsModel.objects.order_by('-created_at').first()
    if latest_settings:
        if latest_settings.openai_key:
            os.environ["OPENAI_API_KEY"] = latest_settings.openai_key
            print(f"OPENAI_API_KEY: {latest_settings.openai_key}")
        if latest_settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = latest_settings.anthropic_api_key
            print(f"ANTHROPIC_API_KEY: {latest_settings.anthropic_api_key}")
        if latest_settings.google_api_key:
            os.environ["GOOGLE_API_KEY"] = latest_settings.google_api_key
            print(f"GOOGLE_API_KEY: {latest_settings.google_api_key}")






