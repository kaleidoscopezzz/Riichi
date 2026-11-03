from django.urls import path
from .views import TournamentListView, TournamentDetailView, TournamentParticipantsView, TournamentStartView

urlpatterns = [
    path("", TournamentListView.as_view()),
    path("<int:pk>/", TournamentDetailView.as_view()),
    path("<int:pk>/participants/", TournamentParticipantsView.as_view()),
    path("<int:pk>/start/", TournamentStartView.as_view()),
]
