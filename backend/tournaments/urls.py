from django.urls import path
from .views import TournamentListView, TournamentDetailView, TournamentParticipantsView, TournamentStartView
from .round_views import RoundListView, RoundDetailView

from .competition_views import WorkspaceView, ReplaceView, ReviewView, LotteryView, ConfirmLotteryView, FinishView

urlpatterns = [
    path("<int:pk>/workspace/", WorkspaceView.as_view()),
    path("<int:pk>/tables/replace/", ReplaceView.as_view()),
    path("<int:pk>/compatibility-review/", ReviewView.as_view()),
    path("<int:pk>/lotteries/", LotteryView.as_view()),
    path("<int:pk>/lotteries/<int:lottery_id>/confirm/", ConfirmLotteryView.as_view()),
    path("<int:pk>/complete/", FinishView.as_view()),
    path("<int:pk>/rounds/", RoundListView.as_view()),
    path("<int:pk>/rounds/<int:round_number>/", RoundDetailView.as_view()),
    path("", TournamentListView.as_view()),
    path("<int:pk>/", TournamentDetailView.as_view()),
    path("<int:pk>/participants/", TournamentParticipantsView.as_view()),
    path("<int:pk>/start/", TournamentStartView.as_view()),
]
