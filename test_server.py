import socket, time

HOST, PORT = "127.0.0.1", 18080

def raw_request(sock, req):
    sock.sendall(req.encode())
    # read one response: headers until \r\n\r\n, then body per Content-Length
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        assert chunk, "server closed early"
        buf += chunk
    head, rest = buf.split(b"\r\n\r\n", 1)
    cl = 0
    for line in head.decode().split("\r\n"):
        if line.lower().startswith("content-length:"):
            cl = int(line.split(":")[1].strip())
    while len(rest) < cl:
        rest += sock.recv(4096)
    return head.decode().split("\r\n")[0], rest[:cl].decode(), rest[cl:]

s = socket.create_connection((HOST, PORT), timeout=5)

tests = [
    ("GET /add?a=2&b=3 HTTP/1.1\r\nHost: x\r\n\r\n", "200", "5"),
    ("GET /sub?a=10&b=4 HTTP/1.1\r\nHost: x\r\n\r\n", "200", "6"),
    ("GET /mul?a=3&b=4 HTTP/1.1\r\nHost: x\r\n\r\n", "200", "12"),
    ("GET /div?a=8&b=2 HTTP/1.1\r\nHost: x\r\n\r\n", "200", "4"),
    ("GET /div?a=1&b=0 HTTP/1.1\r\nHost: x\r\n\r\n", "400", None),
    ("GET /add?a=1 HTTP/1.1\r\nHost: x\r\n\r\n", "400", None),
    ("GET /add?a=x&b=1 HTTP/1.1\r\nHost: x\r\n\r\n", "400", None),
    ("GET /add?a=1&b=2 HTTP/1.1\r\n\r\n", "400", None),  # missing Host
    ("GET /nope?a=1&b=2 HTTP/1.1\r\nHost: x\r\n\r\n", "404", None),
    ("POST /add?a=1&b=2 HTTP/1.1\r\nHost: x\r\n\r\n", "405", None),
]
for req, code, body in tests:
    status, b, _ = raw_request(s, req)
    assert code in status, f"{req!r} -> {status}"
    if body is not None:
        assert b == body, f"{req!r} -> body {b!r}"
    print(f"OK {status} body={b!r}")

# pipelining: two requests in one send, server must answer both in order
s2 = socket.create_connection((HOST, PORT), timeout=5)
s2.sendall(
    b"GET /add?a=1&b=1 HTTP/1.1\r\nHost: x\r\n\r\n"
    b"GET /mul?a=2&b=5 HTTP/1.1\r\nHost: x\r\n\r\n"
)
st1, b1, leftover = raw_request(s2, "")  # already-sent bytes; send empty
print("pipelined req1:", st1, b1)
# leftover may already hold 2nd response; feed it back via new socket read logic
# simplest: read 2nd response from same socket accounting leftover
buf = leftover
while b"\r\n\r\n" not in buf:
    buf += s2.recv(4096)
head, rest = buf.split(b"\r\n\r\n", 1)
cl = 0
for line in head.decode().split("\r\n"):
    if line.lower().startswith("content-length:"):
        cl = int(line.split(":")[1].strip())
while len(rest) < cl:
    rest += s2.recv(4096)
print("pipelined req2:", head.decode().split("\r\n")[0], rest[:cl].decode())
assert "200" in st1 and b1 == "2"
assert "200" in head.decode() and rest[:cl].decode() == "10"
print("ALL TESTS PASSED")
