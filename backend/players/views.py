from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PlayerProfile
from .serializers import PlayerSerializer, ProfileUpdateSerializer


class ProfileView(APIView):
    def get(self, request):
        return Response({"data": PlayerSerializer(request.user.player_profile).data}, headers={"Cache-Control": "no-store"})

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = request.user.player_profile
        profile.nickname = serializer.validated_data["nickname"]
        profile.save(update_fields=["nickname", "updated_at"])
        return Response({"data": PlayerSerializer(profile).data})


class PlayerPagination(PageNumberPagination):
    page_size = 20

    def get_paginated_response(self, data):
        return Response({"data": {"count": self.page.paginator.count, "next": self.get_next_link(), "previous": self.get_previous_link(), "results": data}})


class PlayerListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PlayerSerializer
    pagination_class = PlayerPagination

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        if len(search) > 150:
            raise ValidationError({"search": ["搜索内容最多 150 字符。"]})
        eligible = self.request.query_params.get("eligible", "")
        if eligible not in ("", "true"):
            raise ValidationError({"eligible": ["仅支持 eligible=true 查询有效参赛选手。"]})
        rows = PlayerProfile.objects.select_related("user").filter(Q(nickname__icontains=search) | Q(user__username__icontains=search))
        return rows.filter(user__is_active=True) if eligible else rows
