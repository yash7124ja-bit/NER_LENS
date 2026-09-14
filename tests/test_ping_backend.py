from unittest.mock import MagicMock, patch
from urllib.error import URLError

from scripts.ping_backend import ping


def test_ping_requires_ready_response_and_handles_failure():
    response = MagicMock()
    response.status = 200
    response.__enter__.return_value = response
    with patch("scripts.ping_backend.urlopen", return_value=response) as fetch:
        response.read.return_value = b'{"status":"ready"}'
        assert ping("https://example.invalid/health/ready")
        assert fetch.call_args.kwargs["timeout"] == 30
        for body in (b"<html>Starting service</html>", b"[]", b'{"status":"degraded"}'):
            response.read.return_value = body
            assert not ping("https://example.invalid/health/ready")
    with patch("scripts.ping_backend.urlopen", side_effect=URLError("offline")):
        assert not ping("https://example.invalid/health/ready")
