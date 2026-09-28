"""Build one deterministic pair for /hello.txt and print hex + annotation tables."""
from minibin import enc_block, enc_frame

BODY = b"hello minibin\n"  # 14 bytes
req_blk = enc_block([("host", "127.0.0.1:18081"), ("path", "/hello.txt"),
                     ("user-agent", "miniburl/1"), ("connection", "keep-alive")])
REQ = enc_frame(0x01, 0x01, 1, 1, req_blk)
resp_blk = enc_block([("content-type", "text/plain"),
                      ("content-length", str(len(BODY)))])
RESP = enc_frame(0x02, 0x01, 200, 1, resp_blk + BODY)

print("REQUEST_HEX:", REQ.hex(" "))
print("RESPONSE_HEX:", RESP.hex(" "))

# Offsets computed from construction (request block layout is deterministic).
# Request: count(2B) + host(1+2+15) + path(1+2+10) + ua(1+2+10) + conn(1+2+10)
import struct
rows = [("0-2", REQ[0:3].hex(" "), "FRAME_LENGTH = payload len"),
        ("3", f"{REQ[3]:#04x}", "FRAME_TYPE = 0x01 REQUEST"),
        ("4", f"{REQ[4]:#04x}", "FLAGS = 0x01 END_STREAM"),
        ("5-6", REQ[5:7].hex(" "), "METHOD_STATUS = 1 (GET)"),
        ("7-10", REQ[10-3:11].hex(" "), "STREAM_ID = 1 (top bit 0)"),
        ("11-12", req_blk[0:2].hex(" "), "COUNT = 4 headers")]
pos = 2
for name, val in [("host", "127.0.0.1:18081"), ("path", "/hello.txt"),
                  ("user-agent", "miniburl/1"), ("connection", "keep-alive")]:
    start = 11 + pos
    hid_len = 1 + 2 + len(val)
    rows.append((f"{start}-{start+hid_len-1}", req_blk[pos:pos+hid_len].hex(" "),
                 f"indexed hdr {name}={val!r}"))
    pos += hid_len
print("\nREQUEST ANNOTATION (offsets include 11B frame header):")
for r in rows:
    print("| " + " | ".join(r) + " |")
print("total request bytes:", len(REQ), "= 11 header +", len(req_blk), "payload")

rrows = [("0-2", RESP[0:3].hex(" "), "FRAME_LENGTH"),
         ("3", f"{RESP[3]:#04x}", "FRAME_TYPE = 0x02 RESPONSE"),
         ("4", f"{RESP[4]:#04x}", "FLAGS = END_STREAM"),
         ("5-6", RESP[5:7].hex(" "), "STATUS = 200 (0x00c8)"),
         ("7-10", RESP[7:11].hex(" "), "STREAM_ID = 1")]
base = 11
rrows.append((f"{base}-{base+1}", resp_blk[0:2].hex(" "), "COUNT = 2 headers"))
ct = 1 + 2 + len("text/plain")
rrows.append((f"{base+2}-{base+2+ct-1}", resp_blk[2:2+ct].hex(" "), "content-type=text/plain"))
cl = 1 + 2 + len(str(len(BODY)))
rrows.append((f"{base+2+ct}-{base+2+ct+cl-1}", resp_blk[2+ct:2+ct+cl].hex(" "),
              f"content-length={len(BODY)}"))
rrows.append((f"{base+2+ct+cl}-{len(RESP)-1}", BODY.hex(" "), f"body {BODY!r}"))
print("\nRESPONSE ANNOTATION:")
for r in rrows:
    print("| " + " | ".join(r) + " |")
print("total response bytes:", len(RESP), "= 11 header +", len(resp_blk) + len(BODY), "payload")
