from django.db import models
from gui_spector.llm.llm import LLM
from gui_spector.verfication.config import DEFAULT_AGENT
from uuid import uuid4


class Inputs(models.Model):
    """User-provided input key/value pairs for a setup."""
    mapping_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        try:
            return f"Inputs ({len(self.mapping_json or {})} entries)"
        except Exception:
            return "Inputs"


class Setup(models.Model):
    class State(models.TextChoices):
        READY = "ready", "Ready"
        PROCESSING = "processing", "Processing"

    name = models.CharField(max_length=255)
    start_url = models.URLField()
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.READY,
    )
    screenshot = models.ImageField(upload_to="setups/screenshots/", blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    tags_json = models.JSONField(default=list, blank=True)
    # Selected LLM identifier (used for extraction/summaries). Stored as plain string to avoid coupling.
    llm_model = models.CharField(max_length=64, default=LLM.MODEL_GPT_4_1)
    # Selected MLLM Agent for interactive verification
    agent_model = models.CharField(max_length=64, default=DEFAULT_AGENT)
    # Maximum reasoning steps for agent runs
    max_reasoning_steps = models.PositiveIntegerField(default=60)
    # Agent timeout in seconds (display lease TTL)
    agent_timeout_seconds = models.PositiveIntegerField(default=120)
    # Maximum retries after an error occurs (additional attempts)
    max_retries = models.PositiveIntegerField(default=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Optional user-provided inputs for this setup
    inputs = models.OneToOneField(Inputs, on_delete=models.SET_NULL, null=True, blank=True, related_name="setup")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def num_requirements(self) -> int:
        return self.requirements.count()

    @property
    def num_met(self) -> int:
        return self.requirements.filter(status=Requirement.Status.MET).count()

    @property
    def num_unmet(self) -> int:
        return self.requirements.filter(status=Requirement.Status.UNMET).count()

    @property
    def num_partially_met(self) -> int:
        return self.requirements.filter(status=Requirement.Status.PARTIALLY_MET).count()

    @property
    def num_processing(self) -> int:
        return self.requirements.filter(status=Requirement.Status.PROCESSING).count()

    @property
    def num_error(self) -> int:
        return self.requirements.filter(status=Requirement.Status.ERROR).count()

    @property
    def num_unprocessed(self) -> int:
        return self.requirements.filter(status=Requirement.Status.UNPROCESSED).count()


class Requirement(models.Model):
    class Status(models.TextChoices):
        UNPROCESSED = "unprocessed", "Unprocessed"
        PROCESSING = "processing", "Processing"
        MET = "met", "Met"
        PARTIALLY_MET = "partially_met", "Partially met"
        UNMET = "unmet", "Unmet"
        ERROR = "error", "Error"
    setup = models.ForeignKey(Setup, on_delete=models.CASCADE, related_name="requirements")
    # Framework fields
    framework_id = models.UUIDField(default=uuid4, editable=False)
    title = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=1024, blank=True, null=True)
    tags_json = models.JSONField(default=list, blank=True)
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    metadata_json = models.JSONField(blank=True, null=True)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.UNPROCESSED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.title or (self.description[:40] + ("..." if len(self.description) > 40 else "")) or f"Requirement #{self.pk}"



class AcceptanceCriterion(models.Model):
    class State(models.TextChoices):
        UNPROCESSED = "unprocessed", "Unprocessed"
        MET = "met", "Met"
        UNMET = "unmet", "Unmet"

    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=32)
    text = models.TextField()
    state = models.CharField(max_length=16, choices=State.choices, default=State.UNPROCESSED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.name}: {self.text[:60]}" if self.name else (self.text[:60] or f"AcceptanceCriterion #{self.pk}")


class VerificationRun(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        MET = "met", "Met"
        UNMET = "unmet", "Unmet"
        PARTIALLY_MET = "partially_met", "Partially met"
        ERROR = "error", "Error"

    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=16, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    elapsed_s = models.FloatField()
    start_url = models.URLField()
    current_url = models.URLField(blank=True, null=True)
    steps_taken = models.IntegerField(default=0)
    run_dir = models.CharField(max_length=1024)
    display_str = models.CharField(max_length=8, blank=True, null=True)
    model_decision_json = models.JSONField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    usage_total_json = models.JSONField(blank=True, null=True)
    last_screenshot = models.CharField(max_length=1024, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]


class RunInteraction(models.Model):
    run = models.ForeignKey(VerificationRun, on_delete=models.CASCADE, related_name="interactions")
    turn_index = models.IntegerField()
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    elapsed_s = models.FloatField()
    model_response_id = models.CharField(max_length=255, blank=True, null=True)
    reasoning_summary = models.TextField(blank=True, null=True)
    message_text = models.TextField(blank=True, null=True)
    screenshot_path = models.CharField(max_length=1024, blank=True, null=True)
    usage_json = models.JSONField(blank=True, null=True)
    # Computer action fields
    action_type = models.CharField(max_length=64, blank=True, null=True)
    action_params_json = models.JSONField(blank=True, null=True)
    action_call_id = models.CharField(max_length=255, blank=True, null=True)
    action_status = models.CharField(max_length=64, blank=True, null=True)
    action_safety_checks_json = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["turn_index"]

