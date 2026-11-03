from django.urls import path
from .views import ProfileView, PlayerListView

urlpatterns = [path("me/", ProfileView.as_view()), path("", PlayerListView.as_view())]
