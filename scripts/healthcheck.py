"""Container healthcheck: exit 0 if the API answers /healthz, else 1. Stdlib only."""

import os
import sys
import urllib.request

url = f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz"
try:
    with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 - fixed localhost URL
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
