from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from common.api import StrictFieldsMixin, search_text
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PlayerProfile
from .serializers import PlayerSerializer, ProfileUpdateSerializer, AccountProfileSerializer
from .services import create_player, mutate_player, own_profile


class ProfileView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        return Response({"data": AccountProfileSerializer(own_profile(request.user)).data}, headers={"Cache-Control": "no-store"})

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = own_profile(request.user)
        profile.nickname = serializer.validated_data["nickname"]
        profile.save(update_fields=["nickname", "updated_at"])
        return Response({"data": AccountProfileSerializer(profile).data})


class PlayerPagination(PageNumberPagination):
    page_size = 20

    def get_paginated_response(self, data):
        return Response({"data": {"count": self.page.paginator.count, "next": self.get_next_link(), "previous": self.get_previous_link(), "results": data}})


class PlayerListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PlayerSerializer
    pagination_class = PlayerPagination

    def get_queryset(self):
        search = search_text(self.request.query_params.get("search", "")).strip()
        if len(search) > 150:
            raise ValidationError({"search": ["搜索内容最多 150 字符。"]})
        eligible = self.request.query_params.get("eligible", "")
        if eligible not in ("", "true"):
            raise ValidationError({"eligible": ["仅支持 eligible=true 查询有效参赛选手。"]})
        state = self.request.query_params.get("status", "")
        if state not in ("", "active", "archived"):
            raise ValidationError({"status": ["请选择有效或归档状态。"]})
        rows = player_queryset().filter(nickname__icontains=search)
        if eligible or state == "active":
            rows = rows.filter(user__is_active=True)
        elif state == "archived":
            rows = rows.filter(user__is_active=False)
        return rows

    def post(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return player_response(create_player(serializer.validated_data["nickname"]).pk, status=201)


def player_queryset():
    return PlayerProfile.objects.select_related("user").filter(user__is_staff=False, user__is_superuser=False).annotate(entry_count=Count("tournament_entries", distinct=True)).order_by("-created_at", "-id")


def player_response(pk, status=200):
    return Response({"data": PlayerSerializer(get_object_or_404(player_queryset(), pk=pk)).data}, status=status, headers={"Cache-Control": "no-store"})


class ConfirmSerializer(StrictFieldsMixin, serializers.Serializer):
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("请明确二次确认。")
        return value


def confirm(request):
    serializer = ConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)


class PlayerDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        return player_response(pk)

    def patch(self, request, pk):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mutate_player(pk, nickname=serializer.validated_data["nickname"])
        return player_response(pk)

    def delete(self, request, pk):
        confirm(request)
        mutate_player(pk, action="delete")
        return Response({"data": {"deleted": True}})


class PlayerStateView(APIView):
    permission_classes = [IsAdminUser]
    action = None

    def post(self, request, pk):
        confirm(request)
        mutate_player(pk, action=self.action)
        return player_response(pk)
