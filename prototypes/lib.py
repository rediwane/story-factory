"""Bibliotheque commune des prototypes : personnage, papillon, decors, camera, transitions,
texte, sous-titres, bruitages et musique generes, rendu. Un prototype = une liste de
phrases (voix) et une liste de plans (fonctions de dessin SVG)."""
import sys, math, io, os, subprocess, wave, hashlib
import numpy as np
import cairosvg
from PIL import Image, ImageFont
from multiprocessing import Pool

W, H, FPS, SR = 1080, 1920, 30, 24000
K = "#111114"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
os.makedirs(CACHE, exist_ok=True)

# ------------------------------------------------------------------ outils
def lerp(a, b, u): return a + (b - a) * u
def clamp(u): return max(0.0, min(1.0, u))
def ease(u): u = clamp(u); return u * u * (3 - 2 * u)
def eout(u): u = clamp(u); return 1 - (1 - u) ** 3
def ein(u): u = clamp(u); return u ** 3
def back(u): u = clamp(u); c = 1.9; return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2
def hexrgb(h):
    h = h.lstrip("#"); h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)
def rgbhex(c): return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)
def cl(a, b, u): return rgbhex(lerp(hexrgb(a), hexrgb(b), clamp(u)))
def ln(d, w, c=K, extra=""):
    return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'
def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;")
def g(inner, tx=0, ty=0, s=1.0, r=0.0, op=1.0):
    return f'<g transform="translate({tx:.1f},{ty:.1f}) rotate({r:.2f}) scale({s:.3f})" opacity="{op:.2f}">{inner}</g>'
def rect(x, y, w, h, fill, rx=0, extra=""): return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{rx}" fill="{fill}" {extra}/>'
def circ(x, y, r, fill, extra=""): return f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{fill}" {extra}/>'
def grad(top, bot, idn="bg"):
    return (f'<defs><linearGradient id="{idn}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
            f'<stop offset="1" stop-color="{bot}"/></linearGradient></defs><rect x="-800" y="-800" width="{W + 1600}" height="{H + 1600}" fill="url(#{idn})"/>')
def floor(y, col="#000", op=.18): return rect(-800, y, W + 1600, 1600, col, extra=f'opacity="{op}"')
def cam(z=1.0, cx=W / 2, cy=H / 2, r=0.0, sh=0.0): return (z, cx, cy, r, sh)

# ------------------------------------------------------------------ texte
FONT_BLACK = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
_fonts = {}
def _font(px):
    if px not in _fonts: _fonts[px] = ImageFont.truetype(FONT_BLACK, px)
    return _fonts[px]
def textw(txt, px): return _font(px).getlength(txt)

def bigtext(txt, x, y, size, col="#fff", u=1.0, rot=0, stroke=None, maxw=980):
    """gros mot anime : pop avec depassement, contour noir."""
    if u <= 0: return ""
    stroke = stroke if stroke is not None else int(size * 0.24)
    fit = min(1.0, maxw / max(1, textw(txt, size)))
    s = (back(u) if u < 1 else 1) * fit
    return (f'<g transform="translate({x:.0f},{y:.0f}) rotate({rot}) scale({s:.3f})" opacity="{clamp(u * 4):.2f}">'
            f'<text text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="none" stroke="{K}" stroke-width="{stroke}" stroke-linejoin="round">{esc(txt)}</text>'
            f'<text text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="{col}">{esc(txt)}</text></g>')

def typed(txt, x, y, size, u, col=K, font="JetBrains Mono", anchor="start", lineh=1.35, maxw=820):
    """texte qui s'ecrit lettre a lettre, avec retours a la ligne."""
    n = int(clamp(u) * len(txt)); shown = txt[:n]
    f = ImageFont.truetype("/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf", size) if os.path.exists("/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf") else _font(size)
    lines, cur = [], ""
    for w in txt.split(" "):
        test = (cur + " " + w).strip()
        if f.getlength(test) > maxw and cur: lines.append(cur); cur = w
        else: cur = test
    lines.append(cur)
    out, count = "", 0
    for i, line in enumerate(lines):
        if count >= n: break
        part = line[:max(0, n - count)]; count += len(line) + 1
        out += f'<text x="{x}" y="{y + i * size * lineh:.0f}" text-anchor="{anchor}" font-family="{font}" font-weight="700" font-size="{size}" fill="{col}">{esc(part)}</text>'
    return out

def label(txt, x, y, size=44, bg="#000", fg="#fff", op=.6):
    w = textw(txt, size) + 60
    return rect(x - w / 2, y - size * 0.85, w, size * 1.3, bg, 18, f'opacity="{op}"') + f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="{fg}">{esc(txt)}</text>'

# ------------------------------------------------------------------ personnage
MOOD = {  # verre, opacite verre, halo, couleur chaude (yeux + filament), rayon des yeux, fond haut, fond bas
    "talk":  ("#ffe9a0", .55, .18, "#ff9b30", 6, "#5bc0be", "#1c6e7d"),
    "happy": ("#fff1b8", .7,  .28, "#ffb000", 7, "#ffd166", "#ef8354"),
    "idea":  ("#fff6cf", .9,  .4,  "#ffb000", 8, "#ffb347", "#e0592a"),
    "sad":   ("#9fc8ff", .4,  .18, "#5aa0ff", 4, "#6a4c93", "#241a3d"),
    "fear":  ("#b9d6ff", .35, .14, "#7fb3ff", 3, "#2b2d42", "#0d0e14"),
    "angry": ("#ffb3a7", .6,  .25, "#ff3b30", 5, "#c92a2a", "#5c0b0b"),
    "off":   ("#6d6f76", .18, .0,  "#3a3a40", 3, "#202127", "#0b0b0e"),
}
ARMS_R = {"rest": [(234, 334), (250, 378), (254, 414)], "gest": [(234, 334), (272, 362), (298, 328)],
          "up": [(234, 334), (264, 292), (280, 240)], "chest": [(234, 334), (224, 372), (206, 352)],
          "shrug": [(234, 334), (276, 330), (292, 296)], "point": [(234, 334), (290, 330), (340, 326)],
          "hold": [(234, 334), (262, 372), (240, 400)], "head": [(234, 334), (268, 300), (240, 250)],
          "hang": [(234, 334), (244, 390), (240, 440)], "walk": None}
ARMS_L = {"rest": [(166, 334), (150, 378), (146, 414)], "hip": [(166, 334), (144, 372), (168, 400)],
          "plug": [(166, 334), (136, 358), (108, 348)], "chest": [(166, 334), (176, 372), (194, 352)],
          "shrug": [(166, 334), (124, 330), (108, 296)], "yank": [(166, 334), (120, 300), (96, 252)],
          "hold": [(166, 334), (138, 372), (160, 400)], "head": [(166, 334), (132, 300), (160, 250)],
          "hang": [(166, 334), (156, 390), (160, 440)], "up": [(166, 334), (136, 292), (120, 240)], "walk": None}

def moth(x, y, a=0, s=1.0, flap=1.0, op=1.0):
    w = 'fill="#efe5c8" stroke="#111114" stroke-width="3"'
    fy = 0.3 + 0.7 * flap
    return (f'<g transform="translate({x:.1f},{y:.1f}) rotate({a:.1f}) scale({s:.2f})" opacity="{op:.2f}">'
            f'<g transform="scale(1,{fy:.2f})"><ellipse cx="-12" cy="-6" rx="13" ry="9" {w} transform="rotate(-25 -12 -6)"/>'
            f'<ellipse cx="12" cy="-6" rx="13" ry="9" {w} transform="rotate(25 12 -6)"/>'
            f'<ellipse cx="-8" cy="7" rx="9" ry="7" {w}/><ellipse cx="8" cy="7" rx="9" ry="7" {w}/></g>'
            f'<ellipse cx="0" cy="0" rx="4.5" ry="12" fill="{K}"/>' + ln("M-2,-11 L-8,-21", 2) + ln("M2,-11 L8,-21", 2) + '</g>')

def moth_near(t, x, y, s=2.3, phase=0.0):
    """papillon qui voltige pres d'un point (en haut a droite de la tete)."""
    return moth(x + 20 * math.sin(t * 2 + phase), y + 25 * math.sin(t * 2.7 + phase), 15 + 10 * math.sin(t * 3), s, abs(math.sin(t * 36)))

def char(t, x, y, s, mood="talk", ar="rest", al="rest", tilt=0, mouth=0.0, plug=0.0, halo_boost=0.0, rays=0.0,
         cable=True, lit=None, walk=None, face=1, shiver=0.0, blink=True, eyes=None):
    """(x, y) = position du point (200, 300) du dessin (bas du cou), s = echelle.
    lit : 0 eteint -> 1 humeur (pour allumer, eteindre, clignoter). walk : phase de marche (None = debout).
    face : 1 vers la droite, -1 vers la gauche. eyes : 'closed', 'wide', None."""
    m = MOOD[mood]
    gl, op, halo, hot, er = m[:5]
    if lit is not None:
        o_ = MOOD["off"]
        gl, op, halo, hot, er = cl(o_[0], gl, lit), lerp(o_[1], op, lit), lerp(0, halo, lit), cl(o_[3], hot, lit), lerp(3, er, lit)
    if blink and mood != "off" and (t % 3.1) < 0.11: er = 1.2
    if eyes == "closed": er = 1.2
    if eyes == "wide": er *= 1.6
    o = ""
    if halo + halo_boost > 0.01:
        o += circ(200, 190, 95 + 60 * halo_boost, gl, f'opacity="{min(.7, halo + halo_boost):.2f}"')
    if rays > 0.01:
        k = 0.9 + 0.3 * rays
        for ang in (-90, -130, -50, -165, -15):
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            o += ln(f"M{200 + 118 * k * ca:.0f},{190 + 118 * k * sa:.0f} L{200 + 150 * k * ca:.0f},{190 + 150 * k * sa:.0f}", 8, "#fff6cf", f'opacity="{clamp(rays):.2f}"')
    if walk is not None:
        sw = math.sin(walk)
        R = [(234, 334), (250 + 30 * sw, 378), (254 + 60 * sw, 400)]; L = [(166, 334), (150 - 30 * sw, 378), (146 - 60 * sw, 400)]
        legs = ln(f"M188,420 L{178 + 45 * sw:.0f},{555 - 25 * abs(sw):.0f}", 22) + ln(f"M212,420 L{222 - 45 * sw:.0f},{555 - 25 * abs(sw):.0f}", 22)
        bob = -8 * abs(math.sin(walk))
    else:
        R = [list(p) for p in ARMS_R[ar]]; L = [list(p) for p in ARMS_L[al]]
        if ar == "gest": R[2][0] += 6 * math.sin(t * 5); R[2][1] += 5 * math.sin(t * 4)
        legs = ln("M188,420 L178,555", 22) + ln("M212,420 L222,555", 22)
        bob = 0
    if cable:
        P = np.array(lerp(np.array([352.0, 534.0]), np.array(L[2], float), plug))
        F = np.array([250.0, 556.0]); sg = 1 if P[0] > F[0] else -1
        o += ln(f"M206,312 C262,336 244,500 {F[0]:.0f},{F[1]:.0f} C{F[0] + sg * 70:.0f},{F[1] + 12:.0f} {P[0]:.0f},{P[1] + 70 + 20 * plug:.0f} {P[0]:.0f},{P[1]:.0f}", 7)
        o += f'<g transform="translate({P[0]:.0f},{P[1]:.0f}) rotate({lerp(-20, -60, plug):.0f})">' + rect(-13, -9, 26, 18, K, 4) + ln("M12,-5 L22,-8", 4) + ln("M12,5 L22,8", 4) + '</g>'
    br = 2.5 * math.sin(t * 2.2) + bob
    body = legs + f'<ellipse cx="200" cy="{372 + br:.1f}" rx="34" ry="58" fill="{K}"/>'
    body += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in R for v in p]), 18)
    body += ln("M{:.0f},{:.0f} L{:.0f},{:.0f} L{:.0f},{:.0f}".format(*[v for p in L for v in p]), 18)
    h = rect(182, 282, 36, 34, K, 5) + "".join(ln(f"M184,{yy} L216,{yy}", 3, "#555") for yy in (291, 300, 309))
    h += f'<path d="M184,284 C180,262 146,242 146,192 A55,55 0 1,1 254,192 C254,242 220,262 216,284 Z" fill="{gl}" fill-opacity="{op:.2f}" stroke="{K}" stroke-width="6"/>'
    h += ln("M192,284 L180,206", 3, "#444") + ln("M208,284 L220,206", 3, "#444")
    if mood == "idea" or mood == "happy":
        a = (10 if mood == "idea" else 6) + 10 * mouth
        fil = "M180,206 " + " ".join(f"L{180 + 5 * k},{206 + (0 if k == 8 else (a if k % 2 else -a)):.0f}" for k in range(1, 9)) if mood == "idea" else f"M178,204 Q200,{214 + 22 * mouth + 10:.0f} 222,204"
    elif mood in ("sad", "fear"):
        j = (3 if mood == "sad" else 5) + 5 * mouth
        fil = "M180,214 " + " ".join(f"Q{185 + 10 * k},{214 + (j if k % 2 else -j) + (math.sin(t * 40 + k) * 2 if mood == "fear" else 0):.1f} {190 + 10 * k},214" for k in range(4))
    elif mood == "angry":
        fil = f"M180,210 L200,{196 + 14 * mouth:.0f} L220,210"
    elif mood == "off" and lit is None:
        fil = "M180,206 Q186,222 192,226 M208,232 Q214,222 220,206"
    else:
        fil = f"M180,206 Q200,{206 + 14 + 22 * mouth:.0f} 220,206"
    h += ln(fil, 5, hot)
    if mood == "angry": h += ln("M168,186 L188,194 M232,186 L212,194", 4, hot)
    h += circ(180, 200, er, hot) + circ(220, 200, er, hot)
    h += ln("M170,150 Q178,136 192,132", 5, "#fff", 'opacity=".7"')
    tt = tilt + 2 * math.sin(t * 1.3) + shiver * 3 * math.sin(t * 60)
    body += f'<g transform="rotate({tt:.1f} 200 300)">{h}</g>'
    jx = shiver * 4 * math.sin(t * 53)
    return f'<g transform="translate({x + jx:.1f},{y:.0f}) scale({s * face:.3f},{s:.3f}) translate(-200,-300)">{o}{body}</g>'

# ------------------------------------------------------------------ decors et objets
def person(x, y, s, col=K, arms="down"):
    a = ln("M-12,-20 L-18,60", 20, col) + ln("M12,-20 L18,60", 20, col) if arms == "down" else ln("M-12,-20 L-50,-90", 20, col) + ln("M12,-20 L50,-90", 20, col)
    return g(circ(0, -150, 34, col) + f'<ellipse cx="0" cy="-70" rx="34" ry="56" fill="{col}"/>' + a + ln("M-14,-20 L-20,80", 22, col) + ln("M14,-20 L20,80", 22, col), x, y, s)
def heart(x, y, s, col="#ff4d6d", extra=""):
    return (f'<path transform="translate({x:.0f},{y:.0f}) scale({s:.2f})" d="M0,30 C-46,0 -34,-40 0,-16 C34,-40 46,0 0,30 Z" fill="{col}" stroke="{K}" stroke-width="5" stroke-linejoin="round" {extra}/>')
def table(x, y, w=520):
    return rect(x - w / 2, y, w, 34, "#a3754a", 8, f'stroke="{K}" stroke-width="7"') + ln(f"M{x - w / 2 + 40},{y + 34} L{x - w / 2 + 40},{y + 300}", 18) + ln(f"M{x + w / 2 - 40},{y + 34} L{x + w / 2 - 40},{y + 300}", 18)
def box(x, y, s=1.0, open_u=0.0, txt="", col="#c9a26b"):
    lid = f'<g transform="translate(-120,0) rotate({-110 * open_u:.0f}) translate(120,0)">' + rect(-125, -22, 250, 24, cl(col, "#000", .15), 4, f'stroke="{K}" stroke-width="6"') + '</g>'
    inner = rect(-120, 0, 240, 170, col, 6, f'stroke="{K}" stroke-width="7"') + ln("M0,0 L0,170", 4, "#8a6a3d") + lid
    if txt: inner += f'<text x="0" y="110" text-anchor="middle" font-family="Inter" font-weight="900" font-size="48" fill="{K}">{esc(txt)}</text>'
    return g(inner, x, y, s)
def led_bulb(x, y, s=1.0, on=0.0):
    col = cl("#dfe3ea", "#ffffff", on)
    return g((circ(0, -20, 140, "#fff", f'opacity="{.5 * on:.2f}"') if on else "") + f'<path d="M-50,60 C-55,20 -90,0 -90,-50 A90,90 0 1,1 90,-50 C90,0 55,20 50,60 Z" fill="{col}" stroke="{K}" stroke-width="7"/>' + rect(-40, 60, 80, 50, "#9aa0a6", 6, f'stroke="{K}" stroke-width="6"') + "".join(ln(f"M-36,{yy} L36,{yy}", 3, "#555") for yy in (72, 84, 96)), x, y, s)
def window(x, y, w=380, h=480, sky="#1b1f3b", moon=True, rain=0, t=0.0):
    o = rect(0, 0, w, h, sky, 10, f'stroke="{K}" stroke-width="14"')
    if moon: o += circ(w * 0.7, h * 0.25, 46, "#fff3b0")
    for k in range(rain):
        xx = (k * 73 + t * 900) % w; yy = (k * 131 + t * 1900) % h
        o += ln(f"M{xx:.0f},{yy:.0f} L{xx - 8:.0f},{yy + 40:.0f}", 3, "#9fc8ff", 'opacity=".7"')
    o += ln(f"M{w / 2},0 L{w / 2},{h} M0,{h / 2} L{w},{h / 2}", 12)
    return g(o, x, y)
def door(x, y, w=300, h=620, open_u=0.0, col="#7f5539", light=None):
    o = rect(-16, -16, w + 32, h + 16, "#3d2b1f", 6)
    if light and open_u > 0: o += rect(0, 0, w * open_u, h, light)
    o += f'<g transform="translate(0,0) scale({1 - 0.9 * open_u:.3f},1)">' + rect(0, 0, w, h, col, 4, f'stroke="{K}" stroke-width="8"') + circ(w - 50, h / 2, 14, "#ffd43b") + rect(40, 60, w - 80, h * 0.35, cl(col, "#000", .15), 6) + rect(40, h * 0.5, w - 80, h * 0.4, cl(col, "#000", .15), 6) + '</g>'
    return g(o, x, y)
def switch(x, y, on=1, s=1.0):
    return g(rect(-60, -90, 120, 180, "#f1f3f5", 12, f'stroke="{K}" stroke-width="7"') + rect(-26, -56 if on else -4, 52, 60, "#dee2e6", 6, f'stroke="{K}" stroke-width="6"') + circ(0, -74 if on else 54, 6, "#adb5bd"), x, y, s)
def city(t, y=1450, lamps=True, stars=True, windows_on=.7):
    o = ""
    if stars:
        for k in range(40): o += circ((k * 137) % 1080, (k * 251) % 900, 2 + k % 3, "#fff", 'opacity=".5"')
    for k, (x, h) in enumerate([(-40, 520), (120, 700), (300, 460), (480, 820), (690, 560), (860, 740), (1020, 500)]):
        o += rect(x, y - h, 190, h, "#05070f")
        for r in range(int(h / 90)):
            for c in range(3):
                if ((k * 7 + r * 3 + c) % 10) / 10 < windows_on * 0.4: o += rect(x + 30 + c * 50, y - h + 40 + r * 90, 26, 40, "#ffd43b", extra='opacity=".7"')
    o += rect(-800, y, 2400, 900, "#05070f")
    return o
def lamp_post(x, y, on, t, scale=1.0):
    o = f'<g transform="translate({x},{y}) scale({scale})">'
    if on > 0: o += circ(50, -420, 110 * back(on), "#ffe8a3", 'opacity=".35"')
    o += ln("M0,0 L0,-400", 16) + ln("M0,-400 Q0,-440 40,-440", 12)
    o += f'<path d="M20,-440 L80,-440 L70,-410 L30,-410 Z" fill="{K}"/><ellipse cx="50" cy="-408" rx="22" ry="9" fill="{"#fff3b0" if on > 0 else "#555"}"/>'
    return o + '</g>'
def room(top="#2b2d42", bot="#1a1b2e", fl=1450, wallcol=None):
    return grad(top, bot) + floor(fl, "#000", .25) + ln(f"M-800,{fl} L1900,{fl}", 6, "#000", 'opacity=".3"')
def shelf(x, y, w=420): return rect(x, y, w, 22, "#8d6e63", 4, f'stroke="{K}" stroke-width="6"') + ln(f"M{x + 30},{y + 22} L{x + 60},{y + 70} M{x + w - 30},{y + 22} L{x + w - 60},{y + 70}", 10)
def tools(x, y): return ln(f"M{x},{y} L{x},{y + 160}", 14, "#495057") + rect(x - 50, y - 30, 100, 44, "#868e96", 6, f'stroke="{K}" stroke-width="6"') + ln(f"M{x + 120},{y} L{x + 120},{y + 170}", 10, "#495057") + f'<path d="M{x + 90},{y} L{x + 150},{y} L{x + 120},{y - 60} Z" fill="#868e96" stroke="{K}" stroke-width="6"/>'
def letter(x, y, w=620, h=760, u=1.0, s=1.0, rot=-3):
    return g(rect(0, 0, w, h, "#fdf6e3", 10, f'stroke="{K}" stroke-width="8"') + "".join(ln(f"M50,{80 + k * 60} L{w - 50},{80 + k * 60}", 2, "#e9dcc3") for k in range(int(h / 60) - 1)), x, y, s, rot)
def sun(x, y, r=120): return circ(x, y, r * 1.6, "#fff3b0", 'opacity=".35"') + circ(x, y, r, "#ffe066")
def tree(x, y, s=1.0): return g(ln("M0,0 L0,-220", 40) + circ(0, -300, 150, "#2f9e44") + circ(-110, -230, 100, "#2f9e44") + circ(110, -230, 100, "#2f9e44"), x, y, s)
def clock(x, y, hh, mm, s=1.0):
    ah, am = math.radians(hh % 12 * 30 + mm / 2 - 90), math.radians(mm * 6 - 90)
    return g(circ(0, 0, 90, "#fff", f'stroke="{K}" stroke-width="8"') + ln(f"M0,0 L{48 * math.cos(ah):.0f},{48 * math.sin(ah):.0f}", 9) + ln(f"M0,0 L{70 * math.cos(am):.0f},{70 * math.sin(am):.0f}", 6) + circ(0, 0, 6, K), x, y, s)
def digital(x, y, txt, size=180, col="#ff3b30"): return f'<text x="{x}" y="{y}" text-anchor="middle" font-family="JetBrains Mono" font-weight="800" font-size="{size}" fill="{col}">{esc(txt)}</text>'
def phone(x, y, s=1.0, txt=""):
    return g(rect(-150, -300, 300, 600, "#212529", 36, f'stroke="{K}" stroke-width="8"') + rect(-132, -270, 264, 540, "#f8f9fa", 20) + (f'<text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="54" fill="{K}">{esc(txt)}</text>' if txt else ""), x, y, s)
def speech(x, y, txt, size=58, w=None, tail="left"):
    w = w or textw(txt, size) + 80
    o = rect(-w / 2, -size, w, size * 1.7, "#fff", 30, f'stroke="{K}" stroke-width="7"')
    o += f'<path d="M{-w / 4 if tail == "left" else w / 4},{size * .68} L{-w / 4 - 30 if tail == "left" else w / 4 + 30},{size * 1.3} L{-w / 4 + 40 if tail == "left" else w / 4 - 40},{size * .68} Z" fill="#fff" stroke="{K}" stroke-width="7" stroke-linejoin="round"/>'
    o += rect(-w / 2 + 8, -size + 8, w - 16, size * 1.7 - 16, "#fff", 24)
    o += f'<text x="0" y="{size * .3}" text-anchor="middle" font-family="Inter" font-weight="900" font-size="{size}" fill="{K}">{esc(txt)}</text>'
    return g(o, x, y)

# ------------------------------------------------------------------ sons
rng = np.random.default_rng(3)
def env_ad(n, a, d): x = np.arange(n) / SR; return np.minimum(1, x / max(a, 1e-4)) * np.exp(-x / d)
def s_whoosh(dur=0.32):
    n = int(dur * SR); x = rng.normal(0, 1, n); y = np.zeros(n); c = 0.0
    for i in range(n):
        k = 0.02 + 0.25 * math.sin(math.pi * i / n); c += k * (x[i] - c); y[i] = c
    return 0.5 * y * np.sin(np.linspace(0, math.pi, n)) ** 2
def s_pop(f0=900, f1=300, dur=0.12):
    n = int(dur * SR); ph = np.cumsum(np.linspace(f0, f1, n)) / SR * 2 * math.pi; return 0.4 * np.sin(ph) * env_ad(n, .003, .04)
def s_ding():
    n = int(1.4 * SR); tt = np.arange(n) / SR
    return (0.22 * np.sin(2 * math.pi * 1318 * tt) + 0.1 * np.sin(2 * math.pi * 1976 * tt) + 0.06 * np.sin(2 * math.pi * 2637 * tt)) * env_ad(n, .002, .45)
def s_thud(f0=120, f1=40, dur=0.5):
    n = int(dur * SR); ph = np.cumsum(np.linspace(f0, f1, n)) / SR * 2 * math.pi; return 0.7 * np.sin(ph) * env_ad(n, .002, .12)
def s_click(): n = int(0.04 * SR); return 0.6 * rng.normal(0, 1, n) * env_ad(n, .0005, .008)
def s_buzz(d, f=100):
    n = int(d * SR); tt = np.arange(n) / SR
    return 0.07 * (np.sign(np.sin(2 * math.pi * f * tt)) * .5 + np.sin(2 * math.pi * 2 * f * tt)) * np.minimum(1, tt * 8) * np.minimum(1, (d - tt) * 8)
def s_riser(d=0.6): n = int(d * SR); return 0.15 * rng.normal(0, 1, n) * np.linspace(0, 1, n) ** 2
def s_knock(): return np.concatenate([s_thud(400, 150, 0.09) * .7, np.zeros(int(0.14 * SR)), s_thud(400, 150, 0.09) * .7, np.zeros(int(0.14 * SR)), s_thud(400, 150, 0.09) * .7])
def s_steps(n=4, gap=0.42): return np.concatenate([np.concatenate([s_thud(180, 60, 0.18) * .35, np.zeros(int(gap * SR))]) for _ in range(n)])
def s_creak(d=1.2):
    n = int(d * SR); tt = np.arange(n) / SR; f = 180 + 60 * np.sin(tt * 9) + 40 * tt
    return 0.12 * np.sin(np.cumsum(f) / SR * 2 * math.pi) * (1 + 0.5 * np.sin(tt * 70)) * env_ad(n, .1, d)
def s_heart(d=0.6): n = int(d * SR); return np.concatenate([s_thud(70, 40, 0.15), np.zeros(int(0.12 * SR)), s_thud(60, 35, 0.15) * .8, np.zeros(max(0, n - int(0.42 * SR)))])
def s_scratch(): n = int(0.5 * SR); x = rng.normal(0, 1, n) * (np.sin(np.arange(n) / SR * 2 * math.pi * 11) > 0.3); return 0.18 * x
def s_paper(): n = int(0.25 * SR); return 0.25 * rng.normal(0, 1, n) * env_ad(n, .01, .06) * (np.sin(np.arange(n) / SR * 2 * math.pi * 60) * .5 + .5)
def s_sparkle():
    out = np.zeros(int(0.7 * SR))
    for k in range(4):
        x = s_pop(1200 + 300 * k, 1800 + 300 * k, 0.1) * .4; i = int(0.07 * k * SR); out[i:i + len(x)] += x
    return out
def s_zap(): n = int(0.18 * SR); return 0.5 * rng.normal(0, 1, n) * env_ad(n, .001, .03) * np.sin(np.arange(n) / SR * 2 * math.pi * 3000)
def s_laugh(): return np.concatenate([s_pop(500 + 40 * k, 350, 0.09) for k in range(4)])
def s_drone(d, f=55): n = int(d * SR); tt = np.arange(n) / SR; return 0.08 * (np.sin(2 * math.pi * f * tt) + .5 * np.sin(2 * math.pi * f * 1.5 * tt + np.sin(tt * .7))) * np.minimum(1, tt / 2) * np.minimum(1, (d - tt) / 2)
def s_ticktock(n=6, gap=0.5): return np.concatenate([np.concatenate([s_click() * (.6 if k % 2 else .9), np.zeros(int(gap * SR))]) for k in range(n)])

def music(total, style="upbeat"):
    n = int(total * SR); out = np.zeros(n)
    def note(m, d, vol, bright=1.0):
        f = 440 * 2 ** ((m - 69) / 12); k = int(d * SR); tt = np.arange(k) / SR
        w = np.sin(2 * math.pi * f * tt) + bright * 0.3 * np.sin(4 * math.pi * f * tt) + bright * 0.1 * np.sin(6 * math.pi * f * tt)
        return vol * w * env_ad(k, .004, d / 3)
    def put(x, at):
        j = int(at * SR); m = min(len(x), n - j)
        if m > 0: out[j:j + m] += x[:m]
    if style == "none": return out
    if style == "upbeat":
        bpm, prog, scale, pattern = 104, [57, 53, 60, 55], [0, 2, 4, 7, 9, 12, 14, 16], [0, 4, 2, 5, 3, 4, 1, 6]
        beat = 60 / bpm; i = 0; tb = 0.0
        while tb < total:
            bar = int(tb / (4 * beat)) % 4; root = prog[bar]
            if i % 8 == 0: put(note(root - 12, 4 * beat, 0.12, 0.2), tb)
            put(note(root + 12 + scale[pattern[i % 8]] - (0 if bar % 2 == 0 else 2), beat * 0.45, 0.05), tb)
            i += 1; tb += beat / 2
    elif style == "creepy":
        put(s_drone(total, 49), 0)
        tb = 1.0; k = 0
        for m in [61, 60, 61, 56, 61, 60, 63, 61] * int(total / 8 + 1):
            if tb > total: break
            put(note(m + 12, 1.6, 0.045, 0.1), tb); tb += 1.0 + (0.5 if k % 3 == 0 else 0); k += 1
    elif style == "gentle":
        bpm, beat = 72, 60 / 72; tb = 0.0; i = 0
        chords = [[60, 64, 67, 71], [57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 65]]
        while tb < total:
            ch = chords[int(tb / (4 * beat)) % 4]
            put(note(ch[i % 4] + (12 if i % 4 == 3 else 0), beat * 1.2, 0.05, 0.3), tb)
            if i % 4 == 0: put(note(ch[0] - 12, 4 * beat, 0.08, 0.1), tb)
            i += 1; tb += beat / 2
    elif style == "tense":
        bpm, beat = 120, 0.5; tb = 0.0; i = 0
        while tb < total:
            put(note(45 if i % 8 < 6 else 44, 0.25, 0.1, 0.5), tb)
            if i % 4 == 2: put(note(69 + (3 if int(tb / 4) % 2 else 0), 0.3, 0.035, 0.2), tb)
            i += 1; tb += beat / 2
    elif style == "funk":
        bpm, beat = 112, 60 / 112; tb = 0.0; i = 0
        bass = [45, 45, 52, 45, 48, 45, 50, 52]
        while tb < total:
            if i % 2 == 0: put(note(bass[(i // 2) % 8], 0.2, 0.13, 0.6), tb)
            if i % 4 == 2: put(s_click() * 0.5, tb)
            if i % 8 == 4: put(note(64 + [0, 3, 5, 7][int(tb / 2) % 4], 0.3, 0.04), tb)
            i += 1; tb += beat / 2
    return out

# ------------------------------------------------------------------ histoire
class Story:
    def __init__(self, lines, voice="am_fenrir", speed=1.08, start=0.25, end_hold=3.0):
        """lines : [(texte, pause_apres)]. Les timings sont dans S (debuts), E (fins), TOTAL."""
        self.lines, self.voice, self.speed = lines, voice, speed
        self.clips, t = [], start
        for txt, pause in lines:
            a = self._voice(txt).astype(np.float64)
            self.clips.append((t, a)); t += len(a) / SR + pause
        self.TOTAL = t + end_hold
        self.S = [c[0] for c in self.clips]; self.E = [c[0] + len(c[1]) / SR for c in self.clips]
        vb = np.zeros(int((self.TOTAL + 1) * SR))
        for st, a in self.clips:
            i = int(st * SR); vb[i:i + len(a)] += np.abs(a)
        self.voice_buf = vb
        win = SR // FPS
        env = np.array([vb[i * win:(i + 1) * win].mean() for i in range(int(self.TOTAL * FPS) + 3)])
        self.ENV = np.clip(np.convolve(env / (np.percentile(env, 97) + 1e-9), np.ones(3) / 3, "same"), 0, 1)
        self.sub_words = 3
        self.words = self._words()
        self.hook, self.hook_until = "", 0.0
        self.sub_mute = []; self.sub_y = 1380; self.sub_size = 86
        self.subs_on = True

    def _voice(self, txt):
        cp = os.path.join(CACHE, f"{hashlib.md5((txt + self.voice + str(self.speed)).encode()).hexdigest()[:12]}.npy")
        if os.path.exists(cp): return np.load(cp)
        from kokoro_onnx import Kokoro
        kok = Kokoro("/root/.cache/kokoro/kokoro-v1.0.onnx", "/root/.cache/kokoro/voices-v1.0.bin")
        a, sr = kok.create(txt, voice=self.voice, speed=self.speed, lang="en-us")
        assert sr == SR; np.save(cp, a); return a

    def mouth(self, t): return self.ENV[min(len(self.ENV) - 1, int(t * FPS))]

    def _words(self):
        out = []
        for (st, a), (txt, _) in zip(self.clips, self.lines):
            ws = txt.split(); d = len(a) / SR; tot = sum(len(w) + 1 for w in ws); acc = st + 0.05
            groups, cur = [], []
            for w in ws:
                cur.append(w)
                if len(cur) >= self.sub_words or w[-1] in ".,:!?": groups.append(cur); cur = []
            if cur: groups.append(cur)
            for grp in groups:
                g0 = acc; ts = []
                for w in grp:
                    dd = (d - 0.1) * (len(w) + 1) / tot; ts.append((acc, acc + dd)); acc += dd
                out.append((g0, acc, grp, ts))
        return out

    def subs(self, t):
        if not self.subs_on or any(a <= t < b for a, b in self.sub_mute): return ""
        px = self.sub_size
        for g0, g1, grp, ts in self.words:
            if g0 <= t < g1:
                sp = textw(" ", px); ws = [textw(w, px) for w in grp]; tot = sum(ws) + sp * (len(grp) - 1)
                pop = (1 + 0.07 * max(0, 1 - (t - g0) / 0.12)) * min(1.0, 940 / tot)
                x = -tot / 2; a = b = ""
                for k, w in enumerate(grp):
                    col = "#ffd43b" if ts[k][0] <= t < ts[k][1] else "#fff"
                    a += f'<text x="{x:.0f}" font-family="Inter" font-weight="900" font-size="{px}" fill="none" stroke="#000" stroke-width="{int(px * .21)}" stroke-linejoin="round">{esc(w)}</text>'
                    b += f'<text x="{x:.0f}" font-family="Inter" font-weight="900" font-size="{px}" fill="{col}">{esc(w)}</text>'
                    x += ws[k] + sp
                return f'<g transform="translate(540,{self.sub_y}) scale({pop:.3f})">{a}{b}</g>'
        return ""

    # ---- rendu
    def _world(self, k, t):
        a, b, fn, tr = self.shots[k]
        svg, (z, cx, cy, r, sh) = fn(t - a, b - a, t)
        if sh: cx += sh * math.sin(t * 91); cy += sh * math.cos(t * 77)
        return f'<g transform="translate({W / 2},{H / 2}) rotate({r:.2f}) scale({z:.4f}) translate({-cx:.1f},{-cy:.1f})">{svg}</g>'

    def _shot_at(self, t):
        for k, (a, b, fn, tr) in enumerate(self.shots):
            if a <= t < b: return k
        return len(self.shots) - 1

    def frame(self, f):
        t = f / FPS
        k = self._shot_at(t); a, b, fn, tr = self.shots[k]; tl = t - a
        body = self._world(k, t); over = ""
        if tr == "whip" and tl < 0.16 and k > 0:
            u = eout(tl / 0.16); prev = self._world(k - 1, a - 0.001)
            body = f'<g transform="translate({-W * u:.0f},0)">{prev}</g><g transform="translate({W * (1 - u):.0f},0)">{body}</g>'
            over = "".join(rect(0, y, W, 10, "#fff", extra='opacity=".25"') for y in range(60, H, 140))
        elif tr == "flash" and tl < 0.2: over = rect(0, 0, W, H, "#fff", extra=f'opacity="{1 - tl / 0.2:.2f}"')
        elif tr == "zoom" and tl < 0.22:
            u = eout(tl / 0.22)
            body = f'<g transform="translate({W / 2},{H / 2}) scale({lerp(1.6, 1.0, u):.3f}) translate({-W / 2},{-H / 2})">{body}</g>'
            over = rect(0, 0, W, H, "#fff", extra=f'opacity="{0.5 * (1 - u):.2f}"')
        elif tr == "fade" and tl < 0.3: over = rect(0, 0, W, H, "#000", extra=f'opacity="{1 - tl / 0.3:.2f}"')
        elif tr == "black" and tl < 0.5: over = rect(0, 0, W, H, "#000", extra=f'opacity="{1 - ease((tl - 0.2) / 0.3):.2f}"')
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#000"/>', body, over,
             f'<defs><radialGradient id="vig" cx=".5" cy=".45" r=".8"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".4"/></radialGradient></defs>',
             rect(0, 0, W, H, "url(#vig)")]
        if self.hook and t < self.hook_until:
            px = 66 if textw(self.hook, 66) < 900 else 54
            o.append(f'<g opacity="{clamp((self.hook_until - t) / 0.3):.2f}">' + rect(60, 150, 960, 140, "#000", 30, 'opacity=".6"') + f'<text x="540" y="245" text-anchor="middle" font-family="Inter" font-weight="900" font-size="{px}" fill="#fff">{esc(self.hook)}</text></g>')
        o.append(self.subs(t)); o.append("</svg>")
        png = cairosvg.svg2png(bytestring="".join(o).encode())
        return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).tobytes()

    def audio(self, out_wav, sfx, style="upbeat", music_gate=None, music_vol=0.9):
        """sfx : [(t, array, gain)]. music_gate : fonction t -> 0..1."""
        buf = np.zeros(int((self.TOTAL + 1) * SR))
        def put(x, at, gn=1.0):
            i = int(at * SR); m = min(len(x), len(buf) - i)
            if m > 0 and i >= 0: buf[i:i + m] += x[:m] * gn
        for st, a in self.clips: put(a / (np.max(np.abs(a)) + 1e-9) * 0.85, st)
        mu = music(self.TOTAL + 1, style)
        if music_gate: mu *= np.array([music_gate(i / SR) for i in range(0, len(mu), 240)]).repeat(240)[:len(mu)]
        dv = np.convolve(self.voice_buf[:len(mu)] > 0.02, np.ones(SR // 10) / (SR // 10), "same")
        buf[:len(mu)] += mu * (1 - 0.55 * np.clip(dv * 3, 0, 1)) * music_vol
        for st, en, fn, tr in self.shots[1:]:
            if tr == "whip": put(s_whoosh(), st - 0.12)
            elif tr == "flash": put(s_thud(), st, 0.8); put(s_riser(), st - 0.6, 0.6)
            elif tr == "zoom": put(s_whoosh(0.4), st - 0.15, 0.7)
        for at, x, gn in sfx: put(x, at, gn)
        m = np.percentile(np.abs(buf), 99.8); buf = np.tanh(buf / m * 0.95) * 0.9
        with wave.open(out_wav, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((buf * 32767).astype(np.int16).tobytes())

    def render(self, out, shots, sfx=(), style="upbeat", music_gate=None, stills=None, music_vol=0.9):
        self.shots = shots
        if stills:
            ims = [Image.frombytes("RGB", (W, H), self.frame(int(tt * FPS))).resize((216, 384)) for tt in stills]
            sheet = Image.new("RGB", (216 * min(8, len(ims)), 384 * ((len(ims) + 7) // 8)))
            for i, im in enumerate(ims): sheet.paste(im, ((i % 8) * 216, (i // 8) * 384))
            sheet.save(out + "_sheet.png"); return
        self.audio(out + ".wav", list(sfx), style, music_gate, music_vol)
        nf = int(self.TOTAL * FPS)
        ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                               "-i", out + ".wav", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                               "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
        global _STORY
        _STORY = self
        with Pool(4) as p:
            for fr in p.imap(_frame, range(nf), chunksize=6): ff.stdin.write(fr)
        ff.stdin.close(); ff.wait(); os.remove(out + ".wav")
        print(os.path.basename(out), "total", round(self.TOTAL, 1), "s")

_STORY = None
def _frame(f): return _STORY.frame(f)

def main(build):
    """build() -> (story, shots, sfx, style, gate). Usage : script.py sortie.mp4 [--still t1,t2,...]"""
    out = sys.argv[1]
    story, shots, sfx, style, gate = build()
    stills = [float(x) for x in sys.argv[sys.argv.index("--still") + 1].split(",")] if "--still" in sys.argv else None
    if "--auto" in sys.argv: stills = [a + 0.6 for a, b, fn, tr in shots] + [story.TOTAL - 0.5]
    if stills: print("S =", [round(s, 2) for s in story.S], "TOTAL", round(story.TOTAL, 1)); print("shots", [round(a, 1) for a, b, fn, tr in shots])
    story.render(out, shots, sfx, style, gate, stills)
