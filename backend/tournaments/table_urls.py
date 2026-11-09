from django.urls import path
from .round_views import TableDetailView, AllocationHistoryView, ReassignView, ReleaseView

from .competition_views import ResultView, ConfirmResultView, PreviewResultView, CorrectResultView, ResultCorrectionsView

urlpatterns = [
    path("<int:pk>/result/", ResultView.as_view()),
    path("<int:pk>/result/confirm/", ConfirmResultView.as_view()),
    path("<int:pk>/result/preview/", PreviewResultView.as_view()),
    path("<int:pk>/result/correct/", CorrectResultView.as_view()),
    path("<int:pk>/result/corrections/", ResultCorrectionsView.as_view()),
    path("<int:pk>/", TableDetailView.as_view()),
    path("<int:pk>/machine/history/", AllocationHistoryView.as_view()),
    path("<int:pk>/machine/reassign/", ReassignView.as_view()),
    path("<int:pk>/machine/release/", ReleaseView.as_view()),
]
