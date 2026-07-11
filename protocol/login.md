# Login / Billing protocol (BillingNet.dll + BillingClientDll.dll)

Modules live in `Dlls/`. `BillingClientDll.dll` is a thin wrapper (exports
`BillingServer_*`, `ManagerServer_*`, `InitDll`, `ChangePointer`) that forwards
to the game's callback; `BillingNet.dll` is the actual socket layer.

## Endpoint
- Server IP: `203.248.248.56` (Billing.ini `[Main] BI=`) -> redirected to 127.0.0.1
- Port: **10905** (`0x2A99`, hard-coded in `BillingNet_Connect` @0x100018e0,
  which calls the net object's connect method with `push 0x2a99`).

## Framing
Same as every other Assault TCP protocol (see `framing.md`):

    F1 | len:2 LE | opcode:2 LE | payload[len-6] | F2

`BillingNet.dll` receive path (verified):
- FD_READ handler @0x100022b0 recv()s into an accumulation buffer at `this+0x44`,
  with the running length in the word at `this+0x2044`.
- Frame extractor @0x10002400 loops while `buffered >= 6`, reads `len` at buf+1,
  waits until `buffered >= len`, reads `opcode` at buf+3, hands
  `dispatch(opcode, payload=buf+5, len-6)` to the registered game callback,
  then consumes `len` bytes.

## Login request  (SendLogIn @0x10001980)
`SendLogIn(type, id, pass)` builds the payload, then the send wrapper adds the
F1/len/F2 frame:

    opcode  = 0x0101
    payload = <type:2 LE> <id\0> <pass\0>

- `type`  : login-type word (kind of login / client type)
- `id`    : account id  (lstrcpyA, null-terminated)
- `pass`  : password    (lstrcpyA, null-terminated)

On the wire, e.g. id="tester" pass="secret" type=2:

    f1 16 00 01 01 02 00 74 65 73 74 65 72 00 73 65 63 72 65 74 00 f2
    F1 |len16| op0101 |type2| t  e  s  t  e  r \0 s  e  c  r  e  t \0 |F2

Other exports: `SendDummy` (keep-alive), `SendForceDisconnect`,
`BillingNet_Disconnect`, `BillingNet_HostToIP`.

## STATUS / open item
The **success-reply opcode + payload is not yet pinned down**. The client-side
handler that decides "login OK -> proceed to lobby" is the game callback
registered through `BillingClientDll`/`main.dat`, not BillingNet.dll, and the
reply also carries the session/token data the next server (lobby) needs. That
has to come from one live capture:

1. redirect.ps1, then `py assault_server.py --verbose`
2. play through: launcher -> server select -> pick Assault-1 -> login screen
3. the login frame (opcode 0x0101 to :10905) is logged with id/pass decoded
4. iterate `LOGIN_OK_OPCODE` / `LOGIN_OK_BODY` in assault_server.py until the
   client leaves the login screen and connects onward (round :9010 / lobby).
