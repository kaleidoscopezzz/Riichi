from django.urls import path
from .round_views import TableDetailView, AllocationHistoryView, ReassignView, ReleaseView

from .competition_views import ResultView, ConfirmResultView

urlpatterns = [
    path("<int:pk>/result/", ResultView.as_view()),
    path("<int:pk>/result/confirm/", ConfirmResultView.as_view()),
    path("<int:pk>/", TableDetailView.as_view()),
    path("<int:pk>/machine/history/", AllocationHistoryView.as_view()),
    path("<int:pk>/machine/reassign/", ReassignView.as_view()),
    path("<int:pk>/machine/release/", ReleaseView.as_view()),
]
