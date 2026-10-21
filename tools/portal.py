#!/usr/bin/env python3
"""portal.py - portail de développement C64 : petit serveur web local qui
pilote les outils du projet (make, run.sh, stop.sh, dbg.py, install.sh).

Usage : portal.py [--host 127.0.0.1] [--port 8064]
Puis ouvrir http://localhost:8064 (depuis Windows aussi : WSL2 relaie localhost).

Principes :
- Le portail n'a aucune logique propre d'émulation ou de build : il appelle
  les outils en sous-processus. Ce qu'ils savent faire, il le sait aussi.
- Ce qu'il expose des outils est déclaré ici, dans le REGISTRE ci-dessous.
  Chaque option, commande ou cible d'un outil est soit utilisée par le
  portail, soit explicitement exclue avec une raison. sync_check() compare
  ce registre à l'état réel des outils (aide de run.sh, docstring de dbg.py,
  .PHONY du Makefile...) ; tests/test_4_portal.sh échoue en cas d'écart.
  => Quand on modifie les paramètres d'un outil, on met à jour ce registre
     (et portal/portal.js si une nouvelle action doit apparaître).
- Sécurité : écoute sur 127.0.0.1 ; requêtes refusées si l'en-tête Host
  n'est pas local (anti DNS-rebinding) ; les POST exigent du JSON et une
  éventuelle Origin locale (anti-CSRF) ; aucune commande arbitraire.
"""
import argparse
import ast
import collections
import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
BUILD = os.path.join(ROOT, "build")
STATIC = os.path.join(TOOLS, "portal")
VAR = os.path.join(ROOT, "var")
PORTAL_OUT = os.path.join(BUILD, "portal")  # captures et dumps produits par le portail

# ---------------------------------------------------------------------------
# REGISTRE : ce que le portail utilise de chaque outil
# ---------------------------------------------------------------------------
# Options de ligne de commande des scripts. "used" : option -> où elle sert
# dans le portail ; "excluded" : option -> pourquoi elle n'est pas exposée.
SCRIPT_FLAGS = {
    "tools/run.sh": {
        "help": ["tools/run.sh", "--help"],
        "used": {
            "--show": "Lancer, mode « Visible (WSLg) »",
            "--headless": "Lancer, mode « Invisible » ; Capture",
            "--warp": "case « Warp » (Lancer, Capture)",
            "--monitor": "case « Moniteur » (Lancer)",
            "--cycles": "Capture : champ « Cycles »",
            "--screenshot": "Capture : PNG dans build/portal/",
        },
        "excluded": {
            "--port": "port du moniteur fixé à 6502 (valeur par défaut de dbg.py)",
            "--wait": "bloquerait le portail jusqu'à la fermeture de VICE",
            "--load-only": "réservée à l'adaptateur VS Code (tools/dap.py) : points d'arrêt posés avant le RUN",
        },
    },
    "tools/stop.sh": {
        "help": ["tools/stop.sh", "--help"],
        "used": {
            "--all": "bouton « Tout arrêter (orphelins) »",
        },
        "excluded": {
            "--quiet": "le portail affiche la sortie complète",
        },
    },
    "tools/install.sh": {
        "help": ["tools/install.sh", "--help"],
        "used": {
            "--no-apt": "bouton « Vérifier l'installation » (sans sudo)",
        },
        "excluded": {
            "--build-vice": "compilation longue avec sudo : à lancer dans un terminal",
        },
    },
}

# Cibles du Makefile (.PHONY).
MAKE_TARGETS = {
    "used": {
        "all": "bouton « Compiler » et build avant Lancer/Capture",
        "clean": "bouton « Nettoyer »",
        "test": "bouton « Tous les tests »",
        "list": "liste des programmes",
    },
    "excluded": {
        "run": "remplacée par « Lancer » (make + run.sh avec choix du mode)",
        "debug": "remplacée par « Lancer » avec la case « Moniteur »",
        "install": "peut demander sudo : le portail lance install.sh --no-apt",
        "portal": "démarre le portail lui-même",
        "portal-stop": "arrête le portail lui-même",
        "vscode": "installe l'extension VS Code : une fois, depuis un terminal (make vscode)",
        "code": "ouvre VS Code sur le poste de l'utilisateur : depuis un terminal (make code)",
    },
}

# Commandes dbg.py appelées par des boutons dédiés de l'interface. Toutes
# les commandes de dbg.py sont en plus disponibles dans la console générique.
DBG_USED = {
    "status": "pastille « Moniteur »",
    "screen": "onglet « Texte » de l'écran",
    "capture": "onglet « Image » de l'écran (en direct)",
    "regs": "registres",
    "pause": "bouton « Pause »",
    "jump": "bouton « Recommencer pas à pas » (programme en boucle)",
    "type": "champ « Clavier du C64 » ; « Recommencer pas à pas » (RUN)",
    "step": "bouton « Pas »",
    "next": "bouton « Pas (sans JSR) »",
    "cont": "bouton « Continuer »",
    "wait": "bouton « Attendre l'arrêt »",
    "reset": "bouton « Reset »",
    "quit": "bouton « Quitter VICE »",
    "break": "points d'arrêt : « Exécution »",
    "watch": "points d'arrêt : « Lecture/écriture »",
    "delete": "points d'arrêt : suppression",
    "list": "points d'arrêt : liste",
    "poke": "Mémoire : écriture (double-clic sur un octet)",
    "label": "recherche de labels",
    "disasm": "vue Code : onglet Désassemblage",
    "where": "vue Code : ligne source courante",
    "lines": "vue Code : correspondance lignes source <-> adresses (/api/codeinfo)",
    "segments": "Mémoire : segments du programme sur la carte (/api/codeinfo)",
    "dump": "Mémoire : lecture des 64 Ko (/api/ram)",
    "banks": "Mémoire : choix de la banque",
}
# Commandes dont un argument est un fichier à écrire : le portail force ce
# fichier dans build/portal/ (index de l'argument fichier).
DBG_FILE_ARG = {"dump": 2, "capture": 0}

# ---------------------------------------------------------------------------
# Lecture de l'état réel des outils
# ---------------------------------------------------------------------------
FLAG_RE = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def run_quiet(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def script_flags(cmd):
    """Options --xxx mentionnées dans l'aide d'un script (hors --help)."""
    _, out = run_quiet(cmd)
    return set(FLAG_RE.findall(out)) - {"--help"}


def make_targets():
    """Cibles déclarées .PHONY dans le Makefile."""
    targets = set()
    with open(os.path.join(ROOT, "Makefile"), encoding="utf-8") as f:
        for line in f:
            if line.startswith(".PHONY:"):
                targets.update(line.split(":", 1)[1].split())
    return targets


def dbg_commands():
    """(clés de COMMANDS, {commande: (args, description)} de la docstring),
    lus sans importer dbg.py : toujours à jour, même portail lancé."""
    with open(os.path.join(TOOLS, "dbg.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keys = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets):
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    doc = ast.get_docstring(tree) or ""
    documented = collections.OrderedDict()
    in_list = False
    for line in doc.splitlines():
        if line.strip() == "Commandes :":
            in_list = True
            continue
        if in_list:
            if not line.strip():
                break
            m = re.match(r"^  (\w+)(.*?)\s{2,}(\S.*)$", line)
            if m:
                documented[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return keys, documented


def check_flags(name, actual, used, excluded):
    problems = []
    for f in sorted(set(used) - actual):
        problems.append("%s : le portail utilise %s, que le script ne connaît plus" % (name, f))
    for f in sorted(set(excluded) - actual):
        problems.append("%s : exclusion obsolète de %s (option disparue)" % (name, f))
    for f in sorted(actual - set(used) - set(excluded)):
        problems.append("%s : option %s ni exposée ni exclue dans le portail" % (name, f))
    for f in sorted(set(used) & set(excluded)):
        problems.append("%s : %s à la fois utilisée et exclue" % (name, f))
    return problems


def sync_check():
    """Compare le REGISTRE aux outils. Renvoie {ok, problems, details}."""
    problems, details = [], {}
    for name, spec in SCRIPT_FLAGS.items():
        actual = script_flags(spec["help"])
        details[name] = {"flags": sorted(actual), "used": spec["used"], "excluded": spec["excluded"]}
        problems += check_flags(name, actual, spec["used"], spec["excluded"])
    targets = make_targets()
    details["Makefile"] = {"targets": sorted(targets), "used": MAKE_TARGETS["used"],
                           "excluded": MAKE_TARGETS["excluded"]}
    problems += [p.replace("option", "cible") for p in
                 check_flags("Makefile", targets, MAKE_TARGETS["used"], MAKE_TARGETS["excluded"])]
    keys, documented = dbg_commands()
    details["tools/dbg.py"] = {"commands": sorted(keys), "used": DBG_USED,
                               "documented": {k: list(v) for k, v in documented.items()}}
    for c in sorted(set(DBG_USED) - keys):
        problems.append("tools/dbg.py : le portail utilise '%s', absente de COMMANDS" % c)
    for c in sorted(keys - set(documented)):
        problems.append("tools/dbg.py : '%s' absente de la liste « Commandes » de la docstring" % c)
    for c in sorted(set(documented) - keys):
        problems.append("tools/dbg.py : '%s' documentée mais absente de COMMANDS" % c)
    for c in sorted(set(DBG_FILE_ARG) - keys):
        problems.append("tools/dbg.py : DBG_FILE_ARG cite '%s', absente de COMMANDS" % c)
    return {"ok": not problems, "problems": problems, "details": details}


def flag(script, name):
    """Option d'un script, vérifiée contre le registre (garde-fou interne)."""
    assert name in SCRIPT_FLAGS[script]["used"], "%s %s non déclarée dans le registre" % (script, name)
    return name


# ---------------------------------------------------------------------------
# État : programmes, VICE, moniteur
# ---------------------------------------------------------------------------
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def list_programs():
    rc, out = run_quiet(["make", "-s", "list"])
    names = [l.strip() for l in out.splitlines() if NAME_RE.match(l.strip())] if rc == 0 else []
    progs = []
    for n in names:
        prg = os.path.join(BUILD, n + ".prg")
        labels = os.path.join(BUILD, n + ".labels")
        progs.append({
            "name": n,
            "sources": program_sources(n),
            "built": os.path.isfile(prg),
            "size": os.path.getsize(prg) if os.path.isfile(prg) else None,
            "mtime": os.path.getmtime(prg) if os.path.isfile(prg) else None,
            "labels": sum(1 for _ in open(labels)) if os.path.isfile(labels) else 0,
        })
    return progs


def program_sources(name):
    """Fichiers sources d'un programme (mêmes règles que le Makefile)."""
    found = []
    for d in ("src", "examples"):
        pdir = os.path.join(ROOT, d, name)
        if os.path.isdir(pdir):
            found += sorted(os.path.join(d, name, f) for f in os.listdir(pdir)
                            if f.endswith((".s", ".c", ".h", ".inc")))
        for ext in (".s", ".c"):
            if os.path.isfile(os.path.join(ROOT, d, name + ext)):
                found.append(os.path.join(d, name + ext))
    return found


def pid_alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def read_pid(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def vice_info():
    pid = read_pid(os.path.join(BUILD, "vice.pid"))
    info = {"running": False, "pid": pid, "prog": None, "mode": None, "monitor": False,
            "warp": False, "state": None}
    if pid is None or not pid_alive(pid):
        return info
    info["running"] = True
    try:  # "starting" pendant l'autostart, puis "ready" (écrit par run.sh)
        with open(os.path.join(BUILD, "vice.state")) as f:
            info["state"] = f.read().strip() or None
    except OSError:
        pass
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            args = [a.decode(errors="replace") for a in f.read().split(b"\0")]
    except OSError:
        args = []
    if "-autostart" in args:
        i = args.index("-autostart")
        if i + 1 < len(args):
            info["prog"] = os.path.basename(args[i + 1]).rsplit(".", 1)[0]
    info["mode"] = "headless" if any("xvfb-run" in a for a in args) else "show"
    info["monitor"] = "-binarymonitor" in args
    info["warp"] = "-warp" in args
    return info


def run_dbg(args, timeout=12):
    cmd = [sys.executable, os.path.join(TOOLS, "dbg.py")] + args
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": 3, "stdout": "", "stderr": "dbg.py : pas de réponse en %d s" % timeout}


def monitor_info(vice):
    if not (vice["running"] and vice["monitor"]):
        return {"available": False, "state": None, "error": None}
    if vice["state"] == "starting":
        # Pas de commande moniteur pendant l'autostart (voir run.sh).
        return {"available": False, "state": None, "error": "autostart en cours…"}
    r = run_dbg(["status"], timeout=6)
    if r["rc"] == 0:
        return {"available": True, "state": r["stdout"].strip(), "error": None}
    return {"available": False, "state": None, "error": (r["stderr"] or r["stdout"]).strip()}


# ---------------------------------------------------------------------------
# Tâches (opérations longues, une à la fois)
# ---------------------------------------------------------------------------
class Job:
    _ids = itertools.count(1)

    def __init__(self, title, steps, files=()):
        self.id = next(Job._ids)
        self.title = title
        self.steps = steps            # liste de commandes (listes d'arguments)
        self.files = list(files)      # fichiers produits (relatifs à build/)
        self.lines = []
        self.state = "running"
        self.rc = None
        self.started = time.time()
        self.ended = None

    def to_dict(self, since=0):
        return {"id": self.id, "title": self.title, "state": self.state, "rc": self.rc,
                "started": self.started, "ended": self.ended,
                "lines": self.lines[since:], "next": len(self.lines),
                "files": [f for f in self.files if os.path.isfile(os.path.join(BUILD, f))]}

    def run(self):
        rc = 0
        for cmd in self.steps:
            self.lines.append("$ " + " ".join(cmd))
            try:
                p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                     errors="replace")
                for line in p.stdout:
                    self.lines.append(re.sub(r"\x1b\[[0-9;]*m", "", line.rstrip("\n")))
                rc = p.wait()
            except OSError as e:
                self.lines.append("erreur : %s" % e)
                rc = 127
            if rc != 0:
                self.lines.append("[code de sortie %d]" % rc)
                break
        self.rc = rc
        self.state = "ok" if rc == 0 else "failed"
        self.ended = time.time()


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = collections.OrderedDict()
        self.current = None

    def start(self, title, steps, files=()):
        with self.lock:
            if self.current is not None and self.current.state == "running":
                return None, self.current
            job = Job(title, steps, files)
            self.jobs[job.id] = job
            while len(self.jobs) > 30:
                self.jobs.popitem(last=False)
            self.current = job
        threading.Thread(target=job.run, daemon=True).start()
        return job, None

    def get(self, jid):
        return self.jobs.get(jid)


JOBS = Jobs()

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
    ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8", ".labels": "text/plain; charset=utf-8",
    ".lbl": "text/plain; charset=utf-8", ".map": "text/plain; charset=utf-8",
    ".prg": "application/octet-stream", ".bin": "application/octet-stream",
}
LOGS = {
    "vice": os.path.join(BUILD, "vice.log"),
    "dbg": os.path.join(BUILD, "dbg.log"),
    "portal": os.path.join(VAR, "portal.log"),
}
STARTED = time.time()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def host_of(value):
    """'localhost:8064' -> 'localhost' ; '[::1]:8064' -> '[::1]'."""
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def tail(path, lines):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 256 * 1024))
            data = f.read().decode(errors="replace")
    except OSError:
        return ""
    return "\n".join(data.splitlines()[-lines:])


def git_head():
    rc, out = run_quiet(["git", "log", "-1", "--format=%h %s"], timeout=5)
    return out.strip() if rc == 0 else None


def safe_build_path(rel):
    path = os.path.realpath(os.path.join(BUILD, rel))
    if not path.startswith(os.path.realpath(BUILD) + os.sep):
        raise ApiError(HTTPStatus.FORBIDDEN, "chemin hors de build/")
    return path


def safe_name(value, what="nom"):
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ApiError(HTTPStatus.BAD_REQUEST, "%s invalide : %r" % (what, value))
    return value


def require_program(name):
    safe_name(name, "programme")
    if name not in [p["name"] for p in list_programs()]:
        raise ApiError(HTTPStatus.NOT_FOUND, "programme inconnu : %s (voir make list)" % name)
    return name


class Handler(BaseHTTPRequestHandler):
    server_version = "C64Portal/1.0"

    # --- utilitaires ------------------------------------------------------
    def log_message(self, fmt, *args):
        # Les GET de rafraîchissement sont trop bavards : on ne journalise
        # que les POST et les erreurs.
        if self.command == "POST" or (len(args) > 1 and str(args[1])[:1] in "45"):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_json(self, obj, status=HTTPStatus.OK):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data, ctype, extra=None):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path, download=False):
        if not os.path.isfile(path):
            raise ApiError(HTTPStatus.NOT_FOUND, "fichier absent : %s" % os.path.basename(path))
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            data = f.read()
        extra = {"Content-Disposition": 'attachment; filename="%s"' % os.path.basename(path)} \
            if download or ext in (".prg", ".bin") else None
        self.send_bytes(data, CONTENT_TYPES.get(ext, "application/octet-stream"), extra)

    def check_host(self):
        if host_of(self.headers.get("Host", "")) not in LOCAL_HOSTS:
            raise ApiError(HTTPStatus.FORBIDDEN, "hôte non local refusé")

    def read_json(self):
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        if ctype != "application/json":
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type application/json requis")
        origin = self.headers.get("Origin")
        if origin and host_of(urllib.parse.urlsplit(origin).netloc) not in LOCAL_HOSTS:
            raise ApiError(HTTPStatus.FORBIDDEN, "origine non locale refusée")
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64 * 1024:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "requête trop grosse")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON invalide")
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "objet JSON attendu")
        return body

    def dispatch(self, routes):
        url = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        try:
            self.check_host()
            for pattern, func in routes:
                m = re.fullmatch(pattern, url.path)
                if m:
                    return func(self, query, *m.groups())
            raise ApiError(HTTPStatus.NOT_FOUND, "route inconnue : %s" % url.path)
        except ApiError as e:
            self.send_json({"error": str(e)}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # ne jamais tuer le serveur
            self.send_json({"error": "erreur interne : %s" % e}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):
        self.dispatch(GET_ROUTES)

    def do_POST(self):
        self.dispatch(POST_ROUTES)


# --- GET ----------------------------------------------------------------------
def get_index(h, q):
    h.send_file(os.path.join(STATIC, "index.html"))


def get_static(h, q, name):
    h.send_file(os.path.join(STATIC, safe_name(name, "fichier")))


def get_file(h, q, rel):
    h.send_file(safe_build_path(urllib.parse.unquote(rel)), download=q.get("download") == "1")


def get_source(h, q, rel):
    rel = urllib.parse.unquote(rel)
    path = os.path.realpath(os.path.join(ROOT, rel))
    allowed = [os.path.realpath(os.path.join(ROOT, d)) + os.sep for d in ("src", "examples")]
    if not any(path.startswith(a) for a in allowed) or not os.path.isfile(path):
        raise ApiError(HTTPStatus.NOT_FOUND, "source introuvable : %s" % rel)
    with open(path, "rb") as f:
        h.send_bytes(f.read()[:512 * 1024], "text/plain; charset=utf-8")


def get_ping(h, q):
    h.send_json({"ok": True, "uptime": round(time.time() - STARTED, 1)})


def get_status(h, q):
    vice = vice_info()
    cur = JOBS.current
    h.send_json({
        "vice": vice,
        "monitor": monitor_info(vice),
        "job": cur.to_dict(len(cur.lines)) if cur else None,
        "display": os.environ.get("DISPLAY"),
        "git": git_head(),
        "time": time.time(),
    })


def get_programs(h, q):
    h.send_json({"programs": list_programs()})


def get_meta(h, q):
    keys, documented = dbg_commands()
    tests = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "tests"))
                   if f.startswith("test_") and f.endswith(".sh"))
    h.send_json({
        "dbg": [{"name": n, "args": documented.get(n, ("", ""))[0],
                 "help": documented.get(n, ("", ""))[1]} for n in sorted(keys)],
        "tests": tests,
        "logs": sorted(LOGS),
        "defaults": {"cycles": 5000000, "port": 6502},
    })


def get_selfcheck(h, q):
    h.send_json(sync_check())


def get_jobs(h, q):
    h.send_json({"jobs": [j.to_dict(len(j.lines)) for j in reversed(JOBS.jobs.values())]})


def get_job(h, q, jid):
    job = JOBS.get(int(jid))
    if job is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "tâche inconnue : %s" % jid)
    h.send_json(job.to_dict(int(q.get("since", 0))))


def get_logs(h, q):
    name = q.get("name", "vice")
    if name not in LOGS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "journal inconnu : %s" % name)
    lines = max(1, min(int(q.get("lines", 200)), 5000))
    h.send_json({"name": name, "path": os.path.relpath(LOGS[name], ROOT),
                 "text": tail(LOGS[name], lines)})


BANK_RE = re.compile(r"^[a-z]{1,16}$")


def get_ram(h, q):
    """Octets bruts de la mémoire (dbg.py dump), pour la carte et le focus."""
    try:
        start = int(q.get("start", 0))
        length = int(q.get("len", 65536))
    except ValueError:
        raise ApiError(HTTPStatus.BAD_REQUEST, "start/len invalides")
    if not (0 <= start <= 0xFFFF and 1 <= length and start + length <= 0x10000):
        raise ApiError(HTTPStatus.BAD_REQUEST, "plage hors de $0000-$FFFF")
    bank = q.get("bank", "cpu")
    if not BANK_RE.match(bank):
        raise ApiError(HTTPStatus.BAD_REQUEST, "banque invalide")
    os.makedirs(PORTAL_OUT, exist_ok=True)
    path = os.path.join(PORTAL_OUT, "ram-%d.bin" % threading.get_ident())
    r = run_dbg(["dump", str(start), str(length), path, "--bank", bank], timeout=10)
    if r["rc"] != 0 or not os.path.isfile(path):
        raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE,
                       (r["stderr"] or r["stdout"]).strip() or "lecture mémoire impossible")
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    h.send_bytes(data, "application/octet-stream")


def get_codeinfo(h, q):
    """Correspondance source <-> adresses et segments d'un programme
    (dbg.py lines / segments sur build/<prog>.dbg)."""
    prog = q.get("prog") or vice_info()["prog"]
    if not prog:
        raise ApiError(HTTPStatus.NOT_FOUND, "aucun programme en cours")
    safe_name(prog, "programme")
    dbgfile = os.path.join(BUILD, prog + ".dbg")
    if not os.path.isfile(dbgfile):
        raise ApiError(HTTPStatus.NOT_FOUND, "pas d'infos de débogage pour %s (make)" % prog)
    lines, files = {}, []
    r = run_dbg(["--dbgfile", dbgfile, "lines"], timeout=10)
    for line in r["stdout"].splitlines():
        m = re.match(r"^(.+):(\d+) \$([0-9a-f]{4})-\$([0-9a-f]{4})$", line)
        if not m:
            continue
        fname = m.group(1)
        # Seuls les sources du projet sont affichables (route /source/).
        if not fname.startswith(("src/", "examples/")):
            continue
        if fname not in lines:
            lines[fname] = {}
            files.append(fname)
        lines[fname][int(m.group(2))] = [int(m.group(3), 16), int(m.group(4), 16)]
    segments = []
    r2 = run_dbg(["--dbgfile", dbgfile, "segments"], timeout=10)
    for line in r2["stdout"].splitlines():
        m = re.match(r"^(\S+)\s+\$([0-9a-f]{4})-\$([0-9a-f]{4})", line)
        if m:
            segments.append({"name": m.group(1), "start": int(m.group(2), 16),
                             "end": int(m.group(3), 16)})
    h.send_json({"prog": prog, "files": files, "lines": lines, "segments": segments,
                 "mtime": os.path.getmtime(dbgfile)})


def get_live(h, q):
    """Image de l'écran en direct (dbg.py capture)."""
    os.makedirs(PORTAL_OUT, exist_ok=True)
    path = os.path.join(PORTAL_OUT, "live-%d.png" % threading.get_ident())
    args = ["capture", path] + (["--full"] if q.get("full") == "1" else [])
    r = run_dbg(args, timeout=8)
    if r["rc"] != 0 or not os.path.isfile(path):
        raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE,
                       (r["stderr"] or r["stdout"]).strip() or "capture impossible")
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    h.send_bytes(data, "image/png")


# --- POST ---------------------------------------------------------------------
def start_job(h, title, steps, files=()):
    job, busy = JOBS.start(title, steps, files)
    if job is None:
        raise ApiError(HTTPStatus.CONFLICT, "une tâche est déjà en cours : %s" % busy.title)
    h.send_json({"job": job.to_dict()}, HTTPStatus.ACCEPTED)


def post_build(h, q):
    h.read_json()
    start_job(h, "Compilation (make)", [["make"]])


def post_clean(h, q):
    h.read_json()
    start_job(h, "Nettoyage (make clean)", [["make", "clean"]])


def post_test(h, q):
    body = h.read_json()
    name = body.get("name")
    if not name:
        return start_job(h, "Tests (make test)", [["make", "test"]])
    safe_name(name, "test")
    path = os.path.join("tests", name + ".sh")
    if not os.path.isfile(os.path.join(ROOT, path)):
        raise ApiError(HTTPStatus.NOT_FOUND, "test inconnu : %s" % name)
    start_job(h, "Test %s" % name, [["make"], ["bash", path]])


def post_install_check(h, q):
    h.read_json()
    start_job(h, "Vérification de l'installation",
              [["tools/install.sh", flag("tools/install.sh", "--no-apt")]])


def post_launch(h, q):
    body = h.read_json()
    prog = require_program(body.get("prog"))
    mode = body.get("mode", "show")
    if mode not in ("show", "headless"):
        raise ApiError(HTTPStatus.BAD_REQUEST, "mode invalide : %s" % mode)
    args = ["tools/run.sh", flag("tools/run.sh", "--" + mode)]
    if body.get("warp"):
        args.append(flag("tools/run.sh", "--warp"))
    if body.get("monitor", True):
        args.append(flag("tools/run.sh", "--monitor"))
    args.append("build/%s.prg" % prog)
    title = "Lancement de %s (%s%s)" % (prog, "visible" if mode == "show" else "invisible",
                                        ", moniteur" if body.get("monitor", True) else "")
    start_job(h, title, [["make"], args])


def post_capture(h, q):
    body = h.read_json()
    prog = require_program(body.get("prog"))
    try:
        cycles = int(body.get("cycles", 5000000))
    except (TypeError, ValueError):
        raise ApiError(HTTPStatus.BAD_REQUEST, "cycles invalide")
    if not 100000 <= cycles <= 2000000000:
        raise ApiError(HTTPStatus.BAD_REQUEST, "cycles hors de [100000, 2000000000]")
    rel = "portal/capture-%s.png" % prog
    os.makedirs(PORTAL_OUT, exist_ok=True)
    args = ["tools/run.sh", flag("tools/run.sh", "--headless"),
            flag("tools/run.sh", "--cycles"), str(cycles),
            flag("tools/run.sh", "--screenshot"), os.path.join("build", rel)]
    if body.get("warp", True):
        args.append(flag("tools/run.sh", "--warp"))
    args.append("build/%s.prg" % prog)
    # mkdir dans la tâche aussi : un make clean peut avoir supprimé build/portal.
    start_job(h, "Capture de %s (%d cycles)" % (prog, cycles),
              [["make"], ["mkdir", "-p", "build/portal"], args], files=[rel])


def post_stop(h, q):
    body = h.read_json()
    args = ["tools/stop.sh"]
    if body.get("all"):
        args.append(flag("tools/stop.sh", "--all"))
    # Arrêt immédiat, hors file des tâches : doit marcher même si une tâche tourne.
    rc, out = run_quiet(args, timeout=20)
    h.send_json({"rc": rc, "output": out})


def post_dbg(h, q):
    body = h.read_json()
    keys, _ = dbg_commands()
    cmd = body.get("cmd")
    if cmd not in keys:
        raise ApiError(HTTPStatus.BAD_REQUEST, "commande dbg.py inconnue : %r" % cmd)
    args = body.get("args", [])
    if isinstance(args, str):
        args = args.split()
    if not isinstance(args, list) or not all(isinstance(a, str) and len(a) < 200 for a in args):
        raise ApiError(HTTPStatus.BAD_REQUEST, "arguments invalides")
    if len(args) > 64:
        raise ApiError(HTTPStatus.BAD_REQUEST, "trop d'arguments")
    files = []
    if cmd in DBG_FILE_ARG:
        # Fichier de sortie forcé dans build/portal/ (nom de base seulement).
        idx = DBG_FILE_ARG[cmd]
        plain = [i for i, a in enumerate(args) if not a.startswith("--")]
        if idx < len(plain):
            i = plain[idx]
            base = safe_name(os.path.basename(args[i]) or "out.bin", "fichier")
            os.makedirs(PORTAL_OUT, exist_ok=True)
            args[i] = os.path.join(PORTAL_OUT, base)
            files.append("portal/" + base)
    timeout = 12
    if cmd == "wait":
        try:
            timeout = int(float(args[0])) + 5 if args else 15
        except ValueError:
            pass
        timeout = min(timeout, 125)
    r = run_dbg([cmd] + args, timeout=timeout)
    r["files"] = [f for f in files if os.path.isfile(os.path.join(BUILD, f))]
    h.send_json(r)


GET_ROUTES = [
    (r"/", get_index),
    (r"/static/([^/]+)", get_static),
    (r"/files/(.+)", get_file),
    (r"/source/(.+)", get_source),
    (r"/live\.png", get_live),
    (r"/api/ping", get_ping),
    (r"/api/status", get_status),
    (r"/api/programs", get_programs),
    (r"/api/meta", get_meta),
    (r"/api/selfcheck", get_selfcheck),
    (r"/api/jobs", get_jobs),
    (r"/api/jobs/(\d+)", get_job),
    (r"/api/logs", get_logs),
    (r"/api/ram", get_ram),
    (r"/api/codeinfo", get_codeinfo),
]
POST_ROUTES = [
    (r"/api/build", post_build),
    (r"/api/clean", post_clean),
    (r"/api/test", post_test),
    (r"/api/install-check", post_install_check),
    (r"/api/launch", post_launch),
    (r"/api/capture", post_capture),
    (r"/api/stop", post_stop),
    (r"/api/dbg", post_dbg),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default=os.environ.get("PORTAL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORTAL_PORT", 8064)))
    ap.add_argument("--check", action="store_true",
                    help="vérifie la cohérence outils/portail et quitte (code 1 si écart)")
    opts = ap.parse_args(argv)
    if opts.check:
        res = sync_check()
        for p in res["problems"]:
            print("ECART : %s" % p)
        print("cohérence outils/portail : %s" % ("OK" if res["ok"] else "%d écart(s)" % len(res["problems"])))
        return 0 if res["ok"] else 1
    try:
        server = ThreadingHTTPServer((opts.host, opts.port), Handler)
    except OSError as e:
        print("portal.py: impossible d'écouter sur %s:%d : %s" % (opts.host, opts.port, e), file=sys.stderr)
        return 1
    server.daemon_threads = True
    print("portal.py: portail de développement sur http://localhost:%d (écoute %s)"
          % (opts.port, opts.host), flush=True)
    res = sync_check()
    if not res["ok"]:
        print("portal.py: ATTENTION, %d écart(s) outils/portail :" % len(res["problems"]), flush=True)
        for p in res["problems"]:
            print("  - %s" % p, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
