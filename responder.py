"""
AutoPatch responder for the Assault capture harness.

Loaded via:  py capture_server.py --tcp 10131,28194,10525,9010 --reply responder.py

Goal: make the launcher believe the client is up to date so it stops patching
and launches the real game (main.dat). Iterate the CheckVersion reply flag/values
until the launcher proceeds.

AutoPatch frame format (decoded from AutoPatch.dll):
    F1 | len:2 LE (whole frame incl. markers) | payload | F2
    opcode = word at frame offset 3 (= payload[0:2])

Opcodes (server -> client):
    0x0101 file-metadata / CheckVersion-result:
        off5  flag byte
        off6  dword
        off0xA dword
        off0xE dword
        off0x12 filename (null-terminated)
    0x0102 data block (RecvPatchRequirement reads it)
    0x0103 status byte at off5 (RecvPatchComplete reads it)

Client CheckVersion request captured:
    f1 10 00 01 01 07 00 5b 06 00 00 00 00 00 00 f2
    -> opcode 0x101, appid/type=7, version=0x65b(1627), 0
"""
import struct

F1 = 0xF1
F2 = 0xF2


def frame(payload: bytes) -> bytes:
    total = len(payload) + 4              # F1 + len(2) + payload + F2
    return bytes([F1]) + struct.pack("<H", total) + payload + bytes([F2])


def msg_0101(flag=0, dw1=0, dw2=0, dw3=0, filename=b""):
    # payload: opcode(2) flag(1) dw1(4) dw2(4) dw3(4) filename(z)
    p = struct.pack("<H", 0x0101)
    p += bytes([flag & 0xFF])
    p += struct.pack("<III", dw1, dw2, dw3)
    p += filename + b"\x00"
    return frame(p)


def msg_0103(status=0):
    p = struct.pack("<H", 0x0103) + bytes([status & 0xFF])
    return frame(p)


def parse_frames(data: bytes):
    """Yield (opcode, full_frame) for each complete F1..F2 frame."""
    out = []
    i = 0
    while i + 3 <= len(data):
        if data[i] != F1:
            i += 1
            continue
        ln = struct.unpack_from("<H", data, i + 1)[0]
        if ln < 4 or i + ln > len(data):
            break
        fr = data[i:i + ln]
        op = struct.unpack_from("<H", fr, 3)[0] if ln >= 5 else None
        out.append((op, fr))
        i += ln
    return out


# --- live state we can tweak between runs ---------------------------------
# Reply to CheckVersion: flag=0 ("up to date"), echo client version 1627.
CHECKVERSION_FLAG = 0
CHECKVERSION_VER = 1627


def tcp_reply(port, peer, data):
    if port == 10131:
        replies = b""
        for op, fr in parse_frames(data):
            if op == 0x0101:
                # CheckVersion request -> reply "up to date"
                replies += msg_0101(flag=CHECKVERSION_FLAG,
                                    dw1=CHECKVERSION_VER, dw2=0, dw3=0)
            elif op == 0x0102:
                # PatchRequirement request -> empty requirement
                replies += msg_0103(status=0)
            else:
                # unknown -> ack with status 0
                replies += msg_0103(status=0)
        return replies or None

    if port == 10525:
        # ---- Server List (SelectServer.dll) ----
        # Request captured: f1 08 00 01 01 00 00 f2  (opcode 0x101, param 0)
        # Response is also opcode 0x101. SelectServer.dll msg handler 0x10001500
        # parses the data (frame offset 5+) as:
        #   data[0]      = flag byte
        #   data[1..2]   = word (count/id)
        #   data[3..]    = string1 (null-terminated)   <- strcpy'd
        #   after strlen(string1)+4: string2 (null-terminated)
        # Assault.dat then sscanf's a server entry with:
        #   "%d %s %s 1 %s %d 0"  ==  id name pass 1 IP port 0
        # NOTE: exact field mapping of string1/string2 still being reversed;
        #       this is a first empirical guess to iterate against.
        replies = b""
        for op, fr in parse_frames(data):
            if op == 0x0101:
                entry = b"1 TestServer nopass 1 127.0.0.1 9010 0"
                payload = struct.pack("<H", 0x0101)      # opcode
                payload += bytes([1])                    # flag = 1 server
                payload += struct.pack("<H", 1)          # word = count 1
                payload += entry + b"\x00"               # string1
                payload += entry + b"\x00"               # string2
                replies += frame(payload)
        return replies or None
    return None
