#!/usr/bin/env python3
"""dbg.py - client en ligne de commande du moniteur binaire de VICE (>= 3.5).

Bibliothèque standard uniquement. VICE doit avoir été lancé avec
tools/run.sh --monitor (port 6502 par défaut).

Usage : dbg.py [--port P] [--labels FICHIER] [--timeout S] COMMANDE [ARGS...]

Commandes :
  regs                    registres : A X Y SP PC FLAGS
  mem ADDR [LEN] [--bank B]  hexdump (LEN défaut 64 ; B : banque, voir banks)
  poke ADDR VAL [VAL...]  écrit un ou plusieurs octets
  break ADDR [ADDR2]      point d'arrêt à l'exécution (plage optionnelle)
  watch ADDR [ADDR2]      point d'arrêt en lecture/écriture
  delete N                supprime le point d'arrêt N
  list                    liste les points d'arrêt
  step [N]                exécute N instructions (défaut 1), reste arrêté
  next                    comme step mais passe par-dessus les JSR
  pause                   arrête l'émulateur là où il est (sans exécuter d'instruction)
  jump ADDR               place le PC sur ADDR sans rien exécuter (l'émulateur reste arrêté)
  type TEXTE...           tape au clavier du C64 (\\n = RETURN), ex. : type run\\n
  cont                    reprend l'exécution
  wait [SECONDES]         attend l'arrêt sur un point d'arrêt (défaut 10 s)
  status                  running|stopped + PC, sans toucher à l'émulateur
  reset [hard]            reset logiciel du C64 ("reset hard" : matériel)
  dump ADDR LEN F [--bank B]  sauve LEN octets dans le fichier binaire F
  banks                   banques mémoire de VICE (default, cpu, ram, rom, io...)
  disasm [ADDR|pc] [N]    désassemble N instructions (défaut 20, autour du PC ; > = PC, * = point d'arrêt)
  where                   ligne source de l'instruction courante (PC)
  lines [FICHIER]         lignes source -> adresses, d'après le fichier .dbg (sans VICE)
  segments                segments du programme : CODE, RODATA, DATA, BSS... (sans VICE)
  screen [--lower]        mémoire écran ($0400-$07E7) rendue en texte
  capture F.png [--full]  image de l'écran en direct (PNG 384x272 ; --full : 504x312)
  label TEXTE|ADDR        recherche un symbole (sous-chaîne) ou une adresse
  info                    version de VICE
  ping                    teste la connexion au moniteur
  quit                    arrête VICE

(Format de cette liste : "  commande ARGS  description", au moins deux
espaces avant la description : le portail tools/portal.py la lit pour
construire sa console. Toute commande ajoutée à COMMANDS doit y figurer.)

Adresses : décimal (1024), $hexa ($0400), 0xhexa (0x400), nom de label
(start, .start), ou label+/-décalage (start+3). Les labels viennent de
--labels, de $C64_LABELS ou de build/vice.labels (écrit par run.sh).
Les infos source (where, lines, disasm) viennent de --dbgfile, de
$C64_DBGFILE ou de build/vice.dbg (copie de build/<prog>.dbg par run.sh).

Fonctionnement : VICE ne garde un point d'arrêt actif, et ne reste arrêté,
que tant qu'un client du moniteur binaire est connecté. dbg.py passe donc
par un petit démon (dbg.py --daemon, lancé par run.sh --monitor, socket
Unix build/dbg.sock) qui conserve la connexion à VICE et mémorise l'état.
Si le démon n'est pas lancé alors que VICE l'est, il est démarré à la volée.

Une commande d'inspection laisse l'émulateur dans l'état où elle l'a
trouvé : s'il tournait, il repart ; s'il était arrêté, il le reste.
Codes de sortie : 0 ok, 1 erreur de commande, 2 VICE injoignable,
3 délai dépassé.
"""
import argparse
import collections
import os
import re
import selectors
import socket
import struct
import subprocess
import sys
import time
import zlib

STX = 0x02
API_VERSION = 0x02
EVENT_REQ_ID = 0xFFFFFFFF
CMD_HEADER = struct.Struct("<BBIIB")      # stx, api, len, req_id, cmd
RESP_HEADER = struct.Struct("<BBIBBI")    # stx, api, len, type, err, req_id

# Commandes
CMD_MEM_GET = 0x01
CMD_MEM_SET = 0x02
CMD_CHECKPOINT_GET = 0x11
CMD_CHECKPOINT_SET = 0x12
CMD_CHECKPOINT_DELETE = 0x13
CMD_CHECKPOINT_LIST = 0x14
CMD_CHECKPOINT_TOGGLE = 0x15
CMD_REGISTERS_GET = 0x31
CMD_REGISTERS_SET = 0x32
CMD_ADVANCE = 0x71
CMD_KEYBOARD_FEED = 0x72
CMD_PING = 0x81
CMD_BANKS_AVAILABLE = 0x82
CMD_REGISTERS_AVAILABLE = 0x83
CMD_DISPLAY_GET = 0x84
CMD_VICE_INFO = 0x85
CMD_PALETTE_GET = 0x91
CMD_EXIT = 0xAA
CMD_QUIT = 0xBB
CMD_RESET = 0xCC
CMD_DAEMON_STATUS = 0xF0   # propre à dbg.py : traité par le démon, jamais envoyé à VICE

# Réponses / événements
RESP_CHECKPOINT_INFO = 0x11
RESP_REGISTERS = 0x31
RESP_JAM = 0x61
RESP_STOPPED = 0x62
RESP_RESUMED = 0x63

# Commandes dont la réponse n'a pas le même code que la commande.
RESPONSE_OF = {CMD_CHECKPOINT_SET: RESP_CHECKPOINT_INFO,
               CMD_CHECKPOINT_GET: RESP_CHECKPOINT_INFO,
               CMD_REGISTERS_SET: RESP_REGISTERS}

ERRORS = {
    0x00: "ok", 0x01: "objet inexistant", 0x02: "espace mémoire invalide",
    0x80: "longueur de commande invalide", 0x81: "paramètre invalide",
    0x82: "version d'API invalide", 0x83: "type de commande invalide",
    0x84: "échec général",
}

OP_LOAD, OP_STORE, OP_EXEC = 1, 2, 4
SCREEN_BASE, SCREEN_SIZE = 0x0400, 1000
TRACE = bool(os.environ.get("DBG_TRACE"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")


class DbgError(Exception):
    exit_code = 1


class NotRunning(DbgError):
    exit_code = 2


class Timeout(DbgError):
    exit_code = 3


def trace(fmt, *args):
    if TRACE:
        print(fmt % args, file=sys.stderr)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
class Labels:
    def __init__(self, path):
        self.path = path
        self.by_name = {}
        self.by_addr = {}
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) != 3 or parts[0] != "al":
                        continue
                    addr = int(parts[1].split(":")[-1], 16)
                    name = parts[2].lstrip(".")
                    self.by_name[name] = addr
                    self.by_addr.setdefault(addr, []).append(name)

    def lookup(self, name):
        if name in self.by_name:
            return self.by_name[name]
        lower = {k.lower(): v for k, v in self.by_name.items()}
        return lower.get(name.lower())

    def search(self, text):
        text = text.lower()
        return sorted((a, n) for n, a in self.by_name.items() if text in n.lower())

    def name_of(self, addr):
        names = self.by_addr.get(addr)
        return names[0] if names else None

    def symbol(self, addr, digits=4):
        """Nom pour un opérande : label exact (hors __internes__), sinon
        label+1 (octet haut d'un pointeur), sinon hexa."""
        for a, suffix in ((addr, ""), (addr - 1, "+1")):
            names = [n for n in self.by_addr.get(a, []) if not n.startswith("__")]
            if names:
                return names[0] + suffix
        return "$%0*x" % (digits, addr)


# ---------------------------------------------------------------------------
# Infos de débogage ld65 (--dbgfile) : adresse <-> fichier:ligne
# ---------------------------------------------------------------------------
DBG_FIELD_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^,]*)')


class DebugInfo:
    """Lit build/<prog>.dbg. Une ligne source couvre une ou plusieurs plages
    (span) d'un segment. Type 1 = ligne C (cc65 -g), 0 = assembleur."""

    def __init__(self, path):
        self.path = path
        self.files = {}
        self.entries = []    # (début, fin, fichier, ligne, type)
        self.segments = []   # (début, fin, nom)
        if not path or not os.path.isfile(path):
            return
        segs, spans, lines = {}, {}, []
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                kind, _, rest = raw.rstrip("\n").partition("\t")
                if kind not in ("file", "seg", "span", "line"):
                    continue
                d = {k: v.strip('"') for k, v in DBG_FIELD_RE.findall(rest)}
                if kind == "file":
                    self.files[int(d["id"])] = d["name"]
                elif kind == "seg":
                    start, size = int(d["start"], 16), int(d["size"], 16)
                    segs[int(d["id"])] = start
                    if size:
                        self.segments.append((start, start + size - 1, d["name"]))
                elif kind == "span":
                    spans[int(d["id"])] = (int(d["seg"]), int(d["start"]), int(d["size"]))
                else:
                    lines.append(d)
        for d in lines:
            line = int(d.get("line", 0))
            if "span" not in d or line <= 0:
                continue
            for sid in d["span"].split("+"):
                seg, off, size = spans[int(sid)]
                if size > 0:
                    start = segs[seg] + off
                    self.entries.append((start, start + size - 1, self.files[int(d["file"])],
                                         line, int(d.get("type", 0))))

    @property
    def loaded(self):
        return bool(self.entries)

    def at(self, addr):
        """(fichier, ligne) de l'adresse : ligne C d'abord (le .s
        intermédiaire de cc65 est supprimé), fichier existant, plage la
        plus étroite."""
        best = None
        for start, end, fname, line, typ in self.entries:
            if start <= addr <= end:
                key = (typ != 1, not os.path.isfile(source_path(fname)), end - start)
                if best is None or key < best[0]:
                    best = (key, fname, line)
        return (best[1], best[2]) if best else None

    def segment_of(self, addr):
        for start, end, name in self.segments:
            if start <= addr <= end:
                return start, end, name
        return None

    def line_table(self, only_existing=True):
        """{(fichier, ligne): (début, fin)} ; une ligne C pouvant couvrir
        plusieurs plages, on garde la plus basse adresse de début."""
        table = {}
        for start, end, fname, line, typ in self.entries:
            if only_existing and not os.path.isfile(source_path(fname)):
                continue
            key = (fname, line)
            if key not in table or start < table[key][0]:
                table[key] = (start, end)
        return table


def source_path(fname):
    return fname if os.path.isabs(fname) else os.path.join(ROOT, fname)


def source_text(fname, line):
    try:
        with open(source_path(fname), encoding="utf-8", errors="replace") as f:
            for i, text in enumerate(f, 1):
                if i == line:
                    return text.strip()
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------------------
# Désassembleur 6502 (opcodes officiels)
# ---------------------------------------------------------------------------
MODE_SIZE = {"imp": 1, "acc": 1, "imm": 2, "zp": 2, "zpx": 2, "zpy": 2, "izx": 2,
             "izy": 2, "rel": 2, "abs": 3, "absx": 3, "absy": 3, "ind": 3}
OPCODES = {}


def _build_opcodes():
    alu = ("imm", "zp", "zpx", "abs", "absx", "absy", "izx", "izy")
    for mn, codes in (("ORA", (0x09, 0x05, 0x15, 0x0D, 0x1D, 0x19, 0x01, 0x11)),
                      ("AND", (0x29, 0x25, 0x35, 0x2D, 0x3D, 0x39, 0x21, 0x31)),
                      ("EOR", (0x49, 0x45, 0x55, 0x4D, 0x5D, 0x59, 0x41, 0x51)),
                      ("ADC", (0x69, 0x65, 0x75, 0x6D, 0x7D, 0x79, 0x61, 0x71)),
                      ("LDA", (0xA9, 0xA5, 0xB5, 0xAD, 0xBD, 0xB9, 0xA1, 0xB1)),
                      ("CMP", (0xC9, 0xC5, 0xD5, 0xCD, 0xDD, 0xD9, 0xC1, 0xD1)),
                      ("SBC", (0xE9, 0xE5, 0xF5, 0xED, 0xFD, 0xF9, 0xE1, 0xF1))):
        for mode, code in zip(alu, codes):
            OPCODES[code] = (mn, mode)
    for mode, code in zip(alu[1:], (0x85, 0x95, 0x8D, 0x9D, 0x99, 0x81, 0x91)):
        OPCODES[code] = ("STA", mode)
    for mn, codes in (("ASL", (0x0A, 0x06, 0x16, 0x0E, 0x1E)), ("ROL", (0x2A, 0x26, 0x36, 0x2E, 0x3E)),
                      ("LSR", (0x4A, 0x46, 0x56, 0x4E, 0x5E)), ("ROR", (0x6A, 0x66, 0x76, 0x6E, 0x7E))):
        for mode, code in zip(("acc", "zp", "zpx", "abs", "absx"), codes):
            OPCODES[code] = (mn, mode)
    for mn, codes in (("INC", (0xE6, 0xF6, 0xEE, 0xFE)), ("DEC", (0xC6, 0xD6, 0xCE, 0xDE))):
        for mode, code in zip(("zp", "zpx", "abs", "absx"), codes):
            OPCODES[code] = (mn, mode)
    table = {
        "LDX": {"imm": 0xA2, "zp": 0xA6, "zpy": 0xB6, "abs": 0xAE, "absy": 0xBE},
        "LDY": {"imm": 0xA0, "zp": 0xA4, "zpx": 0xB4, "abs": 0xAC, "absx": 0xBC},
        "STX": {"zp": 0x86, "zpy": 0x96, "abs": 0x8E},
        "STY": {"zp": 0x84, "zpx": 0x94, "abs": 0x8C},
        "CPX": {"imm": 0xE0, "zp": 0xE4, "abs": 0xEC},
        "CPY": {"imm": 0xC0, "zp": 0xC4, "abs": 0xCC},
        "BIT": {"zp": 0x24, "abs": 0x2C},
        "JMP": {"abs": 0x4C, "ind": 0x6C},
        "JSR": {"abs": 0x20},
    }
    for mn, modes in table.items():
        for mode, code in modes.items():
            OPCODES[code] = (mn, mode)
    for mn, code in (("BPL", 0x10), ("BMI", 0x30), ("BVC", 0x50), ("BVS", 0x70),
                     ("BCC", 0x90), ("BCS", 0xB0), ("BNE", 0xD0), ("BEQ", 0xF0)):
        OPCODES[code] = (mn, "rel")
    for mn, code in (("BRK", 0x00), ("PHP", 0x08), ("CLC", 0x18), ("PLP", 0x28), ("SEC", 0x38),
                     ("RTI", 0x40), ("PHA", 0x48), ("CLI", 0x58), ("RTS", 0x60), ("PLA", 0x68),
                     ("SEI", 0x78), ("DEY", 0x88), ("TXA", 0x8A), ("TYA", 0x98), ("TXS", 0x9A),
                     ("TAY", 0xA8), ("TAX", 0xAA), ("CLV", 0xB8), ("TSX", 0xBA), ("INY", 0xC8),
                     ("DEX", 0xCA), ("CLD", 0xD8), ("INX", 0xE8), ("NOP", 0xEA), ("SED", 0xF8)):
        OPCODES[code] = (mn, "imp")


_build_opcodes()
assert len(OPCODES) == 151, len(OPCODES)


def decode(mem, base, addr, labels):
    """(taille, octets, texte) de l'instruction en addr ; mem commence en base."""
    i = addr - base
    op = mem[i] if 0 <= i < len(mem) else None
    if op is None or op not in OPCODES or i + MODE_SIZE[OPCODES[op][1]] > len(mem):
        return 1, mem[i:i + 1], ".byte $%02x" % op if op is not None else "?"
    mn, mode = OPCODES[op]
    size = MODE_SIZE[mode]
    raw = mem[i:i + size]
    lo = raw[1] if size > 1 else 0
    word = lo | (raw[2] << 8) if size == 3 else lo
    fmt = {
        "imp": "", "acc": "a", "imm": "#$%02x" % lo,
        "zp": labels.symbol(lo, 2), "zpx": labels.symbol(lo, 2) + ",x",
        "zpy": labels.symbol(lo, 2) + ",y", "izx": "(%s,x)" % labels.symbol(lo, 2),
        "izy": "(%s),y" % labels.symbol(lo, 2), "abs": labels.symbol(word),
        "absx": labels.symbol(word) + ",x", "absy": labels.symbol(word) + ",y",
        "ind": "(%s)" % labels.symbol(word),
        "rel": labels.symbol((addr + 2 + (lo - 256 if lo > 127 else lo)) & 0xFFFF),
    }[mode]
    return size, raw, (mn + " " + fmt).rstrip()


def find_start(mem, base, pc, before, low):
    """Adresse de départ pour avoir `before` instructions avant pc. Le 6502
    n'a pas de longueur fixe : on essaie des départs en amont et on garde
    ceux dont le décodage retombe exactement sur pc (de préférence un label)."""
    candidates = []
    for back in range(min(3 * before, pc - low), 0, -1):
        start, addr, n = pc - back, pc - back, 0
        while addr < pc:
            op = mem[addr - base]
            if op not in OPCODES:
                break
            addr += MODE_SIZE[OPCODES[op][1]]
            n += 1
        if addr == pc:
            candidates.append((n, start))
    if not candidates:
        return pc
    n, start = max(candidates)
    while n > before:  # trop de contexte : on avance d'une instruction
        start += MODE_SIZE[OPCODES[mem[start - base]][1]]
        n -= 1
    return start


def parse_int(text):
    t = text.strip().lower()
    if t.startswith("$"):
        return int(t[1:], 16)
    if t.startswith("0x"):
        return int(t[2:], 16)
    return int(t, 10)


def parse_addr(text, labels):
    """décimal, $hex, 0xhex, label, label+N, label-N."""
    t = text.strip()
    try:
        v = parse_int(t)
    except ValueError:
        v = None
    if v is None:
        base, sign, off = t, 0, "0"
        for sep in ("+", "-"):
            if sep in t[1:]:
                i = t.rfind(sep)
                base, off = t[:i], t[i + 1:]
                sign = 1 if sep == "+" else -1
                break
        addr = labels.lookup(base.lstrip("."))
        if addr is None:
            raise DbgError("adresse ou label inconnu : %s" % text)
        v = addr
        if sign:
            try:
                v += sign * parse_int(off)
            except ValueError:
                raise DbgError("décalage invalide : %s" % text)
    if not 0 <= v <= 0xFFFF:
        raise DbgError("adresse hors de $0000-$FFFF : %s" % text)
    return v


# ---------------------------------------------------------------------------
# Trames
# ---------------------------------------------------------------------------
class Frame:
    """Une réponse ou un événement VICE."""
    __slots__ = ("type", "error", "req_id", "body")

    def __init__(self, rtype, error, req_id, body):
        self.type, self.error, self.req_id, self.body = rtype, error, req_id, body

    @property
    def is_event(self):
        return self.req_id == EVENT_REQ_ID

    def pack(self):
        return RESP_HEADER.pack(STX, API_VERSION, len(self.body), self.type,
                                self.error, self.req_id) + self.body


def parse_checkpoint(body):
    num, hit, start, end, stop, enabled, op, temp, hits, ignore, cond, memspace = \
        struct.unpack("<IBHHBBBBIIBB", body[:23])
    return {"num": num, "hit": bool(hit), "start": start, "end": end,
            "stop": bool(stop), "enabled": bool(enabled), "op": op,
            "temp": bool(temp), "hits": hits, "ignore": ignore,
            "cond": bool(cond), "memspace": memspace}


class FrameReader:
    """Découpe un flux d'octets en trames (sens VICE -> client, ou client ->
    VICE si request=True)."""

    def __init__(self, request=False):
        self.buf = b""
        self.request = request
        self.header = CMD_HEADER if request else RESP_HEADER

    def feed(self, data):
        self.buf += data
        frames = []
        while len(self.buf) >= self.header.size:
            fields = self.header.unpack(self.buf[:self.header.size])
            if fields[0] != STX:
                raise DbgError("flux désynchronisé (0x%02x)" % fields[0])
            length = fields[2]
            total = self.header.size + length
            if len(self.buf) < total:
                break
            body = self.buf[self.header.size:total]
            self.buf = self.buf[total:]
            if self.request:
                frames.append((fields[3], fields[4], body))      # req_id, cmd, body
            else:
                frames.append(Frame(fields[3], fields[4], fields[5], body))
        return frames


# ---------------------------------------------------------------------------
# Démon : garde la connexion à VICE, mémorise l'état, sert un client à la fois
# ---------------------------------------------------------------------------
class Daemon:
    def __init__(self, port, sock_path):
        self.port = port
        self.sock_path = sock_path
        self.stopped = False
        self.pc = 0
        self.last_hit = None
        self.vice_reader = FrameReader()
        self.client_reader = FrameReader(request=True)
        self.client = None
        self.pending = collections.deque()

    def run(self):
        try:
            vice = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        except OSError as e:
            sys.exit("dbg.py --daemon: VICE injoignable sur le port %d (%s)" % (self.port, e))
        vice.setblocking(False)
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.sock_path)
        srv.listen(8)
        srv.setblocking(False)
        sel = selectors.DefaultSelector()
        sel.register(vice, selectors.EVENT_READ, "vice")
        sel.register(srv, selectors.EVENT_READ, "srv")
        print("dbg.py --daemon: connecté à VICE :%d, socket %s" % (self.port, self.sock_path),
              flush=True)
        try:
            while True:
                for key, _ in sel.select():
                    if key.data == "vice":
                        data = vice.recv(65536)
                        if not data:
                            print("dbg.py --daemon: VICE a fermé la connexion", flush=True)
                            return
                        for frame in self.vice_reader.feed(data):
                            self.on_vice_frame(frame)
                    elif key.data == "srv":
                        conn, _ = srv.accept()
                        if self.client is not None:
                            # Un seul client à la fois : les suivants sont
                            # servis dans l'ordre d'arrivée.
                            self.pending.append(conn)
                            continue
                        self.attach(sel, conn)
                    elif key.data == "client":
                        try:
                            data = key.fileobj.recv(65536)
                        except OSError:
                            data = b""
                        if not data:
                            self.detach(sel)
                            continue
                        try:
                            frames = self.client_reader.feed(data)
                        except DbgError:
                            self.detach(sel)
                            continue
                        for req_id, cmd, body in frames:
                            self.on_client_frame(vice, req_id, cmd, body)
        finally:
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

    def attach(self, sel, conn):
        conn.setblocking(False)
        self.client = conn
        self.client_reader = FrameReader(request=True)
        sel.register(conn, selectors.EVENT_READ, "client")

    def detach(self, sel):
        sel.unregister(self.client)
        try:
            self.client.close()
        except OSError:
            pass
        self.client = None
        if self.pending:
            self.attach(sel, self.pending.popleft())

    def on_vice_frame(self, frame):
        trace("daemon <- vice type=%02x err=%02x req=%08x len=%d", frame.type,
              frame.error, frame.req_id, len(frame.body))
        if frame.is_event:
            if frame.type == RESP_STOPPED and len(frame.body) >= 2:
                self.stopped = True
                self.pc = struct.unpack("<H", frame.body[:2])[0]
            elif frame.type == RESP_RESUMED:
                self.stopped = False
                self.last_hit = None
            elif frame.type == RESP_CHECKPOINT_INFO:
                cp = parse_checkpoint(frame.body)
                if cp["hit"]:
                    self.last_hit = cp["num"]
        if self.client is not None:
            try:
                self.client.sendall(frame.pack())
            except OSError:
                pass

    def on_client_frame(self, vice, req_id, cmd, body):
        trace("daemon <- client cmd=%02x req=%08x", cmd, req_id)
        if cmd == CMD_DAEMON_STATUS:
            hit = self.last_hit if self.last_hit is not None else 0xFFFFFFFF
            resp = Frame(CMD_DAEMON_STATUS, 0, req_id,
                         struct.pack("<BHI", 1 if self.stopped else 0, self.pc, hit))
            self.client.sendall(resp.pack())
            return
        if cmd == CMD_EXIT:
            # L'événement "resumed" arrive après la réponse : on anticipe,
            # l'événement confirmera.
            self.stopped = False
            self.last_hit = None
        elif cmd == CMD_CHECKPOINT_DELETE and len(body) >= 4:
            if struct.unpack("<I", body[:4])[0] == self.last_hit:
                self.last_hit = None
        pkt = CMD_HEADER.pack(STX, API_VERSION, len(body), req_id, cmd) + body
        vice.sendall(pkt)


def daemon_sock_path():
    return os.environ.get("C64_DBG_SOCK", os.path.join(BUILD, "dbg.sock"))


def spawn_daemon(port, sock_path):
    """Lance dbg.py --daemon détaché ; attend que la socket apparaisse."""
    log = open(os.path.join(BUILD, "dbg.log"), "ab")
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--port", str(port), "--daemon",
         "--sock", sock_path],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    with open(os.path.join(BUILD, "dbg.pid"), "w") as f:
        f.write("%d\n" % proc.pid)
    for _ in range(50):
        if os.path.exists(sock_path):
            return
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    raise NotRunning("impossible de démarrer le démon dbg.py (voir build/dbg.log)")


# ---------------------------------------------------------------------------
# Client (via le démon)
# ---------------------------------------------------------------------------
class Monitor:
    def __init__(self, port, timeout, sock_path=None):
        self.timeout = timeout
        self.next_id = 1
        self.reader = FrameReader()
        self.queue = []
        self.checkpoint_hits = []
        self.touched_vice = False
        sock_path = sock_path or daemon_sock_path()
        self.sock = self._connect(sock_path, port)
        self.sock.settimeout(timeout)
        st = self.status()
        self.was_stopped = st["stopped"]

    def _connect(self, sock_path, port):
        for attempt in range(2):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                s.connect(sock_path)
                return s
            except OSError:
                s.close()
                if attempt == 1:
                    break
                # Pas de démon : VICE tourne-t-il ? Si oui, on lance le démon.
                try:
                    probe = socket.create_connection(("127.0.0.1", port), timeout=1)
                    probe.close()
                except OSError as e:
                    raise NotRunning(
                        "VICE n'est pas lancé avec --monitor (port %d : %s). "
                        "Lancez : tools/run.sh --headless --monitor build/<prog>.prg"
                        % (port, e.strerror or e))
                spawn_daemon(port, sock_path)
        raise NotRunning("démon dbg.py injoignable (%s)" % sock_path)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    # --- bas niveau -------------------------------------------------------
    def read_frame(self):
        while not self.queue:
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                raise Timeout("pas de réponse de VICE en %.1f s" % self.timeout)
            if not data:
                raise NotRunning("connexion fermée par le démon dbg.py (VICE arrêté ?)")
            self.queue.extend(self.reader.feed(data))
        frame = self.queue.pop(0)
        trace("<- type=%02x err=%02x req=%08x len=%d %s", frame.type, frame.error,
              frame.req_id, len(frame.body), frame.body[:16].hex())
        if frame.is_event and frame.type == RESP_CHECKPOINT_INFO:
            self.checkpoint_hits.append(parse_checkpoint(frame.body))
        return frame

    def send(self, cmd, body=b""):
        req_id = self.next_id
        self.next_id += 1
        trace("-> cmd=%02x req=%08x %s", cmd, req_id, body.hex())
        if cmd != CMD_DAEMON_STATUS:
            self.touched_vice = True  # VICE s'est mis en pause pour nous
        self.sock.sendall(CMD_HEADER.pack(STX, API_VERSION, len(body), req_id, cmd) + body)
        return req_id

    def call(self, cmd, body=b"", collect=None):
        """Envoie une commande et attend sa réponse ; les réponses
        intermédiaires (ex. 0x11 avant 0x14) vont dans collect."""
        expected = RESPONSE_OF.get(cmd, cmd)
        req_id = self.send(cmd, body)
        while True:
            frame = self.read_frame()
            if frame.req_id != req_id:
                continue
            if frame.type == expected or frame.error:
                break
            if collect is not None:
                collect.append(frame)
        if frame.error:
            raise DbgError("VICE a refusé la commande 0x%02x : %s"
                           % (cmd, ERRORS.get(frame.error, "erreur 0x%02x" % frame.error)))
        return frame

    # --- commandes --------------------------------------------------------
    def status(self):
        resp = self.call(CMD_DAEMON_STATUS)
        stopped, pc, hit = struct.unpack("<BHI", resp.body[:7])
        return {"stopped": bool(stopped), "pc": pc, "hit": None if hit == 0xFFFFFFFF else hit}

    def ping(self):
        self.call(CMD_PING)

    def exit_monitor(self):
        self.call(CMD_EXIT)

    def mem_get(self, start, end, bank=0):
        """Octets start..end (inclus), sans effet de bord sur les E/S. Par
        blocs de 32 Ko : la longueur de réponse tient sur 16 bits."""
        data = b""
        while start <= end:
            stop = min(end, start + 0x7FFF)
            resp = self.call(CMD_MEM_GET, struct.pack("<BHHBH", 0, start, stop, 0, bank))
            (length,) = struct.unpack("<H", resp.body[:2])
            data += resp.body[2:2 + length]
            start = stop + 1
        return data

    def banks(self):
        """{nom: id} des banques mémoire de la machine émulée."""
        body = self.call(CMD_BANKS_AVAILABLE).body
        (count,) = struct.unpack("<H", body[:2])
        pos, banks = 2, collections.OrderedDict()
        for _ in range(count):
            size = body[pos]
            bid = struct.unpack("<H", body[pos + 1:pos + 3])[0]
            nlen = body[pos + 3]
            banks[body[pos + 4:pos + 4 + nlen].decode("ascii", "replace")] = bid
            pos += 1 + size
        return banks

    def bank_id(self, name):
        if name is None:
            return 0
        banks = self.banks()
        if name in banks:
            return banks[name]
        raise DbgError("banque inconnue : %s (disponibles : %s)" % (name, ", ".join(banks)))

    def mem_set(self, start, data):
        self.call(CMD_MEM_SET, struct.pack("<BHHBH", 0, start, start + len(data) - 1, 0, 0) + data)

    def registers_available(self):
        resp = self.call(CMD_REGISTERS_AVAILABLE, bytes([0]))
        (count,) = struct.unpack("<H", resp.body[:2])
        pos, regs = 2, {}
        for _ in range(count):
            size = resp.body[pos]
            rid, bits, nlen = resp.body[pos + 1], resp.body[pos + 2], resp.body[pos + 3]
            regs[rid] = (resp.body[pos + 4:pos + 4 + nlen].decode("ascii", "replace"), bits)
            pos += 1 + size
        return regs

    def registers(self):
        names = self.registers_available()
        resp = self.call(CMD_REGISTERS_GET, bytes([0]))
        (count,) = struct.unpack("<H", resp.body[:2])
        pos, values = 2, {}
        for _ in range(count):
            size = resp.body[pos]
            rid = resp.body[pos + 1]
            (val,) = struct.unpack("<H", resp.body[pos + 2:pos + 4])
            values[names.get(rid, ("R%d" % rid, 16))[0]] = val
            pos += 1 + size
        return values

    def set_register(self, name, value):
        ids = {n: rid for rid, (n, _) in self.registers_available().items()}
        if name not in ids:
            raise DbgError("registre inconnu : %s" % name)
        body = struct.pack("<BHBBH", 0, 1, 3, ids[name], value & 0xFFFF)
        self.call(CMD_REGISTERS_SET, body)

    def keyboard_feed(self, petscii):
        for i in range(0, len(petscii), 255):
            chunk = petscii[i:i + 255]
            self.call(CMD_KEYBOARD_FEED, bytes([len(chunk)]) + chunk)

    def checkpoint_set(self, start, end, op, stop=True, temporary=False):
        body = struct.pack("<HHBBBBB", start, end, 1 if stop else 0, 1, op,
                           1 if temporary else 0, 0)
        return parse_checkpoint(self.call(CMD_CHECKPOINT_SET, body).body)

    def checkpoint_delete(self, num):
        self.call(CMD_CHECKPOINT_DELETE, struct.pack("<I", num))

    def checkpoint_list(self):
        infos = []
        self.call(CMD_CHECKPOINT_LIST, collect=infos)
        # VICE liste un checkpoint load+store une fois par liste interne :
        # on dédoublonne par numéro.
        seen, cps = set(), []
        for f in infos:
            if f.type != RESP_CHECKPOINT_INFO:
                continue
            cp = parse_checkpoint(f.body)
            if cp["num"] not in seen:
                seen.add(cp["num"])
                cps.append(cp)
        return cps

    def advance(self, count, step_over):
        self.call(CMD_ADVANCE, struct.pack("<BH", 1 if step_over else 0, count))

    def reset(self, hard=False):
        self.call(CMD_RESET, bytes([1 if hard else 0]))

    def quit(self):
        self.call(CMD_QUIT)

    def vice_info(self):
        resp = self.call(CMD_VICE_INFO)
        n = resp.body[0]
        ver = ".".join(str(b) for b in resp.body[1:1 + n])
        m = resp.body[1 + n]
        rev = struct.unpack("<I", resp.body[2 + n:2 + n + m])[0] if m == 4 else 0
        return ver, rev

    def display(self):
        """Tampon d'affichage du VIC-II : (largeur, hauteur, x0, y0, w, h, pixels)
        en 8 bits indexés ; (x0, y0, w, h) = zone utile 320x200."""
        body = self.call(CMD_DISPLAY_GET, bytes([1, 0])).body  # VIC-II, 8 bits indexés
        (flen,) = struct.unpack("<I", body[:4])
        dw, dh, xo, yo, iw, ih, bpp = struct.unpack("<HHHHHHB", body[4:17])
        if bpp != 8:
            raise DbgError("format d'affichage inattendu (%d bits par pixel)" % bpp)
        (blen,) = struct.unpack("<I", body[4 + flen:8 + flen])
        pixels = body[8 + flen:8 + flen + blen]
        # VICE 3.7.1 annonce dw*dh octets mais en envoie 4 de moins (longueur
        # de trame calculée sans le champ de 4 octets) : il manque les derniers
        # pixels du coin inférieur droit, hors zone recadrée. On complète.
        missing = dw * dh - len(pixels)
        if 0 < missing <= 4 and pixels:
            pixels += pixels[-1:] * missing
        if len(pixels) != dw * dh:
            raise DbgError("tampon d'affichage tronqué (%d/%d octets)" % (len(pixels), dw * dh))
        return dw, dh, xo, yo, iw, ih, pixels

    def palette(self):
        body = self.call(CMD_PALETTE_GET, bytes([1])).body
        (count,) = struct.unpack("<H", body[:2])
        pos, colors = 2, []
        for _ in range(count):
            size = body[pos]
            colors.append(tuple(body[pos + 1:pos + 4]))
            pos += 1 + size
        return colors

    def wait_stopped(self, seconds):
        """Attend un événement d'arrêt ; renvoie le PC ou None."""
        deadline = time.monotonic() + seconds
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.sock.settimeout(remaining)
                try:
                    frame = self.read_frame()
                except Timeout:
                    return None
                if frame.is_event and frame.type == RESP_STOPPED:
                    return struct.unpack("<H", frame.body[:2])[0]
        finally:
            self.sock.settimeout(self.timeout)


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------
def flags_str(fl):
    return "".join(n if fl & (0x80 >> i) else "." for i, n in enumerate("NV-BDIZC"))


def fmt_regs(r):
    return ("A=%02x X=%02x Y=%02x SP=%02x PC=%04x FLAGS=%s (%02x)"
            % (r.get("A", 0), r.get("X", 0), r.get("Y", 0), r.get("SP", 0),
               r.get("PC", 0), flags_str(r.get("FL", 0)), r.get("FL", 0)))


def fmt_checkpoint(cp, labels):
    ops = "/".join(n for bit, n in ((OP_LOAD, "load"), (OP_STORE, "store"), (OP_EXEC, "exec"))
                   if cp["op"] & bit) or "?"
    rng = "$%04x" % cp["start"]
    if cp["end"] != cp["start"]:
        rng += "-$%04x" % cp["end"]
    name = labels.name_of(cp["start"])
    return ("checkpoint %d %s%s type=%s enabled=%d stop=%d hits=%d"
            % (cp["num"], rng, " (%s)" % name if name else "", ops,
               cp["enabled"], cp["stop"], cp["hits"]))


def hexdump(addr, data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexs = " ".join("%02x" % b for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%04x: %-47s |%s|" % (addr + i, hexs, asc))
    return "\n".join(lines)


def screen_code_to_char(code, lower=False):
    code &= 0x7F  # ignore la vidéo inverse
    if code == 0:
        return "@"
    if 1 <= code <= 26:
        return chr(ord("a" if lower else "A") + code - 1)
    if 27 <= code <= 31:
        return "[£]^<"[code - 27]
    if 32 <= code <= 63:
        return chr(code)
    if code == 64:
        return "-"
    if lower and 65 <= code <= 90:
        return chr(ord("A") + code - 65)
    return "."  # caractère graphique


def write_png_indexed(path, width, height, rows, palette):
    """PNG 8 bits à palette (type 3), bibliothèque standard uniquement."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + row for row in rows)  # filtre 0 sur chaque ligne
    plte = b"".join(bytes(c) for c in palette)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
           + chunk(b"PLTE", plte)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


# Recadrage identique à -exitscreenshot : 32 px de bordure à gauche/droite,
# 36 en haut/bas autour de la zone utile 320x200.
CAPTURE_BORDER_X, CAPTURE_BORDER_Y = 32, 36


def fmt_screen(data, lower=False):
    return "\n".join("%02d|%s|" % (row, "".join(screen_code_to_char(c, lower)
                                                 for c in data[row * 40:(row + 1) * 40]))
                     for row in range(25))


# ---------------------------------------------------------------------------
# Sous-commandes
# ---------------------------------------------------------------------------
def need(args, n, usage):
    if len(args) < n:
        raise DbgError("usage : %s" % usage)


def cmd_regs(mon, labels, args):
    print(fmt_regs(mon.registers()))


def pop_option(args, name):
    """Retire « name VALEUR » de args et renvoie VALEUR (ou None)."""
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise DbgError("%s attend une valeur" % name)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return None


def cmd_mem(mon, labels, args):
    bank = pop_option(args, "--bank")
    need(args, 1, "mem ADDR [LEN] [--bank B]")
    addr = parse_addr(args[0], labels)
    length = parse_int(args[1]) if len(args) > 1 else 64
    if length < 1 or addr + length - 1 > 0xFFFF:
        raise DbgError("plage mémoire invalide")
    print(hexdump(addr, mon.mem_get(addr, addr + length - 1, mon.bank_id(bank))))


def cmd_banks(mon, labels, args):
    for name, bid in mon.banks().items():
        print("bank %d %s" % (bid, name))


def cmd_poke(mon, labels, args):
    need(args, 2, "poke ADDR VAL [VAL...]")
    addr = parse_addr(args[0], labels)
    vals = [parse_int(v) for v in args[1:]]
    if any(not 0 <= v <= 255 for v in vals):
        raise DbgError("valeur hors de 0-255")
    mon.mem_set(addr, bytes(vals))
    print("poke %04x: %s" % (addr, " ".join("%02x" % v for v in vals)))


def _set_checkpoint(mon, labels, args, op, usage):
    need(args, 1, usage)
    start = parse_addr(args[0], labels)
    end = parse_addr(args[1], labels) if len(args) > 1 else start
    print(fmt_checkpoint(mon.checkpoint_set(start, end, op), labels))


def cmd_break(mon, labels, args):
    _set_checkpoint(mon, labels, args, OP_EXEC, "break ADDR [ADDR2]")


def cmd_watch(mon, labels, args):
    _set_checkpoint(mon, labels, args, OP_LOAD | OP_STORE, "watch ADDR [ADDR2]")


def cmd_delete(mon, labels, args):
    need(args, 1, "delete N")
    num = parse_int(args[0])
    mon.checkpoint_delete(num)
    print("checkpoint %d deleted" % num)


def cmd_list(mon, labels, args):
    cps = mon.checkpoint_list()
    if not cps:
        print("no checkpoints")
    for cp in cps:
        print(fmt_checkpoint(cp, labels))


def cmd_step(mon, labels, args, step_over=False):
    count = parse_int(args[0]) if args else 1
    if not 1 <= count <= 0xFFFF:
        raise DbgError("nombre de pas invalide")
    mon.was_stopped = True  # rester arrêté après un pas
    if not step_over:
        mon.advance(count, False)
    else:
        for _ in range(count):
            if not step_over_once(mon, labels):
                break
    print(fmt_regs(mon.registers()))


def step_over_once(mon, labels, timeout=10.0):
    """Un pas sans entrer dans les JSR. Le « step over » de VICE s'arrête
    dans le gestionnaire d'IRQ si une interruption survient pendant le
    sous-programme : on pose plutôt un point d'arrêt temporaire après le
    JSR et on laisse tourner. Renvoie False si l'arrêt a eu lieu ailleurs
    (point d'arrêt de l'utilisateur) ou n'a pas eu lieu."""
    pc = mon.registers().get("PC", 0)
    if mon.mem_get(pc, pc)[0] != 0x20 or pc > 0xFFFC:  # pas un JSR
        mon.advance(1, False)
        return True
    ret = pc + 3
    # Point d'arrêt NON temporaire, supprimé par nos soins : avec un point
    # d'arrêt temporaire, VICE 3.7.1 ignore un autre point d'arrêt atteint
    # juste après la reprise (ex. sur la 1re instruction du sous-programme).
    cp = mon.checkpoint_set(ret, ret, OP_EXEC)
    try:
        mon.exit_monitor()
        stopped = mon.wait_stopped(timeout)
    finally:
        try:
            mon.checkpoint_delete(cp["num"])
        except DbgError:
            pass
    if stopped is None:
        mon.was_stopped = False
        raise Timeout("le sous-programme appelé en $%04x n'est pas revenu en %.0f s "
                      "(l'émulateur continue ; pause pour l'arrêter)" % (pc, timeout))
    return stopped == ret  # sinon : arrêt sur un point d'arrêt de l'utilisateur


def cmd_next(mon, labels, args):
    cmd_step(mon, labels, args, step_over=True)


def cmd_pause(mon, labels, args):
    st = mon.status()
    if not st["stopped"]:
        mon.ping()  # toute commande fait entrer VICE dans le moniteur
    mon.was_stopped = True  # et on y reste
    pc = mon.registers().get("PC", 0)
    name = labels.name_of(pc)
    print("stopped PC=%04x%s" % (pc, " (%s)" % name if name else ""))


def cmd_jump(mon, labels, args):
    need(args, 1, "jump ADDR")
    addr = parse_addr(args[0], labels)
    if not mon.status()["stopped"]:
        mon.ping()
    mon.set_register("PC", addr)
    # VICE 3.7.1 : le premier « advance » après un changement de PC
    # n'exécute rien. On le consomme ici pour que le pas suivant de
    # l'utilisateur avance vraiment ; si une autre version exécute bien
    # l'instruction, on replace le PC.
    mon.advance(1, False)
    if mon.registers().get("PC") != addr:
        mon.set_register("PC", addr)
    mon.was_stopped = True
    name = labels.name_of(addr)
    print("stopped PC=%04x%s" % (addr, " (%s)" % name if name else ""))


def to_petscii(text):
    """Texte -> PETSCII pour le clavier : lettres en majuscules (jeu de
    caractères par défaut), \\n -> RETURN ($0d)."""
    out = bytearray()
    for ch in text.replace("\\n", "\r").replace("\n", "\r"):
        c = ord(ch)
        if ch == "\r":
            out.append(0x0D)
        elif "a" <= ch <= "z":
            out.append(c - 32)
        elif 32 <= c < 127:
            out.append(c)
        else:
            raise DbgError("caractère non tapable : %r" % ch)
    return bytes(out)


def cmd_type(mon, labels, args):
    need(args, 1, "type TEXTE...")
    data = to_petscii(" ".join(args))
    mon.keyboard_feed(data)
    print("typed %d chars" % len(data))


def cmd_cont(mon, labels, args):
    mon.exit_monitor()
    mon.was_stopped = False
    print("resumed")


def _report_stop(mon, labels, pc, hit):
    name = labels.name_of(pc)
    print("stopped PC=%04x%s%s" % (pc, " (%s)" % name if name else "",
                                   " checkpoint=%d" % hit if hit is not None else ""))


def cmd_wait(mon, labels, args):
    seconds = float(args[0]) if args else 10.0
    st = mon.status()
    if st["stopped"]:
        _report_stop(mon, labels, st["pc"], st["hit"])
        return
    pc = mon.wait_stopped(seconds)
    if pc is None:
        raise Timeout("pas d'arrêt en %.1f s" % seconds)
    hit = next((cp["num"] for cp in mon.checkpoint_hits if cp["hit"]), None)
    mon.was_stopped = True
    _report_stop(mon, labels, pc, hit)


def cmd_status(mon, labels, args):
    st = mon.status()
    if st["stopped"]:
        _report_stop(mon, labels, st["pc"], st["hit"])
    else:
        print("running")


def cmd_reset(mon, labels, args):
    mon.reset(hard=bool(args and args[0] == "hard"))
    print("reset")


def cmd_dump(mon, labels, args):
    bank = pop_option(args, "--bank")
    need(args, 3, "dump ADDR LEN FICHIER [--bank B]")
    addr = parse_addr(args[0], labels)
    length = parse_int(args[1])
    if length < 1 or addr + length - 1 > 0xFFFF:
        raise DbgError("plage mémoire invalide")
    data = mon.mem_get(addr, addr + length - 1, mon.bank_id(bank))
    with open(args[2], "wb") as f:
        f.write(data)
    print("dump %04x-%04x (%d bytes) -> %s" % (addr, addr + length - 1, len(data), args[2]))


def cmd_screen(mon, labels, args):
    lower = "--lower" in args
    rest = [a for a in args if not a.startswith("--")]
    base = parse_addr(rest[0], labels) if rest else SCREEN_BASE
    print(fmt_screen(mon.mem_get(base, base + SCREEN_SIZE - 1), lower))


def cmd_capture(mon, labels, args):
    need(args, 1, "capture FICHIER.png [--full]")
    full = "--full" in args
    path = next(a for a in args if not a.startswith("--"))
    dw, dh, xo, yo, iw, ih, pixels = mon.display()
    palette = mon.palette()
    if full:
        x0, y0, w, h = 0, 0, dw, dh
    else:
        x0 = max(0, xo - CAPTURE_BORDER_X)
        y0 = max(0, yo - CAPTURE_BORDER_Y)
        w = min(dw - x0, iw + 2 * CAPTURE_BORDER_X)
        h = min(dh - y0, ih + 2 * CAPTURE_BORDER_Y)
    rows = [pixels[(y0 + y) * dw + x0:(y0 + y) * dw + x0 + w] for y in range(h)]
    if max(pixels) >= len(palette):
        raise DbgError("indice de couleur hors palette (%d >= %d)" % (max(pixels), len(palette)))
    write_png_indexed(path, w, h, rows, palette)
    print("capture %dx%d -> %s" % (w, h, path))


def cmd_label(mon, labels, args):
    need(args, 1, "label TEXTE|ADDR")
    if not labels.by_name:
        raise DbgError("aucun fichier de labels (--labels, $C64_LABELS ou build/vice.labels)")
    try:
        addr = parse_int(args[0])
    except ValueError:
        found = labels.search(args[0])
        if not found:
            raise DbgError("aucun label contenant '%s'" % args[0])
        for addr, name in found:
            print("%s = $%04x" % (name, addr))
        return
    names = labels.by_addr.get(addr, [])
    if not names:
        raise DbgError("aucun label à $%04x" % addr)
    for n in names:
        print("%s = $%04x" % (n, addr))


def debug_info():
    """Infos de débogage du programme courant (chargées à la demande)."""
    if "dbginfo" not in CONTEXT:
        CONTEXT["dbginfo"] = DebugInfo(CONTEXT.get("dbgfile"))
    return CONTEXT["dbginfo"]


CONTEXT = {}
# Segments ld65 contenant du code (les autres sont affichés en .byte).
CODE_SEGMENTS = {"CODE", "STARTUP", "ONCE", "LOWCODE", "INIT"}


def cmd_disasm(mon, labels, args):
    """disasm [ADDR|pc] [N] : sans ADDR (ou "pc"), autour du PC (contexte
    avant inclus)."""
    regs = mon.registers()
    pc = regs.get("PC", 0)
    count = parse_int(args[1]) if len(args) > 1 else 20
    if not 1 <= count <= 500:
        raise DbgError("N hors de 1-500")
    dbgi = debug_info()
    if args and args[0].lower() != "pc":
        start = parse_addr(args[0], labels)
        base = start
        mem = mon.mem_get(base, min(0xFFFF, start + 3 * count + 2))
    else:
        before = min(6, count // 3)
        seg = dbgi.segment_of(pc)
        low = max(0, seg[0] if seg else pc - 3 * before)
        base = max(0, min(low, pc - 3 * before))
        mem = mon.mem_get(base, min(0xFFFF, pc + 3 * count + 2))
        start = find_start(mem, base, pc, before, low)
    bps = [(cp["start"], cp["end"]) for cp in mon.checkpoint_list() if cp["op"] & OP_EXEC]
    addr = start
    for _ in range(count):
        if addr > 0xFFFF or addr - base >= len(mem):
            break
        for name in [n for n in labels.by_addr.get(addr, []) if not n.startswith("__")][:1]:
            print("          %s:" % name)
        seg = dbgi.segment_of(addr)
        if seg and seg[2] not in CODE_SEGMENTS:
            # Données (RODATA, DATA, en-tête BASIC...) : .byte, 8 par ligne,
            # sans dépasser le segment ni le label suivant.
            size = 1
            while (size < 8 and addr + size <= seg[1] and addr + size - base < len(mem)
                   and not labels.by_addr.get(addr + size)):
                size += 1
            raw = mem[addr - base:addr - base + size]
            text = ".byte " + ",".join("$%02x" % b for b in raw)
            raw = raw[:3]  # colonne octets : 3 premiers
        else:
            size, raw, text = decode(mem, base, addr, labels)
        mark = ">" if addr == pc else " "
        bp = "*" if any(s <= addr <= e for s, e in bps) else " "
        print("%s%s  %04x  %-8s  %s" % (mark, bp, addr, " ".join("%02x" % b for b in raw), text))
        addr += size


def cmd_where(mon, labels, args):
    pc = mon.registers().get("PC", 0)
    name = labels.name_of(pc)
    head = "PC=%04x%s" % (pc, " (%s)" % name if name else "")
    loc = debug_info().at(pc)
    if loc is None:
        print("%s (pas d'info source)" % head)
    else:
        print("%s %s:%d  %s" % (head, loc[0], loc[1], source_text(*loc)))


def cmd_lines(mon, labels, args):
    dbgi = debug_info()
    if not dbgi.loaded:
        raise DbgError("pas d'infos de débogage (%s) : make, puis run.sh --monitor"
                       % (CONTEXT.get("dbgfile") or "build/vice.dbg"))
    flt = args[0] if args else ""
    for (fname, line), (start, end) in sorted(dbgi.line_table().items()):
        if flt in fname:
            print("%s:%d $%04x-$%04x" % (fname, line, start, end))


def cmd_segments(mon, labels, args):
    dbgi = debug_info()
    if not dbgi.segments:
        raise DbgError("pas d'infos de débogage (%s)" % (CONTEXT.get("dbgfile") or "build/vice.dbg"))
    for start, end, name in sorted(dbgi.segments):
        print("%-10s $%04x-$%04x %5d" % (name, start, end, end - start + 1))


def cmd_info(mon, labels, args):
    ver, rev = mon.vice_info()
    print("VICE %s (rev %d)" % (ver, rev))


def cmd_quit(mon, labels, args):
    mon.quit()
    mon.was_stopped = True  # plus rien à relancer
    print("quit")


def cmd_ping(mon, labels, args):
    mon.ping()
    print("pong")


COMMANDS = {
    "regs": cmd_regs, "mem": cmd_mem, "poke": cmd_poke, "break": cmd_break,
    "watch": cmd_watch, "delete": cmd_delete, "list": cmd_list, "step": cmd_step,
    "next": cmd_next, "pause": cmd_pause, "jump": cmd_jump, "type": cmd_type,
    "cont": cmd_cont, "wait": cmd_wait,
    "status": cmd_status,
    "reset": cmd_reset, "dump": cmd_dump, "banks": cmd_banks, "disasm": cmd_disasm,
    "where": cmd_where, "lines": cmd_lines, "segments": cmd_segments, "screen": cmd_screen,
    "capture": cmd_capture, "label": cmd_label,
    "info": cmd_info, "quit": cmd_quit, "ping": cmd_ping,
}
OFFLINE = {"label", "lines", "segments"}  # sans VICE
NO_WAIT = {"status", "ping"}   # répondues sans envoyer de commande à VICE
AUTOSTART_WAIT = 30            # secondes


def autostart_running():
    """Vrai si run.sh signale un autostart en cours (build/vice.state)."""
    try:
        with open(os.path.join(BUILD, "vice.state")) as f:
            return f.read().strip() == "starting"
    except OSError:
        return False  # pas de fichier : instance lancée autrement


def wait_autostart():
    """run.sh écrit build/vice.state = starting pendant l'autostart : toute
    activité du moniteur à ce moment peut bloquer l'autostart. On attend."""
    deadline = time.monotonic() + AUTOSTART_WAIT
    while autostart_running():
        if time.monotonic() >= deadline:
            raise Timeout("autostart toujours en cours après %d s (build/vice.state)" % AUTOSTART_WAIT)
        time.sleep(0.1)


KEEP_STATE = {"cont", "quit"}  # ne pas relancer l'émulateur après coup


def default_labels_path():
    return os.environ.get("C64_LABELS", os.path.join(BUILD, "vice.labels"))


def default_dbgfile_path():
    return os.environ.get("C64_DBGFILE", os.path.join(BUILD, "vice.dbg"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dbg.py", description=__doc__.split("\n")[0],
        epilog="Liste des commandes et syntaxe des adresses : en-tête de tools/dbg.py.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("C64_MONITOR_PORT", 6502)))
    ap.add_argument("--labels", default=default_labels_path())
    ap.add_argument("--dbgfile", default=default_dbgfile_path(),
                    help="infos de débogage ld65 (where, lines, disasm)")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--sock", default=None, help="socket Unix du démon")
    ap.add_argument("--daemon", action="store_true", help="mode démon (usage interne)")
    ap.add_argument("command", nargs="?", choices=sorted(COMMANDS))
    # REMAINDER : les options après la commande (screen --lower, capture
    # --full) lui appartiennent, pas à dbg.py.
    ap.add_argument("args", nargs=argparse.REMAINDER)
    opts = ap.parse_args(argv)

    if opts.daemon:
        os.makedirs(BUILD, exist_ok=True)
        Daemon(opts.port, opts.sock or daemon_sock_path()).run()
        return 0
    if not opts.command:
        ap.error("commande manquante")

    labels = Labels(opts.labels)
    CONTEXT["dbgfile"] = opts.dbgfile
    handler = COMMANDS[opts.command]
    mon = None
    try:
        if opts.command in OFFLINE:
            handler(None, labels, opts.args)
            return 0
        if opts.command == "status" and autostart_running():
            # Pas même de connexion (ni démarrage du démon) pendant l'autostart.
            print("starting")
            return 0
        if opts.command not in NO_WAIT:
            wait_autostart()
        mon = Monitor(opts.port, opts.timeout, opts.sock)
        try:
            handler(mon, labels, opts.args)
        finally:
            # Remet l'émulateur dans l'état trouvé : s'il tournait, il repart.
            if opts.command not in KEEP_STATE and mon.touched_vice and not mon.was_stopped:
                try:
                    mon.exit_monitor()
                except DbgError:
                    pass
        return 0
    except DbgError as e:
        print("dbg.py: %s" % e, file=sys.stderr)
        return e.exit_code
    except (ValueError, struct.error) as e:
        print("dbg.py: argument invalide : %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print("dbg.py: erreur d'E/S : %s" % e, file=sys.stderr)
        return 2
    finally:
        if mon is not None:
            mon.close()


if __name__ == "__main__":
    sys.exit(main())
