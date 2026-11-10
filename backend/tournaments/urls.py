from django.urls import path
from .views import TournamentListView, TournamentDetailView, TournamentParticipantsView, TournamentStartView
from .round_views import RoundListView, RoundDetailView, PairingPreviewView

from .competition_views import WorkspaceView, ReplaceView, ReviewView, LotteryView, ConfirmLotteryView, VoidLotteryView, FinishView, EliminationView
from .team_views import (SchedulePreviewView, ScheduleGenerateView, ScheduleResetView, PlansView, PlanView,
                        PlansConfirmView, PlanWithdrawView, RepresentativeView, RepresentativesView, BatchPreviewView, BatchStartView, BatchesView, AuditView)

urlpatterns = [
    path('<int:pk>/team/schedule/preview/', SchedulePreviewView.as_view()),
    path('<int:pk>/team/schedule/generate/', ScheduleGenerateView.as_view()),
    path('<int:pk>/team/schedule/reset/', ScheduleResetView.as_view()),
    path('<int:pk>/team/plans/', PlansView.as_view()),
    path('<int:pk>/team/plans/confirm/', PlansConfirmView.as_view()),
    path('<int:pk>/team/plans/<int:match_id>/', PlanView.as_view()),
    path('<int:pk>/team/plans/<int:match_id>/withdraw/', PlanWithdrawView.as_view()),
    path('<int:pk>/team/stages/<int:stage_id>/representative/', RepresentativeView.as_view()),
    path('<int:pk>/team/stages/<int:stage_id>/representatives/', RepresentativesView.as_view()),
    path('<int:pk>/team/batches/preview/', BatchPreviewView.as_view()),
    path('<int:pk>/team/batches/start/', BatchStartView.as_view()),
    path('<int:pk>/team/batches/', BatchesView.as_view()),
    path('<int:pk>/team/audit/', AuditView.as_view()),
    path('<int:pk>/rounds/preview/', PairingPreviewView.as_view()),
    path("<int:pk>/workspace/", WorkspaceView.as_view()),
    path("<int:pk>/eliminations/", EliminationView.as_view()),
    path("<int:pk>/tables/replace/", ReplaceView.as_view()),
    path("<int:pk>/compatibility-review/", ReviewView.as_view()),
    path("<int:pk>/lotteries/", LotteryView.as_view()),
    path("<int:pk>/lotteries/<int:lottery_id>/confirm/", ConfirmLotteryView.as_view()),
    path("<int:pk>/lotteries/<int:lottery_id>/void/", VoidLotteryView.as_view()),
    path("<int:pk>/complete/", FinishView.as_view()),
    path("<int:pk>/rounds/", RoundListView.as_view()),
    path("<int:pk>/rounds/<int:round_number>/", RoundDetailView.as_view()),
    path("", TournamentListView.as_view()),
    path("<int:pk>/", TournamentDetailView.as_view()),
    path("<int:pk>/participants/", TournamentParticipantsView.as_view()),
    path("<int:pk>/start/", TournamentStartView.as_view()),
]
