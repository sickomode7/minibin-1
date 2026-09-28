# network_architecture_assignment

Two-part networking assignment: a keep-alive HTTP/1.1 calculator on raw TCP sockets, then a custom binary request/response protocol (MiniBin/1) in the spirit of HTTP/2.

## Part 1 — calculator (`server.py`)

Bare TCP socket server, no HTTP framework. Routes `GET /add|/sub|/mul|/div?a=&b=`,
`400` on bad input / missing `Host` / div-by-zero, `404` unknown path, `405` non-GET.
One request per read via `\r\n\r\n` buffering — never reads into the next request's bytes.

```sh
python server.py            # serves 127.0.0.1:18080
python test_server.py       # functional + pipelining tests
python client_keepalive.py  # one socket, back-to-back requests, 1 handshake proof
```

## Part 2 — MiniBin/1 binary protocol

11-byte frame header (`FRAME_LENGTH 24 / TYPE 8 / FLAGS 8 / METHOD_STATUS 16 / STREAM_ID 31`),
10 single-byte header IDs with length-prefixed literals, unknown frame types skipped via length.

```sh
python bserve.py www 18081                  # static file server, keep-alive
python bcurl.py -v 127.0.0.1:18081/index.html
python test_skip.py                         # unknown-frame skip test
python annotate.py                          # annotated hex capture
```

## Hand-in docs

- `PROTOCOL.md` — the 2-page spec (fields, widths, header table, example)
- `ANNOTATION.md` — annotated hexdump of one full request/response pair
