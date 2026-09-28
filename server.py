import socket
import threading
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 18080

REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}


def parse_number(s):
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    return f


def format_number(f):
    if f.is_integer():
        return str(int(f))
    return str(f)


def build_response(code, body: str):
    body_b = body.encode()
    reason = REASONS[code]
    head = (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(body_b)}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    )
    return head.encode() + body_b


def route(method, target, headers):
    if method != "GET":
        return 405, "method not allowed"
    if "host" not in headers:
        return 400, "missing Host header"

    parsed = urlparse(target)
    path = parsed.path
    # manual query parse (no HTTP lib); parse_qs is URL-only, allowed
    qs = parse_qs(parsed.query, keep_blank_values=True)

    if path not in ("/add", "/sub", "/mul", "/div"):
        return 404, "not found"

    if "a" not in qs or "b" not in qs or not qs["a"][0] or not qs["b"][0]:
        return 400, "missing a or b"
    a = parse_number(qs["a"][0])
    b = parse_number(qs["b"][0])
    if a is None or b is None:
        return 400, "invalid a or b"

    if path == "/add":
        return 200, format_number(a + b)
    if path == "/sub":
        return 200, format_number(a - b)
    if path == "/mul":
        return 200, format_number(a * b)
    if path == "/div":
        if b == 0:
            return 400, "division by zero"
        return 200, format_number(a / b)


def recv_one_request(conn, buf: bytearray):
    """Read until b'\\r\\n\\r\\n'. Consume only up to terminator, keep rest in buf."""
    while True:
        idx = buf.find(b"\r\n\r\n")
        if idx != -1:
            end = idx + 4
            raw = bytes(buf[:end])
            del buf[:end]
            return raw
        chunk = conn.recv(4096)
        if not chunk:
            return None  # client closed
        buf.extend(chunk)
        if len(buf) > 64 * 1024:
            return bytes(buf)  # oversized -> caller will 400


def parse_request(raw: bytes):
    try:
        text = raw.decode("iso-8859-1")
    except UnicodeDecodeError:
        return None
    lines = text.split("\r\n")
    if not lines or not lines[0]:
        return None
    parts = lines[0].split()
    if len(parts) != 3:
        return None
    method, target, version = parts
    if not version.startswith("HTTP/"):
        return None
    headers = {}
    for line in lines[1:]:
        if line == "":
            continue
        if ":" not in line:
            return None
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return method, target, headers


def handle_client(conn, addr):
    buf = bytearray()
    try:
        while True:
            raw = recv_one_request(conn, buf)
            if raw is None:
                break  # client closed cleanly
            req = parse_request(raw)
            if req is None:
                conn.sendall(build_response(400, "bad request"))
                continue
            method, target, headers = req
            code, body = route(method, target, headers)
            conn.sendall(build_response(code, body))
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    print(f"serving on {HOST}:{PORT}", flush=True)
    while True:
        conn, addr = srv.accept()
        conn.settimeout(30)
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
