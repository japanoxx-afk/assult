#!/usr/bin/env python3
"""
Assault private-server capture harness.

Stands up dummy TCP + UDP listeners on 127.0.0.1 so the (dead) game client
connects to US instead of the original CodiNET servers. Every byte the client
sends is logged with timestamp / direction / hex+ascii dump, so we can reverse
the protocol from live traffic.

Real servers are dead, so these listeners ARE the capture -- no packet sniffer
needed for ports we bind here. Use discover_*.ps1 (pktmon) to find ports we
have NOT bound yet (e.g. autopatch / billing UDP), then add them below.

Usage:
    py capture_server.py                 # default known ports
    py capture_server.py --tcp 10525,9010,2000 --udp 9000,9001
    py capture_server.py --reply canned.py   # optional canned responder module

Known endpoints (from System.ini / Billing.ini / Patch.ini):
    TCP 10525  Server List   (SelectServer.dll)
    TCP 9010   Round Server  (System.ini)
    TCP ?      AutoPatch      (autopatch.codinet.com / Patch.ini IP)  <- discover
    UDP ?      Billing/Login  (AssaultCommon.dll)                     <- discover
    TCP/UDP ?  Match/Game     (AsMClient.dll / AsMulti.dll)           <- discover
"""
import argparse, datetime, os, socket, sys, threading

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
os.makedirs(LOGDIR, exist_ok=True)
RUN_TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOGFILE = os.path.join(LOGDIR, f"capture_{RUN_TS}.log")
_loglock = threading.Lock()


def ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def hexdump(data: bytes, indent="    "):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        hx = f"{hx:<47}"
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{indent}{i:04x}  {hx}  |{asc}|")
    return "\n".join(lines)


def log(tag, msg, data=None):
    line = f"[{ts()}] {tag} {msg}"
    if data is not None:
        line += f"  ({len(data)} bytes)\n" + hexdump(data)
    with _loglock:
        print(line, flush=True)
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ----- optional canned responder -------------------------------------------
# A responder module may define: tcp_reply(port, peer, data) -> bytes|None
#                                udp_reply(port, peer, data) -> bytes|None
_responder = None


def tcp_reply(port, peer, data):
    if _responder and hasattr(_responder, "tcp_reply"):
        try:
            return _responder.tcp_reply(port, peer, data)
        except Exception as e:
            log("ERR", f"tcp_reply: {e}")
    return None


def udp_reply(port, peer, data):
    if _responder and hasattr(_responder, "udp_reply"):
        try:
            return _responder.udp_reply(port, peer, data)
        except Exception as e:
            log("ERR", f"udp_reply: {e}")
    return None


# ----- TCP -----------------------------------------------------------------
def handle_tcp_client(conn, addr, port):
    peer = f"{addr[0]}:{addr[1]}"
    log("TCP-OPEN", f"port {port} <- {peer}")
    conn.settimeout(300)
    try:
        while True:
            data = conn.recv(65535)
            if not data:
                break
            log("TCP-RECV", f"port {port} <- {peer}", data)
            rep = tcp_reply(port, peer, data)
            if rep:
                conn.sendall(rep)
                log("TCP-SEND", f"port {port} -> {peer}", rep)
    except (socket.timeout, ConnectionResetError, OSError) as e:
        log("TCP-ERR", f"port {port} {peer}: {e}")
    finally:
        conn.close()
        log("TCP-CLOSE", f"port {port} {peer}")


def tcp_listener(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log("BIND-ERR", f"TCP {port}: {e}")
        return
    s.listen(8)
    log("LISTEN", f"TCP {port}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_tcp_client, args=(conn, addr, port),
                         daemon=True).start()


# ----- UDP -----------------------------------------------------------------
def udp_listener(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log("BIND-ERR", f"UDP {port}: {e}")
        return
    log("LISTEN", f"UDP {port}")
    while True:
        data, addr = s.recvfrom(65535)
        peer = f"{addr[0]}:{addr[1]}"
        log("UDP-RECV", f"port {port} <- {peer}", data)
        rep = udp_reply(port, peer, data)
        if rep:
            s.sendto(rep, addr)
            log("UDP-SEND", f"port {port} -> {peer}", rep)


def parse_ports(s):
    return [int(x) for x in s.split(",") if x.strip()]


def main():
    global _responder
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp", default="10525,9010", help="comma TCP ports")
    ap.add_argument("--udp", default="", help="comma UDP ports")
    ap.add_argument("--reply", default="", help="responder .py module path")
    args = ap.parse_args()

    if args.reply:
        import importlib.util
        spec = importlib.util.spec_from_file_location("responder", args.reply)
        _responder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_responder)
        log("INFO", f"loaded responder: {args.reply}")

    log("INFO", f"logging to {LOGFILE}")
    threads = []
    for p in parse_ports(args.tcp):
        threads.append(threading.Thread(target=tcp_listener, args=(p,), daemon=True))
    for p in parse_ports(args.udp):
        threads.append(threading.Thread(target=udp_listener, args=(p,), daemon=True))
    for t in threads:
        t.start()
    log("INFO", "harness running. Ctrl+C to stop.")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("INFO", "stopped.")


if __name__ == "__main__":
    main()
