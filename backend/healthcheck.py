"""Container health check: the server answers ``/api/health``.

The request names the first allowed host, so the check also passes when
``ALLOWED_HOSTS`` holds only the public name of the installation.
"""

import os
import sys
import urllib.request

host = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")[0].strip() or "localhost"
request = urllib.request.Request("http://127.0.0.1:8000/api/health", headers={"Host": host})
try:
    with urllib.request.urlopen(request, timeout=4) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
