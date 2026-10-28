"""Prototype : la tete-lampe et son papillon, anime, voix Kokoro am_fenrir."""
import sys, math, io, subprocess, wave
import numpy as np
import cairosvg
from PIL import Image
import soundfile as sf
from kokoro_onnx import Kokoro
from multiprocessing import Pool

OUT = sys.argv[1]
W, H, FPS, SR = 1080, 1920, 30, 24000
K = "#111114"

# ------------------------------------------------------------ script
# (texte, humeur, bras droit, bras gauche, papillon, pause apres)
LINES = [
    ("This moth is not in love with me.",                       "talk",  "rest",   "rest", "near",  0.35),
    ("Everyone thinks it is. It follows me everywhere.",         "talk",  "gest",   "rest", "near",  0.35),
    ("In 2024, scientists filmed insects around lights, in slow motion.", "talk", "explain", "hip", "near", 0.3),
    ("Turns out, they are not attracted to light at all.",      "idea",  "up",     "hip",  "near",  0.4),
    ("They just keep their back facing it. Always.",            "talk",  "gest",   "rest", "near",  0.35),
    ("For millions of years, the brightest thing was the sky. Back to the light meant: up is this way.", "talk", "up", "rest", "near", 0.35),
    ("Then we invented lamps. Now the sky is me. So it circles. Forever.", "scared", "chest", "chest", "orbit", 0.5),
    ("So I turned myself off.",                                  "off",   "rest",   "plug", "orbit", 1.3),
    ("It is still here.",                                        "off",   "rest",   "plug", "land",  0.0),
]
HOOK = "This moth isn't in love with me."
END_HOLD = 3.2

kok = Kokoro("/root/.cache/kokoro/kokoro-v1.0.onnx", "/root/.cache/kokoro/voices-v1.0.bin")
clips, t = [], 0.4
for i, (txt, *_rest, pause) in enumerate(LINES):
    import hashlib, os
    cp = f"cache_{hashlib.md5(txt.encode()).hexdigest()[:10]}.npy"
    if os.path.exists(cp): a = np.load(cp)
    else:
        a, sr = kok.create(txt, voice="am_fenrir", speed=1.0, lang="en-us"); assert sr == SR; np.save(cp, a)
    clips.append((t, a.astype(np.float64)))
    t += len(a) / SR + pause
TOTAL = t + END_HOLD
starts = [c[0] for c in clips]
ends = [c[0] + len(c[1]) / SR for c in clips]

# sons synthetises (aucun son sous droits)
def tone(f, d, vol, decay):
    tt = np.arange(int(d * SR)) / SR
    return vol * np.sin(2 * np.pi * f * tt) * np.exp(-tt * decay)
def click(d=0.05):
    n = np.random.default_rng(1).normal(0, 1, int(d * SR)) * np.exp(-np.arange(int(d * SR)) / SR * 90)
    return 0.5 * n
def hum(d, f=100):
    tt = np.arange(int(d * SR)) / SR
    return 0.06 * (np.sign(np.sin(2 * np.pi * f * tt)) * 0.5 + np.sin(2 * np.pi * 2 * f * tt)) * np.minimum(1, tt * 8) * np.minimum(1, (d - tt) * 8)

buf = np.zeros(int(TOTAL * SR) + SR)
def put(x, at, g=1.0):
    i = int(at * SR); n = min(len(x), len(buf) - i); buf[i:i + n] += x[:n] * g
for st, a in clips:
    put(a / (np.max(np.abs(a)) + 1e-9) * 0.8, st)
T_REVEAL = starts[3] + 0.55          # sur "not attracted"
T_OFF = ends[7] - 0.15               # "off"
T_BACK = ends[8] + 1.4               # rallumage final
put(tone(1320, 1.2, 0.18, 4) + tone(1980, 1.2, 0.08, 6), T_REVEAL)
put(click(), T_OFF, 0.6)
put(hum(0.5), T_BACK - 0.5, 1.0)
put(click(0.03), T_BACK, 0.4)
put(hum(1.6, 100) * 0.5, T_BACK)

# enveloppe de la voix (bouche)
env_win = SR // FPS
voice_only = np.zeros_like(buf)
for st, a in clips:
    i = int(st * SR); voice_only[i:i + len(a)] += np.abs(a)
env = np.array([voice_only[i * env_win:(i + 1) * env_win].mean() for i in range(int(TOTAL * FPS) + 2)])
env = env / (np.percentile(env, 97) + 1e-9)
env = np.clip(np.convolve(env, np.ones(3) / 3, mode="same"), 0, 1)

# ------------------------------------------------------------ outils
def lerp(a, b, u): return a + (b - a) * u
def ease(u): u = max(0, min(1, u)); return u * u * (3 - 2 * u)
def hexrgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)
def rgbhex(c): return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)
def cl(a, b, u): return rgbhex(lerp(hexrgb(a), hexrgb(b), u))
def ln(d, w, c=K, extra=""):
    return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'

MOOD = {  # bg haut, bg bas, verre, opacite, halo, couleur chaude, yeux
    "talk":   ("#5bc0be", "#1c6e7d", "#ffe9a0", .55, .18, "#ff9b30", 6),
    "idea":   ("#ffb347", "#e0592a", "#fff6cf", .85, .35, "#ffb000", 8),
    "scared": ("#6a4c93", "#241a3d", "#9fc8ff", .40, .18, "#5aa0ff", 4),
    "off":    ("#4a4d57", "#1c1d22", "#8d8f96", .22, .0,  "#3a3a40", 3),
}
ARMS = {
    "rest":    [(234, 334), (250, 378), (254, 414)],
    "gest":    [(234, 334), (272, 362), (298, 328)],
    "explain": [(234, 334), (268, 352), (292, 318)],
    "up":      [(234, 334), (264, 292), (280, 240)],
    "chest":   [(234, 334), (224, 372), (206, 352)],
}
ARMS_L = {
    "rest":  [(166, 334), (150, 378), (146, 414)],
    "hip":   [(166, 334), (144, 372), (168, 400)],
    "plug":  [(166, 334), (136, 358), (108, 348)],
    "chest": [(166, 334), (176, 372), (194, 352)],
}
def mirror_name(n): return n

def scene_at(t):
    i = 0
    for k, s in enumerate(starts):
        if t >= s - 0.15: i = k
    return i

def blend_state(t):
    """humeur et poses, avec transitions de 0.35 s au debut de chaque ligne."""
    i = scene_at(t)
    cur = LINES[i]; prev = LINES[max(0, i - 1)]
    u = ease((t - (starts[i] - 0.15)) / 0.35) if i > 0 else 1.0
    return i, prev, cur, u

def moth_svg(x, y, a, s, flap):
    w = 'fill="#efe5c8" stroke="#111114" stroke-width="3"'
    fy = 0.35 + 0.65 * flap
    return (f'<g transform="translate({x:.1f},{y:.1f}) rotate({a:.1f}) scale({s})">'
            f'<g transform="scale(1,{fy:.2f})"><ellipse cx="-12" cy="-6" rx="13" ry="9" {w} transform="rotate(-25 -12 -6)"/>'
            f'<ellipse cx="12" cy="-6" rx="13" ry="9" {w} transform="rotate(25 12 -6)"/>'
            f'<ellipse cx="-8" cy="7" rx="9" ry="7" {w}/><ellipse cx="8" cy="7" rx="9" ry="7" {w}/></g>'
            f'<ellipse cx="0" cy="0" rx="4.5" ry="12" fill="{K}"/>' + ln("M-2,-11 L-8,-21", 2) + ln("M2,-11 L8,-21", 2) + '</g>')

HEAD = np.array([200.0, 190.0])
def moth_pos(t):
    """renvoie (x, y, angle, derriere?, flap)"""
    i = scene_at(t)
    mode = LINES[i][4]
    near = HEAD + np.array([105 + 14 * math.sin(t * 1.7), -55 + 22 * math.sin(t * 2.3 + 1)])
    ang_o = t * 2.6
    orbit = HEAD + np.array([150 * math.cos(ang_o), 60 * math.sin(ang_o) - 10])
    land = np.array([206.0, 132.0])
    flap = abs(math.sin(t * 38))
    t_orbit = starts[6] + 0.8
    t_land = starts[8] - 0.2
    if t < t_orbit:
        p, behind = near, False
        a = 15 + 10 * math.sin(t * 3)
    elif t < t_orbit + 1.0:
        u = ease(t - t_orbit); p = lerp(near, orbit, u); behind = math.sin(ang_o) < 0 and u > .5
        a = math.degrees(math.atan2(*(HEAD - p)[::-1])) + 90
    elif t < t_land:
        p = orbit; behind = math.sin(ang_o) < 0
        a = math.degrees(math.atan2(HEAD[1] - p[1], HEAD[0] - p[0])) + 90  # dos vers la lumiere
    elif t < t_land + 1.4:
        u = ease((t - t_land) / 1.4); p = lerp(orbit, land, u); behind = False
        a = lerp(0, 0, u); flap = lerp(flap, 0.2, u)
    else:
        p, behind, a = land, False, 0
        flap = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 2.2)) ** 6
    return p[0], p[1], a, behind, flap

def char_svg(t, f):
    i, prev, cur, u = blend_state(t)
    m0, m1 = MOOD[prev[1]], MOOD[cur[1]]
    mood = cur[1] if u > 0.5 else prev[1]
    # lumiere
    glass = cl(m0[2], m1[2], u); op = lerp(m0[3], m1[3], u); halo = lerp(m0[4], m1[4], u)
    hot = cl(m0[5], m1[5], u); er = lerp(m0[6], m1[6], u)
    flash = 0.0
    if t >= T_REVEAL: flash = math.exp(-(t - T_REVEAL) * 3.0)
    # extinction / rallumage
    if T_OFF <= t < T_BACK:
        glass, op, halo, hot, er = MOOD["off"][2], .22, 0, MOOD["off"][5], 3
        mood = "off"
    elif t >= T_BACK:
        k = ease((t - T_BACK) / 0.8)
        flick = 1.0 if t - T_BACK > 0.5 else (1.0 if math.sin((t - T_BACK) * 70) > 0 else 0.2)
        glass = cl(MOOD["off"][2], MOOD["talk"][2], k * flick); op = lerp(.22, .5, k * flick)
        halo = .16 * k * flick; hot = cl(MOOD["off"][5], MOOD["talk"][5], k * flick); er = lerp(3, 5, k)
        mood = "back"
    elif mood == "off" and t < T_OFF:
        # avant le clic, encore allume (fin de la phrase)
        glass, op, halo, hot, er = MOOD["scared"][2], .4, .18, MOOD["scared"][5], 4
        mood = "scared"
    # clignement
    if mood != "off" and (t % 3.3) < 0.12: er = 1.2
    s = ""
    hr = 95 + 40 * flash + (25 if mood == "idea" else 0)
    if halo > 0.01:
        s += f'<circle cx="200" cy="190" r="{hr:.0f}" fill="{glass}" opacity="{min(.6, halo + .3 * flash):.2f}"/>'
    if mood == "idea" or flash > 0.05:
        k = 1 + 0.25 * flash
        for ang in (-90, -135, -45, -170, -10):
            r0, r1 = 120 * k, 145 * k
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            s += ln(f"M{200 + r0 * ca:.0f},{190 + r0 * sa:.0f} L{200 + r1 * ca:.0f},{190 + r1 * sa:.0f}", 7, "#fff6cf")
    # bras
    ar = [tuple(lerp(np.array(a), np.array(b), u)) for a, b in zip(ARMS[prev[2]], ARMS[cur[2]])]
    al = [tuple(lerp(np.array(a), np.array(b), u)) for a, b in zip(ARMS_L[prev[3]], ARMS_L[cur[3]])]
    if cur[2] == "gest": ar[2] = (ar[2][0] + 6 * math.sin(t * 5), ar[2][1] + 5 * math.sin(t * 4))
    breath = 2.5 * math.sin(t * 2.0)
    # cable : du culot jusqu'a la prise (au sol ou dans la main gauche)
    P_floor = np.array([352.0, 534.0]); P_hand = np.array(al[2])
    plug_u = ease((t - (starts[7] + 0.2)) / 0.6) if t < T_BACK else 1.0
    if t >= T_BACK: plug_u = 1.0
    P = lerp(P_floor, P_hand, plug_u)
    F = np.array([250.0, 556.0]); sg = 1 if P[0] > F[0] else -1
    cable = (f"M206,312 C262,336 244,500 {F[0]:.0f},{F[1]:.0f} C{F[0] + sg * 70:.0f},{F[1] + 12:.0f} "
             f"{P[0]:.0f},{P[1] + 70 * (1 - plug_u) + 90 * plug_u:.0f} {P[0]:.0f},{P[1]:.0f}")
    s += ln(cable, 7)
    s += ln("M188,420 L178,555", 22) + ln("M212,420 L222,555", 22)
    s += f'<ellipse cx="200" cy="{372 + breath:.1f}" rx="34" ry="58" fill="{K}"/>'
    s += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in ar for v in p]), 18)
    s += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in al for v in p]), 18)
    rotp = lerp(-20, 0, plug_u)
    s += (f'<g transform="translate({P[0]:.0f},{P[1]:.0f}) rotate({rotp:.0f})"><rect x="-13" y="-9" width="26" height="18" rx="4" fill="{K}"/>'
          + ln("M{0},-5 L{1},-9".format(-12 * (2 * plug_u - 1) if plug_u > .5 else 12, -24 if plug_u > .5 else 22), 4)
          + ln("M{0},5 L{1},7".format(-12 if plug_u > .5 else 12, -24 if plug_u > .5 else 22), 4) + '</g>')
    # tete
    tilt = {"talk": 0, "idea": -6, "scared": 4, "off": 12, "back": 6}[mood] + 2 * math.sin(t * 1.3)
    e = env[min(len(env) - 1, f)]
    h = f'<rect x="182" y="282" width="36" height="34" rx="5" fill="{K}"/>' + "".join(ln(f"M184,{y} L216,{y}", 3, "#555") for y in (291, 300, 309))
    h += f'<path d="M184,284 C180,262 146,242 146,192 A55,55 0 1,1 254,192 C254,242 220,262 216,284 Z" fill="{glass}" fill-opacity="{op:.2f}" stroke="{K}" stroke-width="6"/>'
    h += ln("M192,284 L180,206", 3, "#444") + ln("M208,284 L220,206", 3, "#444")
    if mood == "idea":
        a = 10 + 10 * e
        pts = " ".join(f"L{180 + 5 * k},{206 + (a if k % 2 else -a) * (0 if k in (0, 8) else 1):.0f}" for k in range(1, 9))
        fil = f"M180,206 {pts}"
    elif mood == "scared":
        j = 3 + 6 * e
        fil = "M180,212 " + " ".join(f"Q{185 + 10 * k},{212 + (j if k % 2 else -j) + math.sin(t * 40 + k) * 2:.1f} {190 + 10 * k},212" for k in range(4))
    elif mood == "off":
        fil = "M180,206 Q186,222 192,226 M208,232 Q214,222 220,206"
    else:
        d = 14 + 22 * e
        fil = f"M180,206 Q200,{206 + d:.0f} 220,206"
    h += ln(fil, 5, hot)
    h += f'<circle cx="180" cy="200" r="{er:.1f}" fill="{hot}"/><circle cx="220" cy="200" r="{er:.1f}" fill="{hot}"/>'
    h += ln("M170,150 Q178,136 192,132", 5, "#fff", 'opacity=".7"')
    mx, my, ma, behind, flap = moth_pos(t)
    msvg = moth_svg(mx, my, ma, 1.15, flap)
    head = f'<g transform="rotate({tilt:.1f} 200 300)">{h}</g>'
    if behind: s += msvg + head
    else:
        if mx < 230 and my < 150 and t > starts[8]:   # pose sur la tete : suit l'inclinaison
            s += f'<g transform="rotate({tilt:.1f} 200 300)">{h}{msvg}</g>'
        else:
            s += head + msvg
    return s, mood, flash, i, u

# sous-titres
def chunks(txt, n=3):
    w = txt.split(); out = []; cur = []
    for x in w:
        cur.append(x)
        if len(cur) >= n or x[-1] in ".,:!?": out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out
SUBS = []
for (st, a), line in zip(clips, LINES):
    cs = chunks(line[0]); tot = sum(len(c) for c in cs); d = len(a) / SR; acc = st
    for c in cs:
        dd = d * len(c) / tot; SUBS.append((acc, acc + dd, c)); acc += dd
def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;")

def frame(f):
    t = f / FPS
    cs, mood, flash, i, u = char_svg(t, f)
    prev, cur = LINES[max(0, i - 1)][1], LINES[i][1]
    if t >= T_BACK: top, bot = MOOD["talk"][0], MOOD["talk"][1]; kk = ease((t - T_BACK) / 1.0); top = cl(MOOD["off"][0], top, kk); bot = cl(MOOD["off"][1], bot, kk)
    elif t >= T_OFF: top, bot = MOOD["off"][0], MOOD["off"][1]
    else:
        pm, cm = MOOD[prev], MOOD[cur]
        if cur == "off": cm = MOOD["scared"]
        top, bot = cl(pm[0], cm[0], u), cl(pm[1], cm[1], u)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/></linearGradient>'
         f'<radialGradient id="v" cx=".5" cy=".42" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient></defs>'
         f'<rect width="{W}" height="{H}" fill="url(#g)"/>']
    o.append(f'<rect x="0" y="1440" width="{W}" height="480" fill="#000" opacity=".18"/>')
    o.append(f'<g transform="translate(90,240) scale(2.25)">{cs}</g>')
    o.append(f'<rect width="{W}" height="{H}" fill="url(#v)"/>')
    if flash > 0.02: o.append(f'<rect width="{W}" height="{H}" fill="#fffbe6" opacity="{0.55 * flash:.2f}"/>')
    if t < 3.0:
        a = min(1, (3.0 - t) / 0.3)
        o.append(f'<g opacity="{a:.2f}"><rect x="70" y="150" width="940" height="130" rx="28" fill="#000" opacity=".55"/>'
                 f'<text x="540" y="238" text-anchor="middle" font-family="Inter" font-weight="900" font-size="66" fill="#fff">{esc(HOOK)}</text></g>')
    for a0, a1, c in SUBS:
        if a0 <= t < a1:
            pop = 1 + 0.08 * max(0, 1 - (t - a0) / 0.12)
            o.append(f'<g transform="translate(540,1330) scale({pop:.3f})"><text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="92" '
                     f'fill="none" stroke="#000" stroke-width="18" stroke-linejoin="round">{esc(c)}</text>'
                     f'<text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="92" fill="#fff">{esc(c)}</text></g>')
    o.append("</svg>")
    png = cairosvg.svg2png(bytestring="".join(o).encode())
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).tobytes()

if __name__ == "__main__":
    nf = int(TOTAL * FPS)
    m = np.percentile(np.abs(buf), 99.7); buf = np.tanh(buf / m * 0.9) * 0.89
    with wave.open(OUT + ".wav", "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((buf * 32767).astype(np.int16).tobytes())
    if "--still" in sys.argv:
        for tt in [float(x) for x in sys.argv[sys.argv.index("--still") + 1].split(",")]:
            Image.frombytes("RGB", (W, H), frame(int(tt * FPS))).save(f"{OUT}_{tt:.1f}.png")
        sys.exit()
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", OUT + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT], stdin=subprocess.PIPE)
    with Pool(4) as p:
        for fr in p.imap(frame, range(nf), chunksize=8):
            ff.stdin.write(fr)
    ff.stdin.close(); ff.wait()
    print("total", round(TOTAL, 1), "s,", nf, "frames; reveal", round(T_REVEAL, 1), "off", round(T_OFF, 1), "back", round(T_BACK, 1))
