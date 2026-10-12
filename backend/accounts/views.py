from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        get_token(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # DRF는 미인증 요청의 CSRF를 검사하지 않아, 없으면 login CSRF가 열립니다.
        SessionAuthentication().enforce_csrf(request)
        user = authenticate(
            request, username=request.data.get("username"), password=request.data.get("password")
        )
        if user is None:
            return Response({"detail": "invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response({"username": user.get_username()})


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response({"username": request.user.get_username()})
