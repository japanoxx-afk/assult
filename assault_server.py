#!/usr/bin/env python3
"""
Assault (CodiNET, 2001-2003) private-server emulator.

Single-process emulator for the whole known client->server chain. Every CodiNET
server IP is redirected to 127.0.0.1 (see redirect.ps1), so the client connects
here. This file both ANSWERS the protocols we have reversed and LOGS everything
else so the remaining protocols can be captured during a live play-test.

Run (as Administrator, after redirect.ps1):

    py assault_server.py                 # all known ports
    py assault_server.py --verbose       # + full hex dumps of every packet

Shared wire framing (verified from AutoPatch.dll, SelectServer.dll, BillingNet.dll):

    F1 | len:2 LE | opcode:2 LE | payload[len-6] | F2
      - len   = total frame size INCLUDING the F1/F2 markers (= 6 + len(payload))
      - opcode lives at frame offset 3
      - payload starts at frame offset 5, length = len-6

Endpoint map (see protocol/ for the disassembly notes):

    TCP 10131  AutoPatch control   AutoPatch.dll     opcode 0x0101 CheckVersion
    TCP 28194  AutoPatch data      AutoPatch.dll     (idle when up-to-date)
    TCP 10525  Server List         SelectServer.dll  opcode 0x0101 -> entry list
    TCP 10905  Login / Billing     BillingNet.dll    opcode 0x0101 SendLogIn
    TCP  9010  Round server        (exe)             <-- capture target
    TCP  9011+ Lobby / NetworkMgr   161.dat           <-- capture target
"""
import argparse, datetime, os, socket, struct, threading, time as _time

F1, F2 = 0xF1, 0xF2
LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
os.makedirs(LOGDIR, exist_ok=True)
LOGFILE = os.path.join(LOGDIR, "server_" +
                       datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
_lock = threading.Lock()
VERBOSE = False

# ---------------------------------------------------------------- logging -----
def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

def _hex(data, indent="    "):
    out = []
    for i in range(0, len(data), 16):
        c = data[i:i + 16]
        h = " ".join(f"{b:02x}" for b in c)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        out.append(f"{indent}{i:04x}  {h:<47}  |{a}|")
    return "\n".join(out)

def log(tag, msg, data=None, force_hex=False):
    line = f"[{_ts()}] {tag} {msg}"
    if data is not None:
        line += f"  ({len(data)} bytes)"
        if VERBOSE or force_hex:
            line += "\n" + _hex(data)
    with _lock:
        print(line, flush=True)
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# ---------------------------------------------------------------- framing -----
def build_frame(opcode, payload=b""):
    total = 6 + len(payload)                       # F1 + len(2) + op(2) + data + F2
    return bytes([F1]) + struct.pack("<H", total) + struct.pack("<H", opcode) \
        + payload + bytes([F2])

def parse_frames(buf):
    """Yield (opcode, payload, whole_frame). Tolerates a leading F1 or not."""
    i, out = 0, []
    while i + 5 <= len(buf):
        if buf[i] != F1:            # resync to next marker
            nxt = buf.find(bytes([F1]), i + 1)
            if nxt < 0:
                break
            i = nxt
            continue
        total = struct.unpack_from("<H", buf, i + 1)[0]
        if total < 6 or i + total > len(buf):
            break                    # incomplete frame, wait for more bytes
        op = struct.unpack_from("<H", buf, i + 3)[0]
        payload = buf[i + 5:i + total - 1]
        out.append((op, payload, buf[i:i + total]))
        i += total
    return out

def cstr(payload, off=0):
    end = payload.find(b"\x00", off)
    if end < 0:
        end = len(payload)
    return payload[off:end], end + 1

# ------------------------------------------------------- protocol responders --
def reply_autopatch(payload, opcode):
    """AutoPatch control (10131). Report 'up to date' so the launcher proceeds.

    Client CheckVersion:  opcode 0x0101, payload = 07 00 <ver:2> 00..
    Reply mirrors the captured 20-byte 'no patch needed' frame.
    """
    if opcode == 0x0101:
        # flag=0 (up to date) + echo version dword + padding (matches capture)
        ver = struct.unpack_from("<H", payload, 2)[0] if len(payload) >= 4 else 0
        body = bytes([0x00]) + struct.pack("<H", ver) + b"\x00" * 11
        return build_frame(0x0101, body)
    # any other opcode -> status 0x0103 ok
    return build_frame(0x0103, b"\x00")

# --- Server List (10525) ------------------------------------------------------
# SelectServer.dll 0x10001500 parses the reply payload as:
#     [0]      flag byte
#     [1..2]   count word
#     [3..]    string1 (lstrcpyA, null-terminated)
#     string2  immediately follows string1's null terminator
# Assault.dat's callback keeps entries whose text starts with "1 " and treats an
# empty string as end-of-list. Entry grammar (sprintf/sscanf in Assault.dat):
#     "%d %s %s 1 %s %d 0"  ==  id  name  pass  1  IP  port  0
# The picked entry's IP/port is what main.dat is launched against.
# Server entry grammar (Assault.dat sscanf "%d %s %s 1 %s %d 0"):
#   id  name  pass  1  IP  port  0
# Confirmed live: this reply populates the "AssaultServerList" dialog with a row.
SERVER_ID   = 1
SERVER_NAME = "Assault"
SERVER_IP   = "127.0.0.1"
# Assault.dat's Connect handler HARDCODES the round-server port to 0x2b7b=11131
# in its main.dat cmdline builders (sprintf @0x401d78/@0x401db5, both push
# 0x2b7b regardless of what port is in the list entry) -- so whatever port we
# advertise here is overwritten anyway. Match it so the client actually reaches us.
SERVER_PORT = 11131
SERVER_FLAG = 0            # 0 = "좋음" (connectable); 1 = "사용자많음" (refused)

def reply_serverlist(payload, opcode):
    if opcode != 0x0101:
        return None
    entry = f"{SERVER_ID} {SERVER_NAME} nopass 1 {SERVER_IP} {SERVER_PORT} 0".encode("ascii")
    # CONFIRMED LIVE: string1 must be EMPTY and the server entry goes in string2.
    # (SelectServer.dll passes both strings to Assault.dat's callback; putting the
    #  entry in string1 makes the shell reject the list and exit — string2 is the
    #  slot the client keeps.) flag=1, count=1.
    # flag byte = capacity/usage status shown in the "이용상태" column:
    #   0 -> "좋음" (good, connectable),  1 -> "사용자많음" (full -> connect refused).
    # CONFIRMED LIVE: flag=0 + string1 empty + entry in string2 lets Connect through.
    flag, word = SERVER_FLAG, 1
    # Optional control file for live A/B testing of the string1/string2 split
    # (Connect mangles the cmdline when string2 contains spaces -- see notes).
    variant = "0"
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sl2_variant.txt")) as f:
            variant = f.read().strip() or "0"
    except OSError:
        pass
    ip_only = SERVER_IP.encode("ascii")
    if variant == "1":
        s1, s2 = entry, ip_only          # entry in string1 (display), plain ip in string2
    elif variant == "2":
        s1, s2 = entry, b""
    elif variant == "3":
        s1, s2 = ip_only, entry
    elif variant == "4":
        s1, s2 = ip_only, ip_only
    else:
        s1, s2 = b"", entry              # baseline (current known-working display)
    body = bytes([flag & 0xFF]) + struct.pack("<H", word)   # flag, count
    body += s1 + b"\x00"
    body += s2 + b"\x00"
    log("SERVERLIST", f"flag={flag} entry: {entry.decode()}")
    return build_frame(0x0101, body)

# --- Login / Billing (10905) --------------------------------------------------
# BillingNet.dll SendLogIn builds:  opcode 0x0101, payload = <type:2> <id\0> <pass\0>
# The exact success-reply opcode/flags live in main.dat's billing callback and
# still need one live capture to pin down. We accept any credentials and answer
# with an echo-success frame; tweak LOGIN_OK_* below against the live client.
LOGIN_OK_OPCODE = 0x0101
LOGIN_OK_BODY   = bytes([0x00, 0x00])   # placeholder success flag/word

def reply_login(payload, opcode):
    if opcode == 0x0101 and len(payload) >= 2:
        ltype = struct.unpack_from("<H", payload, 0)[0]
        uid, nxt = cstr(payload, 2)
        pw, _ = cstr(payload, nxt)
        log("LOGIN", f"type={ltype} id={uid.decode('latin1')!r} "
                     f"pass={pw.decode('latin1')!r}  -> accept (best-effort)")
        return build_frame(LOGIN_OK_OPCODE, LOGIN_OK_BODY)
    return None

# --- Round / Assault Server (11131) -------------------------------------------
# main.dat (via 161.dat NetworkMgr) connects here after picking a server and
# registers with opcode 0x0501 carrying its own IP. Same F1|len|op|payload|F2
# framing. Reverse-engineering the exact reply set by watching what main.dat
# sends next after each ack.
# Reply strategy that reaches the game LOBBY with the player's own slot filled and
# a clean 0승 0패 0끊김 record (found live):
#   * 0x0704 = heartbeat/ping (payload = a counter byte) -> PONG by echoing the
#     exact payload back. Zero-filling it breaks keepalive -> ~30s disconnect.
#   * every other opcode -> echo the opcode with a ZERO-FILLED payload. The zeros
#     give the client valid (empty) slot/account structs instead of uninitialized
#     garbage, so the record shows 0-0-0 and the user's slot populates.
# ROUND_PAD bytes of zeros is enough to cover those structs.
ROUND_PAD = 64

_round_trace = []   # low-latency in-memory trace: (t, opcode, payloadhex)
def reply_round(payload, opcode):
    if opcode == 0x0704:                       # heartbeat -> pong (must be FAST;
        return build_frame(0x0704, payload)    # a late pong -> client disconnects)
    _round_trace.append((_time.time(), opcode, payload.hex()))
    return build_frame(opcode, bytes(ROUND_PAD))

# ------------------------------------------------------------- port routing ---
# port -> (name, responder or None). None = log only (capture target).
# NOTE: TCP 28194 was previously listed as the autopatch data channel, but a live
# run showed the traffic on it is Streamlabs Desktop's JSON-RPC API (getScenes /
# ScenesService) — an unrelated app on this machine, not the game. Binding it
# would fight Streamlabs, so it is intentionally omitted. When "up to date",
# AutoPatch never needs a data channel and the game proceeds to the server list.
PORTS = {
    10131: ("autopatch-ctl", reply_autopatch),
    10525: ("serverlist",     reply_serverlist),
    10905: ("login",          reply_login),
    11131: ("round",          reply_round), # Assault/round server (161.dat NetworkMgr)
    9011:  ("lobby?",         None),      # capture target (NetworkMgr)
}

def handle_tcp(conn, addr, port, name, responder):
    peer = f"{addr[0]}:{addr[1]}"
    if port in (11131, 9011, 10905):
        log("PROGRESS", f"*** client connected to {name}:{port} <- {peer} "
                        f"(server-list was ACCEPTED) ***")
    log("OPEN", f"{name}:{port} <- {peer}")
    # autopatch-data must not be reaped or the launcher reconnects in a loop
    conn.settimeout(None if responder is None else 300)
    # NOTE: the round/game connection still drops with "접속이 끊겼습니다" after ~60s.
    # Server-initiated 0x0704 keepalives made it WORSE (client doesn't expect them),
    # so we only react to client packets. Beating the 60s wall needs the real
    # room/session protocol reversed from 161.dat (see protocol notes).
    stop_ka = threading.Event()
    buf = b""
    try:
        while True:
            data = conn.recv(65535)
            if not data:
                break
            log("RECV", f"{name}:{port} <- {peer}", data, force_hex=(responder is None))
            if responder is None:
                continue
            buf += data
            frames = parse_frames(buf)
            if not frames:
                continue
            consumed = sum(len(fr) for _, _, fr in frames)
            buf = buf[consumed:]
            reply = b""
            for op, pl, _ in frames:
                r = responder(pl, op)
                if r:
                    reply += r
            if reply:
                conn.sendall(reply)
                log("SEND", f"{name}:{port} -> {peer}", reply)
    except (socket.timeout, ConnectionResetError, OSError) as e:
        log("ERR", f"{name}:{port} {peer}: {e}")
    finally:
        stop_ka.set()
        conn.close()
        log("CLOSE", f"{name}:{port} {peer}")
        if port == 11131 and _round_trace:
            t0 = _round_trace[0][0]
            lines = [f"    +{t-t0:6.2f}s  0x{op:04x}  {ph}" for t, op, ph in _round_trace]
            log("ROUND-TRACE", f"{len(_round_trace)} non-ping packets:\n" + "\n".join(lines))
            _round_trace.clear()

def tcp_listener(port, name, responder):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log("BIND-ERR", f"{name}:{port}: {e}")
        return
    s.listen(16)
    log("LISTEN", f"TCP {port} ({name})")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_tcp, args=(conn, addr, port, name, responder),
                         daemon=True).start()

def udp_listener(port, name):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log("BIND-ERR", f"UDP {name}:{port}: {e}")
        return
    log("LISTEN", f"UDP {port} ({name})")
    while True:
        data, addr = s.recvfrom(65535)
        log("UDP", f"{name}:{port} <- {addr[0]}:{addr[1]}", data, force_hex=True)

def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="hex-dump every packet")
    ap.add_argument("--extra-tcp", default="", help="comma ports to also log")
    args = ap.parse_args()
    VERBOSE = args.verbose

    log("INFO", f"logging to {LOGFILE}")
    ports = dict(PORTS)
    for p in [x for x in args.extra_tcp.split(",") if x.strip()]:
        ports[int(p)] = (f"extra-{p}", None)

    threads = []
    for port, (name, responder) in ports.items():
        threads.append(threading.Thread(target=tcp_listener,
                                        args=(port, name, responder), daemon=True))
    # billing/login can also use UDP on some builds; log it just in case
    for port, name in [(10905, "login-udp")]:
        threads.append(threading.Thread(target=udp_listener, args=(port, name),
                                        daemon=True))
    for t in threads:
        t.start()
    log("INFO", "Assault emulator running. Ctrl+C to stop.")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("INFO", "stopped.")

if __name__ == "__main__":
    main()
