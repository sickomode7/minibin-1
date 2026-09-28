# MiniBin/1 — Binary File Service over TCP

Version 1. Status: draft. Application: static file server.
`./bserve ROOT PORT` serves files under `ROOT`;
`./bcurl [-v] host:port/path` fetches one file.
Transport: one TCP connection, client speaks first, frames sent
back-to-back; the server replies on the same connection (keep-alive).
All integers are unsigned big-endian.

## 1. Frame header (11 bytes, fixed)

```text
Byte:  0   1   2   3   4   5   6   7   8   9  10
     +---+---+---+---+---+---+---+---+---+---+---+
     |  FRAME_LENGTH |TYPE |FLAGS| METHOD_ | STREAM_ID   |
     |     (24)      |(8)  |(8)  | STATUS  |   (32)      |
     |               |     |     |  (16)   | top bit = 0 |
     +---+---+---+---+---+---+---+---+---+---+---+
```

Wire layout: `LEN(3) | TYPE(1) | FLAGS(1) | CODE(2) | STREAM(4)`,
then exactly `FRAME_LENGTH` payload bytes. `FRAME_LENGTH` counts
**payload bytes only, never the 11-byte header**. A receiver MUST
first read 11 bytes, then read exactly `FRAME_LENGTH` more;
pipelined frames stay in the buffer (`Conn` in `minibin.py`).

| Field | Width | Justification |
|---|---|---|
| `FRAME_LENGTH` | 24-bit | Payload size only. A 24-bit length permits payloads up to 2²⁴−1 bytes (16,777,215, just under 16 MiB) while keeping the fixed header compact — large enough for any file chunk this server sends, small enough to bound receiver buffers. It is also what makes skipping possible. |
| `FRAME_TYPE` | 8-bit | 256 values keep the header tiny while leaving room for future extensions. |
| `FLAGS` | 8-bit | Carries `END_STREAM`/`ACK` without an extra round trip. |
| `METHOD_STATUS` | 16-bit | Dual-use: request method ID vs. response status, disambiguated by `FRAME_TYPE`, so 3-digit statuses fit with no extra bytes. |
| `STREAM_ID` | 31-bit (+1 reserved-zero bit) | Client streams are odd and increment by 2; `0` is connection-level. The demo uses stream 1, then 3. Sequential use only — concurrent/interleaved multiplexing is reserved for a future version. |

Frame types: `0x01 REQUEST`, `0x02 RESPONSE`, `0x03 PING`, `0x04 GOAWAY`;
`0x05–0xFF` are future/unknown. Flags: `0x01 END_STREAM`,
`0x08 ACK` (PING only); senders MUST zero unused bits, receivers
MUST ignore them.
`METHOD_STATUS`: on `REQUEST` → `0x0001 GET` (supported);
`0x0002` is RESERVED for a future method (the current server
replies `405` to it); any other value → `400`.
On `RESPONSE` → `200 OK`, `400 Bad Request`, `404 Not Found`,
`405 Method Not Allowed`; `0` reserved.
`STREAM_ID`: response echoes the request stream ID; high bit MUST
be 0 on send — a set high bit is a framing error.

**Forward-compatibility rule:** a receiver meeting an unknown
`FRAME_TYPE` **MUST read and discard exactly `FRAME_LENGTH`
payload bytes and continue with the next frame — it MUST NOT
error or close the TCP connection solely because the type is
unknown.** This is how room is left for a version 2.

## 2. Header-block encoding

A `REQUEST` payload is a header block; a `RESPONSE` payload is a
header block followed by exactly `content-length` raw body bytes
(split point given by the `content-length` header value).
A block is `COUNT(u16)` then entries. Each entry is one of:

```text
Indexed:  ID(1) != 0x00 | VALUE_LEN(u16) | VALUE bytes
Literal:  0x00 | NAME_LEN(u8) | NAME bytes | VALUE_LEN(u16) | VALUE bytes
```

Static table (single byte on the wire; anything else uses the literal form).
Only a subset is sent by the current programs (see §3); the rest are
defined IDs available to senders and future versions:

| ID | Name | Sent today by | ID | Name | Sent today by |
|---|---|---|---|---|---|
| `0x01` | `host` | client | `0x06` | `accept` | — (reserved for negotiation) |
| `0x02` | `path` | client | `0x07` | `user-agent` | client |
| `0x03` | `content-type` | server | `0x08` | `server` | — (future response header) |
| `0x04` | `content-length` | server | `0x09` | `cache-control` | — (future) |
| `0x05` | `connection` | client | `0x0A` | `content-encoding` | — (future) |

`0x00` = literal (name + value both length-prefixed); `0xFF`
reserved and MUST NOT be sent. Values are always `u16`-prefixed
UTF-8; names are case-insensitive and senders SHOULD use lowercase.
An unknown *indexed* ID is a malformed block (→ `400`, §5);
unknown *literal* names MUST be preserved or ignored, never
treated as framing errors.

## 3. File-service semantics (`./bserve ROOT PORT`)

A request carries `path`, e.g. `path: /hello.txt` against
`./bserve ./www 9000` maps to `ROOT/hello.txt`
(`./www/hello.txt`; `GET /index.html` → `./www/index.html`).
Mapping: strip query (`?...`) and fragment (`#...`), percent-decode,
strip leading `/`, resolve against `ROOT`. A request MUST NOT escape
the root: after resolving, the target MUST still be under `ROOT`
(checked with `relative_to`); `/../secret` or `/../../etc/passwd`
therefore yield `400`. Only regular files are served; directories
and missing names yield `404`. The body is the raw file bytes;
`content-type` is guessed from the suffix
(`application/octet-stream` fallback).

## 4. Canonical example (byte-identical to `ANNOTATION.md`)

`GET /hello.txt`, stream 1, `END_STREAM`. Headers:
`host: 127.0.0.1:18081` (`0x01`), `path: /hello.txt` (`0x02`),
`user-agent: miniburl/1` (`0x07`), `connection: keep-alive`
(`0x05`). Header block 59 bytes (`00 04` = 4 headers); full frame
70 bytes (header `00 00 3b 01 01 00 01 00 00 00 01`, length 0x3b=59):

```text
00 00 3b 01 01 00 01 00 00 00 01 00 04 01 00 0f 31 32 37 2e 30 2e 30 2e 31
3a 31 38 30 38 31 02 00 0a 2f 68 65 6c 6c 6f 2e 74 78 74 07 00 0a 6d 69 6e
69 62 75 72 6c 2f 31 05 00 0a 6b 65 65 70 2d 61 6c 69 76 65
```

RESPONSE `200`, `content-type: text/plain`, `content-length: 14`,
body `hello minibin\n` (34-byte payload, 45 bytes on the wire,
header `00 00 22 02 01 00 c8 00 00 00 01`):

```text
00 00 22 02 01 00 c8 00 00 00 01 00 02 03 00 0a 74 65 78 74 2f 70 6c 61 69
6e 04 00 02 31 34 68 65 6c 6c 6f 20 6d 69 6e 69 62 69 6e 0a
```

RESPONSE payload = encoded header block followed by exactly
`content-length` raw body bytes. A `0x9F` frame with length 4
(`de ad be ef`) between them is discarded by length and the
response still parses — the same bytes `test_skip.py` sends.

## 5. Errors, streams, and the connection

Error semantics (per `bserve.py`): malformed request payload →
`400` (truncated block, entry running past `FRAME_LENGTH`,
trailing bytes after the block, unknown indexed ID, missing `path`
or not starting with `/`, root escape, method code outside
`{1, 2}`); missing file → `404`; method code `2` (reserved) →
`405`. An *unrecoverable frame-header* error — set reserved stream
bit, peer close mid-header, or any state where frame boundaries
cannot be trusted — closes the TCP connection *without* a `400`,
because no stream ID can be addressed safely.
`END_STREAM (0x01)` terminates the logical request/response
stream; it does NOT close TCP. One connection carries
`REQUEST(1) → RESPONSE(1) → REQUEST(3) → RESPONSE(3) …`.
The client speaks first, sends requests back-to-back on its single
socket, and never opens a second connection; the server keeps the
socket open after each exchange. The `connection: keep-alive`
header is informational — persistence is a transport rule, not
negotiated per response.
