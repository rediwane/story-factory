"""Prototype v2 : meme histoire, montage rythme (plans, camera, transitions, texte cinetique, bruitages, musique generee)."""
import sys, math, io, os, subprocess, wave, hashlib
import numpy as np
import cairosvg
from PIL import Image
from multiprocessing import Pool

OUT = sys.argv[1]
W, H, FPS, SR = 1080, 1920, 30, 24000
K = "#111114"
SPEED = 1.08

# ------------------------------------------------------------------ narration
LINES = [  # (texte, pause apres)
    ("This moth is not in love with me.", 0.25),
    ("Everyone thinks it is.", 0.15),
    ("It follows me everywhere.", 0.35),
    ("In 2024,", 0.05),
    ("scientists filmed insects around lights, in super slow motion.", 0.2),
    ("Turns out, they're not attracted to light at all.", 0.3),
    ("They just keep their back facing it.", 0.25),
    ("For millions of years, the brightest thing in the world was the sky.", 0.15),
    ("Back to the light meant: this way is up.", 0.3),
    ("Then we invented lamps.", 0.2),
    ("Now the sky is me.", 0.35),
    ("So it circles. Forever.", 0.5),
    ("So I turned myself off.", 1.4),
    ("It's still here.", 0.0),
]
END_HOLD = 3.4

def voice(txt):
    cp = f"cache2_{hashlib.md5((txt + str(SPEED)).encode()).hexdigest()[:10]}.npy"
    if os.path.exists(cp): return np.load(cp)
    from kokoro_onnx import Kokoro
    kok = Kokoro("/root/.cache/kokoro/kokoro-v1.0.onnx", "/root/.cache/kokoro/voices-v1.0.bin")
    a, sr = kok.create(txt, voice="am_fenrir", speed=SPEED, lang="en-us")
    np.save(cp, a); return a

clips, t = [], 0.25
for txt, pause in LINES:
    a = voice(txt).astype(np.float64)
    clips.append((t, a)); t += len(a) / SR + pause
TOTAL = t + END_HOLD
S = [c[0] for c in clips]
E = [c[0] + len(c[1]) / SR for c in clips]
T_OFF = E[12] - 0.1
T_BACK = E[13] + 1.3

# ------------------------------------------------------------------ outils
def lerp(a, b, u): return a + (b - a) * u
def clamp(u): return max(0.0, min(1.0, u))
def ease(u): u = clamp(u); return u * u * (3 - 2 * u)
def eout(u): u = clamp(u); return 1 - (1 - u) ** 3
def back(u):  # depassement
    u = clamp(u); c = 1.9; return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2
def hexrgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)
def rgbhex(c): return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)
def cl(a, b, u): return rgbhex(lerp(hexrgb(a), hexrgb(b), clamp(u)))
def ln(d, w, c=K, extra=""):
    return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'
def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;")
def grad(top, bot, idn="bg"):
    return (f'<defs><linearGradient id="{idn}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
            f'<stop offset="1" stop-color="{bot}"/></linearGradient></defs><rect x="-600" y="-600" width="{W + 1200}" height="{H + 1200}" fill="url(#{idn})"/>')
def heart(x, y, s, col="#ff4d6d", extra=""):
    return (f'<path transform="translate({x:.0f},{y:.0f}) scale({s:.2f})" d="M0,30 C-46,0 -34,-40 0,-16 C34,-40 46,0 0,30 Z" '
            f'fill="{col}" stroke="{K}" stroke-width="5" stroke-linejoin="round" {extra}/>')
def bigtext(txt, x, y, size, col="#fff", u=1.0, rot=0, stroke=22):
    s = back(u) if u < 1 else 1
    return (f'<g transform="translate({x},{y}) rotate({rot}) scale({s:.3f})" opacity="{clamp(u * 4):.2f}">'
            f'<text text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="none" stroke="{K}" stroke-width="{stroke}" stroke-linejoin="round">{esc(txt)}</text>'
            f'<text text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="{col}">{esc(txt)}</text></g>')

# ------------------------------------------------------------------ personnage
MOOD = {  # verre, opacite, halo, chaud, yeux, fond haut, fond bas
    "talk":   ("#ffe9a0", .55, .18, "#ff9b30", 6, "#5bc0be", "#1c6e7d"),
    "idea":   ("#fff6cf", .9,  .4,  "#ffb000", 8, "#ffb347", "#e0592a"),
    "sad":    ("#9fc8ff", .4,  .18, "#5aa0ff", 4, "#6a4c93", "#241a3d"),
    "off":    ("#6d6f76", .18, .0,  "#3a3a40", 3, "#202127", "#0b0b0e"),
}
ARMS_R = {"rest": [(234, 334), (250, 378), (254, 414)], "gest": [(234, 334), (272, 362), (298, 328)],
          "up": [(234, 334), (264, 292), (280, 240)], "chest": [(234, 334), (224, 372), (206, 352)],
          "shrug": [(234, 334), (276, 330), (292, 296)]}
ARMS_L = {"rest": [(166, 334), (150, 378), (146, 414)], "hip": [(166, 334), (144, 372), (168, 400)],
          "plug": [(166, 334), (136, 358), (108, 348)], "chest": [(166, 334), (176, 372), (194, 352)],
          "shrug": [(166, 334), (124, 330), (108, 296)], "yank": [(166, 334), (120, 300), (96, 252)]}

def moth(x, y, a=0, s=1.0, flap=1.0):
    w = 'fill="#efe5c8" stroke="#111114" stroke-width="3"'
    fy = 0.3 + 0.7 * flap
    return (f'<g transform="translate({x:.1f},{y:.1f}) rotate({a:.1f}) scale({s:.2f})">'
            f'<g transform="scale(1,{fy:.2f})"><ellipse cx="-12" cy="-6" rx="13" ry="9" {w} transform="rotate(-25 -12 -6)"/>'
            f'<ellipse cx="12" cy="-6" rx="13" ry="9" {w} transform="rotate(25 12 -6)"/>'
            f'<ellipse cx="-8" cy="7" rx="9" ry="7" {w}/><ellipse cx="8" cy="7" rx="9" ry="7" {w}/></g>'
            f'<ellipse cx="0" cy="0" rx="4.5" ry="12" fill="{K}"/>' + ln("M-2,-11 L-8,-21", 2) + ln("M2,-11 L8,-21", 2) + '</g>')

def char(t, x, y, s, mood="talk", ar="rest", al="rest", tilt=0, mouth=0.0, plug=0.0, halo_boost=0.0, rays=0.0, cable=True, dark=None):
    """(x, y) = position du point (200, 300) du dessin, s = echelle."""
    g, op, halo, hot, er = MOOD[mood][:5]
    if dark is not None:  # 0 = eteint, 1 = allume talk
        g0, g1 = MOOD["off"], MOOD["talk"]
        g, op, halo, hot, er = cl(g0[0], g1[0], dark), lerp(g0[1], g1[1], dark), lerp(0, g1[2], dark), cl(g0[3], g1[3], dark), lerp(3, 5, dark)
    if mood != "off" and (t % 3.1) < 0.11: er = 1.2
    o = ""
    if halo + halo_boost > 0.01:
        o += f'<circle cx="200" cy="190" r="{95 + 60 * halo_boost:.0f}" fill="{g}" opacity="{min(.7, halo + halo_boost):.2f}"/>'
    if rays > 0.01:
        k = 0.9 + 0.3 * rays
        for ang in (-90, -130, -50, -165, -15):
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            o += ln(f"M{200 + 118 * k * ca:.0f},{190 + 118 * k * sa:.0f} L{200 + 150 * k * ca:.0f},{190 + 150 * k * sa:.0f}", 8, "#fff6cf", f'opacity="{clamp(rays):.2f}"')
    R = [list(p) for p in ARMS_R[ar]]; L = [list(p) for p in ARMS_L[al]]
    if ar == "gest": R[2][0] += 6 * math.sin(t * 5); R[2][1] += 5 * math.sin(t * 4)
    br = 2.5 * math.sin(t * 2.2)
    if cable:
        P = np.array(lerp(np.array([352.0, 534.0]), np.array(L[2], float), plug))
        F = np.array([250.0, 556.0]); sg = 1 if P[0] > F[0] else -1
        o += ln(f"M206,312 C262,336 244,500 {F[0]:.0f},{F[1]:.0f} C{F[0] + sg * 70:.0f},{F[1] + 12:.0f} {P[0]:.0f},{P[1] + 70 + 20 * plug:.0f} {P[0]:.0f},{P[1]:.0f}", 7)
        o += f'<g transform="translate({P[0]:.0f},{P[1]:.0f}) rotate({lerp(-20, -60, plug):.0f})"><rect x="-13" y="-9" width="26" height="18" rx="4" fill="{K}"/>' + ln("M12,-5 L22,-8", 4) + ln("M12,5 L22,8", 4) + '</g>'
    o += ln("M188,420 L178,555", 22) + ln("M212,420 L222,555", 22)
    o += f'<ellipse cx="200" cy="{372 + br:.1f}" rx="34" ry="58" fill="{K}"/>'
    o += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in R for v in p]), 18)
    o += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in L for v in p]), 18)
    h = f'<rect x="182" y="282" width="36" height="34" rx="5" fill="{K}"/>' + "".join(ln(f"M184,{yy} L216,{yy}", 3, "#555") for yy in (291, 300, 309))
    h += f'<path d="M184,284 C180,262 146,242 146,192 A55,55 0 1,1 254,192 C254,242 220,262 216,284 Z" fill="{g}" fill-opacity="{op:.2f}" stroke="{K}" stroke-width="6"/>'
    h += ln("M192,284 L180,206", 3, "#444") + ln("M208,284 L220,206", 3, "#444")
    if mood == "idea":
        a = 10 + 10 * mouth
        fil = "M180,206 " + " ".join(f"L{180 + 5 * k},{206 + (0 if k == 8 else (a if k % 2 else -a)):.0f}" for k in range(1, 9))
    elif mood == "sad":
        j = 3 + 5 * mouth
        fil = "M180,214 " + " ".join(f"Q{185 + 10 * k},{214 + (j if k % 2 else -j):.1f} {190 + 10 * k},214" for k in range(4))
    elif mood == "off" and dark is None:
        fil = "M180,206 Q186,222 192,226 M208,232 Q214,222 220,206"
    else:
        fil = f"M180,206 Q200,{206 + 14 + 22 * mouth:.0f} 220,206"
    h += ln(fil, 5, hot)
    h += f'<circle cx="180" cy="200" r="{er:.1f}" fill="{hot}"/><circle cx="220" cy="200" r="{er:.1f}" fill="{hot}"/>'
    h += ln("M170,150 Q178,136 192,132", 5, "#fff", 'opacity=".7"')
    o += f'<g transform="rotate({tilt + 2 * math.sin(t * 1.3):.1f} 200 300)">{h}</g>'
    return f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.3f}) translate(-200,-300)">{o}</g>'

# ------------------------------------------------------------------ enveloppe de voix
voice_buf = np.zeros(int((TOTAL + 1) * SR))
for st, a in clips:
    i = int(st * SR); voice_buf[i:i + len(a)] += np.abs(a)
win = SR // FPS
ENV = np.array([voice_buf[i * win:(i + 1) * win].mean() for i in range(int(TOTAL * FPS) + 3)])
ENV = np.clip(np.convolve(ENV / (np.percentile(ENV, 97) + 1e-9), np.ones(3) / 3, "same"), 0, 1)
def mouth(t): return ENV[min(len(ENV) - 1, int(t * FPS))]

# ------------------------------------------------------------------ decors
def fridge(x, y):
    return (f'<rect x="{x}" y="{y}" width="230" height="460" rx="22" fill="#f2f2ee" stroke="{K}" stroke-width="8"/>'
            + ln(f"M{x},{y + 160} L{x + 230},{y + 160}", 7) + ln(f"M{x + 30},{y + 60} L{x + 30},{y + 120}", 10) + ln(f"M{x + 30},{y + 200} L{x + 30},{y + 290}", 10)
            + f'<circle cx="{x + 170}" cy="{y + 80}" r="16" fill="#ff6b6b"/><rect x="{x + 140}" y="{y + 230}" width="40" height="30" fill="#4dabf7" transform="rotate(8 {x + 160} {y + 245})"/>')
def bed(x, y):
    return (f'<rect x="{x}" y="{y}" width="560" height="60" rx="10" fill="#8d6e63" stroke="{K}" stroke-width="8"/>'
            f'<rect x="{x}" y="{y - 160}" width="40" height="220" rx="8" fill="#8d6e63" stroke="{K}" stroke-width="8"/>'
            f'<rect x="{x + 40}" y="{y - 60}" width="500" height="64" rx="20" fill="#e9ecef" stroke="{K}" stroke-width="8"/>'
            f'<rect x="{x + 50}" y="{y - 100}" width="140" height="56" rx="24" fill="#fff" stroke="{K}" stroke-width="7"/>'
            f'<rect x="{x + 200}" y="{y - 80}" width="340" height="84" rx="26" fill="#4c6ef5" stroke="{K}" stroke-width="8"/>')
def sofa_tv(x, y, t):
    fl = 0.85 + 0.15 * math.sin(t * 23)
    return (f'<rect x="{x + 330}" y="{y - 330}" width="300" height="200" rx="16" fill="{K}"/>'
            f'<rect x="{x + 348}" y="{y - 312}" width="264" height="164" rx="8" fill="#74c0fc" opacity="{fl:.2f}"/>'
            + ln(f"M{x + 480},{y - 130} L{x + 480},{y - 40}", 10) + ln(f"M{x + 420},{y - 40} L{x + 540},{y - 40}", 10)
            + f'<rect x="{x - 260}" y="{y - 150}" width="440" height="150" rx="40" fill="#e8590c" stroke="{K}" stroke-width="8"/>'
            f'<rect x="{x - 280}" y="{y - 230}" width="480" height="110" rx="40" fill="#fd7e14" stroke="{K}" stroke-width="8"/>')
def floor(y, col="#000", op=.18): return f'<rect x="-600" y="{y}" width="{W + 1200}" height="1400" fill="{col}" opacity="{op}"/>'
def person(x, y, s, col=K):
    return (f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})"><circle cx="0" cy="-150" r="34" fill="{col}"/>'
            f'<ellipse cx="0" cy="-70" rx="34" ry="56" fill="{col}"/>' + ln("M-12,-20 L-18,60", 20, col) + ln("M12,-20 L18,60", 20, col) + '</g>')
def hs_camera(x, y, t):
    rec = "#ff2b2b" if (t * 2) % 1 < 0.6 else "#5a1010"
    return (ln(f"M{x + 60},{y + 150} L{x - 20},{y + 420}", 10) + ln(f"M{x + 120},{y + 150} L{x + 120},{y + 430}", 10) + ln(f"M{x + 180},{y + 150} L{x + 260},{y + 420}", 10)
            + f'<rect x="{x}" y="{y}" width="260" height="160" rx="20" fill="#343a40" stroke="{K}" stroke-width="8"/>'
            f'<rect x="{x + 260}" y="{y + 30}" width="90" height="100" rx="10" fill="#495057" stroke="{K}" stroke-width="8"/>'
            f'<circle cx="{x + 375}" cy="{y + 80}" r="46" fill="#212529" stroke="{K}" stroke-width="8"/><circle cx="{x + 375}" cy="{y + 80}" r="24" fill="#4dabf7" opacity=".7"/>'
            f'<circle cx="{x + 40}" cy="{y + 40}" r="14" fill="{rec}"/>'
            f'<text x="{x + 64}" y="{y + 52}" font-family="Inter" font-weight="900" font-size="34" fill="#fff">REC</text>')
def lamp_post(x, y, on, t, scale=1.0):
    o = f'<g transform="translate({x},{y}) scale({scale})">'
    if on > 0:
        o += f'<circle cx="0" cy="-420" r="{110 * back(on):.0f}" fill="#ffe8a3" opacity=".35"/>'
    o += ln("M0,0 L0,-400", 16) + ln("M0,-400 Q0,-440 40,-440", 12)
    o += f'<path d="M20,-440 L80,-440 L70,-410 L30,-410 Z" fill="{K}"/><ellipse cx="50" cy="-408" rx="22" ry="9" fill="{"#fff3b0" if on > 0 else "#555"}"/>'
    if on > 0.3:
        for k in range(3):
            a = t * 3 + k * 2.1
            o += moth(50 + 70 * math.cos(a), -400 + 35 * math.sin(a), math.degrees(a) + 90, 0.8, abs(math.sin(t * 40 + k)))
    return o + '</g>'
def dino(x, y, s, t):
    leg = 12 * math.sin(t * 6)
    return (f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})">'
            f'<path d="M-160,-40 Q-60,-120 40,-90 Q90,-80 120,-160 Q130,-230 170,-240 Q200,-245 200,-225 Q170,-220 160,-170 Q150,-80 100,-30 Q40,0 -40,-10 Q-120,-10 -230,-20 Q-180,-30 -160,-40 Z" fill="{K}"/>'
            + ln(f"M-60,-20 L{-70 + leg:.0f},40", 26) + ln(f"M50,-30 L{60 - leg:.0f},40", 26) + ln(f"M-20,-20 L{-20 - leg:.0f},40", 22) + ln(f"M80,-30 L{80 + leg:.0f},40", 22) + '</g>')
def side_moth(x, y, a, s):
    w = 'fill="#efe5c8" stroke="#111114" stroke-width="6" stroke-linejoin="round"'
    return (f'<g transform="translate({x:.0f},{y:.0f}) rotate({a:.1f}) scale({s:.2f})">'
            f'<path d="M-10,-10 L-90,-150 Q-20,-140 40,-14 Z" {w}/><path d="M-20,-6 L-130,-90 Q-60,-70 0,-8 Z" {w} opacity=".85"/>'
            f'<ellipse cx="0" cy="0" rx="80" ry="22" fill="{K}"/><circle cx="84" cy="-4" r="18" fill="{K}"/>'
            + ln("M92,-18 Q120,-60 150,-62", 4) + ln("M96,-14 Q130,-40 158,-36", 4) + '</g>')

# ------------------------------------------------------------------ plans
# chaque plan : (debut, fin, fonction(tl, d, t) -> (svg du monde, camera), transition)
# camera = (zoom, cx, cy, rot, shake)
def cam(z=1.0, cx=W / 2, cy=H / 2, r=0.0, sh=0.0): return (z, cx, cy, r, sh)

def p_hook(tl, d, t):
    m = mood_mouth = mouth(t)
    s = grad("#5bc0be", "#1c6e7d") + floor(1450)
    s += char(t, 540, 960, 2.3, "talk", "gest", "rest", mouth=m)
    mx, my = 540 + 250 + 20 * math.sin(t * 2), 960 - 280 + 25 * math.sin(t * 2.7)
    s += moth(mx, my, 15 + 10 * math.sin(t * 3), 2.4, abs(math.sin(t * 36)))
    # coeur qui apparait puis barre
    u = (tl - 0.5) / 0.35
    if u > 0:
        s += heart(mx, my - 150, 2.2 * back(u))
        v = (tl - 1.3) / 0.25
        if v > 0:
            L = 130 * eout(v)
            s += ln(f"M{mx - L:.0f},{my - 150 - L:.0f} L{mx + L:.0f},{my - 150 + L:.0f}", 26, "#fff") + ln(f"M{mx - L:.0f},{my - 150 - L:.0f} L{mx + L:.0f},{my - 150 + L:.0f}", 14, "#e03131")
    z = lerp(3.2, 1.0, eout(tl / 0.7))
    return s, cam(z, lerp(mx, 540, eout(tl / 0.7)), lerp(my, 960, eout(tl / 0.7)), sh=4 if 1.3 < tl < 1.5 else 0)

def p_crowd(tl, d, t):
    s = grad("#ffd6e0", "#f783ac") + floor(1500)
    for k, (x, sc) in enumerate([(160, 1.4), (360, 1.6), (720, 1.6), (920, 1.4)]):
        s += person(x, 1500, sc * (1 + 0.03 * math.sin(t * 8 + k)))
        u = (tl - 0.15 * k) / 0.3
        if u > 0: s += heart(x, 1180 - 120 * eout(tl - 0.15 * k), 1.6 * back(u), extra=f'opacity="{clamp(2 - (tl - 0.15 * k)):.2f}"')
    s += char(t, 540, 1150, 1.3, "talk", "chest", "chest", mouth=0.3)
    s += moth(680, 820 + 15 * math.sin(t * 3), 10, 1.4, abs(math.sin(t * 36)))
    s += bigtext("aww", 540, 420, 190, "#fff", eout(tl / 0.3), -6)
    return s, cam(1.0 + 0.05 * tl)

def p_montage(which):
    def f(tl, d, t):
        if which == 0:
            s = grad("#c3fae8", "#38d9a9") + floor(1480) + fridge(620, 1020)
            s += char(t, 380, 1180, 1.6, "talk", "rest", "rest", tilt=-5, mouth=mouth(t))
            s += moth(690, 980 + 10 * math.sin(t * 4), 0, 1.6, abs(math.sin(t * 36)))
        elif which == 1:
            s = grad("#364fc7", "#1b1f3b") + floor(1480, "#000", .3) + bed(250, 1380)
            s += f'<g transform="rotate(-90 430 1255)">' + char(t, 430, 1255, 1.1, "talk", "rest", "rest", cable=False) + '</g>'
            s += moth(330, 1090 + 8 * math.sin(t * 3), 0, 1.4, 0.3)
            s += bigtext("z", 820, 1000 - 60 * (tl % 1), 110, "#fff", 1.0)
        else:
            s = grad("#ffe066", "#f08c00") + floor(1480) + sofa_tv(340, 1480, t)
            s += char(t, 300, 1120, 1.3, "talk", "rest", "rest", mouth=0)
            s += moth(330, 870, 0, 1.4, abs(math.sin(t * 2)) ** 4)
        return s, cam(1.08 - 0.06 * tl)
    return f

def p_2024(tl, d, t):
    s = grad("#212529", "#000000")
    for k in range(14):
        y = (k * 160 + tl * 900) % 2400 - 200
        s += f'<rect x="-100" y="{y:.0f}" width="1300" height="6" fill="#fff" opacity=".06"/>'
    s += bigtext("2024", 540, 1040, 330, "#ffd43b", eout(tl / 0.18), -4, 28)
    return s, cam(1.0 + 0.15 * tl, sh=8 * max(0, 1 - tl / 0.25))

def p_slowmo(tl, d, t):
    s = grad("#e7f5ff", "#a5d8ff")
    for k in range(-2, 12): s += ln(f"M{k * 110},0 L{k * 110},{H}", 2, "#74c0fc") + ln(f"M0,{k * 180} L{W},{k * 180}", 2, "#74c0fc")
    s += f'<circle cx="790" cy="560" r="150" fill="#fff3b0" opacity=".6"/>' + lamp_post(740, 1000, 0, t, 1.0).replace('"#555"', '"#fff3b0"')
    s += hs_camera(80, 1180, t)
    # papillon au ralenti, trainee
    for k in range(6):
        a = (tl * 0.6 - k * 0.05) * 2.2
        x, y = 790 + 230 * math.cos(a), 600 + 110 * math.sin(a)
        s += moth(x, y, math.degrees(a) + 90, 2.2, abs(math.sin((tl - k * 0.05) * 5)), ).replace("<g ", f'<g opacity="{1 if k == 0 else 0.18:.2f}" ', 1)
    s += f'<rect x="40" y="200" width="1000" height="1100" fill="none" stroke="#fff" stroke-width="6" stroke-dasharray="40 30" opacity=".8"/>'
    s += f'<text x="70" y="270" font-family="JetBrains Mono" font-weight="800" font-size="46" fill="{K}">00:00:{tl * 0.04:06.3f}</text>'
    s += bigtext("SUPER SLOW-MO", 540, 1720, 92, "#fff", eout(tl / 0.25))
    return s, cam(1.0 + 0.04 * tl)

def p_reveal(tl, d, t):
    s = grad("#ffb347", "#e0592a") + floor(1450)
    for k in range(16):
        a = math.radians(k * 22.5 + t * 20)
        s += f'<path d="M540,700 L{540 + 2200 * math.cos(a):.0f},{700 + 2200 * math.sin(a):.0f} L{540 + 2200 * math.cos(a + .2):.0f},{700 + 2200 * math.sin(a + .2):.0f} Z" fill="#fff" opacity=".10"/>'
    s += char(t, 540, 980, 2.4, "idea", "up", "hip", mouth=mouth(t), halo_boost=0.25 * math.exp(-tl * 2), rays=1.0)
    s += moth(800, 560 + 15 * math.sin(t * 3), 20, 2.4, abs(math.sin(t * 36)))
    w0 = S[5] + 0.55 - S[5]
    s += bigtext("NOT", 540, 330, 200, "#fff", eout((tl - w0) / 0.15), -5)
    s += bigtext("ATTRACTED", 540, 520, 150, "#ffd43b", eout((tl - w0 - 0.2) / 0.15), 3)
    punch = 1.0 + 0.12 * math.exp(-max(0, tl - w0) * 6) if tl > w0 else 1.0
    return s, cam(punch * (1.0 + 0.03 * tl), sh=10 * math.exp(-max(0, tl - w0) * 5) if tl > w0 else 0)

def p_back(tl, d, t):
    s = grad("#1b1f3b", "#0b0d1a")
    lx, ly = 540 + 260 * math.sin(tl * 1.6), 360
    s += f'<circle cx="{lx:.0f}" cy="{ly}" r="160" fill="#fff3b0" opacity=".3"/><circle cx="{lx:.0f}" cy="{ly}" r="70" fill="#fff3b0"/>'
    mx, my = 540, 1150
    a = math.degrees(math.atan2(ly - my, lx - mx)) + 90  # le dos (haut du papillon) vers la lumiere
    s += side_moth(mx, my, a, 2.6)
    s += ln(f"M{mx},{my} L{mx + (lx - mx) * 0.55:.0f},{my + (ly - my) * 0.55:.0f}", 10, "#ffd43b", 'stroke-dasharray="26 22"')
    s += bigtext("BACK", mx + (lx - mx) * 0.55, my + (ly - my) * 0.55 - 30, 96, "#ffd43b", eout(tl / 0.3))
    s += bigtext("always.", 540, 1700, 110, "#fff", eout((tl - 1.2) / 0.3)) if tl > 1.2 else ""
    return s, cam(1.0 + 0.04 * tl)

def p_ages(tl, d, t):
    k = clamp(tl / d)
    sky_t, sky_b = cl("#ffd8a8", "#4dabf7", math.sin(tl * 2.2) * .5 + .5), cl("#ff922b", "#d0ebff", math.sin(tl * 2.2) * .5 + .5)
    s = grad(sky_t, sky_b)
    a = tl * 2.2
    s += f'<circle cx="{540 - 600 * math.cos(a):.0f}" cy="{1250 - 900 * abs(math.sin(a)):.0f}" r="110" fill="#fff3b0" stroke="{K}" stroke-width="0" opacity=".95"/>'
    s += f'<path d="M-200,1350 Q200,1200 540,1330 Q900,1450 1300,1300 L1300,2200 L-200,2200 Z" fill="#2b8a3e"/><path d="M-200,1500 Q300,1420 700,1520 Q1000,1580 1300,1500 L1300,2200 L-200,2200 Z" fill="#237032"/>'
    s += dino(lerp(-300, 1400, k), 1440, 1.6, t) + dino(lerp(-700, 1000, k), 1560, 1.1, t + 1)
    s += moth(540 + 60 * math.sin(t * 1.5), 760 + 30 * math.sin(t * 2.5), 0, 2.4, abs(math.sin(t * 34)))
    s += bigtext("MILLIONS", 540, 300, 150, "#fff", eout(tl / 0.2), -3) + bigtext("OF YEARS", 540, 450, 110, "#ffd43b", eout((tl - 0.2) / 0.2), 2)
    return s, cam(1.05 - 0.04 * k)

def p_up(tl, d, t):
    s = grad("#74c0fc", "#d0ebff")
    s += f'<circle cx="540" cy="160" r="300" fill="#fff3b0" opacity=".55"/>'
    u = eout(tl / 0.4)
    s += f'<g transform="translate(540,{1000 - 140 * u:.0f})"><path d="M-90,200 L-90,-40 L-200,-40 L0,-280 L200,-40 L90,-40 L90,200 Z" fill="#ffd43b" stroke="{K}" stroke-width="12" stroke-linejoin="round"/></g>'
    s += moth(540, 1380, 0, 3.0, abs(math.sin(t * 34)))
    s += bigtext("UP", 540, 1700, 220, "#fff", eout((tl - 0.6) / 0.2)) if tl > 0.6 else ""
    return s, cam(1.0 + 0.05 * tl)

def p_lamps(tl, d, t):
    s = grad("#0b1026", "#1c2541")
    for k in range(30):
        s += f'<circle cx="{(k * 137) % 1080}" cy="{(k * 251) % 900}" r="{2 + k % 3}" fill="#fff" opacity=".5"/>'
    for k, (x, h) in enumerate([(-40, 520), (120, 700), (300, 460), (480, 820), (690, 560), (860, 740), (1020, 500)]):
        s += f'<rect x="{x}" y="{1450 - h}" width="190" height="{h}" fill="#05070f"/>'
        for r in range(int(h / 90)):
            for c in range(3):
                if (k * 7 + r * 3 + c) % 4 == 0: s += f'<rect x="{x + 30 + c * 50}" y="{1450 - h + 40 + r * 90}" width="26" height="40" fill="#ffd43b" opacity=".7"/>'
    s += f'<rect x="-600" y="1450" width="2400" height="900" fill="#05070f"/>'
    for k, x in enumerate([120, 420, 720, 1000]):
        on = (tl - 0.25 - k * 0.22) / 0.25
        s += lamp_post(x, 1450, clamp(on) if on > 0 else 0, t + k, 1.5)
    return s, cam(1.08 - 0.05 * tl, 540 + 40 * tl)

def p_skyisme(tl, d, t):
    s = grad("#6a4c93", "#241a3d") + floor(1450)
    s += char(t, 540, 1040, 2.8, "sad", "chest", "chest", tilt=5, mouth=mouth(t))
    s += moth(860, 520 + 15 * math.sin(t * 3), 30, 2.6, abs(math.sin(t * 36)))
    return s, cam(1.0 + 0.10 * ease(tl / d), 540, 760)

def p_orbit(tl, d, t):
    s = grad("#120b24", "#05030b")
    s += f'<circle cx="540" cy="900" r="300" fill="#9fc8ff" opacity=".12"/><circle cx="540" cy="900" r="150" fill="#9fc8ff" opacity=".25"/>'
    s += f'<circle cx="540" cy="900" r="80" fill="#9fc8ff" opacity=".8" stroke="{K}" stroke-width="8"/>'
    for k in range(24):
        a = t * 4.2 - k * 0.09
        r = 330 - 4 * math.sin(t * 3)
        x, y = 540 + r * math.cos(a), 900 + r * math.sin(a)
        if k == 0: s += moth(x, y, math.degrees(a) + 180, 2.6, abs(math.sin(t * 36)))
        else: s += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{10 - k * 0.35:.1f}" fill="#efe5c8" opacity="{0.5 - k * 0.02:.2f}"/>'
    if tl > 0.9: s += bigtext("FOREVER.", 540, 1550, 150, "#9fc8ff", eout((tl - 0.9) / 0.2))
    return s, cam(1.0 + 0.06 * tl, r=-12 * tl)

def p_off(tl, d, t):
    d_off = T_OFF - S[12]
    if tl < d_off:
        s = grad("#6a4c93", "#241a3d") + floor(1450)
        y = eout((tl - (d_off - 0.6)) / 0.35)
        s += char(t, 540, 1040, 2.3, "sad", "rest", "yank" if y > 0.5 else "plug", mouth=mouth(t), plug=clamp(y * 2) if tl > d_off - 0.8 else 0.0)
        s += moth(820, 560 + 15 * math.sin(t * 3), 30, 2.2, abs(math.sin(t * 36)))
        return s, cam(1.0 + 0.05 * tl)
    s = f'<rect x="-600" y="-600" width="{W + 1200}" height="{H + 1200}" fill="#000"/>'
    return s, cam(1.0)

def p_still(tl, d, t):
    tt = t - S[13]
    s = grad("#15171c", "#050506")
    s += f'<circle cx="840" cy="300" r="70" fill="#dee2e6" opacity=".25"/>'
    dark = None
    if t >= T_BACK:
        k = t - T_BACK
        dark = clamp(k / 0.7) * (1.0 if k > 0.45 else (1.0 if math.sin(k * 70) > 0 else 0.15))
        s = grad(cl("#15171c", "#5bc0be", dark * 0.7), cl("#050506", "#1c6e7d", dark * 0.7))
    s += floor(1450)
    s += char(t, 540, 1040, 2.3, "off", "rest", "plug", tilt=10, plug=1.0, dark=dark)
    # le papillon se pose sur la tete
    u = ease((tt + 0.6) / 1.4)
    hx, hy = 540 + (200 - 200) * 2.3, 1040 + (128 - 300) * 2.3
    x = lerp(860, hx + 30, u); y = lerp(600, hy, u)
    fl = abs(math.sin(t * 36)) if u < 1 else 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 2.2)) ** 6
    s += moth(x, y, 0, 2.2, fl)
    if t > T_BACK + 1.1:
        v = (t - T_BACK - 1.1) / 0.35
        s += heart(x, y - 110, 1.0 * back(v))
    return s, cam(1.0 + 0.12 * ease(tt / 4), 540, lerp(960, 700, ease(tt / 4)))

d2 = E[2] - S[2] + 0.35
SHOTS = [
    (0.0,            S[1] - 0.05, p_hook,          "cut"),
    (S[1] - 0.05,    S[2] - 0.05, p_crowd,         "whip"),
    (S[2] - 0.05,    S[2] + d2 / 3, p_montage(0),  "whip"),
    (S[2] + d2 / 3,  S[2] + 2 * d2 / 3, p_montage(1), "whip"),
    (S[2] + 2 * d2 / 3, S[3] - 0.02, p_montage(2), "whip"),
    (S[3] - 0.02,    S[4] - 0.02, p_2024,          "flash"),
    (S[4] - 0.02,    S[5] - 0.05, p_slowmo,        "zoom"),
    (S[5] - 0.05,    S[6] - 0.05, p_reveal,        "flash"),
    (S[6] - 0.05,    S[7] - 0.05, p_back,          "whip"),
    (S[7] - 0.05,    S[8] - 0.05, p_ages,          "zoom"),
    (S[8] - 0.05,    S[9] - 0.05, p_up,            "whip"),
    (S[9] - 0.05,    S[10] - 0.05, p_lamps,        "cut"),
    (S[10] - 0.05,   S[11] - 0.05, p_skyisme,      "zoom"),
    (S[11] - 0.05,   S[12] - 0.05, p_orbit,        "whip"),
    (S[12] - 0.05,   S[13] - 0.4, p_off,           "cut"),
    (S[13] - 0.4,    TOTAL + 1, p_still,           "fade"),
]

# ------------------------------------------------------------------ sous-titres mot a mot
WORDS = []
for (st, a), (txt, _) in zip(clips, LINES):
    ws = txt.split(); d = len(a) / SR; tot = sum(len(w) + 1 for w in ws); acc = st + 0.05
    groups, cur = [], []
    for w in ws:
        cur.append(w)
        if len(cur) >= 3 or w[-1] in ".,:!?": groups.append(cur); cur = []
    if cur: groups.append(cur)
    for g in groups:
        g0 = acc; ts = []
        for w in g:
            dd = (d - 0.1) * (len(w) + 1) / tot; ts.append((acc, acc + dd)); acc += dd
        WORDS.append((g0, acc, g, ts))

from PIL import ImageFont
_F = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Black.otf", 86)
def subs(t):
    for g0, g1, g, ts in WORDS:
        if g0 <= t < g1:
            sp = _F.getlength(" ")
            ws = [_F.getlength(w) for w in g]; tot = sum(ws) + sp * (len(g) - 1)
            fit = min(1.0, 940 / tot)
            pop = (1 + 0.07 * max(0, 1 - (t - g0) / 0.12)) * fit
            x = -tot / 2; a, b = "", ""
            for k, w in enumerate(g):
                col = "#ffd43b" if ts[k][0] <= t < ts[k][1] else "#fff"
                a += f'<text x="{x:.0f}" font-family="Inter" font-weight="900" font-size="86" fill="none" stroke="#000" stroke-width="18" stroke-linejoin="round">{esc(w)}</text>'
                b += f'<text x="{x:.0f}" font-family="Inter" font-weight="900" font-size="86" fill="{col}">{esc(w)}</text>'
                x += ws[k] + sp
            return f'<g transform="translate(540,1380) scale({pop:.3f})">{a}{b}</g>'
    return ""

# ------------------------------------------------------------------ audio : bruitages + musique generee
rng = np.random.default_rng(3)
def env_ad(n, a, d): x = np.arange(n) / SR; return np.minimum(1, x / max(a, 1e-4)) * np.exp(-x / d)
def s_whoosh(dur=0.32):
    n = int(dur * SR); x = rng.normal(0, 1, n); y = np.zeros(n); c = 0
    for i in range(n):
        k = 0.02 + 0.25 * math.sin(math.pi * i / n); c += k * (x[i] - c); y[i] = c
    return 0.5 * y * np.sin(np.linspace(0, math.pi, n)) ** 2
def s_pop(f0=900, f1=300, dur=0.12):
    n = int(dur * SR); ph = np.cumsum(np.linspace(f0, f1, n)) / SR * 2 * math.pi; return 0.4 * np.sin(ph) * env_ad(n, .003, .04)
def s_ding():
    n = int(1.4 * SR); tt = np.arange(n) / SR
    return (0.22 * np.sin(2 * math.pi * 1318 * tt) + 0.1 * np.sin(2 * math.pi * 1976 * tt) + 0.06 * np.sin(2 * math.pi * 2637 * tt)) * env_ad(n, .002, .45)
def s_thud():
    n = int(0.5 * SR); ph = np.cumsum(np.linspace(120, 40, n)) / SR * 2 * math.pi; return 0.7 * np.sin(ph) * env_ad(n, .002, .12)
def s_click(): n = int(0.04 * SR); return 0.6 * rng.normal(0, 1, n) * env_ad(n, .0005, .008)
def s_buzz(d):
    n = int(d * SR); tt = np.arange(n) / SR
    return 0.07 * (np.sign(np.sin(2 * math.pi * 100 * tt)) * .5 + np.sin(2 * math.pi * 200 * tt)) * np.minimum(1, tt * 8) * np.minimum(1, (d - tt) * 8)
def s_shutter(): return s_click() * .8
def s_riser(d=0.6):
    n = int(d * SR); x = rng.normal(0, 1, n) * np.linspace(0, 1, n) ** 2; return 0.15 * x

def music(total):
    bpm = 104; beat = 60 / bpm; n = int(total * SR); out = np.zeros(n)
    scale = [0, 2, 4, 7, 9, 12, 14, 16]
    prog = [57, 53, 60, 55]  # A F C G (midi des basses)
    def note(m, d, vol, bright=1.0):
        f = 440 * 2 ** ((m - 69) / 12); k = int(d * SR); tt = np.arange(k) / SR
        w = np.sin(2 * math.pi * f * tt) + bright * 0.3 * np.sin(4 * math.pi * f * tt) + bright * 0.1 * np.sin(6 * math.pi * f * tt)
        return vol * w * env_ad(k, .004, d / 3)
    i = 0; tb = 0.0
    pattern = [0, 4, 2, 5, 3, 4, 1, 6]
    while tb < total:
        bar = int(tb / (4 * beat)) % 4; root = prog[bar]
        if i % 4 == 0:
            x = note(root - 12, 4 * beat, 0.12, 0.2); j = int(tb * SR); m = min(len(x), n - j); out[j:j + m] += x[:m]
        mel = root + 12 + scale[pattern[i % 8]] - (0 if bar % 2 == 0 else 2)
        x = note(mel, beat * 0.9, 0.05); j = int(tb * SR); m = min(len(x), n - j); out[j:j + m] += x[:m]
        i += 1; tb += beat / 2 if i % 2 else beat / 2
    return out

if __name__ == "__main__":
    buf = np.zeros(int((TOTAL + 1) * SR))
    def put(x, at, g=1.0):
        i = int(at * SR); m = min(len(x), len(buf) - i)
        if m > 0 and i >= 0: buf[i:i + m] += x[:m] * g
    for st, a in clips: put(a / (np.max(np.abs(a)) + 1e-9) * 0.85, st)
    # musique, coupee au noir, rallumee a la fin
    mu = music(TOTAL + 1)
    gate = np.ones_like(mu)
    i0, i1 = int(T_OFF * SR), int((T_BACK + 0.3) * SR)
    gate[i0:i1] = 0; gate[i1:] = np.minimum(1, np.arange(len(gate) - i1) / SR / 1.0)
    duck = np.ones_like(mu)
    dv = np.convolve(voice_buf[:len(mu)] > 0.02, np.ones(SR // 10) / (SR // 10), "same")
    duck = 1 - 0.55 * np.clip(dv * 3, 0, 1)
    buf[:len(mu)] += mu * gate * duck * 0.9
    # bruitages aux transitions
    for st, en, fn, tr in SHOTS[1:]:
        if tr == "whip": put(s_whoosh(), st - 0.12)
        elif tr == "flash": put(s_thud(), st, 0.8); put(s_riser(), st - 0.6, 0.6)
        elif tr == "zoom": put(s_whoosh(0.4), st - 0.15, 0.7)
    put(s_pop(700, 1100), 0.5 + 0.0, 0.8); put(s_pop(300, 120, 0.25), 1.3, 1.0)
    for k in range(4): put(s_pop(800 + 100 * k, 1200 + 100 * k), S[1] - 0.05 + 0.15 * k, 0.5)
    put(s_thud(), S[3] - 0.02, 1.0)
    for k in range(6): put(s_shutter(), S[4] + 0.2 + 0.35 * k, 0.5)
    put(s_ding(), S[5] + 0.5, 1.0); put(s_thud(), S[5] + 0.5, 0.6)
    for k in range(4): put(s_click(), S[9] + 0.25 + k * 0.22, 0.7); put(s_buzz(0.3), S[9] + 0.25 + k * 0.22, 0.5)
    put(s_click(), T_OFF, 1.0); put(s_thud(), T_OFF, 0.5)
    put(s_buzz(0.5), T_BACK, 1.0); put(s_click(), T_BACK, 0.5); put(s_pop(600, 900), T_BACK + 1.1, 0.6)
    m = np.percentile(np.abs(buf), 99.8); buf = np.tanh(buf / m * 0.95) * 0.9
    with wave.open(OUT + ".wav", "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((buf * 32767).astype(np.int16).tobytes())

def shot_at(t):
    for k, (a, b, fn, tr) in enumerate(SHOTS):
        if a <= t < b: return k
    return len(SHOTS) - 1

def world(k, t):
    a, b, fn, tr = SHOTS[k]
    svg, (z, cx, cy, r, sh) = fn(t - a, b - a, t)
    if sh: cx += sh * math.sin(t * 91); cy += sh * math.cos(t * 77)
    return f'<g transform="translate({W / 2},{H / 2}) rotate({r:.2f}) scale({z:.4f}) translate({-cx:.1f},{-cy:.1f})">{svg}</g>'

def frame(f):
    t = f / FPS
    k = shot_at(t); a, b, fn, tr = SHOTS[k]; tl = t - a
    body = world(k, t)
    over = ""
    if tr == "whip" and tl < 0.16 and k > 0:
        u = eout(tl / 0.16)
        prev = world(k - 1, a - 0.001)
        body = (f'<g transform="translate({-W * u:.0f},0)">{prev}</g><g transform="translate({W * (1 - u):.0f},0)">{body}</g>')
        over = "".join(f'<rect x="0" y="{y}" width="{W}" height="10" fill="#fff" opacity=".25"/>' for y in range(60, H, 140))
    elif tr == "flash" and tl < 0.2:
        over = f'<rect width="{W}" height="{H}" fill="#fff" opacity="{1 - tl / 0.2:.2f}"/>'
    elif tr == "zoom" and tl < 0.22:
        u = eout(tl / 0.22)
        body = f'<g transform="translate({W / 2},{H / 2}) scale({lerp(1.6, 1.0, u):.3f}) translate({-W / 2},{-H / 2})">{body}</g>'
        over = f'<rect width="{W}" height="{H}" fill="#fff" opacity="{0.5 * (1 - u):.2f}"/>'
    elif tr == "fade" and tl < 0.3:
        over = f'<rect width="{W}" height="{H}" fill="#000" opacity="{1 - tl / 0.3:.2f}"/>'
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#000"/>', body, over,
         f'<defs><radialGradient id="vig" cx=".5" cy=".45" r=".8"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".4"/></radialGradient></defs>'
         f'<rect width="{W}" height="{H}" fill="url(#vig)"/>']
    if t < 2.2:
        o.append(f'<g opacity="{clamp((2.2 - t) / 0.3):.2f}"><rect x="60" y="150" width="960" height="140" rx="30" fill="#000" opacity=".6"/>'
                 f'<text x="540" y="245" text-anchor="middle" font-family="Inter" font-weight="900" font-size="68" fill="#fff">This moth isn\'t in love with me.</text></g>')
    if not (T_OFF <= t < S[13]) and not (S[3] - 0.02 <= t < S[4] - 0.02):
        o.append(subs(t))
    o.append("</svg>")
    png = cairosvg.svg2png(bytestring="".join(o).encode())
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).tobytes()

if __name__ == "__main__":
    if "--still" in sys.argv:
        ts = [float(x) for x in sys.argv[sys.argv.index("--still") + 1].split(",")]
        ims = [Image.frombytes("RGB", (W, H), frame(int(tt * FPS))).resize((216, 384)) for tt in ts]
        sheet = Image.new("RGB", (216 * min(8, len(ims)), 384 * ((len(ims) + 7) // 8)))
        for i, im in enumerate(ims): sheet.paste(im, ((i % 8) * 216, (i // 8) * 384))
        sheet.save(OUT + "_sheet.png"); print("shots", [(round(a, 1), fn.__name__) for a, b, fn, tr in SHOTS]); sys.exit()
    nf = int(TOTAL * FPS)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", OUT + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT], stdin=subprocess.PIPE)
    with Pool(4) as p:
        for fr in p.imap(frame, range(nf), chunksize=6): ff.stdin.write(fr)
    ff.stdin.close(); ff.wait()
    print("total", round(TOTAL, 1), "s")
