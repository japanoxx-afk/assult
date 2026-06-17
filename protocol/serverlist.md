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

## STATUS
First empirical reply (flag=1,word=1, entry "1 TestServer nopass 1 127.0.0.1 9010 0"
duplicated as string1+string2) was RECEIVED by the client, but Assault.dat then
RST'd the connection -> format mismatch. Suspect the string2 offset (+4 gap, not
immediately after string1's null) and/or the flag/word/string-role mapping.

NEXT: reverse Assault.dat callback (the object whose vtable[+8] is called) to learn
exactly what string1 vs string2 must contain and the count/flag semantics; then
iterate the 10525 reply until the server list populates and main.dat is launched.
