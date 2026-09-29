from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Papel(models.TextChoices):
    CLIENTE = "cliente", "Cliente"
    OPERADOR = "operador", "Operador"
    COMPLIANCE = "compliance", "Compliance"


class GerenciadorUsuarios(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("email é obrigatório")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class Usuario(AbstractUser):
    """Login por email. O papel decide o que cada um vê; só o admin muda o papel."""

    username = None
    email = models.EmailField("email", unique=True)
    nome = models.CharField(max_length=120)
    papel = models.CharField(max_length=12, choices=Papel.choices, default=Papel.CLIENTE)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = GerenciadorUsuarios()

    def __str__(self) -> str:
        return f"{self.email} ({self.papel})"
