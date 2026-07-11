# Assault wire framing (shared by all TCP protocols)

Verified identical in AutoPatch.dll, SelectServer.dll and BillingNet.dll:

    F1 | len:2 LE | opcode:2 LE | payload[len-6] | F2

- `F1` (0xF1) start marker, `F2` (0xF2) end marker.
- `len` = total frame size **including** both markers  (= 6 + len(payload)).
- `opcode` at frame offset 3 (little-endian word).
- `payload` at frame offset 5, length `len-6`.

Receivers accumulate bytes and extract frames only once `buffered >= len`
(confirmed in BillingNet.dll frame extractor @0x10002400). The request opcode
seen so far for AutoPatch CheckVersion, Server List request and Login is all
`0x0101`; direction/context disambiguates them, not the opcode.

`assault_server.py` implements this as `build_frame(opcode, payload)` /
`parse_frames(buf)`; both are round-trip tested against the live captures
(`captures/`) and reproduce the recorded bytes exactly.

## Module / server map (from PE exports + Dlls/)

| Stage          | Module (Dlls/ unless noted)     | Transport            |
|----------------|---------------------------------|----------------------|
| AutoPatch      | AutoPatch.dll                   | TCP 10131 / 28194    |
| Server List    | SelectServer.dll                | TCP 10525            |
| Login/Billing  | BillingNet.dll + BillingClientDll.dll | TCP 10905      |
| Round server   | (exe)                           | TCP 9010             |
| Lobby/Match net| 161.dat (NetworkMgrDll*)        | TCP (from list) capture |
| Match modules  | 150-160.dat (MatchGames/Map/Weapon/…) | -              |
| In-game P2P    | AsMulti.dll (AsMultiCreate)     | UDP peer-to-peer     |

`main.dat` is the real game; `Assault.dat` is the shell that shows the server
list and launches `main.dat <selected-server-info>` via CreateProcessA.
