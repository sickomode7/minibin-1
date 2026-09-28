"""bcurl [-v] <host:port>/<path> — MiniBin/1 client, single connection."""
import socket
import sys

from minibin import (Conn, FLAG_END_STREAM, REQ, RESP, dec_block, enc_block,
                     enc_frame, hexdump)

UV = "miniburl/1"


def parse_target(t):
    if "/" in t:
        hp, _, path = t.partition("/")
        path = "/" + path
    else:
        hp, path = t, "/"
    host, _, port = hp.partition(":")
    return host or "127.0.0.1", int(port), path


def main():
    verbose = "-v" in sys.argv
    args = [a for a in sys.argv[1:] if a != "-v"]
    if len(args) != 1:
        print("usage: bcurl [-v] <host:port>/<path>", file=sys.stderr)
        sys.exit(2)
    host, port, path = parse_target(args[0])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # the ONLY connection
    s.settimeout(10)
    s.connect((host, port))
    req_blk = enc_block([("host", f"{host}:{port}"), ("path", path),
                         ("user-agent", UV), ("connection", "keep-alive")])
    req = enc_frame(REQ, FLAG_END_STREAM, 1, 1, req_blk)
    if verbose:
        hexdump("SEND REQUEST", req)
    s.sendall(req)

    c = Conn(s)
    while True:
        ftype, _fl, code, sid, payload = c.read_raw_frame()  # see EVERY frame
        if verbose:
            from minibin import KNOWN, enc_frame as _e
            tag = "RECV" if ftype in KNOWN else "RECV-UNKNOWN-SKIP"
            hexdump(f"{tag} type={ftype:#x} code={code} stream={sid} skipped={c.skipped}",
                    _e(ftype, _fl, code, sid, payload))
        if ftype not in KNOWN:
            c.skipped += 1  # MUST skip via LENGTH (already consumed), keep going
            continue
        if ftype != RESP or sid != 1:
            continue  # ignore PING etc. on this minimal client
        headers, used = dec_block(payload)
        h = {k.lower(): v for k, v in headers}
        body = payload[used:used + int(h.get("content-length", "0"))]
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
        print(f"status={code} bytes={len(body)}", file=sys.stderr)
        s.close()
        sys.exit(0 if code < 400 else 1)


if __name__ == "__main__":
    main()
