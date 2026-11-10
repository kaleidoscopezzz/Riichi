from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tournament, TournamentParticipant
from .serializers import TournamentSerializer, TournamentCreateSerializer, TournamentUpdateSerializer, ParticipantWriteSerializer, EmptySerializer
from .services import create_tournament, mutate_tournament
from common.api import search_text


def queryset():
    return Tournament.objects.prefetch_related(Prefetch("participants", queryset=TournamentParticipant.objects.select_related("player__user")))


def response(pk, status=200):
    return Response({"data": TournamentSerializer(get_object_or_404(queryset(), pk=pk)).data}, status=status, headers={"Cache-Control": "no-store"})


class TournamentPagination(PageNumberPagination):
    page_size = 20


class TournamentListView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = TournamentPagination

    def get(self, request):
        search = search_text(request.query_params.get("search", "")).strip()
        status = request.query_params.get("status", "")
        if len(search) > 120:
            raise ValidationError({"search": ["搜索内容最多120字符。"]})
        if status and status not in Tournament.Status.values:
            raise ValidationError({"status": ["未知赛事状态。"]})
        rows = queryset().filter(name__icontains=search)
        if status:
            rows = rows.filter(status=status)
        page = self.paginate_queryset(rows)
        return Response({"data": {"count": self.paginator.page.paginator.count, "next": self.paginator.get_next_link(), "previous": self.paginator.get_previous_link(), "results": TournamentSerializer(page, many=True).data}}, headers={"Cache-Control": "no-store"})

    def post(self, request):
        if request.data.get('competition_type') == 'team':
            from .team_serializers import TeamTournamentWrite
            serializer = TeamTournamentWrite(data=request.data)
        else:
            serializer = TournamentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return response(create_tournament(request.user, serializer.validated_data).pk, 201)


class TournamentDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        return response(pk)

    def patch(self, request, pk):
        t = get_object_or_404(Tournament, pk=pk)
        if t.competition_type == 'team':
            from .team_serializers import TeamTournamentUpdate
            serializer = TeamTournamentUpdate(data=request.data, partial=True)
        else:
            serializer = TournamentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop("revision", None)
        if not values:
            raise ValidationError({"non_field_errors": ["请提供需要修改的字段。"]})
        ids = values.pop("participant_ids", None)
        if t.competition_type == 'team':
            from .team_services import update_team_tournament
            return response(update_team_tournament(pk, values, user=request.user, revision=revision).pk)
        return response(mutate_tournament(pk, values=values, participant_ids=ids, revision=revision, actor=request.user).pk)


class TournamentParticipantsView(APIView):
    permission_classes = [IsAdminUser]

    def put(self, request, pk):
        serializer = ParticipantWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return response(mutate_tournament(pk, participant_ids=serializer.validated_data["participant_ids"], revision=serializer.validated_data.get("revision")).pk)


class TournamentStartView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = EmptySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        t = get_object_or_404(Tournament, pk=pk)
        if t.competition_type == 'team':
            from .team_services import start_team_tournament
            return response(start_team_tournament(pk, user=request.user).pk)
        return response(mutate_tournament(pk, start=True, actor=request.user).pk)
