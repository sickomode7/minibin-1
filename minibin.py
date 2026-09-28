"""MiniBin/1 shared framing. See PROTOCOL.md."""
import struct

REQ, RESP, PING, GOAWAY = 0x01, 0x02, 0x03, 0x04
KNOWN = {REQ, RESP, PING, GOAWAY}
FLAG_END_STREAM = 0x01
FLAG_ACK = 0x08
HDR_LEN = 11

TABLE = {
    "host": 0x01, "path": 0x02, "content-type": 0x03,
    "content-length": 0x04, "connection": 0x05, "accept": 0x06,
    "user-agent": 0x07, "operation": 0x08, "operand-a": 0x09,
    "operand-b": 0x0A,
}
RTABLE = {v: k for k, v in TABLE.items()}


def enc_header(name, value):
    v = value.encode()
    key = name.lower()
    if key in TABLE:
        return bytes([TABLE[key]]) + struct.pack(">H", len(v)) + v
    n = name.encode()
    if len(n) > 255:
        raise ValueError("header name too long")
    return bytes([0x00, len(n)]) + n + struct.pack(">H", len(v)) + v


def enc_block(pairs):
    out = struct.pack(">H", len(pairs))
    for k, v in pairs:
        out += enc_header(k, v)
    return out


def dec_block(buf):
    """Decode header block at buf[0:]. Returns (list[(name,value)], bytes_consumed)."""
    if len(buf) < 2:
        raise ValueError("truncated block count")
    (count,) = struct.unpack(">H", buf[0:2])
    pos = 2
    out = []
    for _ in range(count):
        if pos >= len(buf):
            raise ValueError("truncated header id")
        hid = buf[pos]
        pos += 1
        if hid == 0x00:
            if pos >= len(buf):
                raise ValueError("truncated literal name len")
            nl = buf[pos]
            pos += 1
            if len(buf) < pos + nl + 2:
                raise ValueError("truncated literal name/value")
            name = buf[pos:pos + nl].decode("utf-8")
            pos += nl
            (vl,) = struct.unpack(">H", buf[pos:pos + 2])
            pos += 2
            if len(buf) < pos + vl:
                raise ValueError("truncated literal value")
            out.append((name, buf[pos:pos + vl].decode("utf-8")))
            pos += vl
        elif hid == 0xFF or hid not in RTABLE:
            raise ValueError(f"unknown indexed header id {hid:#x}")
        else:
            if len(buf) < pos + 2:
                raise ValueError("truncated value len")
            (vl,) = struct.unpack(">H", buf[pos:pos + 2])
            pos += 2
            if len(buf) < pos + vl:
                raise ValueError("truncated value")
            out.append((RTABLE[hid], buf[pos:pos + vl].decode("utf-8")))
            pos += vl
    return out, pos


def enc_frame(ftype, flags, code, stream_id, payload):
    if stream_id & 0x80000000:
        raise ValueError("stream reserved bit must be 0")
    if len(payload) > 0xFFFFFF:
        raise ValueError("payload too large")
    return (len(payload).to_bytes(3, "big") + bytes([ftype, flags])
            + struct.pack(">H", code) + struct.pack(">I", stream_id) + payload)


def hexdump(label, data):
    import sys
    print(f"--- {label} ({len(data)} bytes) ---", file=sys.stderr)
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        print(f"{i:04x}  {chunk.hex(' '):<48}  |{''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)}|",
              file=sys.stderr)


class Conn:
    """Buffered frame reader: never loses pipelined bytes after LENGTH."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = bytearray()
        self.skipped = 0

    def _fill(self, need):
        while len(self.buf) < need:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("peer closed")
            self.buf.extend(chunk)

    def read_raw_frame(self):
        """Return next frame WITHOUT skipping unknown types."""
        self._fill(HDR_LEN)
        ln = int.from_bytes(self.buf[0:3], "big")
        ftype, flags = self.buf[3], self.buf[4]
        code = struct.unpack(">H", self.buf[5:7])[0]
        raw_sid = struct.unpack(">I", self.buf[7:11])[0]
        if raw_sid & 0x80000000:
            raise ValueError("stream reserved bit set")
        self._fill(HDR_LEN + ln)
        payload = bytes(self.buf[HDR_LEN:HDR_LEN + ln])
        del self.buf[:HDR_LEN + ln]
        return ftype, flags, code, raw_sid, payload

    def read_frame(self):
        """Return next KNOWN frame, silently skipping unknown types via LENGTH."""
        while True:
            ftype, flags, code, raw_sid, payload = self.read_raw_frame()
            if ftype not in KNOWN:
                self.skipped += 1  # MUST skip, not error
                continue
            return ftype, flags, code, raw_sid, payload
