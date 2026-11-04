from django.urls import path
from .views import ProfileView, PlayerListView, PlayerDetailView, PlayerStateView

urlpatterns = [path("me/", ProfileView.as_view()), path("", PlayerListView.as_view()), path("<int:pk>/", PlayerDetailView.as_view()), path("<int:pk>/archive/", PlayerStateView.as_view(action="archive")), path("<int:pk>/restore/", PlayerStateView.as_view(action="restore"))]
