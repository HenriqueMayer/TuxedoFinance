"""URL routes: the API under ``/api/`` and the client for every other path."""

from django.conf import settings
from django.http import Http404, HttpResponse
from django.urls import path, re_path
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from config.api import api


@never_cache
@require_safe
def client(request):
    """Return the client entry document for a client-side route.

    WhiteNoise serves the client's files. A path that is not a file, such as
    ``/transactions``, is a route of the client and gets ``index.html``. The
    document is not cached, because it names the hashed files of one build.
    """
    index = settings.CLIENT_DIR / "index.html"
    if not index.is_file():
        raise Http404("The client is not built. Run the build in web/.")
    return HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")


urlpatterns = [
    path("api/", api.urls),
    # An unknown API path is an error, not a client route.
    re_path(r"^(?!api/).*$", client, name="client"),
]
