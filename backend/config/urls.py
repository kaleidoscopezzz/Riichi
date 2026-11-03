from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/players/", include("players.urls")),
    path("api/v1/machines/", include("machines.urls")),
    path("api/v1/tournaments/", include("tournaments.urls")),
]
