from django.urls import path
from .views import MachineListView, MachineDetailView, MachineRetireView

urlpatterns = [
    path("", MachineListView.as_view()),
    path("<int:pk>/", MachineDetailView.as_view()),
    path("<int:pk>/retire/", MachineRetireView.as_view()),
]
