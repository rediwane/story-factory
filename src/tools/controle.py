"""
Le juge automatique d'une vidéo liste. Il ne regarde pas : il mesure. Il passe avant
tout rendu (sur la simulation), puis après (sur le mp4), et sort en 1 au moindre défaut
bloquant. Les juges humains (agents, skill `juger`) ne reçoivent qu'une vidéo qui l'a passé.

    python3 src/tools/controle.py configs/<name>.json          # avant rendu : simulation
    python3 src/tools/controle.py configs/<name>.json --post   # après rendu : + mp4, planches

Ce qu'il vérifie, et pourquoi : chaque règle vient d'un défaut qui a fait recaler ou
décrocher une vidéo. Les seuils sont dans SEUILS ; on les change ici, pas au cas par cas.
"""
import os
import re
import sys
import json
import math
import glob
import subprocess
import importlib.util

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "sim"))
sys.path.insert(0, os.path.join(ROOT, "src", "stories"))
import base  # noqa: E402
from listkit import penetration, disc_rect_overlap, SCENE_TOP  # noqa: E402

SEUILS = {
    "duree_min": 60.0, "duree_max": 66.0,          # une minute, sans s'étirer
    "premiere_chute_max": 6.0,                      # on décroche à 0:01 : la première chute avant 6 s
    "chapitre_min": 5.5, "chapitre_max": 12.5,
    "chute_locale_min": 2.0,                        # une chute instantanée ne se comprend pas
    "titre_retard_max": 0.6,                        # la voix annonce le lieu dès la coupe
    "penetration_max": 8.0,                         # px : rien ne traverse un solide
    "sous_titre_marge": 0.0,
    "fenetre_figee_s": 1.5, "mouvement_min": 0.5,   # niveaux de gris moyens par image (10 i/s, 54x96)
    "ouverture_mouvement_min": 1.6,                 # les 3 premières secondes bougent franchement (les métiers : 1,0, 43 % partis à 6 s)
    "silence_max_s": 1.6,
    "luma_haut_max": 110.0,                         # le compte est de nuit (moyenne glissante sur 1 s : un flash est permis)
    "estimation_facteur": 1.2,                      # l'estimation avant rendu surestime le mp4 (0,85 × mesuré sur six_hobbies) : seuils relevés
}


def charge(path):
    with open(path, encoding="utf-8") as fh:
        user = json.load(fh)
    theme_name = user.get("theme")
    spec = importlib.util.spec_from_file_location(theme_name, os.path.join(ROOT, "src", "stories", theme_name + ".py"))
    theme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(theme)
    cfg = base.load_config(path, theme.DEFAULTS)
    return theme, cfg


def accroches_utilisees():
    seen = set()
    for f in [os.path.join(ROOT, "history.json"), os.path.join(ROOT, "..", "bouncefactory", "history.json"),
              os.path.join(ROOT, "..", "bouncefactory", "history_archive.json")]:
        if os.path.exists(f):
            try:
                txt = open(f, encoding="utf-8").read()
                seen.update(m.lower() for m in re.findall(r'"hook_text":\s*"([^"]*)"', txt))
            except Exception:
                pass
    for f in glob.glob(os.path.join(ROOT, "..", "bouncefactory", "configs", "*.json")):
        try:
            h = json.load(open(f, encoding="utf-8")).get("hook_text")
            if h:
                seen.add(h.lower())
        except Exception:
            pass
    return seen


def pre(path, out):
    theme, cfg = charge(path)
    W, H = cfg["width"], cfg["height"]
    ko, warn = [], []
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    total = max(dur, narr[-1]["end"] + cfg["narr_tail_s"]) if narr else dur
    sims = sim.sims
    # chapitres : débuts, chutes
    starts, last = [], None
    for (t, s) in states:
        if s["i"] != last:
            starts.append(t); last = s["i"]
    if len(starts) != len(sims):
        ko.append(f"{len(sims)} chapitres, {len(starts)} joués")
    ends = starts[1:] + [total]
    chutes = []
    for i, ch in enumerate(sims):
        el = getattr(ch, "_end_local", None)
        if el is None:
            ko.append(f"chapitre {i + 1} ({ch.title}) : pas de chute avant la coupe (coupé à la durée maximale)")
            chutes.append(None)
            continue
        chutes.append(starts[i] + el if i < len(starts) else None)
        d = ends[i] - starts[i] if i < len(starts) else 0
        if i < len(sims) - 1 and not (SEUILS["chapitre_min"] <= d <= SEUILS["chapitre_max"]):
            ko.append(f"chapitre {i + 1} ({ch.title}) : {d:.1f} s (attendu {SEUILS['chapitre_min']}–{SEUILS['chapitre_max']})")
        if el < SEUILS["chute_locale_min"]:
            ko.append(f"chapitre {i + 1} ({ch.title}) : chute à {el:.1f} s du début, trop tôt pour qu'on comprenne")
    if not (SEUILS["duree_min"] <= total <= SEUILS["duree_max"]):
        ko.append(f"durée {total:.1f} s (attendu {SEUILS['duree_min']}–{SEUILS['duree_max']})")
    if chutes and chutes[0] is not None and chutes[0] > SEUILS["premiere_chute_max"]:
        ko.append(f"première chute à {chutes[0]:.1f} s (au plus {SEUILS['premiere_chute_max']} s : on décroche à 0:01)")
    # la voix annonce chaque chapitre dès la coupe, et avant la chute
    for i in range(len(starts)):
        tl = [n for n in narr if n["key"] == f"{i}:title"]
        if not tl:
            ko.append(f"chapitre {i + 1} : aucune réplique de clé 'title'")
            continue
        n0 = tl[0]
        if i > 0 and n0["start"] - starts[i] > SEUILS["titre_retard_max"]:
            ko.append(f"chapitre {i + 1} : le titre est dit {n0['start'] - starts[i]:.1f} s après la coupe")
        if chutes[i] is not None and n0["start"] > chutes[i]:
            ko.append(f"chapitre {i + 1} : la chute ({chutes[i]:.1f} s) arrive avant que la voix annonce le chapitre ({n0['start']:.1f} s)")
    # aucune réplique ne déborde sur le chapitre suivant
    for n in narr:
        i = int(n["key"].split(":")[0])
        if i + 1 < len(starts) and n["end"] > starts[i + 1] + 0.05:
            ko.append(f"réplique « {n['text'][:40]} » du chapitre {i + 1} déborde sur le suivant ({n['end']:.1f} > {starts[i + 1]:.1f})")
    # les répliques de Bounce : dans leur scène, jamais sous la voix
    for (key, delay), tr in zip([r for r in sim.replies if any(n['key'] == r[0] for n in narr)], replies):
        i = int(key.split(":")[0])
        if i + 1 < len(starts) and tr + 0.6 > starts[i + 1]:
            ko.append(f"réplique de Bounce à {tr:.1f} s : tombe après la coupe vers le chapitre suivant ({starts[i + 1]:.1f} s)")
        if base.in_narration(tr, narr, pad=0.05):
            ko.append(f"réplique de Bounce à {tr:.1f} s : sous la voix du narrateur")
    # textes à l'image
    cf = base.font(cfg["counter_font_size"] * W / 1080)
    for ch in sims:
        if ch.title and base.text_w(cf, ch.title) > 0.92 * W:
            ko.append(f"titre « {ch.title} » trop large pour l'image")
    sf = base.font(cfg["sub_font_size"] * W / 1080)

    def sub_rects(t):
        line = base.subtitle_at(narr, t, cfg["sub_words"])
        if not line:
            return []
        rows = [""]
        for wd in line.split():
            cand = (rows[-1] + " " + wd).strip()
            if base.text_w(sf, cand) <= W * 0.86 or not rows[-1]:
                rows[-1] = cand
            else:
                rows.append(wd)
        out_r = []
        for k, row in enumerate(rows):
            cy = H * cfg["sub_y"] + (k - (len(rows) - 1) / 2) * sf.size * 1.2
            w = base.text_w(sf, row)
            out_r.append((W / 2 - w / 2 - 6, cy - sf.size * 0.6, W / 2 + w / 2 + 6, cy + sf.size * 0.6))
        return out_r

    def stamp_rect(ch):
        if not ch.stamp:
            return None
        text = ch.stamp[0]
        size = 150
        f = base.font(size)
        while base.text_w(f, text) > W * 0.86 and size > 40:
            size = int(size * 0.9); f = base.font(size)
        w = base.text_w(f, text)
        cy = H * getattr(ch, "stamp_y", 0.52)
        return (W / 2 - w / 2, cy - size * 0.55, W / 2 + w / 2, cy + size * 0.55)

    # image par image : cadre, solides, textes sur Bounce
    pen_seen, frame_seen, cover_seen, sub_seen = {}, {}, {}, {}
    for (t, s) in states:
        i = s["i"]
        ch = sims[i]
        hs = ch.hero(s["snap"])
        if hs is None:
            continue
        x, y, r = hs
        ended = s["end_local"] is not None
        if not getattr(ch, "exit_ok", False):
            if x - r < -2 or x + r > W + 2 or y - r < SCENE_TOP - 4 or y + r > H:
                frame_seen.setdefault(i, t)
        for sh in ch.solids(s["snap"]):
            p = penetration(x, y, r, sh)
            if p > SEUILS["penetration_max"]:
                key = (i, sh[0])
                if key not in pen_seen or p > pen_seen[key][1]:
                    pen_seen[key] = (t, p)
        if ended:
            rect = stamp_rect(ch)
            if rect and disc_rect_overlap(x, y, r, *rect):
                cover_seen.setdefault(i, t)
        near_chute = chutes[i] is not None and abs(t - chutes[i]) < 1.0
        if near_chute or ended:
            for rr in sub_rects(t):
                if disc_rect_overlap(x, y, r * 0.7, *rr):
                    sub_seen.setdefault(i, t)
    for i, t in frame_seen.items():
        ko.append(f"chapitre {i + 1} ({sims[i].title}) : Bounce sort du cadre à {t:.2f} s")
    for (i, kind), (t, p) in pen_seen.items():
        ko.append(f"chapitre {i + 1} ({sims[i].title}) : Bounce entre de {p:.0f} px dans un solide ({kind}) à {t:.2f} s")
    for i, t in cover_seen.items():
        ko.append(f"chapitre {i + 1} ({sims[i].title}) : le tampon recouvre Bounce à {t:.2f} s")
    for i, t in sub_seen.items():
        ko.append(f"chapitre {i + 1} ({sims[i].title}) : un sous-titre recouvre Bounce autour de la chute ({t:.2f} s)")
    # mouvement estimé avant rendu : la scène dessinée en 54x96 à 10 i/s, sans les textes ni
    # le lissage de l'encodage ; elle surestime le mp4, d'où des seuils relevés
    from PIL import Image, ImageDraw
    Sm = 54.0 / W
    prev, diffs, k_next = None, [], 0.0
    for (t, s) in states:
        if t + 1e-9 < k_next:
            continue
        k_next = t + 0.1
        img = Image.new("RGB", (54, 96), tuple(cfg["bg_color"]))
        dr = ImageDraw.Draw(img)
        base.HERO["pos"] = None
        try:
            sim.draw(dr, s, t, Sm)
        except Exception:
            pass
        a = np.asarray(img.convert("L"), dtype=np.float32)
        if prev is not None:
            diffs.append(float(np.abs(a - prev).mean()))
        prev = a
    diffs = np.array(diffs)
    win = int(SEUILS["fenetre_figee_s"] * 10)
    figees = [k / 10.0 for k in range(0, len(diffs) - win) if diffs[k:k + win].mean() < SEUILS["mouvement_min"] * SEUILS["estimation_facteur"]]
    figees = [f for f in figees if f < total - 2.5]
    if figees:
        groups = [figees[0]]
        for a in figees[1:]:
            if a - groups[-1] > 1.0:
                groups.append(a)
        ko.append("(estimation) image presque figée à : " + ", ".join(f"{g:.1f} s" for g in groups[:6]))
    ouv_est = float(diffs[:30].mean()) if len(diffs) >= 30 else 0.0
    if ouv_est < SEUILS["ouverture_mouvement_min"] * SEUILS["estimation_facteur"]:
        ko.append(f"(estimation) les 3 premières secondes bougent trop peu ({ouv_est:.2f})")
    # accroche jamais utilisée
    hook = (cfg.get("hook_text") or "").strip()
    if not hook:
        ko.append("pas d'accroche")
    else:
        others = accroches_utilisees()
        mine = cfg["name"]
        own = json.load(open(path, encoding="utf-8")).get("hook_text", "").lower()
        if hook.lower() in others and not _hook_is_self(hook, mine):
            ko.append(f"accroche déjà utilisée : {hook}")
    # variété des chutes : un même tampon pour tous les chapitres, c'est une recette
    stamps = [c.stamp[0] for c in sims if c.stamp]
    if stamps and len(set(stamps)) == 1 and len(stamps) > 2:
        warn.append("tous les chapitres ont le même tampon")
    rapport = {"name": cfg["name"], "duration_s": round(total, 2),
               "chapters": [{"title": c.title, "start": round(starts[k], 2) if k < len(starts) else None,
                             "chute": round(chutes[k], 2) if chutes[k] is not None else None,
                             "stamp": c.stamp[0] if c.stamp else None} for k, c in enumerate(sims)],
               "narration": [{"t": round(n["start"], 2), "end": round(n["end"], 2), "text": n["text"]} for n in narr],
               "replies": [round(x, 2) for x in replies],
               "mouvement_estime": {"ouverture": round(ouv_est, 2), "min_fenetre": round(float(min([diffs[k:k + win].mean() for k in range(len(diffs) - win)] or [0])), 2)},
               "ko": ko, "warn": warn}
    os.makedirs(out, exist_ok=True)
    json.dump(rapport, open(os.path.join(out, "controle.json"), "w"), ensure_ascii=False, indent=1)
    return rapport, cfg


def _hook_is_self(hook, name):
    """L'accroche figure déjà dans un historique… mais pour cette vidéo-ci (re-contrôle)."""
    for f in [os.path.join(ROOT, "history.json"), os.path.join(ROOT, "..", "bouncefactory", "history.json")]:
        if os.path.exists(f):
            try:
                h = json.load(open(f, encoding="utf-8"))
                for v in h.get("videos", []):
                    if (v.get("hook_text") or "").lower() == hook.lower():
                        return v.get("name") == name
            except Exception:
                pass
    return True


def post(path, rapport, cfg, out):
    ko, warn = rapport["ko"], rapport["warn"]
    mp4 = os.path.join(ROOT, "output", cfg["name"] + ".mp4")
    if not os.path.exists(mp4):
        ko.append("mp4 absent : rendre avant --post")
        return rapport
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                               capture_output=True, text=True).stdout.strip() or 0)
    if abs(dur - rapport["duration_s"]) > 0.6:
        ko.append(f"le mp4 dure {dur:.1f} s, la simulation {rapport['duration_s']:.1f} s")
    # mouvement : images 54x96 en gris à 10 i/s
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mp4, "-vf", "fps=10,scale=54:96,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 96, 54).astype(np.float32)
    diffs = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    win = int(SEUILS["fenetre_figee_s"] * 10)
    figees = []
    for k in range(0, len(diffs) - win):
        if diffs[k:k + win].mean() < SEUILS["mouvement_min"]:
            figees.append(k / 10.0)
    if figees:
        groups = [figees[0]]
        for a in figees[1:]:
            if a - groups[-1] > 1.0:
                groups.append(a)
        if not (len(groups) == 1 and groups[0] > dur - 2.5):
            ko.append("image presque figée pendant " + str(SEUILS["fenetre_figee_s"]) + " s à : " + ", ".join(f"{g:.1f} s" for g in groups[:6]))
    ouv = diffs[:30].mean() if len(diffs) >= 30 else 0
    if ouv < SEUILS["ouverture_mouvement_min"]:
        ko.append(f"les 3 premières secondes bougent trop peu ({ouv:.2f} < {SEUILS['ouverture_mouvement_min']})")
    # nuit : la moitié haute de l'image reste sombre
    luma_inst = fr[:, :48, :].mean(axis=(1, 2))
    luma_haut = np.convolve(luma_inst, np.ones(10) / 10, mode="valid") if len(luma_inst) >= 10 else luma_inst
    if luma_haut.max() > SEUILS["luma_haut_max"]:
        k = int(np.argmax(luma_haut))
        ko.append(f"image trop claire en haut autour de {k / 10:.1f} s (luma moyenne sur 1 s {luma_haut.max():.0f}) : le compte est de nuit")
    # silences
    sil = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp4, "-af", f"silencedetect=noise=-40dB:d={SEUILS['silence_max_s']}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", sil)]
    starts = [s for s in starts if s < dur - 1.5]
    if starts:
        ko.append("silence de plus de " + str(SEUILS["silence_max_s"]) + " s à : " + ", ".join(f"{s:.1f} s" for s in starts[:6]))
    # planches pour les juges
    planches(mp4, rapport, out, dur)
    rapport["post"] = {"duree_mp4": round(dur, 2), "mouvement_ouverture": round(float(ouv), 2),
                       "luma_haut_max": round(float(luma_haut.max()), 1)}
    json.dump(rapport, open(os.path.join(out, "controle.json"), "w"), ensure_ascii=False, indent=1)
    return rapport


def grab(mp4, t, w=240):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}", "-i", mp4, "-frames:v", "1",
                          "-vf", f"scale={w}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    h = len(raw) // (w * 3)
    from PIL import Image
    return Image.frombytes("RGB", (w, h), raw) if h else None


def strip(mp4, times, path, w=240, cols=None):
    from PIL import Image, ImageDraw
    ims = [grab(mp4, t, w) for t in times]
    ims = [(t, im) for t, im in zip(times, ims) if im is not None]
    if not ims:
        return
    cols = cols or len(ims)
    rows = math.ceil(len(ims) / cols)
    iw, ih = ims[0][1].size
    m = Image.new("RGB", (cols * (iw + 6), rows * (ih + 26)), (255, 0, 255))
    d = ImageDraw.Draw(m)
    for k, (t, im) in enumerate(ims):
        x, y = (k % cols) * (iw + 6), (k // cols) * (ih + 26)
        m.paste(im, (x, y + 22))
        d.text((x + 4, y + 4), f"{t:.2f}s", fill=(0, 0, 0))
    m.save(path)


def planches(mp4, rapport, out, dur):
    """Ce que voient les juges : la vidéo en planche, les ouvertures, chaque chute et chaque coupe."""
    strip(mp4, [round(x, 1) for x in np.arange(0.5, dur - 0.2, 2.0)], os.path.join(out, "planche.png"), w=180, cols=11)
    strip(mp4, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0], os.path.join(out, "ouverture.png"))
    for k, ch in enumerate(rapport["chapters"]):
        if ch["chute"] is not None:
            c = ch["chute"]
            strip(mp4, [round(c + d, 2) for d in (-1.2, -0.8, -0.4, -0.2, 0.0, 0.15, 0.3, 0.6, 1.0)],
                  os.path.join(out, f"chute_{k + 1}.png"), w=200)
        if k > 0 and ch["start"] is not None:
            s = ch["start"]
            strip(mp4, [round(s + d, 2) for d in (-0.4, -0.1, 0.05, 0.4, 0.9)], os.path.join(out, f"coupe_{k + 1}.png"), w=200)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    path = sys.argv[1]
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(ROOT, "output", "controle_" + name)
    rapport, cfg = pre(path, out)
    if "--post" in sys.argv:
        rapport = post(path, rapport, cfg, out)
    print(f"{rapport['name']} : {rapport['duration_s']} s, {len(rapport['chapters'])} chapitres")
    for c in rapport["chapters"]:
        print(f"  {c['start']:>6} s  {c['title']}  -> chute {c['chute']}  {c['stamp'] or ''}")
    for w in rapport["warn"]:
        print("avertissement :", w)
    if rapport["ko"]:
        print()
        for k in rapport["ko"]:
            print("KO ", k)
        print(f"\n{len(rapport['ko'])} défaut(s) bloquant(s). Planches et rapport : {out}")
        return 1
    print(f"\nAucun défaut bloquant. Planches et rapport : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
