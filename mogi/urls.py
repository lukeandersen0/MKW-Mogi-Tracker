
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views, api

app_name = "mogi"

urlpatterns = [
    # Auth

    # Pages
    path("", views.dashboard, name="dashboard"),
    path("mogis/", views.mogi_list, name="mogi_list"),
    path("mogis/<int:mogi_id>/", views.mogi_detail, name="mogi_detail"),
    path("tracks/", views.track_list, name="track_list"),
    path("tracks/<slug:slug>/", views.track_detail, name="track_detail"),
    path("history/", views.race_history, name="race_history"),
    path("stats/", views.all_time_stats, name="all_time_stats"),

    # Live fragments for sort toggle
    path("fragments/mogi-cards/", views.mogi_cards_fragment, name="mogi_cards_fragment"),
    path("fragments/dashboard-cards/", views.dashboard_cards_fragment, name="dashboard_cards_fragment"),

    # APIs (JSON)
    path("api/add/", api.add_race, name="api_add"),
    path("api/undo/", api.undo_last, name="api_undo"),
    path("api/reset/", api.reset_current, name="api_reset"),
    path("api/finalize/", api.finalize_current, name="api_finalize"),
    path("api/export/", api.export_data, name="api_export"),
    path("api/import/", api.import_data, name="api_import"),
]
