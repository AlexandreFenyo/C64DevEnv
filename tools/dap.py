#!/usr/bin/env python3
"""dap.py - adaptateur de débogage VS Code (Debug Adapter Protocol) pour VICE.

Bibliothèque standard uniquement. VS Code le lance via l'extension
tools/vscode/ (type de débogage "c64") et lui parle sur stdin/stdout.
Il passe par le démon de tools/dbg.py (socket build/dbg.sock) : le
portail, dbg.py en ligne de commande et VS Code partagent la même
instance VICE et voient les mêmes arrêts.

Requêtes :
  launch   make (si "build"), run.sh --monitor --load-only (programme chargé
           sans RUN), points d'arrêt posés, puis RUN tapé au clavier ;
           "stopOnEntry" : arrêt sur main (C) ou sur le point d'entrée (asm).
           À la fin de la session, VICE est arrêté.
  attach   s'attache à l'instance lancée par make debug / le portail
           (labels et infos source de build/vice.*) ; la quitte en la
           laissant tourner.

Pas à pas : ligne source (asm ou C), instruction (vue Désassemblage),
entrée/sortie de sous-programme ; les JSR vers du code sans source (ROM,
runtime cc65) sont franchis d'un bloc ; une IRQ survenue pendant un pas
est exécutée sans s'y arrêter. Points d'arrêt : lignes, fonctions/labels,
instructions, données (lecture/écriture d'une variable). Variables :
registres, locales C (pile logicielle cc65), globales, pile, écran.
Console de débogage : toute commande de dbg.py (regs, mem $0400 32,
screen, disasm...) ou une expression : label, $adresse, variable C,
avec un format optionnel ",b" ",w" ",l" ",s" ou ",N" (N octets).

Journal : build/dap.log.
"""
import base64
import contextlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbg  # noqa: E402

ROOT, BUILD = dbg.ROOT, dbg.BUILD
THREAD_ID = 1
POLL_INTERVAL = 0.15       # s, surveillance de l'état de VICE pendant l'exécution
MAX_LINE_STEPS = 500       # instructions au plus pour un pas « ligne »
QUICK_WAIT = 0.5           # s : attente directe d'un arrêt proche (retour de JSR)
MAX_FRAMES = 12
ROM_START = 0xA000
SOURCE_EXTS = (".s", ".c", ".inc", ".h", ".asm")
PROGRAM_DIRS = ("src", "examples", "mygame")   # SRC_DIRS du Makefile
CODE_SEGMENTS = dbg.CODE_SEGMENTS
DATA_SEGMENTS = {"DATA", "BSS", "RODATA", "ZEROPAGE"}
LOG_PATH = os.path.join(BUILD, "dap.log")
REPL_REFRESH = {"step", "next", "jump", "cont", "pause", "reset", "wait", "poke", "type", "quit"}
REPL_KEEP = {"cont", "quit"}   # comme dbg.py : ne pas relancer l'émulateur après coup


class DapError(Exception):
    pass


def log(fmt, *args):
    try:
        os.makedirs(BUILD, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args if args else fmt))
    except OSError:
        pass


def hexaddr(addr):
    return "0x%04X" % addr


def parse_ref(ref, offset=0):
    try:
        return int(str(ref), 0) + (offset or 0)
    except ValueError:
        raise DapError("référence mémoire invalide : %s" % ref)


class Mon(dbg.Monitor):
    """Monitor de dbg.py, avec la liste des registres mise en cache."""
    _names = None

    def registers_available(self):
        if Mon._names is None:
            Mon._names = super().registers_available()
        return Mon._names


# ---------------------------------------------------------------------------
# Types C : cc65 2.19 n'écrit pas les types dans le .dbg ; on les déduit de
# la déclaration dans le source (heuristique), sinon de la place occupée.
# ---------------------------------------------------------------------------
C_BASE_TYPES = [
    (r"(?:unsigned\s+|signed\s+)?char", 1), (r"(?:unsigned\s+|signed\s+)?short(?:\s+int)?", 2),
    (r"(?:unsigned\s+|signed\s+)?long(?:\s+int)?", 4), (r"(?:unsigned\s+|signed\s+)?int", 2),
    (r"unsigned|signed", 2), (r"u?int8_t|bool|_Bool", 1), (r"u?int16_t|size_t", 2),
    (r"u?int32_t", 4),
]
C_TYPE_ALT = "|".join("(?:%s)" % t for t, _ in C_BASE_TYPES)


def c_type_of(path, name, before_line=None):
    """(texte du type, taille élémentaire, signé, pointeur, nb d'éléments) ou None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except OSError:
        return None
    rx = re.compile(r"(?:\b(?:const|volatile|static|register|extern)\s+)*\b(%s)\b\s*(\*?)\s*\b%s\b"
                    r"\s*(?:\[\s*(\d+)\s*\])?\s*[;,)=\[]" % (C_TYPE_ALT, re.escape(name)))
    best = None
    for i, text in enumerate(lines, 1):
        m = rx.search(text.split("//")[0])
        if not m:
            continue
        if best is None or before_line is None or i <= before_line:
            best = m
        if before_line is not None and i > before_line:
            break
    if best is None:
        return None
    base = re.sub(r"\s+", " ", best.group(1))
    size = next(sz for t, sz in C_BASE_TYPES if re.fullmatch(t, base))
    pointer = bool(best.group(2))
    count = int(best.group(3)) if best.group(3) else 1
    signed = not (base.startswith("unsigned") or base.startswith("uint") or "char" in base
                  and not base.startswith("signed") or base in ("bool", "_Bool", "size_t"))
    text = base + (" *" if pointer else "") + ("[%d]" % count if best.group(3) else "")
    if pointer:
        size, signed = 2, False
    return text, size, signed, pointer, count


COLOR_NAMES = ("noir", "blanc", "rouge", "cyan", "violet", "vert", "bleu", "jaune", "orange", "marron",
               "rose", "gris foncé", "gris", "vert clair", "bleu clair", "gris clair")


def color_name(value):
    return "%d %s" % (value & 15, COLOR_NAMES[value & 15])


def fmt_scalar(data, signed):
    v = int.from_bytes(data, "little")
    if signed and data and data[-1] & 0x80:
        v -= 1 << (8 * len(data))
    return "%d ($%0*x)" % (v, 2 * len(data), int.from_bytes(data, "little"))


def petscii_text(data):
    out = []
    for b in data:
        if b == 0:
            break
        if 0x41 <= b <= 0x5A:
            out.append(chr(b + 32))       # minuscules PETSCII -> ascii
        elif 0xC1 <= b <= 0xDA:
            out.append(chr(b - 0x80))
        elif 32 <= b < 127:
            out.append(chr(b))
        elif b == 13:
            out.append("\\n")
        else:
            out.append(".")
    return "".join(out)


# ---------------------------------------------------------------------------
# Programme : labels + infos de débogage + table d'adresses
# ---------------------------------------------------------------------------
class Program:
    def __init__(self, name, labels_path, dbg_path):
        self.name = name
        self.labels = dbg.Labels(labels_path)
        self.info = dbg.DebugInfo(dbg_path)
        self.dbg_path = dbg_path
        self.addr_loc = {}      # adresse -> (fichier, ligne) (fichiers existants)
        self.file_lines = {}    # chemin réel -> {ligne: [(début, fin)]} (segments de code)
        best = {}
        for start, end, fname, line, typ in self.info.entries:
            path = dbg.source_path(fname)
            if not os.path.isfile(path):
                continue
            seg = self.info.segment_of(start)
            if seg and seg[2] in CODE_SEGMENTS:
                self.file_lines.setdefault(os.path.realpath(path), {}) \
                    .setdefault(line, []).append((start, end))
            key = (typ != 1, end - start)
            for a in range(start, end + 1):
                if a not in best or key < best[a]:
                    best[a] = key
                    self.addr_loc[a] = (fname, line)
        self.span_starts = sorted({(s, self.addr_loc[s]) for s, e, f, ln, t in self.info.entries
                                   if s in self.addr_loc and self.addr_loc[s] == (f, ln)
                                   and (self.info.segment_of(s) or (0, 0, ""))[2] in CODE_SEGMENTS})
        self.symbols = {}       # nom -> (adresse, segment, type) : symboles du programme
        for name_, val, seg, typ in self.info.user_symbols():
            self.symbols.setdefault(name_, (val, seg, typ))
        self.label_addrs = sorted(self.labels.by_addr)
        main = self.labels.lookup("_main")
        starts = [s for s, e, n in self.info.segments if n in ("STARTUP", "CODE") and s >= 0x0801]
        self.entry = main if main is not None else (min(starts) if starts else 0x080D)
        self.sp_addr = self.labels.lookup("sp") if self.labels.lookup("sp") is not None else 0x02
        self.is_c = any(f.endswith(".c") for f in self.info.files.values()
                        if os.path.isfile(dbg.source_path(f)))

    def loc(self, addr):
        return self.addr_loc.get(addr)

    def line_ranges(self, path, line):
        """(ligne effective, [(début, fin)]) pour un point d'arrêt sur
        path:line : la première ligne ≥ line qui a du code (comme gdb) ;
        plages contiguës fusionnées."""
        table = self.file_lines.get(os.path.realpath(path), {})
        cands = [ln for ln in table if line <= ln <= line + 50]
        if not cands:
            return None, []
        eff = min(cands)
        ranges = []
        for start, end in sorted(table[eff]):
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        return eff, ranges

    def line_addrs(self, path, line):
        """(ligne effective, [début de chaque plage])."""
        eff, ranges = self.line_ranges(path, line)
        return eff, [s for s, e in ranges]

    def lookup(self, name):
        """Adresse d'un label/symbole : nom exact, _nom (C), puis équivalences."""
        for n in (name, "_" + name):
            a = self.labels.lookup(n)
            if a is not None:
                return a
            if n in self.symbols:
                return self.symbols[n][0]
        return None

    def symbol_size(self, addr, cap=64):
        """Taille d'une donnée : écart jusqu'au label suivant (borné)."""
        import bisect
        i = bisect.bisect_right(self.label_addrs, addr)
        nxt = self.label_addrs[i] if i < len(self.label_addrs) else addr + 1
        seg = self.info.segment_of(addr)
        if seg:
            nxt = min(nxt, seg[1] + 1)
        return max(1, min(cap, nxt - addr))

    def function_name(self, pc):
        f = self.info.function_at(pc)
        if f:
            return f[1]
        # asm : label de code le plus proche en amont, dans le même segment
        seg = self.info.segment_of(pc)
        best = None
        for name, (val, sseg, typ) in self.symbols.items():
            if typ == "lab" and sseg in CODE_SEGMENTS and val <= pc and seg is not None and seg[2] == sseg:
                if best is None or val > best[0]:
                    best = (val, name)
        if best:
            return best[1] if best[0] == pc else "%s+%d" % (best[1], pc - best[0])
        name = self.labels.name_of(pc)
        if name:
            return name
        if 0xA000 <= pc <= 0xBFFF or 0xE000 <= pc <= 0xE4FF:   # BASIC déborde en $E000
            return "BASIC $%04x" % pc
        if pc >= 0xE000:
            return "KERNAL $%04x" % pc
        return "$%04x" % pc


# ---------------------------------------------------------------------------
# Session DAP
# ---------------------------------------------------------------------------
class Session:
    def __init__(self, out):
        self.out = out
        self.out_lock = threading.Lock()
        self.seq = 1
        self.tasks = queue.Queue()
        self.port = int(os.environ.get("C64_MONITOR_PORT", 6502))
        self.timeout = 5.0
        self.prog = None
        self.mode = None          # "launch" | "attach"
        self.connected = False    # VICE prêt, surveillance active
        self.running = False
        self.gen = None           # pas à pas en cours (générateur)
        self.mon = None
        self.bp_sets = {}         # (genre, clé) -> [ {id, cps, ...} ]
        self.cp_owner = {}        # n° checkpoint -> (genre, id DAP)
        self.next_bp = 1
        self.refs = {}
        self.frames = []
        self.entry_cp = None
        self.done = False
        self.stop_on_entry = False
        self.io_bank = None
        self.targets = None       # cibles de saut du programme (points d'entrée des lignes)
        self.src_ranges = {}      # fichier -> plages des lignes portant un point d'arrêt

    # --- E/S DAP ---------------------------------------------------------
    def send(self, msg):
        msg["seq"] = self.seq
        self.seq += 1
        data = json.dumps(msg).encode("utf-8")
        with self.out_lock:
            self.out.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
            self.out.flush()

    def event(self, name, body=None):
        log("event %s %s", name, json.dumps(body or {})[:200])
        self.send({"type": "event", "event": name, "body": body or {}})

    def output(self, text, category="console"):
        if text and not text.endswith("\n"):
            text += "\n"
        self.event("output", {"category": category, "output": text})

    def respond(self, req, body=None, error=None):
        msg = {"type": "response", "request_seq": req["seq"], "command": req["command"],
               "success": error is None}
        if error is not None:
            msg["message"] = error
            msg["body"] = {"error": {"id": 1, "format": error.replace("{", "(").replace("}", ")"),
                                     "showUser": True}}
        else:
            msg["body"] = body or {}
        self.send(msg)

    # --- boucle principale ---------------------------------------------------
    def reader(self, inp):
        while True:
            headers = {}
            while True:
                line = inp.readline()
                if not line:
                    self.tasks.put(None)
                    return
                line = line.strip()
                if not line:
                    break
                k, _, v = line.decode("ascii", "replace").partition(":")
                headers[k.strip().lower()] = v.strip()
            body = inp.read(int(headers.get("content-length", 0)))
            try:
                msg = json.loads(body.decode("utf-8"))
            except ValueError:
                continue
            if msg.get("type") == "request":
                self.tasks.put(msg)

    def run(self, inp):
        threading.Thread(target=self.reader, args=(inp,), daemon=True).start()
        req = False
        while not self.done:
            try:
                req = self.tasks.get(timeout=POLL_INTERVAL)
            except queue.Empty:
                req = False
            if req is None:       # VS Code a fermé le canal
                self.shutdown(terminate=self.mode == "launch")
                break
            if req:
                self.handle(req)
            if self.connected and not self.done:
                try:
                    self.poll()
                except dbg.NotRunning as e:
                    self.vice_gone(str(e))
                except dbg.DbgError as e:
                    log("poll: %s", e)
        # Après « disconnect » : attendre que VS Code ferme le canal (sinon
        # il signale une erreur de lecture sur un adaptateur déjà parti).
        deadline = time.monotonic() + 3
        while req is not None and time.monotonic() < deadline:
            try:
                req = self.tasks.get(timeout=0.2)
            except queue.Empty:
                pass

    def handle(self, req):
        cmd = req.get("command", "")
        args = req.get("arguments") or {}
        log("request %s %s", cmd, json.dumps(args)[:300])
        fn = getattr(self, "req_" + cmd, None)
        if fn is None:
            self.respond(req, error="requête non prise en charge : %s" % cmd)
            return
        try:
            body = fn(args, req)
        except DapError as e:
            self.respond(req, error=str(e))
            return
        except dbg.NotRunning as e:
            self.respond(req, error="VICE injoignable : %s" % e)
            if self.connected:
                self.vice_gone(str(e))
            return
        except dbg.DbgError as e:
            self.respond(req, error=str(e))
            return
        except Exception as e:  # noqa: BLE001 - l'adaptateur ne doit pas mourir
            log("exception %s", traceback.format_exc())
            self.respond(req, error="erreur interne de dap.py : %s (voir build/dap.log)" % e)
            return
        if body is not False:     # False : réponse déjà envoyée
            self.respond(req, body)

    @contextlib.contextmanager
    def vice(self):
        """Connexion au démon dbg.py le temps d'une opération. Si VICE
        tournait et qu'on l'a interrompu, il repart à la fin (sauf si
        l'opération l'a laissé arrêté : mon.was_stopped = True)."""
        if self.mon is not None:      # appel imbriqué : on réutilise
            yield self.mon
            return
        mon = Mon(self.port, self.timeout)
        self.mon = mon
        try:
            yield mon
        finally:
            try:
                if mon.touched_vice and not mon.was_stopped and not getattr(mon, "keep", False):
                    mon.exit_monitor()
            except dbg.DbgError:
                pass
            mon.close()
            self.mon = None

    # --- surveillance de l'état ----------------------------------------------
    def poll(self):
        with self.vice() as mon:
            st = mon.status()
            if st["stopped"]:
                if self.gen is not None:
                    self.resume_gen(st)
                elif self.running:
                    self.running = False
                    self.report_stop(self.classify(st))
            elif not self.running and self.gen is None:
                # Relancé par quelqu'un d'autre (portail, dbg.py cont).
                self.running = True
                self.refs.clear()
                self.event("continued", {"threadId": THREAD_ID, "allThreadsContinued": True})

    def classify(self, st):
        hit = st.get("hit")
        if hit is not None and hit == self.entry_cp:
            return {"reason": "entry"}
        if hit in self.cp_owner:
            kind, bp_id = self.cp_owner[hit]
            reason = {"source": "breakpoint", "function": "function breakpoint",
                      "instruction": "instruction breakpoint", "data": "data breakpoint"}[kind]
            return {"reason": reason, "hitBreakpointIds": [bp_id]}
        return {"reason": "pause", "description": "arrêté"}

    def report_stop(self, info):
        self.running = False
        self.refs.clear()
        self.frames = []
        body = {"threadId": THREAD_ID, "allThreadsStopped": True}
        body.update(info or {"reason": "step"})
        self.event("stopped", body)

    def vice_gone(self, why):
        log("VICE disparu : %s", why)
        self.connected = False
        self.running = False
        self.gen = None
        self.output("VICE s'est arrêté (%s)" % why)
        if self.mode == "launch":
            subprocess.run([os.path.join(ROOT, "tools", "stop.sh"), "--quiet"], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.event("terminated")

    # --- générateurs de pas à pas ------------------------------------------
    # Un générateur pilote VICE à travers self.mon ; « yield » signifie :
    # VICE a été relancé, rends-moi la main (avec l'état d'arrêt) quand il
    # s'arrête. Pendant ce temps, l'adaptateur reste disponible (pause,
    # points d'arrêt, portail...). Valeur de retour : infos d'arrêt (dict)
    # ou None pour un pas normal.
    def start_gen(self, gen):
        self.gen = gen
        self.running = False
        self._step_gen(lambda: next(gen))

    def resume_gen(self, st):
        self._step_gen(lambda: self.gen.send(st))

    def _step_gen(self, advance):
        try:
            advance()
            self.running = True          # le générateur attend un arrêt
        except StopIteration as e:
            self.gen = None
            self.report_stop(e.value)
        except dbg.NotRunning:
            self.gen = None
            raise
        except dbg.DbgError as e:
            self.gen = None
            self.output("pas à pas interrompu : %s" % e, "stderr")
            self.report_stop({"reason": "exception", "description": str(e)})

    def abort_gen(self):
        """Abandonne le pas en cours (pause, déconnexion) : ses blocs finally
        suppriment ses points d'arrêt."""
        gen, self.gen = self.gen, None
        if gen is not None:
            try:
                gen.close()
            except dbg.DbgError:
                pass

    def regs(self):
        return self.mon.registers()

    def mem(self, start, end):
        return self.mon.mem_get(max(0, start), min(0xFFFF, end))

    def io(self, start, end):
        """Registres des puces lus dans la banque « io » de VICE : sans effet
        de bord, et visibles même si le programme a masqué les E/S ($01)."""
        if self.io_bank is None:
            self.io_bank = self.mon.bank_id("io")
        return self.mon.mem_get(start, end, self.io_bank)

    def g_run_to(self, addrs, sp_min=None):
        """Relance VICE jusqu'à l'une des adresses (points d'arrêt à nous).
        sp_min : ignorer un arrêt atteint avec SP < sp_min (appel récursif
        plus profond). Renvoie (état d'arrêt, atteint)."""
        cps = []
        try:
            for a in sorted(set(addrs)):
                cps.append(self.mon.checkpoint_set(a, a, dbg.OP_EXEC)["num"])
            while True:
                self.mon.exit_monitor()
                # Arrêt rapide (cas courant : retour d'un JSR) : on l'attend
                # sur place ; sinon on rend la main et la surveillance
                # reprendra le générateur à l'arrêt.
                if self.mon.wait_stopped(QUICK_WAIT) is not None:
                    st = self.mon.status()
                else:
                    st = yield
                pc, hit = st["pc"], st.get("hit")
                ours = hit in cps or (pc in addrs and hit not in self.cp_owner)
                if ours and sp_min is not None and self.regs().get("SP", 0xFF) < sp_min:
                    continue
                return st, ours
        finally:
            for n in cps:
                try:
                    self.mon.checkpoint_delete(n)
                except dbg.DbgError:
                    pass

    def successors(self, pc, code, regs):
        """Adresses possibles après l'instruction en pc (None : inconnu)."""
        op = code[0]
        if op not in dbg.OPCODES:
            return None
        mn, mode = dbg.OPCODES[op]
        size = dbg.MODE_SIZE[mode]
        fall = (pc + size) & 0xFFFF
        word = code[1] | (code[2] << 8) if size == 3 else 0
        sp = regs.get("SP", 0xFF)
        if mode == "rel":
            off = code[1] - 256 if code[1] > 127 else code[1]
            return {fall, (pc + 2 + off) & 0xFFFF}
        if mn == "JSR" or (mn == "JMP" and mode == "abs"):
            return {word}
        if mn == "JMP":
            lo = self.mem(word, word)[0]
            hi = self.mem((word & 0xFF00) | ((word + 1) & 0xFF), (word & 0xFF00) | ((word + 1) & 0xFF))[0]
            return {lo | (hi << 8)}
        if mn in ("RTS", "RTI"):
            st = self.mem(0x100, 0x1FF)
            k = 1 if mn == "RTI" else 0
            ret = st[(sp + 1 + k) & 0xFF] | (st[(sp + 2 + k) & 0xFF] << 8)
            return {(ret + 1) & 0xFFFF if mn == "RTS" else ret}
        if mn == "BRK":
            v = self.mem(0xFFFE, 0xFFFF)
            return {v[0] | (v[1] << 8)}
        return {fall}

    def g_step_instr(self, into):
        """Une instruction. JSR franchi si into est faux. Une interruption
        prise pendant le pas est exécutée jusqu'à son retour."""
        for _ in range(3):
            regs = self.regs()
            pc, sp = regs["PC"], regs.get("SP", 0xFF)
            code = self.mem(pc, pc + 2) + b"\0\0"
            if code[0] == 0x20 and not into:
                st, ours = yield from self.g_run_to([(pc + 3) & 0xFFFF], sp_min=sp)
                return None if ours else self.classify(st)
            succ = self.successors(pc, code, regs)
            self.mon.advance(1, False)
            regs = self.regs()
            npc = regs["PC"]
            if succ is None or npc in succ:
                return None
            # Interruption (IRQ, NMI) : on cherche son adresse de retour dans
            # la pile et on y retourne.
            nsp = regs.get("SP", 0xFF)
            stack = self.mem(0x100, 0x1FF)
            ret = None
            for k in range(1, 10):
                lo, hi = stack[(nsp + k + 1) & 0xFF], stack[(nsp + k + 2) & 0xFF]
                cand = lo | (hi << 8)
                if cand in succ or cand == pc:
                    ret = cand
                    break
            if ret is None:
                return None
            st, ours = yield from self.g_run_to([ret])
            if not ours:
                return self.classify(st)
            if ret != pc:
                return None
            # l'interruption a eu lieu avant l'instruction : on recommence
        return None

    def g_step_line(self, into):
        """Pas « ligne source » : exécute jusqu'à une autre ligne."""
        regs = self.regs()
        loc0 = self.prog.loc(regs["PC"])
        if loc0 is None:
            return (yield from self.g_step_instr(into))
        for _ in range(MAX_LINE_STEPS):
            regs = self.regs()
            pc = regs["PC"]
            code = self.mem(pc, pc + 2) + b"\0\0"
            if into and code[0] == 0x20:
                target = code[1] | (code[2] << 8)
                if self.prog.loc(target) is not None:
                    stop = yield from self.g_step_instr(True)
                    if stop:
                        return stop
                    # Fonction C : on saute son prologue (jsr pusha/pushax, jsr
                    # decspN), comme gdb, pour arriver avec les paramètres et
                    # les locales en place sur la pile C.
                    f = self.prog.info.function_at(target)
                    if f and min(s for s, e in self.prog.info.scopes[f[0]]["ranges"]) == target:
                        return (yield from self.g_step_line(False))
                    return None
            stop = yield from self.g_step_instr(False)
            if stop:
                return stop
            regs = self.regs()
            loc = self.prog.loc(regs["PC"])
            if loc is None:
                if code[0] in (0x60, 0x40):
                    return None       # retour dans du code sans source (ROM, runtime)
                # Saut dans du code sans source (ex. « jmp incsp2 » de cc65) :
                # on le laisse revenir (RTS) à son appelant.
                stack = self.mem(0x100, 0x1FF)
                sp = regs.get("SP", 0xFF)
                ret = ((stack[(sp + 1) & 0xFF] | (stack[(sp + 2) & 0xFF] << 8)) + 1) & 0xFFFF
                if self.prog.loc(ret) is None:
                    return None
                st, ours = yield from self.g_run_to([ret], sp_min=(sp + 2) & 0xFF)
                if not ours:
                    return self.classify(st)
                loc = self.prog.loc(self.regs()["PC"])
            if loc != loc0:
                return None
        # Toujours sur la même ligne (boucle) : on court jusqu'au début d'une
        # autre ligne ou au retour de la fonction.
        others = [a for a, loc in self.prog.span_starts if loc != loc0]
        regs = self.regs()
        stack = self.mem(0x100, 0x1FF)
        sp = regs.get("SP", 0xFF)
        ret = ((stack[(sp + 1) & 0xFF] | (stack[(sp + 2) & 0xFF] << 8)) + 1) & 0xFFFF
        if self.mem(ret - 3, ret - 3)[0] == 0x20:
            others.append(ret)
        st, ours = yield from self.g_run_to(others)
        return None if ours else self.classify(st)

    def g_step_out(self):
        frames = self.compute_frames()
        if len(frames) < 2:
            return (yield from self.g_step_instr(False))
        ret = frames[1]["ret"]
        st, ours = yield from self.g_run_to([ret], sp_min=frames[1]["sp"])
        return None if ours else self.classify(st)

    def g_continue_to_entry(self):
        st, ours = yield from self.g_run_to([self.prog.entry])
        return {"reason": "entry", "description": "point d'entrée"} if ours else self.classify(st)

    # --- pile d'appels (heuristique : adresses de retour des JSR) -----------
    def compute_frames(self):
        regs = self.regs()
        pc, sp = regs["PC"], regs.get("SP", 0xFF)
        frames = [{"pc": pc, "ret": None, "sp": sp}]
        stack = self.mem(0x100, 0x1FF)
        i = sp + 1
        while i + 1 <= 0xFF and len(frames) < MAX_FRAMES:
            ret = ((stack[i] | (stack[i + 1] << 8)) + 1) & 0xFFFF
            call = ret - 3
            if call >= 0x0200 and self.mem(call, call)[0] == 0x20:
                frames.append({"pc": call, "ret": ret, "sp": (i + 1) & 0xFF})
                if call >= ROM_START:
                    break           # appelé depuis le BASIC / KERNAL : on s'arrête là
                i += 2
            else:
                i += 1
        return frames

    # --- requêtes : cycle de vie -------------------------------------------
    def req_initialize(self, args, req):
        return {
            "supportsConfigurationDoneRequest": True,
            "supportsFunctionBreakpoints": True,
            "supportsEvaluateForHovers": True,
            "supportsSetVariable": True,
            "supportsDisassembleRequest": True,
            "supportsSteppingGranularity": True,
            "supportsInstructionBreakpoints": True,
            "supportsReadMemoryRequest": True,
            "supportsWriteMemoryRequest": True,
            "supportsDataBreakpoints": True,
            "supportsTerminateRequest": True,
            "supportsGotoTargetsRequest": True,
            "supportsConditionalBreakpoints": False,
            "supportsRestartRequest": False,
            "exceptionBreakpointFilters": [],
        }

    def resolve_program(self, value):
        v = (value or "").strip()
        if not v:
            raise DapError("« program » manquant (nom du programme, fichier source ou .prg)")
        if v.endswith(".prg"):
            return os.path.basename(v)[:-4]
        if os.path.isfile(v) or v.endswith(SOURCE_EXTS):
            rel = os.path.relpath(os.path.realpath(v), os.path.realpath(ROOT)).split(os.sep)
            if len(rel) >= 3 and rel[0] in PROGRAM_DIRS:
                return rel[1]
            if len(rel) == 2 and rel[0] in PROGRAM_DIRS:
                return os.path.splitext(rel[1])[0]
            raise DapError("%s n'est pas dans %s : programme inconnu (fichier de bibliothèque ? "
                           "ouvrez un source du programme avant F5)" % (v, ", ".join(d + "/" for d in PROGRAM_DIRS)))
        return v

    def run_tool(self, argv, what):
        env = dict(os.environ)
        if not env.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
            env["DISPLAY"] = ":0"          # WSLg
        if not env.get("PULSE_SERVER") and os.path.exists("/mnt/wslg/PulseServer"):
            env["PULSE_SERVER"] = "unix:/mnt/wslg/PulseServer"
        log("exec %s", " ".join(argv))
        self.output("$ " + " ".join(argv))
        proc = subprocess.run(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        text = proc.stdout.decode("utf-8", "replace")
        if text:
            self.output(text.rstrip("\n"))
        if proc.returncode != 0:
            tail = "\n".join(text.strip().split("\n")[-6:])
            raise DapError("%s a échoué (code %d) :\n%s" % (what, proc.returncode, tail))

    def load_program(self, name, labels_path, dbg_path):
        self.prog = Program(name, labels_path, dbg_path)
        dbg.CONTEXT.clear()
        dbg.CONTEXT["dbgfile"] = dbg_path
        dbg.CONTEXT["dbginfo"] = self.prog.info
        if not self.prog.info.loaded:
            self.output("ATTENTION : pas d'infos source (%s) : pas à pas en désassemblage seulement"
                        % dbg_path, "stderr")

    def req_launch(self, args, req):
        self.mode = "launch"
        name = self.resolve_program(args.get("program"))
        self.port = int(args.get("port", self.port))
        if args.get("build", True):
            self.run_tool(["make"], "make")
        prg = os.path.join(BUILD, name + ".prg")
        if not os.path.isfile(prg):
            raise DapError("programme introuvable : build/%s.prg (make list)" % name)
        mode = args.get("mode", "show")
        if mode not in ("show", "headless"):
            raise DapError("« mode » : show ou headless")
        argv = ["tools/run.sh", "--" + mode, "--monitor", "--load-only"]
        if args.get("warp"):
            argv.append("--warp")
        if self.port != 6502:
            argv += ["--port", str(self.port)]
        self.run_tool(argv + [prg], "run.sh")
        self.load_program(name, os.path.join(BUILD, name + ".labels"), os.path.join(BUILD, name + ".dbg"))
        self.stop_on_entry = bool(args.get("stopOnEntry", False))
        self.respond(req, {})
        self.event("initialized")
        return False

    def req_attach(self, args, req):
        self.mode = "attach"
        self.port = int(args.get("port", self.port))
        dbg.wait_autostart()
        if args.get("program"):
            name = self.resolve_program(args["program"])
            labels, dbgf = os.path.join(BUILD, name + ".labels"), os.path.join(BUILD, name + ".dbg")
        else:
            name, labels, dbgf = "?", dbg.default_labels_path(), dbg.default_dbgfile_path()
        try:
            with self.vice() as mon:
                mon.status()
        except dbg.NotRunning as e:
            raise DapError("%s\nLancez d'abord VICE avec le moniteur : make debug PROG=xxx, "
                           "ou le portail (case Moniteur)." % e)
        self.load_program(name, labels, dbgf)
        self.respond(req, {})
        self.event("initialized")
        return False

    def req_configurationDone(self, args, req):
        self.respond(req, {})
        self.connected = True
        with self.vice() as mon:
            st = mon.status()
            if self.mode == "launch":
                # Programme chargé, pas lancé : RUN au clavier.
                if not st["stopped"]:
                    mon.ping()
                mon.keyboard_feed(b"RUN\r")
                mon.was_stopped = True     # c'est nous qui relançons
                if self.stop_on_entry:
                    self.start_gen(self.g_continue_to_entry())
                else:
                    mon.exit_monitor()
                    self.running = True
            elif st["stopped"]:
                self.report_stop({"reason": "pause", "description": "déjà arrêté"})
            else:
                self.running = True
        return False

    def shutdown(self, terminate):
        """Fin de session : on retire nos points d'arrêt ; VICE est arrêté
        (launch) ou relancé (attach)."""
        if self.connected:
            try:
                with self.vice() as mon:
                    self.abort_gen()
                    for n in list(self.cp_owner):
                        try:
                            mon.checkpoint_delete(n)
                        except dbg.DbgError:
                            pass
                    self.cp_owner.clear()
                    if not terminate:
                        mon.exit_monitor()
                        mon.keep = True
            except dbg.DbgError as e:
                log("shutdown: %s", e)
        self.connected = False
        if terminate:
            subprocess.run([os.path.join(ROOT, "tools", "stop.sh"), "--quiet"], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def req_disconnect(self, args, req):
        terminate = args.get("terminateDebuggee", self.mode == "launch")
        self.shutdown(terminate=bool(terminate) and self.mode == "launch")
        self.respond(req, {})
        self.done = True
        return False

    def req_terminate(self, args, req):
        self.shutdown(terminate=True)
        self.respond(req, {})
        self.event("terminated")
        return False

    # --- requêtes : exécution ------------------------------------------------
    def req_threads(self, args, req):
        return {"threads": [{"id": THREAD_ID, "name": "6510 (%s)" % (self.prog.name if self.prog else "C64")}]}

    def req_continue(self, args, req):
        self.respond(req, {"allThreadsContinued": True})
        self.refs.clear()
        with self.vice() as mon:
            self.abort_gen()
            mon.was_stopped = True
            if mon.status()["stopped"]:
                self.start_gen(self.g_continue())
            else:
                self.running = True
        return False

    def g_continue(self):
        """Reprise. Si l'arrêt est sur une ligne à point d'arrêt, on la quitte
        d'abord pas à pas : sinon un autre point d'entrée de la même ligne
        arrêterait aussitôt sur elle (voir dbg.line_entries)."""
        pc = self.regs()["PC"]
        rng = next(((s, e) for rs in self.src_ranges.values() for s, e in rs if s <= pc <= e), None)
        for _ in range(64 if rng else 0):
            stop = yield from self.g_step_instr(False)
            if stop:
                return stop
            pc = self.regs()["PC"]
            if not rng[0] <= pc <= rng[1]:
                break
        self.mon.exit_monitor()
        st = yield
        return self.classify(st)

    def req_pause(self, args, req):
        with self.vice() as mon:
            st = mon.status()
            if not st["stopped"]:
                mon.ping()
            mon.was_stopped = True
            self.abort_gen()
        self.respond(req, {})
        self.report_stop({"reason": "pause"})
        return False

    def _step(self, req, make_gen):
        self.respond(req, {})
        with self.vice() as mon:
            if not mon.status()["stopped"]:
                raise DapError("le programme tourne : Pause d'abord")
            mon.was_stopped = True
            self.start_gen(make_gen())
        return False

    def req_next(self, args, req):
        instr = args.get("granularity") == "instruction"
        return self._step(req, lambda: self.g_step_instr(False) if instr else self.g_step_line(False))

    def req_stepIn(self, args, req):
        instr = args.get("granularity") == "instruction"
        return self._step(req, lambda: self.g_step_instr(True) if instr else self.g_step_line(True))

    def req_stepOut(self, args, req):
        return self._step(req, self.g_step_out)

    def req_gotoTargets(self, args, req):
        path = (args.get("source") or {}).get("path", "")
        line, addrs = self.prog.line_addrs(path, int(args.get("line", 0)))
        if not addrs:
            raise DapError("pas de code à cette ligne")
        return {"targets": [{"id": addrs[0], "label": "ligne %d ($%04x)" % (line, addrs[0]),
                             "line": line}]}

    def req_goto(self, args, req):
        addr = int(args["targetId"])
        with self.vice() as mon:
            with contextlib.redirect_stdout(io.StringIO()):
                dbg.cmd_jump(mon, self.prog.labels, ["$%04x" % addr])
            mon.was_stopped = True
        self.respond(req, {})
        self.report_stop({"reason": "goto"})
        return False

    # --- requêtes : points d'arrêt -------------------------------------------
    def replace_bps(self, key, specs):
        """specs : [(adresses, op, infos DAP)] ; remplace le jeu de points
        d'arrêt « key » ; renvoie la liste DAP."""
        result = []
        with self.vice() as mon:
            for old in self.bp_sets.get(key, []):
                for n in old["cps"]:
                    self.cp_owner.pop(n, None)
                    try:
                        mon.checkpoint_delete(n)
                    except dbg.DbgError:
                        pass
            new = []
            for addrs, op, info in specs:
                bp_id = self.next_bp
                self.next_bp += 1
                cps = []
                for a in addrs:
                    end = a[1] if isinstance(a, tuple) else a
                    start = a[0] if isinstance(a, tuple) else a
                    cp = mon.checkpoint_set(start, end, op)
                    cps.append(cp["num"])
                    self.cp_owner[cp["num"]] = (key[0], bp_id)
                new.append({"id": bp_id, "cps": cps})
                d = {"id": bp_id, "verified": bool(cps)}
                d.update(info)
                result.append(d)
            self.bp_sets[key] = new
        return result

    def branch_targets(self):
        if self.targets is None:
            with self.vice():
                self.targets = dbg.branch_targets(self.prog.info, self.mem)
        return self.targets

    def req_setBreakpoints(self, args, req):
        source = args.get("source") or {}
        path = source.get("path", "")
        specs, all_ranges = [], []
        for bp in args.get("breakpoints") or [{"line": ln} for ln in args.get("lines", [])]:
            line, ranges = self.prog.line_ranges(path, int(bp["line"]))
            # Tous les points d'entrée de la ligne (sauts de l'optimiseur au
            # milieu de la ligne compris), pas seulement son début.
            addrs = dbg.line_entries(ranges, self.branch_targets()) if ranges else []
            all_ranges += ranges
            if addrs:
                specs.append((addrs, dbg.OP_EXEC, {"line": line, "source": source,
                                                   "instructionReference": hexaddr(addrs[0])}))
            else:
                specs.append(([], dbg.OP_EXEC, {"line": bp["line"], "source": source,
                                                "message": "pas de code à cette ligne (ou programme non compilé)"}))
        self.src_ranges[os.path.realpath(path)] = all_ranges
        return {"breakpoints": self.replace_bps(("source", os.path.realpath(path)), specs)}

    def req_setFunctionBreakpoints(self, args, req):
        specs = []
        for bp in args.get("breakpoints", []):
            name = bp.get("name", "").strip()
            try:
                addr = self.prog.lookup(name)
                if addr is None:
                    addr = dbg.parse_addr(name, self.prog.labels)
            except dbg.DbgError:
                addr = None
            if addr is None:
                specs.append(([], dbg.OP_EXEC, {"message": "label ou fonction inconnue : %s" % name}))
                continue
            info = {"instructionReference": hexaddr(addr)}
            loc = self.prog.loc(addr)
            if loc:
                info.update(line=loc[1], source=self.source(loc[0]))
            specs.append(([addr], dbg.OP_EXEC, info))
        return {"breakpoints": self.replace_bps(("function", ""), specs)}

    def req_setInstructionBreakpoints(self, args, req):
        specs = []
        for bp in args.get("breakpoints", []):
            addr = parse_ref(bp["instructionReference"], bp.get("offset", 0)) & 0xFFFF
            specs.append(([addr], dbg.OP_EXEC, {"instructionReference": hexaddr(addr)}))
        return {"breakpoints": self.replace_bps(("instruction", ""), specs)}

    def req_setExceptionBreakpoints(self, args, req):
        return {"breakpoints": []}

    def req_dataBreakpointInfo(self, args, req):
        name = args.get("name", "")
        var = None
        ref = args.get("variablesReference")
        with self.vice():
            if ref and ref in self.refs:
                var = next((v for v in self.refs[ref]["vars"]() if v["name"] == name), None)
            if var is None:
                var = self.eval_var(name)
        if not var or "addr" not in var:
            return {"dataId": None, "description": "pas d'adresse mémoire pour %s" % name}
        return {"dataId": "%04x:%d" % (var["addr"], var.get("size", 1)),
                "description": "%s ($%04x, %d octet%s)" % (name, var["addr"], var.get("size", 1),
                                                          "s" if var.get("size", 1) > 1 else ""),
                "accessTypes": ["read", "write", "readWrite"], "canPersist": False}

    def req_setDataBreakpoints(self, args, req):
        specs = []
        for bp in args.get("breakpoints", []):
            addr_s, _, size_s = bp["dataId"].partition(":")
            addr, size = int(addr_s, 16), int(size_s or 1)
            op = {"read": dbg.OP_LOAD, "write": dbg.OP_STORE}.get(bp.get("accessType"),
                                                                  dbg.OP_LOAD | dbg.OP_STORE)
            specs.append(([(addr, addr + size - 1)], op, {}))
        return {"breakpoints": self.replace_bps(("data", ""), specs)}

    # --- requêtes : inspection -----------------------------------------------
    def source(self, fname):
        path = dbg.source_path(fname)
        return {"name": os.path.basename(path), "path": path}

    def req_stackTrace(self, args, req):
        with self.vice() as mon:
            st = mon.status()
            if not st["stopped"]:
                return {"stackFrames": [], "totalFrames": 0}
            self.frames = self.compute_frames()
        out = []
        for i, fr in enumerate(self.frames):
            pc = fr["pc"]
            d = {"id": i, "name": self.prog.function_name(pc), "line": 0, "column": 0,
                 "instructionPointerReference": hexaddr(pc)}
            loc = self.prog.loc(pc)
            if loc:
                d.update(source=self.source(loc[0]), line=loc[1], column=1)
            else:
                d["presentationHint"] = "subtle"
                if "$%04x" % pc not in d["name"]:
                    d["name"] += "  [$%04x]" % pc
            out.append(d)
        start = int(args.get("startFrame", 0))
        levels = int(args.get("levels", 0)) or len(out)
        return {"stackFrames": out[start:start + levels], "totalFrames": len(out)}

    def new_ref(self, vars_fn):
        ref = len(self.refs) + 1
        self.refs[ref] = {"vars": vars_fn}
        return ref

    def req_scopes(self, args, req):
        frame = int(args.get("frameId", 0))
        if not self.frames:
            with self.vice():
                self.frames = self.compute_frames()
        scopes = []
        if frame == 0:
            # VS Code déplie le premier groupe : les locales en C, sinon les registres.
            if self.prog.is_c and self.frames and self.prog.info.function_at(self.frames[0]["pc"]):
                scopes.append({"name": "Locales", "presentationHint": "locals",
                               "variablesReference": self.new_ref(self.vars_locals), "expensive": False})
            scopes.append({"name": "Registres", "presentationHint": "registers",
                           "variablesReference": self.new_ref(self.vars_registers), "expensive": False})
        scopes.append({"name": "Globales" if self.prog.is_c else "Données du programme",
                       "variablesReference": self.new_ref(self.vars_globals), "expensive": False})
        scopes.append({"name": "Pile 6502", "variablesReference": self.new_ref(self.vars_stack),
                       "expensive": False})
        scopes.append({"name": "Écran ($0400)", "variablesReference": self.new_ref(self.vars_screen),
                       "expensive": True})
        # État des puces : groupes repliés, lus seulement à l'ouverture.
        for name, fn in (("Mémoire ($01, vecteurs)", self.vars_memconfig),
                         ("VIC-II ($D000)", self.vars_vic), ("Sprites", self.vars_sprites),
                         ("SID ($D400)", self.vars_sid), ("CIA 1 ($DC00)", lambda: self.vars_cia(0xDC00)),
                         ("CIA 2 ($DD00)", lambda: self.vars_cia(0xDD00))):
            scopes.append({"name": name, "variablesReference": self.new_ref(fn), "expensive": True})
        return {"scopes": scopes}

    def req_variables(self, args, req):
        ref = int(args.get("variablesReference", 0))
        if ref not in self.refs:
            return {"variables": []}
        with self.vice():
            vars_ = self.refs[ref]["vars"]()
        out = []
        for v in vars_:
            d = {k: v[k] for k in ("name", "value", "type", "evaluateName", "presentationHint") if k in v}
            d["variablesReference"] = v.get("ref", 0)
            if "addr" in v:
                d["memoryReference"] = hexaddr(v["addr"])
            out.append(d)
        return {"variables": out}

    # Variables : dict name, value, [type, addr, size, ref, set]
    def vars_registers(self):
        r = self.regs()
        fl = r.get("FL", 0)
        pc = r.get("PC", 0)
        name = self.prog.labels.name_of(pc)
        out = []
        for reg in ("A", "X", "Y"):
            out.append({"name": reg, "value": "$%02x (%d)" % (r.get(reg, 0), r.get(reg, 0)),
                        "evaluateName": reg, "set": ("reg", reg, 1)})
        out.append({"name": "SP", "value": "$%02x" % r.get("SP", 0), "evaluateName": "SP",
                    "set": ("reg", "SP", 1)})
        out.append({"name": "PC", "value": "$%04x%s" % (pc, " (%s)" % name if name else ""),
                    "evaluateName": "PC", "addr": pc, "set": ("pc",)})
        flag_vars = [{"name": n, "value": "1" if fl & (0x80 >> i) else "0", "set": ("flag", 0x80 >> i)}
                     for i, n in enumerate("NV-BDIZC") if n != "-"]
        out.append({"name": "FLAGS", "value": "%s ($%02x)" % (dbg.flags_str(fl), fl),
                    "ref": self.new_ref(lambda: flag_vars)})
        if "01" in r:
            out.append({"name": "$01 (port 6510)", "value": "$%02x" % r["01"], "addr": 1})
        if "LIN" in r:
            out.append({"name": "raster", "value": "ligne %d, cycle %d" % (r["LIN"], r.get("CYC", 0))})
        return out

    def mem_var(self, name, addr, size, ctype=None, signed=False, pointer=False, count=1, evaluate=None):
        """Variable mémoire (C ou données asm)."""
        v = {"name": name, "addr": addr, "size": size * count, "evaluateName": evaluate or name}
        data = self.mem(addr, addr + size * count - 1)
        if ctype:
            v["type"] = ctype
        if count > 1:
            v["value"] = "[%d] %s" % (count, " ".join("%02x" % b for b in data[:16])
                                      + (" ..." if len(data) > 16 else ""))
            if size == 1:
                v["value"] += "  \"%s\"" % petscii_text(data)
            elems = [self.mem_var("[%d]" % i, addr + i * size, size, signed=signed,
                                  evaluate="%s+%d" % (evaluate or name, i * size) if size == 1 else None)
                     for i in range(min(count, 256))]
            v["ref"] = self.new_ref(lambda: elems)
        elif pointer:
            p = int.from_bytes(data, "little")
            label = self.prog.labels.name_of(p)
            v["value"] = "$%04x%s" % (p, " (%s)" % label if label else "")
            v["set"] = ("mem", addr, 2)
        elif ctype is None and size > 2:
            v["value"] = " ".join("%02x" % b for b in data) + "  |%s|" % petscii_text(data)
        else:
            v["value"] = fmt_scalar(data, signed)
            v["set"] = ("mem", addr, size)
        return v

    def c_var(self, name, addr, gap, line, display=None):
        src = self.c_source()
        t = c_type_of(src, name, line) if src else None
        if t:
            ctype, size, signed, pointer, count = t
            if size * count > gap > 0 and count == 1:
                size = gap
            return self.mem_var(display or name, addr, size, ctype, signed, pointer, count, evaluate=name)
        size = gap if gap in (1, 2, 4) else 2
        return self.mem_var(display or name, addr, size, "(%d octets ?)" % size, size > 1, evaluate=name)

    def c_source(self):
        for f in self.prog.info.files.values():
            if f.endswith(".c") and os.path.isfile(dbg.source_path(f)):
                return dbg.source_path(f)
        return None

    def c_locals(self):
        """[(nom, adresse, taille max)] des locales de la fonction courante,
        ou un message si elles ne sont pas encore sur la pile."""
        r = self.regs()
        pc = r["PC"]
        f = self.prog.info.function_at(pc)
        if not f:
            return [], None
        sid, _ = f
        autos = sorted(self.prog.info.locals_of(sid), key=lambda t: t[1])
        if not autos:
            return [], None
        scope = self.prog.info.scopes[sid]
        fstart = min(s for s, e in scope["ranges"])
        frame_size = -min(o for _, o in autos) if autos[0][1] < 0 else 0
        # Prologue cc65 : jsr pushax (paramètres) puis jsr decspN / subysp
        # (locales). Avant la fin de ce prologue, la pile n'est pas en place.
        code = self.mem(fstart, fstart + 15)
        alloc_end = None
        pos = 0
        while pos + 2 < len(code) and pos < 12:
            if code[pos] == 0x20:
                target = self.prog.labels.name_of(code[pos + 1] | (code[pos + 2] << 8)) or ""
                if target.startswith("decsp") or target == "subysp":
                    alloc_end = fstart + pos + 3
                    break
                pos += 3
            elif code[pos] == 0xA0:   # ldy #N (avant jsr subysp)
                pos += 2
            else:
                break
        if pc == fstart:
            return [], "paramètres pas encore empilés (début de la fonction)"
        spv = self.mem(self.prog.sp_addr, self.prog.sp_addr + 1)
        sp = spv[0] | (spv[1] << 8)
        base = sp + frame_size if alloc_end is None or pc >= alloc_end else sp
        out = []
        for i, (name, offs) in enumerate(autos):
            nxt = autos[i + 1][1] if i + 1 < len(autos) else None
            if offs < 0 and (nxt is None or nxt > 0):
                nxt = 0
            gap = (nxt - offs) if nxt is not None else 0
            out.append((name, (base + offs) & 0xFFFF, gap))
        note = None if alloc_end is None or pc >= alloc_end else "locales pas encore allouées"
        return out, note

    def vars_locals(self):
        loc = self.prog.loc(self.regs()["PC"])
        items, note = self.c_locals()
        out = [self.c_var(n, a, gap, loc[1] if loc else None) for n, a, gap in items]
        if note:
            out.insert(0, {"name": "(note)", "value": note, "presentationHint": {"kind": "virtual"}})
        return out

    def vars_globals(self):
        out = []
        for name, (addr, seg, typ) in sorted(self.prog.symbols.items(), key=lambda kv: kv[1][0]):
            if typ != "lab" or seg not in DATA_SEGMENTS:
                continue
            if self.prog.is_c:
                if not name.startswith("_"):
                    continue          # étiquettes internes de cc65 (L0022...)
                out.append(self.c_var(name[1:], addr, self.prog.symbol_size(addr, 8), None))
            else:
                size = self.prog.symbol_size(addr, 32)
                out.append(self.mem_var(name, addr, size, ctype=None if size > 2 else "octet" if size == 1 else "mot"))
        return out

    def vars_stack(self):
        sp = self.regs().get("SP", 0xFF)
        data = self.mem(0x100 + sp + 1, 0x1FF) if sp < 0xFF else b""
        out = []
        for i, b in enumerate(data[:48]):
            addr = 0x100 + sp + 1 + i
            out.append({"name": "$%04x" % addr, "value": "$%02x" % b, "addr": addr,
                        "set": ("mem", addr, 1)})
        if not out:
            out.append({"name": "(vide)", "value": "SP=$ff"})
        return out

    def vars_screen(self):
        data = self.mem(dbg.SCREEN_BASE, dbg.SCREEN_BASE + dbg.SCREEN_SIZE - 1)
        return [{"name": "%02d" % row, "addr": dbg.SCREEN_BASE + 40 * row,
                 "value": "|%s|" % "".join(dbg.screen_code_to_char(c) for c in data[row * 40:row * 40 + 40])}
                for row in range(25)]

    # --- état des puces du C64 ------------------------------------------
    def raw_regs(self, base, data, names):
        """Registres bruts, modifiables (écriture dans la vue processeur)."""
        return [{"name": "$%04x %s" % (base + i, names[i] if i < len(names) else ""), "addr": base + i,
                 "value": "$%02x  %%%s" % (b, format(b, "08b")), "set": ("mem", base + i, 1)}
                for i, b in enumerate(data)]

    def vic_bank(self):
        return (3 - (self.io(0xDD00, 0xDD00)[0] & 3)) * 0x4000

    def vars_memconfig(self):
        r = self.regs()
        port = r.get("01", self.mem(1, 1)[0])
        lo, hi, ch = port & 1, port & 2, port & 4
        basic = "ROM" if lo and hi else "RAM"
        kernal = "ROM" if hi else "RAM"
        if not (lo or hi):
            dxxx = "RAM"
        else:
            dxxx = "E/S" if ch else "ROM de caractères"
        out = [{"name": "$01 (port 6510)", "value": "$%02x  %%%s" % (port, format(port, "08b")), "addr": 1,
                "set": ("mem", 1, 1)},
               {"name": "$A000-$BFFF", "value": "BASIC " + basic if basic == "ROM" else "RAM"},
               {"name": "$D000-$DFFF", "value": dxxx},
               {"name": "$E000-$FFFF", "value": "KERNAL " + kernal if kernal == "ROM" else "RAM"},
               {"name": "banque VIC", "value": "$%04x-$%04x (CIA 2, $DD00)" % (self.vic_bank(), self.vic_bank() + 0x3FFF)}]
        vec = self.mem(0x0314, 0x0319)
        for i, n in enumerate(("IRQ ($0314)", "BRK ($0316)", "NMI ($0318)")):
            a = vec[2 * i] | (vec[2 * i + 1] << 8)
            label = self.prog.labels.name_of(a)
            out.append({"name": "vecteur " + n, "addr": 0x0314 + 2 * i,
                        "value": "$%04x%s" % (a, " (%s)" % label if label else
                                              " (KERNAL)" if a in (0xEA31, 0xFE66, 0xFE47) else ""),
                        "set": ("mem", 0x0314 + 2 * i, 2)})
        return out

    def vars_vic(self):
        v = self.io(0xD000, 0xD02E)
        d011, d016, d018 = v[0x11], v[0x16], v[0x18]
        bank = self.vic_bank()
        ecm, bmm, mcm = d011 & 0x40, d011 & 0x20, d016 & 0x10
        mode = {(0, 0, 0): "texte standard", (0, 0, 1): "texte multicolore", (0, 1, 0): "bitmap haute résolution",
                (0, 1, 1): "bitmap multicolore", (1, 0, 0): "texte couleur de fond étendue (ECM)"}.get(
                    (bool(ecm), bool(bmm), bool(mcm)), "mode invalide (écran noir)")
        screen = bank + (d018 >> 4) * 0x400
        chars = bank + ((d018 >> 1) & 7) * 0x800
        raster = v[0x12] | ((d011 & 0x80) << 1)
        line = self.regs().get("LIN")
        names = ["M%dX" % (i // 2) if i % 2 == 0 else "M%dY" % (i // 2) for i in range(16)] + [
            "MSBX", "CTRL1", "RASTER", "LPX", "LPY", "SPR_ENA", "CTRL2", "SPR_EXPY", "MEMPTR", "IRQ",
            "IRQ_MASK", "SPR_PRI", "SPR_MCOL", "SPR_EXPX", "SPR-SPR", "SPR-FOND", "BORDURE", "FOND0",
            "FOND1", "FOND2", "FOND3", "SPR_MC0", "SPR_MC1"] + ["SPR%d_COL" % i for i in range(8)]
        out = [{"name": "mode", "value": mode},
               {"name": "écran affiché", "value": "oui" if d011 & 0x10 else "non (DEN=0, bordure seule)"},
               {"name": "mémoire écran", "value": "$%04x" % screen, "addr": screen},
               {"name": "bitmap" if bmm else "jeu de caractères",
                "value": "$%04x%s" % ((bank + (0x2000 if d018 & 8 else 0)) if bmm else chars,
                                       " (ROM de caractères)" if not bmm and bank in (0, 0x8000)
                                       and chars - bank in (0x1000, 0x1800) else ""),
                "addr": (bank + (0x2000 if d018 & 8 else 0)) if bmm else chars},
               {"name": "bordure ($D020)", "value": color_name(v[0x20]), "addr": 0xD020},
               {"name": "fond ($D021)", "value": color_name(v[0x21]), "addr": 0xD021},
               {"name": "ligne raster", "value": "%d%s" % (line if line is not None else raster,
                                                           ", cycle %d" % self.regs().get("CYC", 0) if line is not None else "")},
               {"name": "interruption raster sur la ligne", "value": "%d (%s)" % (
                   raster, "activée" if v[0x1A] & 1 else "désactivée")},
               {"name": "défilement", "value": "X=%d Y=%d" % (d016 & 7, d011 & 7)},
               {"name": "format", "value": "%d colonnes, %d lignes" % (40 if d016 & 8 else 38, 25 if d011 & 8 else 24)},
               {"name": "IRQ en attente / masque", "value": "$%02x / $%02x" % (v[0x19] & 0x8F, v[0x1A] & 0x0F)},
               {"name": "sprites actifs", "value": ", ".join(str(i) for i in range(8) if v[0x15] >> i & 1) or "aucun"}]
        raw = self.raw_regs(0xD000, v, names)
        out.append({"name": "registres bruts", "value": "$D000-$D02E", "ref": self.new_ref(lambda: raw)})
        return out

    def vars_sprites(self):
        v = self.io(0xD000, 0xD02E)
        screen = self.vic_bank() + (v[0x18] >> 4) * 0x400
        ptrs = self.mem(screen + 0x3F8, screen + 0x3FF)
        out = []
        for i in range(8):
            bit = 1 << i
            x = v[2 * i] | (0x100 if v[0x10] & bit else 0)
            data = self.vic_bank() + ptrs[i] * 64
            props = [{"name": "actif", "value": "oui" if v[0x15] & bit else "non"},
                     {"name": "position", "value": "x=%d y=%d" % (x, v[2 * i + 1])},
                     {"name": "couleur", "value": color_name(v[0x27 + i])},
                     {"name": "multicolore", "value": "oui (%s, %s)" % (color_name(v[0x25]), color_name(v[0x26]))
                      if v[0x1C] & bit else "non"},
                     {"name": "agrandi", "value": "%s%s" % ("X " if v[0x1D] & bit else "", "Y" if v[0x17] & bit else "")
                      or "non"},
                     {"name": "derrière le texte", "value": "oui" if v[0x1B] & bit else "non"},
                     {"name": "pointeur ($%04x)" % (screen + 0x3F8 + i), "value": "%d -> données en $%04x" % (ptrs[i], data),
                      "addr": data},
                     {"name": "collisions", "value": "sprite-sprite %s, sprite-fond %s" % (
                         "oui" if v[0x1E] & bit else "non", "oui" if v[0x1F] & bit else "non")}]
            out.append({"name": "sprite %d" % i,
                        "value": ("x=%d y=%d %s" % (x, v[2 * i + 1], color_name(v[0x27 + i]))) if v[0x15] & bit else "inactif",
                        "ref": self.new_ref(lambda p=props: p)})
        return out

    def vars_sid(self):
        v = self.io(0xD400, 0xD41C)
        out = []
        for n in range(3):
            b = 7 * n
            freq = v[b] | (v[b + 1] << 8)
            pw = (v[b + 2] | (v[b + 3] << 8)) & 0x0FFF
            ctrl = v[b + 4]
            waves = [w for bit, w in ((0x10, "triangle"), (0x20, "dent de scie"), (0x40, "carrée"), (0x80, "bruit"))
                     if ctrl & bit] or ["aucune"]
            hz = freq * 985248 / 16777216
            props = [{"name": "fréquence", "value": "$%04x = %.1f Hz (PAL)" % (freq, hz)},
                     {"name": "forme d'onde", "value": "+".join(waves) + (" (largeur %.0f %%)" % (pw / 40.95) if ctrl & 0x40 else "")},
                     {"name": "gate", "value": "ouvert (note jouée)" if ctrl & 1 else "fermé (relâchement)"},
                     {"name": "sync / modulation en anneau", "value": "%s / %s" % ("oui" if ctrl & 2 else "non", "oui" if ctrl & 4 else "non")},
                     {"name": "ADSR", "value": "A=%d D=%d S=%d R=%d" % (v[b + 5] >> 4, v[b + 5] & 15, v[b + 6] >> 4, v[b + 6] & 15)}]
            out.append({"name": "voix %d ($%04x)" % (n + 1, 0xD400 + b),
                        "value": "%s, %.0f Hz, %s" % ("+".join(waves), hz, "gate ouvert" if ctrl & 1 else "gate fermé"),
                        "ref": self.new_ref(lambda p=props: p)})
        filt = (v[0x15] & 7) | (v[0x16] << 3)
        out.append({"name": "volume", "value": "%d/15" % (v[0x18] & 15)})
        out.append({"name": "filtre", "value": "coupure %d, résonance %d, voix %s, %s" % (
            filt, v[0x17] >> 4, ",".join(str(i + 1) for i in range(3) if v[0x17] >> i & 1) or "aucune",
            "+".join(t for bit, t in ((0x10, "passe-bas"), (0x20, "passe-bande"), (0x40, "passe-haut")) if v[0x18] & bit)
            or "aucun type")})
        out.append({"name": "note", "value": "registres en écriture seule sur un vrai C64 : VICE montre la dernière valeur écrite"})
        raw = self.raw_regs(0xD400, v, [])
        out.append({"name": "registres bruts", "value": "$D400-$D41C", "ref": self.new_ref(lambda: raw)})
        return out

    def vars_cia(self, base):
        v = self.io(base, base + 0x0F)
        ta, tb = v[4] | (v[5] << 8), v[6] | (v[7] << 8)
        out = []
        if base == 0xDC00:
            out.append({"name": "rôle", "value": "clavier (port A = colonnes, port B = lignes), joysticks, IRQ du KERNAL (timer A, 60 Hz)"})
        else:
            out.append({"name": "rôle", "value": "banque VIC (port A bits 0-1), port série, NMI"})
            out.append({"name": "banque VIC", "value": "$%04x" % self.vic_bank()})
        out += [{"name": "port A / sens", "value": "$%02x / $%02x" % (v[0], v[2])},
                {"name": "port B / sens", "value": "$%02x / $%02x" % (v[1], v[3])},
                {"name": "timer A", "value": "%d (%s, %s)" % (ta, "en marche" if v[0x0E] & 1 else "arrêté",
                                                           "une fois" if v[0x0E] & 8 else "continu")},
                {"name": "timer B", "value": "%d (%s)" % (tb, "en marche" if v[0x0F] & 1 else "arrêté")},
                {"name": "horloge TOD", "value": "%x:%02x:%02x.%x" % (v[0x0B] & 0x1F, v[0x0A], v[0x09], v[0x08] & 0x0F)},
                {"name": "interruptions (ICR)", "value": "$%02x" % v[0x0D]}]
        raw = self.raw_regs(base, v, ["PRA", "PRB", "DDRA", "DDRB", "TA_LO", "TA_HI", "TB_LO", "TB_HI",
                                       "TOD_10", "TOD_SEC", "TOD_MIN", "TOD_HR", "SDR", "ICR", "CRA", "CRB"])
        out.append({"name": "registres bruts", "value": "$%04x-$%04x" % (base, base + 15), "ref": self.new_ref(lambda: raw)})
        return out

    def req_setVariable(self, args, req):
        ref, name, value = int(args["variablesReference"]), args["name"], args["value"].strip()
        if ref not in self.refs:
            raise DapError("variable inconnue")
        with self.vice() as mon:
            var = next((v for v in self.refs[ref]["vars"]() if v["name"] == name), None)
            if not var or "set" not in var:
                raise DapError("%s n'est pas modifiable" % name)
            kind = var["set"]
            try:
                num = dbg.parse_int(value.split()[0])
            except (ValueError, IndexError):
                raise DapError("valeur invalide : %s (décimal, $hexa ou 0xhexa)" % value)
            if kind[0] == "reg":
                mon.set_register(kind[1], num & 0xFF)
            elif kind[0] == "pc":
                with contextlib.redirect_stdout(io.StringIO()):
                    dbg.cmd_jump(mon, self.prog.labels, [str(num & 0xFFFF)])
            elif kind[0] == "flag":
                fl = self.regs().get("FL", 0)
                fl = (fl | kind[1]) if num else (fl & ~kind[1])
                mon.set_register("FL", fl & 0xFF)
            elif kind[0] == "mem":
                mon.mem_set(kind[1], (num & ((1 << (8 * kind[2])) - 1)).to_bytes(kind[2], "little"))
            new = next((v for v in self.refs[ref]["vars"]() if v["name"] == name), {})
        return {"value": new.get("value", value)}

    # --- évaluation (survol, espions, console) ------------------------------
    def eval_var(self, expr):
        """Variable correspondant à une expression, ou None."""
        expr = expr.strip()
        fmt = None
        m = re.fullmatch(r"(.+?)\s*,\s*(\w+)", expr)
        if m:
            expr, fmt = m.group(1), m.group(2).lower()
        loc = None
        regs = self.regs()
        pc = regs["PC"]
        if fmt is None and self.prog.is_c and re.fullmatch(r"[A-Za-z_]\w*", expr):
            loc = self.prog.loc(pc)
            items, _ = self.c_locals()
            for n, a, gap in items:
                if n == expr:
                    return self.c_var(n, a, gap, loc[1] if loc else None)
            if ("_" + expr) in self.prog.symbols:
                addr = self.prog.symbols["_" + expr][0]
                if self.prog.symbols["_" + expr][1] in DATA_SEGMENTS:
                    return self.c_var(expr, addr, self.prog.symbol_size(addr, 8), None)
        up = expr.upper()
        if fmt is None and up in ("A", "X", "Y", "SP", "PC", "FL", "FLAGS"):
            reg = "FL" if up == "FLAGS" else up
            v = regs.get(reg, 0)
            text = dbg.flags_str(v) if reg == "FL" else ("$%04x" % v if reg == "PC" else "$%02x (%d)" % (v, v))
            return {"name": expr, "value": text}
        addr = self.prog.lookup(expr)
        is_symbol = addr is not None
        if addr is None:
            try:
                addr = dbg.parse_addr(expr, self.prog.labels)
            except dbg.DbgError:
                return None
        addr &= 0xFFFF
        sym = self.prog.symbols.get(expr) or self.prog.symbols.get("_" + expr)
        if fmt is None and sym and sym[2] == "equ":
            data = self.mem(addr, addr)
            return {"name": expr, "value": "= $%x (%d) ; [$%04x] = $%02x" % (addr, addr, addr, data[0]),
                    "addr": addr}
        seg = self.prog.info.segment_of(addr)
        if fmt is None and is_symbol and seg and seg[2] in CODE_SEGMENTS:
            return {"name": expr, "value": "$%04x (code, %s)" % (addr, seg[2]), "addr": addr}
        if fmt in (None, "b"):
            data = self.mem(addr, addr)
            prefix = "$%04x → " % addr if is_symbol else ""
            return {"name": expr, "value": "%s$%02x (%d)" % (prefix, data[0], data[0]), "addr": addr,
                    "size": 1, "set": ("mem", addr, 1)}
        if fmt in ("w", "l"):
            size = 2 if fmt == "w" else 4
            return self.mem_var(expr, addr, size, "mot" if size == 2 else "long", False)
        if fmt == "s":
            data = self.mem(addr, addr + 79)
            return {"name": expr, "value": "\"%s\"" % petscii_text(data), "addr": addr}
        if fmt.isdigit():
            n = max(1, min(256, int(fmt)))
            v = self.mem_var(expr, addr, 1, "octets", count=n)
            return v
        raise DapError("format inconnu : ,%s (b, w, l, s ou un nombre d'octets)" % fmt)

    def req_evaluate(self, args, req):
        expr = (args.get("expression") or "").strip()
        context = args.get("context", "repl")
        with self.vice() as mon:
            if context == "repl":
                word = expr.split()[0] if expr else ""
                if word in ("help", "?", "aide"):
                    return {"result": "Commandes dbg.py : %s\nExpressions : label, $adresse, variable C, "
                                      "registre (A X Y SP PC), suivi de ,b ,w ,l ,s ou ,N"
                                      % " ".join(sorted(dbg.COMMANDS)), "variablesReference": 0}
                if word in dbg.COMMANDS:
                    return self.repl_command(mon, expr)
            # Programme en cours : VICE est interrompu le temps de la lecture.
            var = self.eval_var(expr)
        if var is None:
            raise DapError("inconnu : %s" % expr if context != "repl" else
                           "inconnu : %s (help : liste des commandes)" % expr)
        body = {"result": var["value"], "variablesReference": var.get("ref", 0)}
        if "type" in var:
            body["type"] = var["type"]
        if "addr" in var:
            body["memoryReference"] = hexaddr(var["addr"])
        return body

    def repl_command(self, mon, expr):
        import shlex
        try:
            argv = shlex.split(expr)
        except ValueError as e:
            raise DapError(str(e))
        cmd, args = argv[0], argv[1:]
        if cmd in REPL_REFRESH:
            self.abort_gen()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                dbg.COMMANDS[cmd](mon, self.prog.labels, args)
        except dbg.DbgError as e:
            text = buf.getvalue() + "dbg.py: %s" % e
            return {"result": text.rstrip("\n"), "variablesReference": 0}
        if cmd in REPL_KEEP:
            mon.keep = True
        text = buf.getvalue().rstrip("\n")
        if cmd == "quit":
            self.connected = False
            self.event("terminated")
        elif cmd in REPL_REFRESH:
            st = mon.status()
            stays = mon.was_stopped or cmd in ("step", "next", "jump", "pause", "wait")
            if st["stopped"] and stays and cmd != "cont":
                mon.was_stopped = True
                self.report_stop({"reason": "step", "description": "commande %s" % cmd})
            else:
                self.running = True
                self.refs.clear()
                self.event("continued", {"threadId": THREAD_ID, "allThreadsContinued": True})
        return {"result": text, "variablesReference": 0}

    # --- mémoire et désassemblage -----------------------------------------
    def req_readMemory(self, args, req):
        addr = parse_ref(args["memoryReference"], args.get("offset", 0))
        count = int(args.get("count", 0))
        if addr < 0 or addr > 0xFFFF or count <= 0:
            return {"address": hexaddr(max(0, addr) & 0xFFFF), "unreadableBytes": max(0, count)}
        end = min(0xFFFF, addr + count - 1)
        with self.vice():
            data = self.mem(addr, end)
        return {"address": hexaddr(addr), "data": base64.b64encode(data).decode("ascii"),
                "unreadableBytes": count - len(data)}

    def req_writeMemory(self, args, req):
        addr = parse_ref(args["memoryReference"], args.get("offset", 0))
        data = base64.b64decode(args.get("data", ""))
        if addr < 0 or addr + len(data) - 1 > 0xFFFF:
            raise DapError("écriture hors de $0000-$FFFF")
        with self.vice() as mon:
            if data:
                mon.mem_set(addr, data)
        self.event("memory", {"memoryReference": hexaddr(addr), "offset": 0, "count": len(data)})
        return {"bytesWritten": len(data)}

    def req_disassemble(self, args, req):
        base = parse_ref(args["memoryReference"], args.get("offset", 0)) & 0xFFFF
        ioff = int(args.get("instructionOffset", 0))
        count = int(args.get("instructionCount", 0))
        before = max(0, -ioff)
        lo = max(0, base - 3 * before - 3)
        hi = min(0xFFFF, base + 3 * (count + max(0, ioff)) + 8)
        with self.vice():
            mem = self.mem(lo, hi)
        start = dbg.find_start(mem, lo, base, before, lo) if before else base
        insts, addr = [], start
        while addr <= hi and addr - lo < len(mem):
            size, raw, text = dbg.decode_at(mem, lo, addr, self.prog.labels, self.prog.info)
            insts.append((addr, raw, text))
            addr += size
        idx = next((i for i, t in enumerate(insts) if t[0] >= base), len(insts))
        out, last_loc = [], None
        for k in range(idx + ioff, idx + ioff + count):
            if 0 <= k < len(insts):
                a, raw, text = insts[k]
                d = {"address": hexaddr(a), "instructionBytes": " ".join("%02x" % b for b in raw[:3]),
                     "instruction": text}
                name = self.prog.labels.name_of(a)
                if name and not name.startswith("__"):
                    d["symbol"] = name
                loc = self.prog.loc(a)
                if loc and loc != last_loc:
                    d["location"] = self.source(loc[0])
                    d["line"] = loc[1]
                last_loc = loc
            else:
                a = (start - (idx + ioff - k)) if k < 0 else (insts[-1][0] + (k - len(insts) + 1) if insts else base)
                d = {"address": hexaddr(max(0, min(0xFFFF, a))), "instruction": "??",
                     "presentationHint": "invalid"}
            out.append(d)
        return {"instructions": out}

    def req_source(self, args, req):
        raise DapError("source indisponible (fichier de bibliothèque cc65) : voir le désassemblage")


def main():
    # Le canal DAP passe par le vrai stdout ; tout le reste (print égarés,
    # sous-processus) part dans le journal.
    out = os.fdopen(os.dup(1), "wb", buffering=0)
    os.makedirs(BUILD, exist_ok=True)
    logf = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logf, 1)
    sys.stdout = io.TextIOWrapper(os.fdopen(1, "wb", buffering=0), write_through=True)
    log("--- dap.py démarré (pid %d)", os.getpid())
    Session(out).run(sys.stdin.buffer)
    log("--- dap.py terminé")
    # Sortie immédiate : le fil de lecture de stdin est encore bloqué.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
