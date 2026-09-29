from rest_framework.permissions import BasePermission

from contas.models import Papel


class TemPapel(BasePermission):
    papeis: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.papel in self.papeis)


class EhCliente(TemPapel):
    papeis = (Papel.CLIENTE,)


class EhOperador(TemPapel):
    papeis = (Papel.OPERADOR,)


class EhCompliance(TemPapel):
    papeis = (Papel.COMPLIANCE,)


class EhEquipe(TemPapel):
    papeis = (Papel.OPERADOR, Papel.COMPLIANCE)
