"""
Détecteur d'incohérences, à lancer en début de session ou de run. Sort en 1 s'il trouve
quelque chose.

- history.json lisible et au schéma ; era_start vide ou une date ;
- aucune vidéo d'un jour précédent encore publication_failed ;
- les vidéos portent leurs champs de base, leur config existe ;
- la table des skills de CLAUDE.md correspond aux dossiers .claude/skills/ ;
- aucun exemple dans les instructions (formule d'exemple, phrase citée, marqueur oublié) ;
- le moteur s'importe ;
- aucun fichier audio dans le dépôt, aucun mp4 versionné.

    python3 src/tools/coherence.py
"""
import os
import re
import sys
import json
import glob
import datetime
import subprocess
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def p(*a):
    return os.path.join(ROOT, *a)


def rd(*a):
    return open(p(*a), encoding="utf-8").read()


problems, notes = [], []


def ko(w, m):
    problems.append((w, m))


def ok(m):
    notes.append(m)


# ------------------------------------------------------------------ history.json
try:
    H = json.loads(rd("history.json"))
except Exception as e:
    print(f"KO  history.json: JSON illisible : {e}")
    sys.exit(1)
for k in ("era_start", "videos", "themes", "daily", "veille", "notes"):
    if k not in H:
        ko("history.json", f"clé manquante : {k}")
era = H.get("era_start")
if era is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(era)):
    ko("history.json", f"era_start doit être vide ou une date AAAA-MM-JJ : {era!r}")
today = datetime.date.today().isoformat()
for v in H.get("videos", []):
    for k in ("name", "date", "theme", "status", "config"):
        if k not in v:
            ko("history.json", f"vidéo sans champ '{k}' : {v.get('name', '?')}")
    if v.get("status") == "publication_failed" and (v.get("date") or "") < today:
        ko("history.json", f"'{v.get('name')}' encore publication_failed : à passer abandoned")
    if v.get("config") and not os.path.exists(p(v["config"])):
        ko("history.json", f"'{v.get('name')}' : config absente {v['config']}")
if H.get("videos") and era is None:
    ko("history.json", "des vidéos existent mais era_start est vide")
ok(f"history.json lisible, {len(H.get('videos', []))} vidéo(s), {len(H.get('themes', []))} thème(s)")

# ------------------------------------------------------------------ skills
claude = rd("CLAUDE.md")
table = set(re.findall(r"^\|\s*`(\w+)`\s*\|\s*[\w\-–]+", claude, re.M))
dirs = {os.path.basename(d) for d in glob.glob(p(".claude", "skills", "*")) if os.path.isdir(d)}
for s in table - dirs:
    ko("CLAUDE.md", f"la table cite la skill '{s}', qui n'existe pas")
for s in dirs - table:
    ko(".claude/skills", f"la skill '{s}' n'est pas dans la table de CLAUDE.md")
for s in dirs:
    f = p(".claude", "skills", s, "SKILL.md")
    if not os.path.exists(f):
        ko(".claude/skills", f"{s}/SKILL.md manquant")
    elif not re.match(r"^---\nname: \w+\ndescription: .+\n---\n", rd(".claude", "skills", s, "SKILL.md")):
        ko(f, "frontmatter invalide (name, description, ---)")
ok(f"{len(dirs)} skills, table et frontmatters en ordre")

# ------------------------------------------------------------------ exemples
PROSE = ["CLAUDE.md"] + [os.path.relpath(f, ROOT) for f in glob.glob(p(".claude", "skills", "*", "SKILL.md"))]
INTERDIT = [(r"À TRANCHER|A TRANCHER", "marqueur de décision oublié"),
            (r"pour l'exemple|par exemple|ne pas les recopier", "formule d'exemple"),
            (r"«\s*[A-Z][^»]{6,}[?!.]\s*»", "phrase citée"),
            (r"^\s*[-*]\s*[«\"][A-Z][^»\"]{4,}[?!][»\"]\s*$", "liste d'accroches")]
for f in PROSE:
    s = rd(f)
    for pat, why in INTERDIT:
        for m in re.finditer(pat, s, re.M):
            ko(f, f"ligne {s[:m.start()].count(chr(10)) + 1} : {why} -> {m.group(0)[:50]!r}")
ok("aucun exemple ni marqueur dans les instructions")

# ------------------------------------------------------------------ moteur, dépôt
for mod in ("voice", "render"):
    spec = importlib.util.spec_from_file_location(mod, p("src", "engine", mod + ".py"))
    try:
        m = importlib.util.module_from_spec(spec)
        sys.path.insert(0, p("src", "engine"))
        spec.loader.exec_module(m)
    except Exception as e:
        ko(f"src/engine/{mod}.py", f"ne s'importe pas : {e}")
for f in glob.glob(p("configs", "*.json")):
    try:
        json.load(open(f, encoding="utf-8"))
    except Exception as e:
        ko(os.path.relpath(f, ROOT), f"config illisible : {e}")
try:
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True).stdout.split()
except Exception:
    tracked = []
for f in tracked:
    if f.endswith((".mp3", ".wav", ".ogg", ".m4a", ".mp4")):
        ko(f, "fichier audio ou vidéo versionné")
ok("moteur importable, aucun média versionné")

print("\n".join(f"ok  {n}" for n in notes))
if problems:
    print()
    for w, m in problems:
        print(f"KO  {w}: {m}")
    print(f"\n{len(problems)} incohérence(s).")
    sys.exit(1)
print("\nAucune incohérence.")
