from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import StrictFieldsMixin
from .serializers import ExactInteger
from .models import Tournament, RoundTable, LotteryRecord
from . import competition_services as svc


class SeatPoints(StrictFieldsMixin, serializers.Serializer):
    participant_id = ExactInteger(min_value=1)
    raw_points = ExactInteger(min_value=-(2**53-1), max_value=2**53-1, allow_null=True)


class ResultWrite(StrictFieldsMixin, serializers.Serializer):
    version = ExactInteger(min_value=0)
    points = SeatPoints(many=True, required=False, max_length=4)


class ResultPreviewWrite(ResultWrite):
    points = SeatPoints(many=True, max_length=4)


class Versions(StrictFieldsMixin, serializers.Serializer):
    table_id = ExactInteger(min_value=1)
    version = ExactInteger(min_value=1)


class FinishWrite(StrictFieldsMixin, serializers.Serializer):
    source_versions = Versions(many=True)
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError('需要明确二次确认。')
        return value


class LotteryWrite(StrictFieldsMixin, serializers.Serializer):
    source_versions = Versions(many=True)
    members = serializers.ListField(child=ExactInteger(min_value=1), min_length=2, max_length=16)
    order = serializers.ListField(child=ExactInteger(min_value=1), min_length=2, max_length=16)
    method = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000)
    drawn_at = serializers.DateTimeField()


class ConfirmWrite(StrictFieldsMixin, serializers.Serializer):
    confirmed = serializers.BooleanField()

    validate_confirmed = FinishWrite.validate_confirmed


class ReplaceWrite(StrictFieldsMixin, serializers.Serializer):
    ordinal = ExactInteger(min_value=1, max_value=4)
    machine_id = ExactInteger(min_value=1)
    reason = serializers.CharField(max_length=500)


class ReviewWrite(StrictFieldsMixin, serializers.Serializer):
    historical_only = serializers.BooleanField()
    machine_ids = serializers.ListField(child=ExactInteger(min_value=1), max_length=4)
    reason = serializers.CharField(max_length=500)


class ExactText(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class ResultCorrectionWrite(ResultPreviewWrite):
    version = ExactInteger(min_value=1)
    reason = ExactText(max_length=500, allow_blank=True, required=False, default='')


class VoidWrite(StrictFieldsMixin, serializers.Serializer):
    # Trimmed first; blank or over 500 characters is rejected.
    reason = ExactText(max_length=500)


def validated(cls, request):
    serializer = cls(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def response(data, status=200):
    return Response({'data': data}, status=status, headers={'Cache-Control': 'no-store'})


def lottery_data(row):
    return {key: getattr(row, key) for key in ['id', 'members', 'order', 'method', 'description', 'drawn_at', 'created_by_id', 'created_at', 'confirmed_by_id', 'confirmed_at', 'source_versions', 'rules_version', 'voided_by_id', 'voided_at', 'void_reason']}


class AdminView(APIView):
    permission_classes = [IsAdminUser]


class WorkspaceView(AdminView):
    def get(self, request, pk):
        t = get_object_or_404(Tournament, pk=pk)
        return response({'resource_state': t.resource_state, 'mapping': svc.mapping(t), 'compatibility_audit': t.compatibility_audit, 'order_source': t.order_source, 'lotteries': [lottery_data(x) for x in t.lotteries.all()], **svc.preview(pk, tournament=t)})


class ResultView(AdminView):
    def get(self, request, pk):
        return response(svc.result_data(get_object_or_404(RoundTable, pk=pk)))

    def put(self, request, pk):
        values = validated(ResultWrite, request)
        if 'points' not in values:
            raise serializers.ValidationError({'points': ['保存草稿需要点数条目。']})
        return response(svc.write_result(pk, request.user, **values))


class ConfirmResultView(AdminView):
    def post(self, request, pk):
        return response(svc.write_result(pk, request.user, confirm=True, **validated(ResultWrite, request)))


class PreviewResultView(AdminView):
    def post(self, request, pk):
        return response(svc.preview_result(pk, **validated(ResultPreviewWrite, request)))


class CorrectResultView(AdminView):
    def post(self, request, pk):
        return response(svc.correct_result(pk, request.user, **validated(ResultCorrectionWrite, request)))


class ResultCorrectionsView(AdminView):
    def get(self, request, pk):
        return response(svc.result_corrections(pk))


class ReplaceView(AdminView):
    def post(self, request, pk):
        svc.replace_machine(pk, user=request.user, **validated(ReplaceWrite, request))
        return response(svc.mapping(Tournament.objects.get(pk=pk)))


class ReviewView(AdminView):
    def post(self, request, pk):
        svc.review_legacy(pk, request.user, **validated(ReviewWrite, request))
        return response(svc.mapping(Tournament.objects.get(pk=pk)))


class LotteryView(AdminView):
    def post(self, request, pk):
        return response(lottery_data(svc.record_lottery(pk, request.user, validated(LotteryWrite, request))), 201)


class ConfirmLotteryView(AdminView):
    def post(self, request, pk, lottery_id):
        validated(ConfirmWrite, request)
        return response(lottery_data(svc.confirm_lottery(pk, lottery_id, request.user)))


class VoidLotteryView(AdminView):
    def post(self, request, pk, lottery_id):
        return response(lottery_data(svc.void_lottery(pk, lottery_id, request.user, validated(VoidWrite, request)['reason'])))


class FinishView(AdminView):
    def post(self, request, pk):
        values = validated(FinishWrite, request)
        return response(svc.finish(pk, request.user, values['source_versions']))
