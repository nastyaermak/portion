from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import ProfileSerializer, RegisterSerializer


class RegisterView(APIView):
    """POST /api/auth/register — реєстрація."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            RegisterSerializer(user).data, status=status.HTTP_201_CREATED
        )


class LoginView(TokenObtainPairView):
    """POST /api/auth/login — вхід, повертає access і refresh токени."""

    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            raise AuthenticationFailed(
                "Неправильний username або пароль",
                code="invalid_credentials",
            )


class MeView(APIView):
    """GET і PATCH /api/me — профіль залогіненого користувача."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
