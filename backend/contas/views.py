from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from contas.models import Usuario


class CadastroSerializer(serializers.Serializer):
    email = serializers.EmailField()
    nome = serializers.CharField(max_length=120)
    senha = serializers.CharField(write_only=True)

    def validate_email(self, email: str) -> str:
        email = email.lower()
        if Usuario.objects.filter(email=email).exists():
            raise serializers.ValidationError("email já cadastrado")
        return email

    def validate(self, dados: dict) -> dict:
        validate_password(dados["senha"], Usuario(email=dados["email"], nome=dados["nome"]))
        return dados


def perfil(u: Usuario) -> dict:
    return {"id": u.id, "email": u.email, "nome": u.nome, "papel": u.papel}


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def cadastro(request):
    """Todo cadastro público vira cliente. Um campo "papel" no corpo é ignorado de propósito."""
    s = CadastroSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    u = Usuario.objects.create_user(s.validated_data["email"], s.validated_data["senha"],
                                    nome=s.validated_data["nome"])
    return Response(perfil(u), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def eu(request):
    return Response(perfil(request.user))
