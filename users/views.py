import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import ProfileSerializer, RegisterSerializer

logger = logging.getLogger("portion.auth")


class RegisterView(APIView):
    """POST /api/auth/register — реєстрація."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Вхід і профіль"],
        summary="Реєстрація",
        request=RegisterSerializer,
        responses={201: RegisterSerializer},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info("User registered: id=%s", user.pk)
        return Response(
            RegisterSerializer(user).data, status=status.HTTP_201_CREATED
        )


class LoginView(TokenObtainPairView):
    """POST /api/auth/login — вхід, повертає access і refresh токени."""

    authentication_classes = []

    def post(self, request, *args, **kwargs):
        # У лог — лише username, ніколи пароль чи токени
        data = request.data if isinstance(request.data, dict) else {}
        username = data.get("username", "")
        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            logger.warning("Failed login for username=%r", username)
            raise AuthenticationFailed(
                "Неправильний username або пароль",
                code="invalid_credentials",
            )
        logger.info("User logged in: username=%r", username)
        return response


class MeView(APIView):
    """GET і PATCH /api/me — профіль залогіненого користувача."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Вхід і профіль"],
        summary="Мій профіль",
        responses={200: ProfileSerializer},
    )
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    @extend_schema(
        tags=["Вхід і профіль"],
        summary="Змінити профіль",
        request=ProfileSerializer,
        responses={200: ProfileSerializer},
    )
    def patch(self, request):
        serializer = ProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
