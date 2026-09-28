# MiniBin/1 — Binary Request/Response over TCP

Version 1. Status: draft. Transport: one TCP connection, client speaks first,
frames sent back-to-back; server replies on the same connection (keep-alive).
All integers are unsigned big-endian. Max frame payload is 2²⁴−1 bytes.

## 1. Frame header (11 bytes)

```text
Byte:  0   1   2   3   4   5   6   7   8   9  10
     +---+---+---+---+---+---+---+---+---+---+---+
     |  FRAME_LENGTH |TYPE |FLAGS| METHOD_ | STREAM_ID   |
     |     (24)      |(8)  |(8)  | STATUS  |   (32)      |
     |               |     |     |  (16)   | top bit = 0 |
     +---+---+---+---+---+---+---+---+---+---+---+
```

Wire layout: `LEN(3) | TYPE(1) | FLAGS(1) | CODE(2) | STREAM(4)`, then
exactly `FRAME_LENGTH` payload bytes. A receiver MUST first read 11 bytes,
then read exactly `FRAME_LENGTH` more; pipelined frames stay in the buffer.

| Field | Width | One-line justification |
|---|---|---|
| `FRAME_LENGTH` | 24-bit | Payload size only (excl. header); 16 MiB cap bounds memory yet fits any calculator body, and it is what makes skipping possible. |
| `FRAME_TYPE` | 8-bit | 256 values keep the header tiny while leaving room for future extensions. |
| `FLAGS` | 8-bit | Carries `END_STREAM`/`ACK` without an extra round trip. |
| `METHOD_STATUS` | 16-bit | Dual-use: request method ID vs. response status, disambiguated by `FRAME_TYPE`, so 3-digit statuses fit with no extra bytes. |
| `STREAM_ID` | 31-bit (+1 reserved-zero bit) | Mirrors HTTP/2 multiplexing; demo uses stream 1 sequentially, future versions can interleave. |

Frame types: `0x01 REQUEST`, `0x02 RESPONSE`, `0x03 PING`, `0x04 GOAWAY`;
`0x05–0xFF` are future/unknown. Flags: `0x01 END_STREAM`, `0x08 ACK`
(PING only); senders MUST zero unused bits, receivers MUST ignore them.
`METHOD_STATUS`: on `REQUEST` → `1 GET`, `2 POST`; on `RESPONSE` →
`200/400/404/405`; `0` reserved. `STREAM_ID`: client streams are odd,
increment by 2; `0` is connection-level (PING/GOAWAY).

**Forward-compatibility rule:** a receiver hitting an unknown `FRAME_TYPE`
**MUST skip it via `FRAME_LENGTH` (read and discard exactly that many bytes)
and continue with the next frame — it MUST NOT error or close.** This is the
only way old code stays alive when new frame types appear.

## 2. Header-block encoding

A `REQUEST` payload is a header block; a `RESPONSE` payload is a header
block followed by raw body bytes (split point given by `content-length`).
A block is `COUNT(u16)` then entries. Each entry is one of:

```text
Indexed:  ID(1) != 0x00 | VALUE_LEN(u16) | VALUE bytes
Literal:  0x00 | NAME_LEN(u8) | NAME bytes | VALUE_LEN(u16) | VALUE bytes
```

Static table (single byte on the wire; anything else uses the literal form):

| ID | Name | ID | Name |
|---|---|---|---|
| `0x01` | `host` | `0x06` | `accept` |
| `0x02` | `path` | `0x07` | `user-agent` |
| `0x03` | `content-type` | `0x08` | `operation` |
| `0x04` | `content-length` | `0x09` | `operand-a` |
| `0x05` | `connection` | `0x0A` | `operand-b` |

`0x00` = literal (name + value both length-prefixed); `0xFF` reserved.
Values are always `u16`-prefixed UTF-8; names are case-insensitive and
senders SHOULD use lowercase. Unknown literal names MUST be preserved or
ignored, never treated as framing errors.

## 3. Example (both encodings)

`GET /add?a=2&b=3`, stream 1, `END_STREAM`. Headers: `host: calc.local`
(indexed `0x01`), `path: /add?a=2&b=3` (indexed `0x02`), `operation: add`
(indexed `0x08`), plus custom `X-Trace-ID: abc-123` (**literal `0x00`**).

Header block (57 bytes, `00 04` = 4 headers):

```text
00 04  01 00 0a 63 61 6c 63 2e 6c 6f 63 61 6c  02 00 0c 2f 61 64 64 3f 61
3d 32 26 62 3d 33  08 00 03 61 64 64  00 0a 58 2d 54 72 61 63 65 2d 49 44
00 07 61 62 63 2d 31 32 33
```

Full REQUEST frame (header `00 00 39 01 01 00 01 00 00 00 01`, length 0x39=57):

```text
00 00 39 01 01 00 01 00 00 00 01  00 04 ... (block above)
```

RESPONSE `200`, body `5` (block of 2 indexed headers + 1 body byte, 20 bytes):

```text
00 00 14 02 01 00 c8 00 00 00 01  00 02 03 00 0a 74 65 78 74 2f 70 6c 61
69 6e 04 00 01 31  35
```

i.e. `content-type: text/plain`, `content-length: 1`, body `35` (`"5"`).
A `0x9F` frame with length 4 (`de ad be ef`) between them is discarded by
length and the response still parses — verified by `gen_example.py`.
