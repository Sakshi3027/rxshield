"""One shared HTTP session that retries transient network and server failures with exponential backoff."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RETRY = Retry(
    total=6,
    connect=6,
    read=6,
    status=6,
    backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
    respect_retry_after_header=True,
    raise_on_status=False,
)

session = requests.Session()
_adapter = HTTPAdapter(max_retries=RETRY)
session.mount("https://", _adapter)
session.mount("http://", _adapter)