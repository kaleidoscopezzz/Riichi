from django.urls import include, path
from tournaments.round_views import MachineResourceView

urlpatterns = [
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/players/", include("players.urls")),
    path("api/v1/machines/", include("machines.urls")),
    path("api/v1/tournaments/", include("tournaments.urls")),
    path("api/v1/round-tables/", include("tournaments.table_urls")),
    path("api/v1/machine-resources/", MachineResourceView.as_view()),
]
