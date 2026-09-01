import http.client
import threading
from socketserver import ThreadingTCPServer

from bg_server import AppHandler


def _request(port, path, token=None, origin=None):
    headers = {}
    if token is not None:
        headers["X-Battery-Guardian-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def test_local_api_requires_session_token_and_same_origin():
    server = ThreadingTCPServer(("127.0.0.1", 0), AppHandler)
    port = server.server_address[1]
    token = "test-session-secret"
    AppHandler.configure(token, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(port, "/api/status")[0] == 403
        assert _request(port, "/api/status", token, "https://attacker.example")[0] == 403
        assert _request(port, "/api/status", token, f"http://localhost:{port}")[0] == 200

        status, html = _request(port, "/")
        assert status == 200
        assert token.encode() in html
        assert b"{{API_TOKEN}}" not in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
