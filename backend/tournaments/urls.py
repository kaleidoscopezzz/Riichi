from django.urls import path
from .views import TournamentListView, TournamentDetailView, TournamentParticipantsView, TournamentStartView
from .round_views import RoundListView, RoundDetailView

urlpatterns = [
    path("<int:pk>/rounds/", RoundListView.as_view()),
    path("<int:pk>/rounds/<int:round_number>/", RoundDetailView.as_view()),
    path("", TournamentListView.as_view()),
    path("<int:pk>/", TournamentDetailView.as_view()),
    path("<int:pk>/participants/", TournamentParticipantsView.as_view()),
    path("<int:pk>/start/", TournamentStartView.as_view()),
]
