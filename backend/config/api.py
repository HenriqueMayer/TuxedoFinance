"""The JSON API: one ``NinjaAPI`` that mounts one router per application.

Every operation needs the Django session unless it sets ``auth=None``. Cookie
authentication also checks the CSRF token on unsafe methods. Public operations
that change state (sign in, sign up) check it themselves with
``config.security.require_csrf``.
"""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import NinjaAPI
from ninja.errors import ValidationError as RequestValidationError
from ninja.security import django_auth

from config import __version__

api = NinjaAPI(
    title="Tuxedo Finance",
    version=__version__,
    auth=django_auth,
    docs_url="/docs" if settings.DEBUG else None,
)


@api.exception_handler(DjangoValidationError)
def domain_validation_error(request, error):
    """Return a domain validation failure as field errors.

    Domain services raise Django's ``ValidationError``. Errors without a field
    use the key ``__all__``.
    """
    if hasattr(error, "error_dict"):
        errors = {
            field: [str(m) for m in messages] for field, messages in error.message_dict.items()
        }
    else:
        errors = {"__all__": [str(m) for m in error.messages]}
    return api.create_response(request, {"detail": "Invalid data", "errors": errors}, status=400)


@api.exception_handler(RequestValidationError)
def request_validation_error(request, error):
    """Return a malformed request in the same shape as a domain failure."""
    errors = {}
    for item in error.errors:
        location = [
            str(part) for part in item.get("loc", []) if part not in {"body", "payload", "data"}
        ]
        errors.setdefault(".".join(location) or "__all__", []).append(
            item.get("msg", "Invalid value")
        )
    return api.create_response(request, {"detail": "Invalid request", "errors": errors}, status=422)


@api.get("/health", auth=None, tags=["system"], summary="Report that the server answers")
def health(request):
    return {"status": "ok", "version": __version__}


api.add_router("/session", "accounts.api.router", tags=["session"])
api.add_router("/banking", "banking.api.router", tags=["banking"])
api.add_router("/ledger", "ledger.api.router", tags=["ledger"])
