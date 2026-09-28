"""Send unknown frame type + real request on ONE socket; server must skip & answer."""
import socket
import subprocess
import sys
import time
from pathlib import Path

from minibin import Conn, FLAG_END_STREAM, REQ, RESP, dec_block, enc_block, enc_frame

PORT = 18081
ROOT = Path(__file__).parent / "www_test"
ROOT.mkdir(exist_ok=True)
(ROOT / "hello.txt").write_bytes(b"hello minibin\n")

srv = subprocess.Popen([sys.executable, "bserve.py", str(ROOT), str(PORT)],
                       cwd=str(Path(__file__).parent))
try:
    for _ in range(50):
        try:
            probe = socket.create_connection(("127.0.0.1", PORT), timeout=1)
            probe.close()
            break
        except OSError:
            time.sleep(0.1)

    s = socket.create_connection(("127.0.0.1", PORT), timeout=5)  # single connection
    local = s.getsockname()
    unknown = enc_frame(0x9F, 0x00, 0, 1, b"\xde\xad\xbe\xef")  # unrecognized type, len=4
    blk = enc_block([("host", f"127.0.0.1:{PORT}"), ("path", "/hello.txt"),
                     ("user-agent", "skip-test"), ("connection", "keep-alive")])
    real = enc_frame(REQ, FLAG_END_STREAM, 1, 1, blk)
    s.sendall(unknown + real)  # pipelined: garbage frame first
    print(f"sent unknown(0x9F,len=4) + REQUEST back-to-back on {local}")

    c = Conn(s)
    ftype, _fl, code, sid, payload = c.read_frame()
    assert ftype == RESP and code == 200, (ftype, code)
    headers, used = dec_block(payload)
    body = payload[used:]
    print(f"resp: type=RESP code={code} stream={sid} skipped_unknown={c.skipped}")
    print(f"headers={headers} body={body!r}")
    assert body == b"hello minibin\n"
    assert s.getsockname() == local, "new connection detected!"

    # connection still alive: second real request, no reconnect
    blk2 = enc_block([("host", "x"), ("path", "/missing.txt")])
    s.sendall(enc_frame(REQ, FLAG_END_STREAM, 1, 3, blk2))
    ftype, _fl, code2, sid2, payload2 = c.read_frame()
    assert code2 == 404, code2
    print(f"second req on same socket -> {code2} (still open, same port {s.getsockname()})")
    print("SKIP-TEST PASSED: server skipped 0x9F via length, parsed next frame")
    s.close()
finally:
    srv.terminate()
