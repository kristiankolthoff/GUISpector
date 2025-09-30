from django.contrib import admin
from .models import Setup, Requirement, AcceptanceCriterion


class AcceptanceCriterionInline(admin.TabularInline):
    model = AcceptanceCriterion
    extra = 0


@admin.register(Setup)
class SetupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "start_url", "state", "created_at")
    list_filter = ("state",)
    search_fields = ("name", "start_url")
    inlines = []


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ("id", "setup", "title", "priority", "status", "created_at")
    list_filter = ("status", "priority", "setup")
    search_fields = ("title", "description", "setup__name")
    inlines = [AcceptanceCriterionInline]


