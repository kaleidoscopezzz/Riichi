from django.db.models import Count, Q
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import StrictFieldsMixin, search_text
from .models import MahjongMachine
from .serializers import MachineSerializer, MachineWriteSerializer
from .services import change_machine, create_machine


class MachinePagination(PageNumberPagination):
    page_size = 20


class MachineListView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = MachineSerializer
    pagination_class = MachinePagination

    def get(self, request):
        search = search_text(request.query_params.get("search", "")).strip()
        status = request.query_params.get("status", "")
        if len(search) > 100:
            raise ValidationError({"search": ["搜索内容最多100字符。"]})
        if status and status not in MahjongMachine.Status.values:
            raise ValidationError({"status": ["未知设备状态。"]})
        queryset = MahjongMachine.objects.all()
        summary = queryset.aggregate(**{value: Count("id", filter=Q(status=value)) for value in MahjongMachine.Status.values})
        summary["active"] = summary["available"] + summary["maintenance"] + summary["disabled"]
        if search:
            queryset = queryset.filter(Q(machine_no__icontains=search) | Q(name__icontains=search))
        if status:
            queryset = queryset.filter(status=status)
        page = self.paginate_queryset(queryset)
        return Response({"data": {
            "count": self.paginator.page.paginator.count,
            "next": self.paginator.get_next_link(), "previous": self.paginator.get_previous_link(),
            "results": self.get_serializer(page, many=True).data, "summary": summary,
        }}, headers={"Cache-Control": "no-store"})

    def post(self, request):
        serializer = MachineWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        machine = create_machine(serializer.validated_data)
        return Response({"data": MachineSerializer(machine).data}, status=201)


class MachineDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        return Response({"data": MachineSerializer(get_object_or_404(MahjongMachine, pk=pk)).data}, headers={"Cache-Control": "no-store"})

    def patch(self, request, pk):
        serializer = MachineWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ValidationError({"non_field_errors": ["请提供需要修改的字段。"]})
        return Response({"data": MachineSerializer(change_machine(pk, serializer.validated_data)).data})


class EmptySerializer(StrictFieldsMixin, serializers.Serializer):
    pass


class MachineRetireView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = EmptySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"data": MachineSerializer(change_machine(pk, retire=True)).data})
