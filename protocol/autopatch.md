# AutoPatch protocol (AutoPatch.dll)

Ports (discovered via pktmon loopback, passed as args not in ini):
- TCP 10131 : control channel, CLIENT speaks first
- ~~TCP 28194 : data/file transfer~~ — WRONG. A live run showed 28194 traffic is
  Streamlabs Desktop's JSON-RPC API (`getScenes`/`ScenesService`), an unrelated
  app, not the game. When CheckVersion says "up to date" no data channel is used.

Frame:  F1 [len:2 LE, includes both markers] [payload...] F2
Dispatcher @0x10001290: opcode = word at byte offset 3 (LE).

Opcodes (server -> client, parsed by client):
- 0x0101  file metadata: byte[5]=flag, dword[6]=size, dword[0xA]=?, dword[0xE]=?, filename string @ [0x12]
- 0x0102  data/text block: copies (len-6) bytes from [5] into 0x100030da, len->0x100030d8
- 0x0103  status: byte[5] -> global 0x100030d0, then call 0x10001390

Captured client->server first packet (opcode 0x0101 = CheckVersion):
  f1 10 00 01 01 07 00 5b 06 00 00 00 00 00 00 f2
  len=0x0010(16), opcode=0x0101, 07 00, version=0x065b(1627), zeros

Launcher (Assault.exe) AutoPatch.dll call sequence:
  AutoPatchHostToIP -> AutoPatchConnect -> InitDll -> SendCheckVersion ->
  RecvCheckVersion -> SendPatchRequirement -> RecvPatchRequirement/RecvPatchComplete
  -> (on up-to-date) set Patch.ini Status, launch game.

TODO: determine status byte[5] value for "up to date" (analyze 0x10001390) and
the RecvPatchComplete handshake, then build responder.py.
