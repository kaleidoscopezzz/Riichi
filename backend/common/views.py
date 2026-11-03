from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Public liveness endpoint. This does not claim database readiness."""

    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        response = Response({"status": "ok", "service": "riichi-api", "api_version": "v1"})
        response["Cache-Control"] = "no-store"
        return response
