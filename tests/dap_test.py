#!/usr/bin/env python3
"""dap_test.py - teste tools/dap.py comme le ferait VS Code : client DAP
sur stdin/stdout de l'adaptateur, VICE en headless.

Scénarios : asm (hello_rts : arrêt au début, pas par-dessus un JSR ROM,
point d'arrêt, registres, survol, console dbg.py, désassemblage, mémoire),
C (squares_c : point d'arrêt sur une ligne, locales/globales, pas à pas,
entrée dans une fonction, pile d'appels, sortie, point d'arrêt sur une
donnée, modification de variable, fin du programme), puis attach à une
instance lancée par run.sh, qui doit survivre à la déconnexion.
"""
import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(cond, what):
    print(("ok : " if cond else "ECHEC : ") + what, flush=True)
    if not cond:
        FAILS.append(what)
    return cond


def line_of(path, text):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if text in line:
                return i
    raise SystemExit("ligne introuvable dans %s : %s" % (path, text))


class Client:
    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "dap.py")],
                                     cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.seq = 1
        self.responses = {}
        self.events = queue.Queue()
        self.lock = threading.Condition()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        out = self.proc.stdout
        while True:
            headers = {}
            while True:
                line = out.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                k, _, v = line.decode().partition(":")
                headers[k.lower()] = v.strip()
            msg = json.loads(out.read(int(headers["content-length"])))
            if msg["type"] == "event":
                self.events.put(msg)
            elif msg["type"] == "response":
                with self.lock:
                    self.responses[msg["request_seq"]] = msg
                    self.lock.notify_all()

    def send(self, command, args=None):
        seq = self.seq
        self.seq += 1
        data = json.dumps({"seq": seq, "type": "request", "command": command,
                           "arguments": args or {}}).encode()
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
        self.proc.stdin.flush()
        return seq

    def request(self, command, args=None, timeout=60, ok=True):
        seq = self.send(command, args)
        deadline = time.monotonic() + timeout
        with self.lock:
            while seq not in self.responses:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise SystemExit("pas de réponse à %s" % command)
                self.lock.wait(left)
            resp = self.responses.pop(seq)
        if ok and not resp["success"]:
            raise SystemExit("%s a échoué : %s" % (command, resp.get("message")))
        return resp

    def body(self, command, args=None, timeout=60):
        return self.request(command, args, timeout)["body"]

    def wait_event(self, name, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise SystemExit("événement %s non reçu" % name)
            try:
                ev = self.events.get(timeout=left)
            except queue.Empty:
                continue
            if ev["event"] == name:
                return ev
            if ev["event"] == "output":
                text = ev["body"].get("output", "")
                if text.strip():
                    print("   | " + text.rstrip().replace("\n", "\n   | "))

    def stopped(self, timeout=30):
        return self.wait_event("stopped", timeout)["body"]

    def top(self):
        frames = self.body("stackTrace", {"threadId": 1})["stackFrames"]
        return frames

    def where(self):
        f = self.top()[0]
        return os.path.basename(f.get("source", {}).get("path", "?")), f["line"], f["name"]

    def variables(self, scope_name, frame=0):
        scopes = self.body("scopes", {"frameId": frame})["scopes"]
        ref = next(s["variablesReference"] for s in scopes if s["name"].startswith(scope_name))
        return {v["name"]: v for v in self.body("variables", {"variablesReference": ref})["variables"]}, ref

    def evaluate(self, expr, context="repl"):
        return self.body("evaluate", {"expression": expr, "context": context, "frameId": 0})["result"]

    def close(self):
        try:
            self.request("disconnect", {}, timeout=20)
        except SystemExit:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def x64sc_alive():
    out = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "stat=,comm="],
                         stdout=subprocess.PIPE, text=True).stdout
    return any(l.split()[1:] == ["x64sc"] and not l.startswith("Z") for l in out.splitlines() if l.strip())


def start(program, stop_on_entry=True):
    c = Client()
    caps = c.body("initialize", {"adapterID": "c64", "linesStartAt1": True, "columnsStartAt1": True})
    check(caps.get("supportsDisassembleRequest") and caps.get("supportsDataBreakpoints"),
          "initialize : capacités (désassemblage, points d'arrêt sur données...)")
    c.body("launch", {"program": program, "mode": "headless", "warp": True, "build": False,
                      "stopOnEntry": stop_on_entry}, timeout=90)
    c.wait_event("initialized")
    return c


def scenario_asm():
    print("--- asm : examples/hello_rts")
    src = os.path.join(ROOT, "examples/hello_rts/hello_rts.s")
    l_jsr = line_of("examples/hello_rts/hello_rts.s", "jsr CLRSCR")
    l_chrout = line_of("examples/hello_rts/hello_rts.s", "jsr CHROUT")
    l_inx = line_of("examples/hello_rts/hello_rts.s", "        inx")
    c = start(src)
    bps = c.body("setBreakpoints", {"source": {"path": src}, "breakpoints": [{"line": l_inx}, {"line": 2}]})
    check(bps["breakpoints"][0]["verified"] and bps["breakpoints"][0]["line"] == l_inx,
          "point d'arrêt ligne %d (inx) vérifié" % l_inx)
    check(bps["breakpoints"][1]["line"] == l_jsr, "point d'arrêt sur un commentaire : déplacé sur la 1re ligne de code (%d)"
          % bps["breakpoints"][1]["line"])
    c.body("configurationDone")
    st = c.stopped()
    check(st["reason"] == "entry", "arrêt au point d'entrée (reason=%s)" % st["reason"])
    f, line, name = c.where()
    check((f, line, name) == ("hello_rts.s", l_jsr, "start"), "position : %s:%d (%s)" % (f, line, name))
    c.body("next", {"threadId": 1})
    c.stopped()
    f, line, _ = c.where()
    check(line == l_jsr + 1, "next par-dessus jsr CLRSCR (ROM) : ligne %d" % line)
    c.body("continue", {"threadId": 1})
    st = c.stopped()
    f, line, _ = c.where()
    check(st["reason"] == "breakpoint" and line == l_inx, "continue -> point d'arrêt ligne %d (%s)" % (line, st["reason"]))
    regs, _ = c.variables("Registres")
    check(regs["A"]["value"].startswith("$48"), "registre A = 'H' ($48) : %s" % regs["A"]["value"])
    check(regs["X"]["value"].startswith("$00"), "registre X = 0 : %s" % regs["X"]["value"])
    data, _ = c.variables("Données")
    check("message" in data and "|HELLO FROM CA65" in data["message"]["value"].upper(),
          "données : message = %s" % data.get("message", {}).get("value"))
    hv = c.evaluate("message", "hover")
    check("$0832" in hv and "$48" in hv, "survol de message : %s" % hv)
    # État des puces : VIC-II (bordure verte posée par le programme), mémoire,
    # sprites, SID, CIA ; modification d'un registre brut.
    vic, _ = c.variables("VIC-II")
    check(vic["bordure ($D020)"]["value"] == "5 vert" and vic["mode"]["value"] == "texte standard"
          and vic["mémoire écran"]["value"] == "$0400", "VIC-II : bordure %s, mode %s, écran %s"
          % (vic["bordure ($D020)"]["value"], vic["mode"]["value"], vic["mémoire écran"]["value"]))
    raw = {v["name"].split()[0]: v for v in c.body("variables", {"variablesReference": vic["registres bruts"]["variablesReference"]})["variables"]}
    r = c.body("setVariable", {"variablesReference": vic["registres bruts"]["variablesReference"],
                               "name": raw["$d020"]["name"], "value": "$02"})
    vic, _ = c.variables("VIC-II")
    check(vic["bordure ($D020)"]["value"] == "2 rouge", "VIC-II : bordure modifiée -> %s" % vic["bordure ($D020)"]["value"])
    memc, _ = c.variables("Mémoire")
    check(memc["$D000-$DFFF"]["value"] == "E/S" and memc["$E000-$FFFF"]["value"] == "KERNAL ROM"
          and "$ea31" in memc["vecteur IRQ ($0314)"]["value"], "configuration mémoire : %s / %s / %s"
          % (memc["$D000-$DFFF"]["value"], memc["$E000-$FFFF"]["value"], memc["vecteur IRQ ($0314)"]["value"]))
    spr, _ = c.variables("Sprites")
    check(len(spr) == 8 and spr["sprite 0"]["value"] == "inactif", "sprites : 8, sprite 0 %s" % spr["sprite 0"]["value"])
    c.body("writeMemory", {"memoryReference": "0xd418", "data": base64.b64encode(b"\x0f").decode()})
    sid, _ = c.variables("SID")
    check(sid["volume"]["value"] == "15/15", "SID : volume écrit à 15 relu %s" % sid["volume"]["value"])
    cia, _ = c.variables("CIA 1")
    check("en marche" in cia["timer A"]["value"], "CIA 1 : timer A de l'IRQ KERNAL %s" % cia["timer A"]["value"])
    hv = c.evaluate("CHROUT", "hover")
    check("$ffd2" in hv, "survol d'une équivalence : %s" % hv)
    out = c.evaluate("regs")
    check(out.startswith("A=48 X=00"), "console : commande dbg.py regs -> %s" % out)
    out = c.evaluate("message,s")
    check(out.upper().startswith('"HELLO FROM CA65!'), "console : message,s -> %s" % out)
    frames = c.top()
    check(frames[0]["instructionPointerReference"].lower() == "0x0829", "PC dans la pile d'appels : %s"
          % frames[0]["instructionPointerReference"])
    dis = c.body("disassemble", {"memoryReference": "0x0829", "instructionOffset": -4,
                                 "instructionCount": 10})["instructions"]
    texts = [i["instruction"] for i in dis]
    check(len(dis) == 10 and dis[4]["address"] == "0x0829" and dis[4]["instruction"] == "INX",
          "désassemble : %s" % texts)
    check("JSR $ffd2" in texts or any("JSR" in t for t in texts), "désassemblage contient le JSR CHROUT")
    mem = c.body("readMemory", {"memoryReference": "0x0400", "count": 16})
    check(base64.b64decode(mem["data"])[:2] == bytes([8, 32]), "readMemory $0400 : 'H' (1er caractère affiché)")
    c.body("writeMemory", {"memoryReference": "0x02fe", "data": base64.b64encode(b"\x5a").decode()})
    check(c.evaluate("$02fe") .startswith("$5a"), "writeMemory $02fe = $5a")
    # stepIn sur jsr CHROUT (ROM, sans source) : franchi, on reste dans le source.
    c.body("setBreakpoints", {"source": {"path": src}, "breakpoints": []})
    c.body("next", {"threadId": 1})       # inx -> bne print
    c.stopped()
    c.body("next", {"threadId": 1})       # bne -> lda message,x
    c.stopped()
    c.body("next", {"threadId": 1})       # lda -> beq
    c.stopped()
    c.body("next", {"threadId": 1})       # beq -> jsr CHROUT
    c.stopped()
    f, line, _ = c.where()
    check(line == l_chrout, "boucle print : de retour sur jsr CHROUT (ligne %d)" % line)
    c.body("stepIn", {"threadId": 1})
    c.stopped()
    f, line, _ = c.where()
    check(f == "hello_rts.s" and line == l_chrout + 1, "stepIn sur un JSR ROM : franchi (ligne %d)" % line)
    c.body("next", {"threadId": 1, "granularity": "instruction"})
    c.stopped()
    ipr = c.top()[0]["instructionPointerReference"]
    check(ipr.lower() == "0x082a", "pas d'instruction (granularity=instruction) : %s" % ipr)
    c.body("continue", {"threadId": 1})
    time.sleep(1.0)
    c.body("pause", {"threadId": 1})
    c.stopped()
    scr = c.evaluate("screen")
    check("C64 DEV ENV READY." in scr and "READY." in scr, "programme terminé : retour au BASIC (écran)")
    c.close()
    time.sleep(0.5)
    check(not x64sc_alive(), "fin de session (launch) : VICE arrêté")


def scenario_c():
    print("--- C : examples/squares_c")
    src = os.path.join(ROOT, "examples/squares_c/squares.c")
    rel = "examples/squares_c/squares.c"
    l_total = line_of(rel, "total += s;")
    l_counter = line_of(rel, "++counter;")
    l_printf = line_of(rel, 'printf("%d^2')
    l_square = line_of(rel, "s = square(i);")
    l_mul = line_of(rel, "r = n * n;")
    c = start(src)
    bps = c.body("setBreakpoints", {"source": {"path": src}, "breakpoints": [{"line": l_total}]})
    check(bps["breakpoints"][0]["verified"], "point d'arrêt ligne %d (total += s)" % l_total)
    c.body("configurationDone")
    st = c.stopped()
    f, line, name = c.where()
    check(st["reason"] == "entry" and f == "squares.c" and name == "main",
          "arrêt sur main (%s:%d %s)" % (f, line, name))
    c.body("continue", {"threadId": 1})
    st = c.stopped()
    f, line, _ = c.where()
    check(st["reason"] == "breakpoint" and line == l_total, "point d'arrêt atteint ligne %d" % line)
    loc, _ = c.variables("Locales")
    check(loc.get("i", {}).get("value", "").startswith("1 ") and loc.get("s", {}).get("value", "").startswith("1 "),
          "locales : i=%s s=%s" % (loc.get("i", {}).get("value"), loc.get("s", {}).get("value")))
    check(loc.get("i", {}).get("type") == "unsigned char" and loc.get("s", {}).get("type") == "int",
          "types des locales : %s / %s" % (loc.get("i", {}).get("type"), loc.get("s", {}).get("type")))
    glob, gref = c.variables("Globales")
    check(glob.get("total", {}).get("value", "").startswith("0 ") and glob.get("counter", {}).get("value", "").startswith("0 "),
          "globales : total=%s counter=%s" % (glob.get("total", {}).get("value"), glob.get("counter", {}).get("value")))
    c.body("next", {"threadId": 1})
    c.stopped()
    check(c.where()[1] == l_counter, "next : ligne %d (++counter)" % c.where()[1])
    c.body("next", {"threadId": 1})
    c.stopped()
    check(c.where()[1] == l_printf, "next : ligne %d (printf)" % c.where()[1])
    c.body("next", {"threadId": 1})       # par-dessus printf
    c.stopped()
    line = c.where()[1]
    for _ in range(4):
        if line == l_square:
            break
        c.body("next", {"threadId": 1})
        c.stopped()
        line = c.where()[1]
    check(line == l_square, "retour en haut de la boucle : ligne %d (s = square(i))" % line)
    scr = c.evaluate("screen")
    check("1^2=1" in scr, "printf a affiché 1^2=1")
    c.body("stepIn", {"threadId": 1})
    c.stopped()
    f, line, name = c.where()
    check(name == "square", "stepIn : dans square (%s:%d)" % (f, line))
    c.body("next", {"threadId": 1})
    c.stopped()
    f, line, name = c.where()
    check(line == l_mul, "next : ligne %d (r = n * n)" % line)
    loc, _ = c.variables("Locales")
    check(loc.get("n", {}).get("value", "").startswith("2 "), "paramètre n = %s" % loc.get("n", {}).get("value"))
    frames = c.top()
    names = [fr["name"] for fr in frames]
    check(names[:2] == ["square", "main"] and names[-1].startswith("BASIC "), "pile d'appels : %s" % names)
    c.body("stepOut", {"threadId": 1})
    c.stopped()
    f, line, name = c.where()
    check(name == "main" and line == l_square, "stepOut : retour dans main ligne %d" % line)
    c.body("continue", {"threadId": 1})
    c.stopped()
    loc, _ = c.variables("Locales")
    check(loc.get("s", {}).get("value", "").startswith("4 "), "2e passage : s = %s" % loc.get("s", {}).get("value"))
    check(c.evaluate("total", "hover").startswith("1 "), "survol de total : %s" % c.evaluate("total", "hover"))
    # Modification d'une variable puis point d'arrêt sur donnée.
    glob, gref = c.variables("Globales")
    r = c.body("setVariable", {"variablesReference": gref, "name": "counter", "value": "100"})
    check(r["value"].startswith("100 "), "setVariable counter=100 -> %s" % r["value"])
    c.body("setBreakpoints", {"source": {"path": src}, "breakpoints": []})
    info = c.body("dataBreakpointInfo", {"variablesReference": gref, "name": "counter"})
    check(info.get("dataId"), "dataBreakpointInfo counter : %s" % info.get("description"))
    c.body("setDataBreakpoints", {"breakpoints": [{"dataId": info["dataId"], "accessType": "write"}]})
    c.body("continue", {"threadId": 1})
    st = c.stopped()
    check(st["reason"] == "data breakpoint", "arrêt sur écriture de counter (%s)" % st["reason"])
    check(c.evaluate("counter").startswith("101 "), "counter = %s" % c.evaluate("counter"))
    c.body("setDataBreakpoints", {"breakpoints": []})
    c.body("continue", {"threadId": 1})
    deadline = time.time() + 15
    scr = ""
    while time.time() < deadline:
        time.sleep(0.5)
        scr = c.evaluate("screen")
        if "TOTAL=" in scr:
            break
    check("TOTAL=55" in scr, "fin du programme : TOTAL=55 à l'écran")
    c.close()


def scenario_attach():
    print("--- attach : instance lancée par run.sh (examples/hello)")
    subprocess.run(["tools/run.sh", "--headless", "--warp", "--monitor", "build/hello.prg"], cwd=ROOT,
                   check=True, stdout=subprocess.DEVNULL)
    c = Client()
    c.body("initialize", {"adapterID": "c64"})
    c.body("attach", {})
    c.wait_event("initialized")
    c.body("configurationDone")
    c.body("pause", {"threadId": 1})
    c.stopped()
    f, line, name = c.where()
    check((f, name) == ("hello.s", "loop"), "attach + pause : %s:%d (%s)" % (f, line, name))
    fb = c.body("setFunctionBreakpoints", {"breakpoints": [{"name": "loop"}]})
    check(fb["breakpoints"][0]["verified"], "point d'arrêt sur le label loop")
    c.body("continue", {"threadId": 1})
    st = c.stopped()
    check(st["reason"] == "function breakpoint", "arrêt sur loop (%s)" % st["reason"])
    c.close()
    time.sleep(0.5)
    st = subprocess.run([sys.executable, "tools/dbg.py", "status"], cwd=ROOT, stdout=subprocess.PIPE,
                        text=True).stdout.strip()
    check(st == "running", "après déconnexion (attach) : VICE tourne toujours (%s)" % st)
    lst = subprocess.run([sys.executable, "tools/dbg.py", "list"], cwd=ROOT, stdout=subprocess.PIPE,
                         text=True).stdout.strip()
    check(lst == "no checkpoints", "points d'arrêt de VS Code retirés (%s)" % lst)
    subprocess.run(["tools/stop.sh", "--quiet"], cwd=ROOT)


def check_sync():
    """Attributs de launch/attach lus par dap.py == ceux déclarés par
    l'extension (tools/vscode/package.json), pour la complétion de launch.json."""
    import re
    with open(os.path.join(ROOT, "tools", "dap.py"), encoding="utf-8") as f:
        src = f.read()
    with open(os.path.join(ROOT, "tools", "vscode", "package.json"), encoding="utf-8") as f:
        attrs = json.load(f)["contributes"]["debuggers"][0]["configurationAttributes"]
    for req in ("launch", "attach"):
        body = re.search(r"def req_%s\(self.*?\n    def " % req, src, re.S).group(0)
        used = set(re.findall(r'args(?:\.get\(|\[)"(\w+)"', body))
        declared = set(attrs[req]["properties"])
        check(used == declared, "extension VS Code en phase avec dap.py (%s) : %s / %s"
              % (req, sorted(used), sorted(declared)))


def main():
    os.chdir(ROOT)
    check_sync()
    subprocess.run(["tools/stop.sh", "--quiet", "--all"])
    t0 = time.time()
    try:
        scenario_asm()
        scenario_c()
        scenario_attach()
    finally:
        subprocess.run(["tools/stop.sh", "--quiet", "--all"])
    print("durée : %.0f s" % (time.time() - t0))
    if FAILS:
        print("ECHEC : %d vérification(s) : %s" % (len(FAILS), "; ".join(FAILS)))
        return 1
    print("DAP OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
