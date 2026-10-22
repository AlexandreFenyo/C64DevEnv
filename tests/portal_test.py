#!/usr/bin/env python3
"""portal_test.py - test de bout en bout du portail (appelé par test_4_portal.sh).

Démarre tools/portal.py sur un port de test, puis vérifie via HTTP :
cohérence outils/portail, protections (Host, Content-Type, Origin), build,
capture headless, lancement avec moniteur, mémoire, écran texte et image,
point d'arrêt, console dbg, journaux, arrêt. Nettoie derrière lui.
"""
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import portal  # noqa: E402

PORT = int(os.environ.get("PORTAL_TEST_PORT", 18064))
BASE = "http://127.0.0.1:%d" % PORT
failures = []


def check(cond, msg):
    print(("ok : " if cond else "ECHEC : ") + msg, flush=True)
    if not cond:
        failures.append(msg)
    return cond


def request(method, path, body=None, headers=None, raw=False):
    data = None
    hdrs = dict(headers or {})
    if method == "POST":
        data = json.dumps(body or {}).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b"null"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def wait_job(job, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, j = request("GET", "/api/jobs/%d" % job["id"])
        if j["state"] != "running":
            return j
        time.sleep(0.3)
    raise RuntimeError("tâche %s trop longue" % job["title"])


def run_job(path, body=None):
    st, r = request("POST", path, body)
    if not check(st == 202, "POST %s accepté (%s)" % (path, st)):
        print(r)
        return None
    j = wait_job(r["job"])
    st, full = request("GET", "/api/jobs/%d" % j["id"])
    if j["state"] != "ok":
        print("\n".join(full["lines"][-20:]))
    check(j["state"] == "ok", "tâche « %s » réussie (rc=%s)" % (j["title"], j["rc"]))
    return full


def dbg(cmd, *args):
    st, r = request("POST", "/api/dbg", {"cmd": cmd, "args": list(args)})
    return st, r


def main():
    # --- Cohérence : unitaire sur check_flags, puis réelle ------------------
    probs = portal.check_flags("x.sh", {"--a", "--b", "--new"}, {"--a": ""}, {"--b": "", "--old": ""})
    check(any("--new" in p and "ni exposée ni exclue" in p for p in probs),
          "check_flags détecte une option nouvelle non reportée")
    check(any("--old" in p and "obsolète" in p for p in probs),
          "check_flags détecte une exclusion obsolète")
    # post_launch : --no-sound transmis à run.sh en mode visible seulement
    # (tâche interceptée : pas de fenêtre VICE pendant les tests).
    class FakeHandler:
        def __init__(self, body):
            self.body = body

        def read_json(self):
            return self.body
    launched = []
    real_start_job = portal.start_job
    portal.start_job = lambda h, title, steps, **kw: launched.append((title, steps[-1]))
    try:
        portal.post_launch(FakeHandler({"prog": "hello", "mode": "show", "nosound": True}), {})
        portal.post_launch(FakeHandler({"prog": "hello", "mode": "headless", "nosound": True}), {})
        portal.post_launch(FakeHandler({"prog": "hello", "mode": "show"}), {})
    finally:
        portal.start_job = real_start_job
    check(len(launched) == 3 and "--no-sound" in launched[0][1] and "sans son" in launched[0][0]
          and "--no-sound" not in launched[1][1] and "--no-sound" not in launched[2][1],
          "Lancer : case « Sans son » -> run.sh --no-sound (mode visible seulement)")
    probs = portal.check_flags("x.sh", {"--a"}, {"--a": "", "--gone": ""}, {})
    check(any("--gone" in p for p in probs), "check_flags détecte une option utilisée disparue")

    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "portal.py"),
                             "--port", str(PORT)], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            try:
                if request("GET", "/api/ping")[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                pass
            time.sleep(0.1)
        else:
            check(False, "le portail démarre")
            return
        check(True, "le portail répond sur le port %d" % PORT)

        st, sc = request("GET", "/api/selfcheck")
        check(st == 200 and sc["ok"], "cohérence outils/portail : %s" % (sc["problems"] or "OK"))

        # --- Sécurité ---------------------------------------------------
        st, _ = request("GET", "/api/status", headers={"Host": "evil.example:%d" % PORT})
        check(st == 403, "Host non local refusé (%s)" % st)
        req = urllib.request.Request(BASE + "/api/build", data=b"{}", method="POST",
                                     headers={"Content-Type": "text/plain"})
        try:
            urllib.request.urlopen(req, timeout=10)
            st = 200
        except urllib.error.HTTPError as e:
            st = e.code
        check(st == 415, "POST sans JSON refusé (%s)" % st)
        st, _ = request("POST", "/api/build", {}, headers={"Origin": "http://evil.example"})
        check(st == 403, "Origin non locale refusée (%s)" % st)
        st, _ = request("GET", "/files/../Makefile")
        check(st in (403, 404), "pas d'accès hors de build/ (%s)" % st)
        st, r = dbg("rm", "-rf")
        check(st == 400, "commande dbg inconnue refusée (%s)" % st)
        st, r = request("POST", "/api/launch", {"prog": "../../etc/passwd"})
        check(st == 400, "nom de programme invalide refusé (%s)" % st)

        # --- Méta, programmes ------------------------------------------
        st, meta = request("GET", "/api/meta")
        names = {c["name"] for c in meta["dbg"]}
        check({"capture", "pause", "mem", "break"} <= names, "méta : commandes dbg.py exposées")
        check(all(c["help"] for c in meta["dbg"]), "méta : chaque commande dbg.py a une aide")
        check("test_4_portal" in meta["tests"], "méta : tests listés")
        st, progs = request("GET", "/api/programs")
        pnames = {p["name"] for p in progs["programs"]}
        check({"hello", "hello_rts", "hello_c"} <= pnames, "programmes : %s" % sorted(pnames))

        # --- Build et capture --------------------------------------------
        run_job("/api/build")
        job = run_job("/api/capture", {"prog": "hello", "cycles": 5000000})
        if job:
            check("portal/capture-hello.png" in job["files"], "capture produite : %s" % job["files"])
            st, png = request("GET", "/files/portal/capture-hello.png", raw=True)
            check(st == 200 and png[:8] == b"\x89PNG\r\n\x1a\n", "capture servie en PNG")
            w, h = struct.unpack(">II", png[16:24])
            check((w, h) == (384, 272), "capture 384x272 (%dx%d)" % (w, h))
        st, r = request("POST", "/api/capture", {"prog": "hello", "cycles": 10})
        check(st == 400, "cycles hors bornes refusés (%s)" % st)

        # --- Lancement avec moniteur (headless) -----------------------
        run_job("/api/launch", {"prog": "hello", "mode": "headless", "warp": True, "monitor": True})
        st, s = request("GET", "/api/status")
        v = s["vice"]
        check(v["running"] and v["prog"] == "hello" and v["mode"] == "headless" and v["monitor"],
              "statut VICE : %s" % v)
        witness = None
        for _ in range(50):
            st, r = dbg("mem", "$02FF", "1")
            if r.get("rc") == 0 and r["stdout"].split()[1:2] == ["42"]:
                witness = "42"
                break
            time.sleep(0.2)
        check(witness == "42", "témoin $02FF = $42 via le portail")
        st, s = request("GET", "/api/status")
        check(s["monitor"]["available"] and s["monitor"]["state"] == "running",
              "statut moniteur : %s" % s["monitor"])
        st, r = dbg("screen")
        check("HELLO FROM CA65!" in r["stdout"], "écran texte via le portail")
        st, png = request("GET", "/live.png", raw=True)
        check(st == 200 and png[:4] == b"\x89PNG", "image en direct (/live.png)")
        if st == 200:
            check(struct.unpack(">II", png[16:24]) == (384, 272), "image en direct 384x272")

        st, r = dbg("break", "loop")
        check(r["rc"] == 0 and "(loop)" in r["stdout"], "point d'arrêt sur loop : %s" % r["stdout"].strip())
        st, r = dbg("wait", "5")
        check(r["rc"] == 0 and "stopped PC=0831" in r["stdout"], "arrêt sur loop : %s" % r["stdout"].strip())
        st, s = request("GET", "/api/status")
        check((s["monitor"]["state"] or "").startswith("stopped"), "statut : arrêté (%s)" % s["monitor"]["state"])
        st, r = dbg("list")
        check("checkpoint 1" in r["stdout"], "liste des points d'arrêt")
        st, r = dbg("delete", "1")
        st, r = dbg("cont")
        check(r["rc"] == 0 and "resumed" in r["stdout"], "continuer")
        st, r = dbg("poke", "$02FE", "$99")
        st, r = dbg("dump", "$02FE", "2", "../../evil.bin")
        check(r["rc"] == 0 and r["files"] == ["portal/evil.bin"], "dump forcé dans build/portal/ : %s" % r["files"])
        st, data = request("GET", "/files/portal/evil.bin", raw=True)
        check(data == b"\x99\x42", "contenu du dump (%r)" % data)
        st, r = dbg("label", "loop")
        check("loop = $0831" in r["stdout"], "recherche de label")

        # Vue Code : infos source et désassemblage via l'API.
        st, ci = request("GET", "/api/codeinfo")
        check(st == 200 and ci["prog"] == "hello" and ci["files"] == ["examples/hello/hello.s"],
              "codeinfo : programme et fichier source (%s)" % (ci.get("files") if isinstance(ci, dict) else ci))
        check(ci["lines"]["examples/hello/hello.s"].get("18") == [0x080d, 0x080f],
              "codeinfo : ligne 18 -> $080d-$080f")
        check(any(s["name"] == "CODE" and s["start"] == 0x080d for s in ci["segments"]), "codeinfo : segment CODE")
        st, r = dbg("disasm", "pc", "10")
        check(r["rc"] == 0 and "JMP loop" in r["stdout"], "disasm via le portail")
        st, r = dbg("where")
        check("hello.s:38" in r["stdout"], "where via le portail : %s" % r["stdout"].strip())
        # Points d'entrée : mygame/demo, ligne sprite_move(...) atteinte aussi
        # par un saut au milieu de la ligne (optimiseur de cc65).
        st, ci = request("GET", "/api/codeinfo?prog=demo")
        n_move = next(i for i, l in enumerate(open(os.path.join(ROOT, "mygame/demo/main.c"), encoding="utf-8"), 1)
                      if "sprite_move(0, ship_x, ship_y);" in l)
        ent = (ci.get("entries", {}).get("mygame/demo/main.c", {}).get(str(n_move)) if isinstance(ci, dict) else None)
        check(st == 200 and ent and len(ent) >= 2, "codeinfo : points d'entrée de la ligne %d de demo (%s)" % (n_move, ent))
        check("libc64/sprite/sprite_move.s" in ci.get("files", []), "codeinfo : sources de libc64 utilisées par demo")
        st, _ = request("GET", "/source/libc64/sprite/sprite_move.s", raw=True)
        check(st == 200, "source de libc64 servie")
        st, _ = request("GET", "/api/codeinfo?prog=../x")
        check(st == 400, "codeinfo : nom invalide refusé (%s)" % st)

        # Mémoire : lecture brute des 64 Ko et par banque.
        st, ram = request("GET", "/api/ram", raw=True)
        check(st == 200 and len(ram) == 65536 and ram[0x02FF] == 0x42, "RAM 64 Ko, témoin $02FF = $42")
        st, rom = request("GET", "/api/ram?start=40960&len=2&bank=rom", raw=True)
        check(st == 200 and rom == b"\x94\xe3", "RAM banque rom en $A000 (%r)" % rom)
        st, _ = request("GET", "/api/ram?start=65535&len=2")
        check(st == 400, "RAM : plage hors limites refusée (%s)" % st)
        st, _ = request("GET", "/api/ram?bank=../x")
        check(st == 400, "RAM : banque invalide refusée (%s)" % st)

        # Page : les nouvelles vues sont présentes.
        st, page = request("GET", "/", raw=True)
        for anchor in (b'id="code-view"', b'id="mem-map"', b'id="hex-view"', b'id="restart-step"', b'id="type-form"'):
            check(anchor in page, "page : %s" % anchor.decode())

        st, logs = request("GET", "/api/logs?name=vice&lines=2000")
        check(st == 200 and "AUTOSTART" in logs["text"], "journal VICE lisible")
        st, jobs = request("GET", "/api/jobs")
        check(len(jobs["jobs"]) >= 3, "historique des tâches (%d)" % len(jobs["jobs"]))

        # Une tâche à la fois.
        st1, r1 = request("POST", "/api/capture", {"prog": "hello", "cycles": 5000000})
        st2, r2 = request("POST", "/api/build")
        check(st1 == 202 and st2 == 409, "une seule tâche à la fois (%s, %s)" % (st1, st2))
        if st1 == 202:
            wait_job(r1["job"])
        st, s = request("GET", "/api/status")
        check(s["vice"]["running"], "la capture n'a pas arrêté l'instance interactive")

        st, r = request("POST", "/api/stop", {})
        check(st == 200 and r["rc"] == 0, "arrêt de VICE")
        st, s = request("GET", "/api/status")
        check(not s["vice"]["running"], "VICE arrêté")
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        subprocess.run([os.path.join(ROOT, "tools", "stop.sh"), "--quiet", "--all"], cwd=ROOT)
        if failures:
            print("--- journal du portail de test ---")
            print(out[-3000:])


if __name__ == "__main__":
    main()
    if failures:
        print("%d échec(s)" % len(failures))
        sys.exit(1)
    print("Portail OK")
