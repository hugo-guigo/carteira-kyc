from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from carteira import servicos
from carteira.models import LIMITE_CENTAVOS, Conta, Lancamento, Transacao
from contas.permissoes import EhCliente

CABECALHO_CHAVE = "Idempotency-Key"


class OperacaoSerializer(serializers.Serializer):
    valor_centavos = serializers.IntegerField(min_value=1, max_value=LIMITE_CENTAVOS)


class TransacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transacao
        fields = ["id", "tipo", "valor_centavos", "criado_em"]


class LancamentoSerializer(serializers.ModelSerializer):
    tipo = serializers.CharField(source="transacao.tipo", read_only=True)
    transacao = serializers.UUIDField(source="transacao_id", read_only=True)

    class Meta:
        model = Lancamento
        fields = ["id", "transacao", "tipo", "valor_centavos", "criado_em"]


def _chave(request) -> str | None:
    chave = request.headers.get(CABECALHO_CHAVE, "").strip()
    return chave if 8 <= len(chave) <= 64 else None


@api_view(["GET"])
@permission_classes([EhCliente])
def resumo(request):
    try:
        conta = servicos.conta_do(request.user)
    except servicos.SemConta as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_404_NOT_FOUND)
    return Response({"saldo_centavos": servicos.saldo(conta)})


def _operacao(request, operar) -> Response:
    chave = _chave(request)
    if chave is None:
        return Response({"detail": f"envie o cabeçalho {CABECALHO_CHAVE} com 8 a 64 caracteres"},
                        status=status.HTTP_400_BAD_REQUEST)
    s = OperacaoSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    try:
        r = operar(request.user, s.validated_data["valor_centavos"], chave)
    except servicos.SemConta as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_404_NOT_FOUND)
    except servicos.SaldoInsuficiente as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
    except servicos.ChaveReusada as erro:
        return Response({"detail": str(erro)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    corpo = {**TransacaoSerializer(r.transacao).data, "saldo_centavos": servicos.saldo(r.transacao.conta)}
    if r.repetida:
        return Response(corpo, status=status.HTTP_200_OK, headers={"Idempotent-Replayed": "true"})
    return Response(corpo, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([EhCliente])
def depositos(request):
    return _operacao(request, servicos.depositar)


@api_view(["POST"])
@permission_classes([EhCliente])
def saques(request):
    return _operacao(request, servicos.sacar)


class PaginaDoExtrato(CursorPagination):
    # Cursor em vez de número de página: a página seguinte continua de onde a anterior parou, mesmo que
    # um lançamento novo entre no meio, e a consulta usa o índice (conta, criado_em, id) sem OFFSET.
    ordering = ("-criado_em", "-id")
    page_size = 20


class Extrato(generics.ListAPIView):
    serializer_class = LancamentoSerializer
    permission_classes = [EhCliente]
    pagination_class = PaginaDoExtrato

    def get_queryset(self):
        # Só a conta do próprio cliente; sem conta, a lista vem vazia. Filtra pelo id da conta (e não por
        # conta__dono) para a consulta ser a medida em docs/explain-extrato.md, sem junção.
        conta = Conta.objects.filter(dono=self.request.user).values_list("id", flat=True).first()
        return Lancamento.objects.filter(conta_id=conta).select_related("transacao")
