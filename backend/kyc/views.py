from datetime import date

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from contas.models import Papel
from contas.permissoes import EhCliente, EhCompliance, EhOperador
from kyc import servicos
from kyc.models import EventoAuditoria, Status, Verificacao
from kyc.validadores import cpf_valido, limpar_cpf

# Assinatura dos primeiros bytes de cada tipo aceito. O content-type vem do navegador e pode ser
# falsificado; os bytes do arquivo, não.
ASSINATURAS = {"application/pdf": b"%PDF", "image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG"}


class EnvioSerializer(serializers.Serializer):
    nome_completo = serializers.CharField(max_length=120)
    cpf = serializers.CharField(max_length=14)
    data_nascimento = serializers.DateField()
    documento = serializers.FileField()

    def validate_cpf(self, cpf: str) -> str:
        if not cpf_valido(cpf):
            raise serializers.ValidationError("CPF inválido")
        return limpar_cpf(cpf)

    def validate_data_nascimento(self, nascimento: date) -> date:
        hoje = date.today()
        idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        if idade < 18:
            raise serializers.ValidationError("é preciso ter 18 anos ou mais")
        return nascimento

    def validate_documento(self, arquivo):
        if arquivo.size > settings.KYC_TAMANHO_MAXIMO:
            raise serializers.ValidationError("arquivo maior que 2 MB")
        assinatura = ASSINATURAS.get(arquivo.content_type)
        inicio = arquivo.read(8)
        arquivo.seek(0)
        if assinatura is None or not inicio.startswith(assinatura):
            raise serializers.ValidationError("envie um PDF, JPG ou PNG")
        return arquivo


class VerificacaoSerializer(serializers.ModelSerializer):
    cliente_email = serializers.EmailField(source="cliente.email", read_only=True)
    decidido_por_email = serializers.EmailField(source="decidido_por.email", read_only=True, default=None)

    class Meta:
        model = Verificacao
        fields = ["id", "cliente_email", "nome_completo", "cpf", "data_nascimento", "documento_tipo", "status",
                  "motivo_recusa", "decidido_por_email", "decidido_em", "criado_em"]


class EventoSerializer(serializers.ModelSerializer):
    ator_email = serializers.EmailField(source="ator.email", read_only=True)

    class Meta:
        model = EventoAuditoria
        fields = ["id", "ator_email", "acao", "verificacao", "dados", "criado_em"]


class DecisaoSerializer(serializers.Serializer):
    aprovar = serializers.BooleanField()
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


@api_view(["GET", "POST"])
@permission_classes([EhCliente])
@parser_classes([MultiPartParser])
def minha(request):
    """GET: a verificação mais recente do cliente logado. POST: envia uma nova."""
    if request.method == "GET":
        v = request.user.verificacoes.order_by("-criado_em").first()
        if v is None:
            return Response({"detail": "nenhuma verificação enviada"}, status=status.HTTP_404_NOT_FOUND)
        return Response(VerificacaoSerializer(v).data)
    s = EnvioSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    try:
        v = servicos.enviar(request.user, **s.validated_data)
    except servicos.Conflito as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
    return Response(VerificacaoSerializer(v).data, status=status.HTTP_201_CREATED)


class Fila(generics.ListAPIView):
    """Fila do operador. ?status=pendente (padrão), aprovada ou recusada."""

    serializer_class = VerificacaoSerializer
    permission_classes = [EhOperador]

    def get_queryset(self):
        filtro = self.request.query_params.get("status", Status.PENDENTE)
        return Verificacao.objects.select_related("cliente", "decidido_por").filter(status=filtro)


@api_view(["POST"])
@permission_classes([EhOperador])
def decisao(request, pk: int):
    s = DecisaoSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    try:
        v = servicos.decidir(pk, request.user, aprovar=s.validated_data["aprovar"], motivo=s.validated_data["motivo"])
    except Verificacao.DoesNotExist:
        raise Http404
    except servicos.Conflito as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
    except ValueError as erro:
        return Response({"motivo": [str(erro)]}, status=status.HTTP_400_BAD_REQUEST)
    return Response(VerificacaoSerializer(v).data)


@api_view(["GET"])
def documento(request, pk: int):
    """O dono e os operadores veem o documento. Para os outros, o pedido "não existe" (404, não 403),
    para não confirmar que o id existe."""
    v = Verificacao.objects.filter(pk=pk).first()
    pode = v is not None and (v.cliente_id == request.user.id or request.user.papel == Papel.OPERADOR)
    if not pode:
        raise Http404
    return FileResponse(v.documento.open("rb"), content_type=v.documento_tipo)


class Auditoria(generics.ListAPIView):
    serializer_class = EventoSerializer
    permission_classes = [EhCompliance]
    queryset = EventoAuditoria.objects.select_related("ator")
