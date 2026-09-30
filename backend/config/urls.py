from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from carteira import views as carteira
from contas import views as contas
from kyc import views as kyc

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/saude", lambda request: JsonResponse({"status": "ok"})),
    path("api/token", TokenObtainPairView.as_view()),
    path("api/token/renovar", TokenRefreshView.as_view()),
    path("api/contas/cadastro", contas.cadastro),
    path("api/contas/eu", contas.eu),
    path("api/kyc/minha", kyc.minha),
    path("api/kyc/fila", kyc.Fila.as_view()),
    path("api/kyc/<int:pk>/decisao", kyc.decisao),
    path("api/kyc/<int:pk>/documento", kyc.documento),
    path("api/auditoria", kyc.Auditoria.as_view()),
    path("api/carteira", carteira.resumo),
    path("api/carteira/depositos", carteira.depositos),
    path("api/carteira/saques", carteira.saques),
    path("api/carteira/extrato", carteira.Extrato.as_view()),
]
