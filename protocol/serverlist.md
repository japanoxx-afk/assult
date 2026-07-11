# Server List protocol (SelectServer.dll, loaded by Assault.dat)

Port: TCP 10525 (System.ini [ServerList])
Same framing as autopatch:  F1 | len:2 LE | opcode:2 | data | F2
Data starts at frame offset 5; data length = framelen - 6.

Request (captured, SendServerInfo @0x10001660):
    f1 08 00 01 01 00 00 f2     opcode 0x101, param word=0

Response: opcode 0x101 -> SelectServer.dll msg handler 0x10001500 parses data:
    data[0]       = flag byte (al)
    data[1..2]    = word (bx)            ; count/id
    data[3..]     = string1 (strcpy, null-terminated)
    string2 @ esi + strlen(string1) + 4  ; NOTE the +4 gap, not +1
    -> Assault.dat callback vtable[+8](string1, X, word, string2)

Assault.dat parses a server entry via sscanf:
    "%d %s %s 1 %s %d 0"   == id name pass 1 IP port 0
  (also seen: "%d noname nopass 0 %s %d 0", "%d %s %s 1 %s %s 1")
After server pick, Assault.dat launches:  main.dat <args>  (formats "main.dat %s", "%smain.dat")

## STATUS — SOLVED and verified live (2026-07-10)
SelectServer.dll 0x10001500 passes BOTH strings + a flag + a word to Assault.dat's
callback: `callback(string1, flag, word, string2)`, with `string2` at
`data + strlen(string1) + 4` (the byte after string1's null). The reply payload is:

    [flag:1] [count:2 LE] [string1\0] [string2\0]

Reply shape that actually works (found by live A/B testing — screenshot + process
survival, since a wrong shape makes Assault.dat crash at 0x302030 and the launcher
relaunches, looking like an "empty list + instant exit"):

  * `string1` must be **EMPTY**; the server entry goes in **`string2`**.
    (Putting the entry in string1 crashes/rejects — the shell exits.)
  * `flag` byte = the **capacity** shown in the "이용상태" column:
    `0` -> "좋음" (connectable);  `1` -> "사용자많음" -> Connect is REFUSED
    with a "사용자가 너무 많습니다" message box. Use **flag=0**.
  * `count` word = 1.
  * entry grammar (Assault.dat sprintf/sscanf `"%d %s %s 1 %s %d 0"`):
    `id name pass 1 IP port 0`  e.g. `1 Assault nopass 1 127.0.0.1 9010 0`.

With this, the server row appears as "좋음" and clicking **Connect** is accepted:
Assault.dat writes the pick into `System.ini [System Config] Server Name=` and
CreateProcessA's `main.dat <server-info>`, then the shell exits.

Implemented in `assault_server.py` (`reply_serverlist`, `SERVER_FLAG=0`).

## NEXT BLOCKER — main.dat exits before login (client-side, not protocol)
`main.dat` (the real game exe) exits cleanly and instantly on launch — **before**
loading any module DLL, before DirectDraw init, before writing its own
`AssaultLogFile.txt` — both standalone and via the real Connect flow. So login
(BillingNet :10905) is never reached. Two client-side problems, both outside the
server emulation:
  1. An early startup guard in main.dat's InitInstance (uses OpenFileMappingA /
     shared memory; likely a launch-token / single-instance / parent check that
     the modern-hardware launch race or standalone launch doesn't satisfy).
  2. This install's `Dlls\` is **incomplete**: main.dat loads `Dlls\4.dat`
     (and the folder is also missing 2,5,6,7,8,9,10.dat). `Dlls\4.dat` does not
     exist here, so even past the guard it would fail with "4.dat dll Load failure".
Resolving these needs the complete original game files and/or reversing main.dat's
InitInstance guard — tracked separately from the server work.
