"""Request checks shared by the API routers."""

from ninja.errors import HttpError
from ninja.utils import check_csrf


def require_csrf(request):
    """Reject a state-changing request that has no valid CSRF token.

    Session authentication already does this check. A public operation that
    changes state has no authentication, so it calls this function.
    """
    if check_csrf(request):
        raise HttpError(403, "CSRF check failed")
