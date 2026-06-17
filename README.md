# Assault (CodiNET) Private Server — Capture Harness

Goal: revive the dead **Assault** online game (CodiNET, 2001–2003) by emulating
its servers. The client is a standard Winsock client-server app, and every
server address is configured in `.ini` files, so we redirect the client to
`127.0.0.1` (no binary patch) and reverse the protocol from live captures.

Game install: `C:\Program Files (x86)\CodiNET\Assault`

## Server map

| Endpoint        | Original                              | Module             | Proto |
|-----------------|---------------------------------------|--------------------|-------|
| AutoPatch       | autopatch.codinet.com / 61.74.201.227 | AutoPatch.dll      | TCP   |
| Billing / Login | 203.248.248.56                        | AssaultCommon.dll  | UDP   |
| Server List     | 203.248.248.54:10525                  | SelectServer.dll   | TCP   |
| Round Server    | 203.248.248.58:9010                   | (exe)              | TCP   |
| Match / Lobby   | (from server list)                    | AsMClient.dll      | TCP   |
| In-game sync    | (from match)                          | AsMulti.dll        | UDP   |

`AsMClient.dll` kept clean symbols: `ProcessMServerRoomEnter`,
`RoomOpen/CloseSlotUser`, `RoomTeamChange`, `RoomPCList`, `OnPacket` — the
lobby protocol is room/slot/team based.

> `Assault.exe` is the **autopatch launcher**, not the game. It patches, then
> runs the real game. Bypassing autopatch may be needed to reach login fast.

## Workflow

All commands run **as Administrator** (hosts file + pktmon need it).

```powershell
# 1. Redirect client -> localhost (backs up ini + hosts first)
.\redirect.ps1

# 2a. Start the capture listeners on known ports
py capture_server.py --tcp 10525,9010

# 2b. (other terminal) discover unknown ports while you play
.\discover.ps1 -Watch        # live TCP connection attempts
#   or full packet capture (TCP+UDP incl. loopback):
.\discover.ps1 -Start ; <run game> ; .\discover.ps1 -Stop

# 3. Launch the game, watch captures\capture_*.log fill with hex dumps.

# 4. As you discover ports, add them:
py capture_server.py --tcp 10525,9010,<new> --udp <billing>,<game>

# 5. Once a handshake is understood, write a responder module and load it:
py capture_server.py --tcp 10525,9010 --reply responder.py

# Undo everything (restore ini + hosts):
.\redirect.ps1 -Restore
```

A responder module defines optional functions:
```python
def tcp_reply(port, peer, data): ...   # return bytes or None
def udp_reply(port, peer, data): ...
```

## Reversing order (easiest → hardest)

1. **AutoPatch** — make it report "no patch / up to date" so the game launches.
2. **Login** — accept any credentials, return success.
3. **Server List** — return one game server pointing back at us.
4. **Match/Lobby** — room create/join/slot/team (symbols help a lot here).
5. **In-game UDP sync** — the real work; capture two clients to diff packets.

## Files

- `capture_server.py` — multi-port TCP/UDP sink + hex logger + optional responder
- `redirect.ps1` — ini/hosts redirect to 127.0.0.1 (`-Restore` to undo)
- `discover.ps1` — `-Watch` (netstat) / `-Start`/`-Stop` (pktmon) port discovery
- `backup/` — originals of the ini files + hosts (created on first redirect)
- `captures/` — timestamped capture logs
