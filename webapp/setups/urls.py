from django.urls import path
from django.views.generic import RedirectView
from . import views


app_name = "setups"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("setups/", views.overview, name="overview_alias"),
    path("setups/api/list/", views.api_list_setups, name="api_list"),
    path("setups/add/", views.add_setup, name="add"),
    path("setups/<int:pk>/", views.open_setup, name="open"),
    path("setups/<int:pk>/edit/", views.edit_setup, name="edit"),
    path("setups/<int:pk>/api/delete/", views.api_setup_delete, name="api_setup_delete"),
    # Detail view APIs
    path("setups/<int:pk>/api/requirements/", views.api_requirements, name="api_requirements"),
    path("setups/<int:pk>/api/requirements/add/", views.api_requirements_add, name="api_requirements_add"),
    path("setups/<int:pk>/api/requirements/<int:req_id>/delete/", views.api_requirements_delete, name="api_requirements_delete"),
    path("setups/<int:pk>/api/requirements/delete_all/", views.api_requirements_delete_all, name="api_requirements_delete_all"),
    path("setups/<int:pk>/api/summary/", views.api_setup_summary, name="api_setup_summary"),
    # New MCP-oriented endpoints
    path("setups/<int:pk>/api/next_unprocessed/", views.api_setup_next_unprocessed, name="api_setup_next_unprocessed"),
    path("setups/<int:pk>/api/requirements/unprocessed/", views.api_requirements_unprocessed_in_setup, name="api_requirements_unprocessed_in_setup"),
    path("setups/<int:pk>/api/requirements/<int:req_id>/verification/start/", views.api_verification_start_single, name="api_verification_start_single"),
    path("requirements/api/verification/start_batch/", views.api_verification_start_batch, name="api_verification_start_batch"),
    # Runs overview
    path("requirements/<int:req_id>/runs/", views.runs_overview, name="runs_overview"),
    path("requirements/<int:req_id>/api/runs/", views.api_runs_list, name="api_runs_list"),
    path("requirements/<int:req_id>/api/runs/start/", views.api_runs_start, name="api_runs_start"),
    path("setups/<int:pk>/api/runs/start_all/", views.api_runs_start_all, name="api_runs_start_all"),
    # Minimal decision-only endpoint
    path("requirements/<int:req_id>/api/decision/", views.api_requirement_latest_decision, name="api_requirement_latest_decision"),
    path("requirements/<int:req_id>/api/summary/", views.api_requirement_summary, name="api_requirement_summary"),
    # Run detail
    path("runs/<int:run_id>/", views.run_detail, name="run_detail"),
    # Graceful redirects for common typos
    path("setup/add/", RedirectView.as_view(pattern_name="setups:add", permanent=False)),
    path("setup/<int:pk>/", RedirectView.as_view(pattern_name="setups:open", permanent=False)),
]


