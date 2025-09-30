from django.shortcuts import render, redirect
from django.views import View
from .models import SettingsModel  # Ensure correct import
from django import forms

# Form for the SettingsModel to handle OpenAI key input
class SettingsForm(forms.ModelForm):
    class Meta:
        model = SettingsModel
        fields = ['openai_key', 'google_api_key', 'anthropic_api_key', 'num_workers']
        widgets = {
            'openai_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your OpenAI key'}),
            'google_api_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your Google API key'}),
            'anthropic_api_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your Anthropic API key'}),
            'num_workers': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5, 'step': 1}),
        }

# View to display and save the OpenAI key in settings
class SettingsView(View):
    template_name = 'settings/settings.html'

    def get(self, request):
        # Use the model manager to fetch the latest settings
        # type: ignore[attr-defined] is used to suppress linter error for Django model manager
        latest_settings = SettingsModel.objects.order_by('-created_at').first()  # type: ignore[attr-defined]
        form = SettingsForm(instance=latest_settings)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = SettingsForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('setups:overview')
        return render(request, self.template_name, {'form': form})
