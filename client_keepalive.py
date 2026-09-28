import socket

HOST, PORT = "127.0.0.1", 18080

REQUESTS = [
    ("GET /add?a=10&b=5 HTTP/1.1", "valid add, expect 200 body=15"),
    ("GET /sub?a=10&b=4 HTTP/1.1", "valid sub, expect 200 body=6"),
    ("GET /mul?a=3&b=7 HTTP/1.1", "valid mul, expect 200 body=21"),
    ("GET /div?a=20&b=4 HTTP/1.1", "valid div, expect 200 body=5"),
    ("GET /div?a=1&b=0 HTTP/1.1", "div by zero, expect 400"),
    ("GET /pow?a=2&b=8 HTTP/1.1", "unknown path, expect 404"),
    ("POST /add?a=1&b=2 HTTP/1.1", "non-GET, expect 405"),
]

buf = bytearray()

def read_one_response(sock):
    while True:
        idx = buf.find(b"\r\n\r\n")
        if idx != -1:
            break
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("server closed connection mid-response")
        buf.extend(chunk)
    head_end = idx + 4
    head = bytes(buf[:head_end])
    del buf[:head_end]
    headers = head.decode("iso-8859-1").split("\r\n")
    status_line = headers[0]
    cl = 0
    for line in headers:
        if line.lower().startswith("content-length:"):
            cl = int(line.split(":", 1)[1].strip())
    while len(buf) < cl:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("server closed mid-body")
        buf.extend(chunk)
    body = bytes(buf[:cl])
    del buf[:cl]
    return status_line, body.decode()


def main():
    handshakes = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((HOST, PORT))  # the ONE and only TCP handshake
    handshakes += 1

    local0 = sock.getsockname()
    remote0 = sock.getpeername()
    print(f"[connect] TCP handshake #{handshakes}: {local0} -> {remote0}")
    print(f"[info] single socket fileno={sock.fileno()}, sending {len(REQUESTS)} requests back-to-back\n")

    # Back-to-back on the SAME socket (pipelined: no waiting between sends)
    for line, _ in REQUESTS:
        sock.sendall(f"{line}\r\nHost: {HOST}\r\n\r\n".encode())

    for i, ((line, note)) in enumerate(REQUESTS, 1):
        status, body = read_one_response(sock)
        print(f"--- response {i}/{len(REQUESTS)} ---")
        print(f"req : {line}  ({note})")
        print(f"resp: {status}  body={body!r}")
        # connection identity must be unchanged => no new handshake
        assert sock.getsockname() == local0, "local port changed = new connection!"
        assert sock.getpeername() == remote0, "remote changed = new connection!"

    print(f"\n[check] handshakes performed: {handshakes} (connect() called once)")
    print(f"[check] ports unchanged: local={sock.getsockname()} remote={sock.getpeername()}")

    # Socket still open at end: peername works + liveness probe succeeds
    try:
        sock.getpeername()
        open_before_probe = sock.fileno() != -1
    except OSError:
        open_before_probe = False
    sock.sendall(b"GET /add?a=1&b=1 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    status, body = read_one_response(sock)
    print(f"[probe] liveness request after batch -> {status} body={body!r}")
    print(f"[result] socket still open at end: {open_before_probe and '200' in status}")
    sock.close()

if __name__ == "__main__":
    main()
