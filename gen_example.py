import struct

TABLE = {
    "host": 0x01, "path": 0x02, "content-type": 0x03,
    "content-length": 0x04, "connection": 0x05, "accept": 0x06,
    "user-agent": 0x07, "operation": 0x08, "operand-a": 0x09,
    "operand-b": 0x0A,
}

def enc_header(name, value):
    v = value.encode()
    key = name.lower()
    if key in TABLE:
        return bytes([TABLE[key]]) + struct.pack(">H", len(v)) + v
    n = name.encode()
    return bytes([0x00, len(n)]) + n + struct.pack(">H", len(v)) + v

def enc_block(pairs):
    out = struct.pack(">H", len(pairs))
    for k, v in pairs:
        out += enc_header(k, v)
    return out

def enc_frame(ftype, flags, code, stream_id, payload):
    assert stream_id & 0x80000000 == 0
    h = (len(payload).to_bytes(3, "big") + bytes([ftype, flags])
         + struct.pack(">H", code) + struct.pack(">I", stream_id))
    return h + payload

def dec_frames(buf):
    """Yield (ftype, flags, code, stream, payload) skipping unknown types per spec."""
    KNOWN = {0x01, 0x02, 0x03, 0x04}
    i, out, skipped = 0, [], 0
    while i + 11 <= len(buf):
        ln = int.from_bytes(buf[i:i+3], "big")
        ftype, flags = buf[i+3], buf[i+4]
        code = struct.unpack(">H", buf[i+5:i+7])[0]
        sid = struct.unpack(">I", buf[i+7:i+11])[0] & 0x7FFFFFFF
        payload = bytes(buf[i+11:i+11+ln])
        assert len(payload) == ln, "truncated"
        if ftype not in KNOWN:
            skipped += 1  # MUST skip, not error
        else:
            out.append((ftype, flags, code, sid, payload))
        i += 11 + ln
    return out, skipped

# --- Example from spec ---
req_block = enc_block([("host", "calc.local"), ("path", "/add?a=2&b=3"),
                       ("operation", "add"), ("X-Trace-ID", "abc-123")])
req = enc_frame(0x01, 0x01, 1, 1, req_block)

resp_block = enc_block([("content-type", "text/plain"), ("content-length", "1")])
resp = enc_frame(0x02, 0x01, 200, 1, resp_block + b"5")

print("REQ_BLOCK", req_block.hex(" "))
print("REQ_FRAME", req.hex(" "))
print("RESP_FRAME", resp.hex(" "))

# skip-rule demo: REQ + unknown(0x9F,len=4) + RESP
unknown = enc_frame(0x9F, 0x00, 0, 1, b"\xde\xad\xbe\xef")
stream = req + unknown + resp
frames, skipped = dec_frames(stream)
print("parsed:", [(hex(t), c, s) for t, f, c, s, p in frames], "skipped_unknown:", skipped)
assert len(frames) == 2 and skipped == 1 and frames[1][2] == 200
print("SKIP-RULE OK")
