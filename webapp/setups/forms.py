from django import forms
from .models import Setup, Requirement
from gui_spector.llm.config import AVAILABLE_MODELS
from gui_spector.verfication.config import AVAILABLE_AGENTS


class SetupForm(forms.ModelForm):

    class Meta:
        model = Setup
        fields = ["name", "start_url", "agent_model", "llm_model", "max_reasoning_steps", "agent_timeout_seconds", "max_retries"]
        labels = {
            "name": "Name",
            "start_url": "Start URL",
            "agent_model": "MLLM Agent",
            "llm_model": "LLM Model",
            "max_reasoning_steps": "Maximum Reasoning Steps",
            "agent_timeout_seconds": "Agent Timeout (seconds)",
            "max_retries": "Maximum Retries",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "My verification setup"}),
            "start_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://example.com"}),
            "agent_model": forms.Select(attrs={"class": "form-select"}),
            "llm_model": forms.Select(attrs={"class": "form-select"}),
            "max_reasoning_steps": forms.NumberInput(attrs={"class": "form-control", "min": 10, "step": 10}),
            "agent_timeout_seconds": forms.NumberInput(attrs={"class": "form-control", "min": 30, "step": 10}),
            "max_retries": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 5, "step": 1}),
        }

    # Not a model field; free text input for extraction
    requirements_input = forms.CharField(
        required=False,
        label="Requirements",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 12,
                "style": "min-height:220px; height:220px; overflow-y:auto; overflow-x:hidden; white-space:pre-wrap; word-break:break-word; overflow-wrap:anywhere; font-family:monospace; resize: both;",
                "wrap": "off",
                "placeholder": "Describe your requirements in any format (lists, bullets, or free text).",
                "spellcheck": "false",
            }
        ),
        help_text="",
    )

    tags_input = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "tag1, tag2, tag3",
            }
        ),
    )

    allow_guess = forms.BooleanField(
        required=False,
        initial=True,
        label="Allow the LLM to infer/guess missing details",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def save(self, commit=True):
        # Save the Setup first so it has a primary key
        instance = super().save(commit=True)
        # We no longer handle tags here (extracted automatically later)
        # Create simple Requirement rows from textarea is moved to view for processor
        return instance



class SetupEditForm(forms.ModelForm):

    class Meta:
        model = Setup
        fields = [
            "name",
            "start_url",
            "agent_model",
            "llm_model",
            "max_reasoning_steps",
            "agent_timeout_seconds",
            "max_retries",
        ]
        labels = {
            "name": "Name",
            "start_url": "Start URL",
            "agent_model": "MLLM Agent",
            "llm_model": "LLM Model",
            "max_reasoning_steps": "Maximum Reasoning Steps",
            "agent_timeout_seconds": "Agent Timeout (seconds)",
            "max_retries": "Maximum Retries",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "My verification setup"}),
            "start_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://example.com"}),
            "max_reasoning_steps": forms.NumberInput(attrs={"class": "form-control", "min": 10, "step": 10}),
            "agent_timeout_seconds": forms.NumberInput(attrs={"class": "form-control", "min": 30, "step": 10}),
            "max_retries": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 5, "step": 1}),
        }

    tags_input = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "tag1, tag2, tag3",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert plain CharFields into ChoiceFields populated like Add page options
        current_llm = (self.instance.llm_model if getattr(self.instance, "llm_model", None) else None)
        current_agent = (self.instance.agent_model if getattr(self.instance, "agent_model", None) else None)
        self.fields["llm_model"] = forms.ChoiceField(
            choices=AVAILABLE_MODELS,
            initial=current_llm,
            label=self.fields.get("llm_model").label if self.fields.get("llm_model") else "LLM Model",
            widget=forms.Select(attrs={"class": "form-select"}),
            required=True,
        )
        self.fields["agent_model"] = forms.ChoiceField(
            choices=AVAILABLE_AGENTS,
            initial=current_agent,
            label=self.fields.get("agent_model").label if self.fields.get("agent_model") else "MLLM Agent",
            widget=forms.Select(attrs={"class": "form-select"}),
            required=True,
        )
