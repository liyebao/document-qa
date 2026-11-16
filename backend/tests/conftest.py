import base64
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"0" * 32).decode()
)

_test_database_url = os.environ.get("TEST_DATABASE_URL")
if _test_database_url:
    os.environ["DATABASE_URL"] = _test_database_url
