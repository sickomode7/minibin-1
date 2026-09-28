"""bserve <root_dir> <port> — MiniBin/1 static file server (keep-alive)."""
import mimetypes
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import unquote

from minibin import (Conn, FLAG_END_STREAM, GOAWAY, PING, REQ, RESP,
                     dec_block, enc_block, enc_frame)

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 2 else None
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else None


def err_frame(stream_id, code, msg):
    body = msg.encode()
    blk = enc_block([("content-type", "text/plain"), ("content-length", str(len(body)))])
    return enc_frame(RESP, FLAG_END_STREAM, code, stream_id, blk + body)


def handle(conn_sock):
    c = Conn(conn_sock)
    while True:
        try:
            ftype, _flags, code, sid, payload = c.read_frame()
        except (ConnectionError, ValueError):
            break  # closed or unrecoverable framing error -> drop connection
        try:
            if ftype == PING:
                conn_sock.sendall(enc_frame(PING, 0x08, 0, 0, payload))
            elif ftype == GOAWAY:
                break
            elif ftype == REQ:
                if code not in (1, 2):
                    conn_sock.sendall(err_frame(sid, 400, "bad method code"))
                    continue
                if code != 1:
                    conn_sock.sendall(err_frame(sid, 405, "method not allowed"))
                    continue
                try:
                    headers, used = dec_block(payload)
                    if used != len(payload):
                        raise ValueError("trailing bytes after header block")
                    h = {k.lower(): v for k, v in headers}
                    path = h.get("path")
                    if not path or not path.startswith("/"):
                        raise ValueError("missing/bad path")
                except ValueError:
                    conn_sock.sendall(err_frame(sid, 400, "bad request"))
                    continue
                rel = unquote(path.split("?", 1)[0].split("#", 1)[0].lstrip("/"))
                target = (ROOT / rel).resolve()
                try:
                    target.relative_to(ROOT)
                except ValueError:
                    conn_sock.sendall(err_frame(sid, 400, "bad request"))
                    continue
                if not target.is_file():
                    conn_sock.sendall(err_frame(sid, 404, "not found"))
                    continue
                body = target.read_bytes()
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                blk = enc_block([("content-type", ctype),
                                 ("content-length", str(len(body)))])
                conn_sock.sendall(enc_frame(RESP, FLAG_END_STREAM, 200, sid, blk + body))
        except (ConnectionError, BrokenPipeError):
            break
    try:
        conn_sock.close()
    except OSError:
        pass


def main():
    if ROOT is None:
        print("usage: bserve <root_dir> <port>", file=sys.stderr)
        sys.exit(2)
    ROOT.mkdir(parents=True, exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(50)
    print(f"bserve {ROOT} on :{PORT}", flush=True)
    while True:
        s, _ = srv.accept()
        s.settimeout(30)
        threading.Thread(target=handle, args=(s,), daemon=True).start()


if __name__ == "__main__":
    main()
