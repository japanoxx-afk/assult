# Assault (CodiNET) Private Server

Reviving the dead **Assault** online game (CodiNET, 2001–2003) by emulating its
servers. The client is a Winsock client-server app whose server addresses live
in `.ini` files, so we redirect it to `127.0.0.1` (no binary patch) and answer
the protocols we have reversed from the client DLLs + live captures.

Game install: `C:\Program Files (x86)\CodiNET\Assault`

## Quick start (run as Administrator)

```powershell
.\redirect.ps1                 # point client -> 127.0.0.1 (backs up ini + hosts)
py assault_server.py --verbose # emulator: answers known protocols, logs the rest
#  ... launch the game (Assault.exe), play through ...
.\redirect.ps1 -Restore        # undo when done
```

`assault_server.py` is the single consolidated emulator. `capture_server.py` +
`responder.py` are the older capture harness, kept for reference.

## Boot chain & status

| Stage        | Endpoint          | Module                | Status |
|--------------|-------------------|-----------------------|--------|
| AutoPatch    | TCP 10131         | AutoPatch.dll         | ✅ bypassed ("up to date") |
| Server List  | TCP 10525         | SelectServer.dll      | ✅ **verified live** — server shows "좋음", Connect accepted |
| (game launch)| —                 | Assault.dat→main.dat  | ⛔ main.dat crashes (0xC0000005, DirectDraw) on launch — see below |
| **Login**    | TCP **10905**     | BillingNet.dll        | ◑ request fully decoded; blocked upstream by main.dat |
| Round        | TCP 9010          | (exe)                 | ▫ listening + logging (capture target) |
| Lobby/Match  | TCP (from list)   | 161.dat NetworkMgrDll | ▫ capture target |
| In-game sync | UDP peer-to-peer  | AsMulti.dll           | ▫ not started |

### Verified server-list reply (the fix for "empty list / exits at server select")
Reply payload = `[flag:1][count:2][string1\0][string2\0]` where **string1 is empty,
the entry is in string2, and flag=0** ("좋음", connectable — flag=1 shows
"사용자많음" and Connect is refused). Entry = `id name pass 1 IP port 0`. With this
the server appears and Connect launches `main.dat`. See `protocol/serverlist.md`.

### ✅ Login → multiplayer lobby WORKS (2026-07-11)
`play.ps1` launches the game to the in-game **lobby/room** (character select, team
mode, map pick, start). Three fixes made it work:
1. **DDrawCompat** `ddraw.dll` (copied from Red Alert II, ~2.8MB) in the game root —
   provides the Direct3D7 HAL main.dat needs on Win11. cnc-ddraw (2D only) does not.
2. **Bypass Assault.dat, launch `main.dat` directly** with a clean 7-token arg
   `main.dat 1 <user> <pass> 1 <ip> <port> 0`. main.dat requires `argc==8`; Assault.dat's
   Connect mangles the arg (11+ tokens, truncated IP) → "Wrong parameter".
3. **Single-core CPU affinity** — dodges a fast-multicore DirectDraw startup crash.

The emulator's round-server handler (`reply_round`, TCP 11131) PONGs the 0x0704
heartbeat and zero-fills every other reply (`ROUND_PAD=64`). Those zeros give the
client valid *empty* structs instead of garbage, so the game navigates the whole
menu flow — **login → character select (전적 0승 0패 0끊김, initialized) → room list
→ in-room lobby (your own slot filled)** — all rendering.

Remaining for full play: the connection still drops (`접속이 끊겼습니다`) at ~60s and
player slots for *other* users / battle start need 161.dat's real per-opcode room
protocol reversed (zero-fill only fakes empty state), then the match server +
AsMulti.dll UDP P2P for the actual in-game battle. Within the ~60s window you can
navigate the menus by clicking directly (the game is fullscreen via DDrawCompat).

Run it:  `.\redirect.ps1` (once, admin) then `.\play.ps1`.

### (historical) main.dat crashed on launch ("Connect does nothing")
Connect **does** launch `main.dat` (Assault.dat reads the install path from
`HKLM\SOFTWARE\CodiNET\Assault\InstallDir` — correct here). But `main.dat` then
**crashes with 0xC0000005 (access violation)** deterministically at
`98.dat+0x1cc76`: it dereferences the global IDirectDraw7 object (`0x100596c8`)
which is **NULL** because DirectDraw init fails on modern Win11 hardware. It only
survives under a debugger (debug-heap timing masks it) and even then never reaches
login. So from the user's view "Connect does nothing / no connection log."

Two independent client-side problems block login/play, both outside the server work:
  1. **Win11 DirectDraw crash** in `98.dat` (DrawDll7). Needs a DirectDraw
     compatibility layer (e.g. cnc-ddraw / DDrawCompat, with config tuning) or an
     old-Windows VM; a quick cnc-ddraw drop-in did not fix it by itself.
  2. **Incomplete install**: `main.dat` loads `Dlls\4.dat`, which is **missing**
     here (folder also lacks 2,5-10.dat; `Data\4.DAT` is game data, not the DLL).
Reaching login needs the complete original game files **and** solving the crash.
See `protocol/serverlist.md` and the memory note for the exact fault address.

All TCP protocols share one framing: `F1 | len:2 | opcode:2 | payload | F2`
(see `protocol/framing.md`). Details per stage in `protocol/*.md`.

### What's verified from the binaries
- **Framing** reproduces the live captures byte-for-byte (`build_frame` tested).
- **AutoPatch** CheckVersion → "no patch" reply matches the recorded 20 bytes.
- **Server List** reply format confirmed by disassembling SelectServer.dll
  0x10001500; entry grammar `"%d %s %s 1 %s %d 0"` from Assault.dat.
- **Login** port 10905 (`BillingNet_Connect`), request opcode 0x0101,
  payload `<type:2> <id\0> <pass\0>` (`SendLogIn` @0x10001980).

### The remaining work (needs a live play-test to capture)
The success-reply opcodes for login/lobby, plus the whole lobby (room create/
join/team/ready) and in-game P2P protocols, are driven by `main.dat` + the
numbered `Dlls/*.dat` modules and can only be pinned down by capturing a real
session. `assault_server.py` already listens on and hex-logs those ports, so one
guided play-test through the login screen will reveal the next packets to answer.

## Files
- `assault_server.py` — consolidated emulator (all ports, shared framing, logging)
- `redirect.ps1` — ini/hosts redirect to 127.0.0.1 (`-Restore` to undo)
- `discover.ps1` — pktmon/netstat port discovery for unbound ports
- `protocol/` — per-stage reverse-engineering notes (framing, autopatch, serverlist, login)
- `capture_server.py`, `responder.py` — original capture harness (reference)
- `captures/` — timestamped traffic logs
- `backup/` — original ini files + hosts (created on first redirect)
