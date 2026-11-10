from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .competition_views import AdminView, response, validated
from .serializers import EmptySerializer
from .models import Tournament, TeamMatchPlan, TeamAuditRecord
from .round_views import rounds_query
from .round_serializers import RoundSerializer
from . import team_services as svc
from .team_serializers import (TokenWrite, ResetWrite, PlanWrite, PlansConfirm, PlanWithdraw,
                               RepresentativeWrite, RepresentativesWrite, BatchPreviewWrite)


def get_team(pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    svc.require_team(tournament)
    return tournament


def page_number(request):
    value = request.query_params.get('page', '1')
    if not value.isdigit() or not 1 <= int(value) <= 10000:
        raise ValidationError({'page': ['页码必须是正整数。']})
    return int(value)


class SchedulePreviewView(AdminView):
    def post(self, request, pk):
        validated(EmptySerializer, request)
        return response(svc.preview_schedule(pk, request.user))


class ScheduleGenerateView(AdminView):
    def post(self, request, pk):
        values = validated(TokenWrite, request)
        return response(svc.generate_schedule(pk, request.user, values['token']), 201)


class ScheduleResetView(AdminView):
    def post(self, request, pk):
        values = validated(ResetWrite, request); values.pop('confirmed')
        svc.reset_schedule(pk, request.user, **values)
        return response({'withdrawn': True})


class PlansView(AdminView):
    def get(self, request, pk):
        t = get_team(pk)
        plans = svc.plan_query(t)
        stage = request.query_params.get('stage')
        if stage:
            if not stage.isdigit():
                raise ValidationError({'stage': ['位置阶段ID须为整数。']})
            plans = plans.filter(stage_id=int(stage))
        status = request.query_params.get('status')
        if status:
            if status not in ('draft', 'confirmed', 'started', 'completed'):
                raise ValidationError({'status': ['未知计划状态。']})
            if status == 'completed':
                plans = plans.filter(table__result__status='confirmed')
            elif status == 'started':
                plans = plans.filter(status='started').exclude(table__result__status='confirmed')
            else:
                plans = plans.filter(status=status)
        page = page_number(request); count = plans.count()
        results = svc.result_batch(t); done = {row.table_id: row for row in results}; teams = svc.roster(t)
        rows = [svc.plan_data(p, teams, done) for p in plans[(page - 1) * 50:page * 50]]
        return response({'results': rows, 'count': count, 'page': page, 'has_next': page * 50 < count})


class PlanView(AdminView):
    def get(self, request, pk, match_id):
        t = get_team(pk); p = svc.current_plan(t, match_id)
        return response(svc.plan_data(p, svc.roster(t), {row.table_id: row for row in svc.result_batch(t)}))

    def put(self, request, pk, match_id):
        return response(svc.update_plan(pk, match_id, request.user, **validated(PlanWrite, request)))


class PlansConfirmView(AdminView):
    def post(self, request, pk):
        values = validated(PlansConfirm, request)
        svc.confirm_plans(pk, request.user, values['plan_sources'])
        return response({'confirmed': True})


class PlanWithdrawView(AdminView):
    def post(self, request, pk, match_id):
        values = validated(PlanWithdraw, request); values.pop('confirmed')
        svc.withdraw_plan(pk, match_id, request.user, **values)
        return response({'withdrawn': True})


class RepresentativeView(AdminView):
    def put(self, request, pk, stage_id):
        svc.set_representative(pk, stage_id, request.user, **validated(RepresentativeWrite, request))
        t = get_team(pk)
        return response({'revision': t.revision})


class BatchPreviewView(AdminView):
    def post(self, request, pk):
        return response(svc.preview_batch(pk, request.user, **validated(BatchPreviewWrite, request)))


class RepresentativesView(AdminView):
    def put(self, request, pk, stage_id):
        return response(svc.set_representatives(pk, stage_id, request.user, **validated(RepresentativesWrite, request)))


class BatchStartView(AdminView):
    def post(self, request, pk):
        values = validated(TokenWrite, request)
        batch = svc.start_batch(pk, request.user, values['token'])
        return response(RoundSerializer(rounds_query().get(pk=batch.pk)).data, 201)


class BatchesView(AdminView):
    def get(self, request, pk):
        get_team(pk)
        query = rounds_query().filter(tournament_id=pk).order_by('-round_number')
        page = page_number(request); count = query.count()
        return response({'results': RoundSerializer(query[(page - 1) * 10:page * 10], many=True).data,
                         'page': page, 'count': count, 'has_next': page * 10 < count})


class AuditView(AdminView):
    def get(self, request, pk):
        get_team(pk)
        page = page_number(request)
        query = TeamAuditRecord.objects.filter(tournament_id=pk).order_by('-id')
        rows = [{'id': row.pk, 'action': row.action, 'revision': row.revision, 'before': row.before_snapshot,
                 'after': row.after_snapshot, 'reason': row.reason, 'created_by': row.created_by_id, 'created_at': row.created_at}
                for row in query[(page - 1) * 20:page * 20]]
        return response({'results': rows, 'page': page, 'has_next': page * 20 < query.count()})
