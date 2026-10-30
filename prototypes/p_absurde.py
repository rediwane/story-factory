"""Absurde pince-sans-rire : trois micro-histoires enchainees, voix off plate, gag recurrent ('So he sued.')."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from lib import *

def build():
    L = [
        # --- 1. l'ombre en retard
        ("A man noticed his shadow was three seconds late.", 0.3),
        ("Clearly, a case of negligence.", 0.3),
        ("So he sued.", 0.5),
        ("In court, the shadow arrived three seconds after its lawyer.", 0.3),
        ("The judge ruled it was jet lag.", 0.4),
        ("The man appealed.", 0.2),
        ("The appeal arrived three seconds late.", 0.3),
        ("Case dismissed.", 0.7),
        # --- 2. la lettre
        ("Another man received a letter from his future self.", 0.3),
        ("It said: do not open this.", 0.4),
        ("He had already opened it.", 0.3),
        ("Clearly, a breach of contract.", 0.3),
        ("So he sued himself.", 0.4),
        ("He won.", 0.3),
        ("He also lost.", 0.4),
        ("The court ordered him to pay himself forty dollars.", 0.3),
        ("He is still waiting for the check.", 0.7),
        # --- 3. le wifi
        ("Another man's wifi went down for one minute.", 0.3),
        ("Clearly, an act of war.", 0.3),
        ("So he sued the internet.", 0.4),
        ("The internet did not show up.", 0.3),
        ("It was buffering.", 0.5),
        ("The judge waited.", 0.6),
        ("The man grew old, and died.", 0.5),
        ("The internet sent a notification.", 0.3),
        ("Connection restored.", 0.6),
        ("His grandson sued.", 0.0),
    ]
    st = Story(L, speed=1.12, end_hold=2.8)
    S, E = st.S, st.E
    st.sub_words = 2; st.words = st._words()
    st.hook, st.hook_until = "His shadow was 3 seconds late.", 2.2

    # ---- decors
    def street(t, top="#dfe3ea", bot="#9aa5b1"):
        o = grad(top, bot) + floor(1450, "#495057", .55)
        o += "".join(rect(k * 280 - 160, 560 + (k % 3) * 60, 230, 900, cl("#adb5bd", "#000", .08 * (k % 4))) for k in range(6))
        o += "".join(rect(k * 280 - 110, 700 + (k % 2) * 120, 60, 80, "#fff3bf", 4) for k in range(6))
        return o
    def court(t, top="#5c4a3b", bot="#2f2620"):
        o = grad(top, bot) + floor(1450, "#000", .35)
        o += rect(-800, 300, 2400, 60, "#3d2b1f") + rect(260, 820, 560, 420, "#7f5539", 14, f'stroke="{K}" stroke-width="8"') + rect(300, 760, 480, 70, "#5d4037", 10)
        o += person(540, 900, 1.4, "#1f1f28") + g(rect(-60, -30, 120, 60, "#1f1f28", 10) + circ(0, -30, 40, "#e9ecef"), 540, 690)
        o += g(ln("M-60,0 L60,0", 14) + ln("M0,0 L0,-60", 10) + circ(0, -60, 20, "#7f5539"), 760, 760)  # marteau
        return o
    def judge_bang(t, tl):
        a = -40 * abs(math.sin(min(tl, 0.5) * 6.3))
        return g(ln("M0,0 L0,-120", 12, "#7f5539") + rect(-50, -160, 100, 50, "#5d4037", 10, f'stroke="{K}" stroke-width="6"'), 780, 760, 1.0, a)
    def shadow(x, y, s, t, late=3.0, mood="talk"):
        return g(char(t - late, 0, 0, 1.0, mood, "rest", "rest", mouth=0, cable=False, blink=False).replace('fill="#ffe9a0"', 'fill="#000"').replace("#ff9b30", "#000"), x, y, s)
    def home(t):
        o = grad("#ffe8cc", "#f8c291") + floor(1450) + window(640, 280, 320, 400, "#a5d8ff", False, 0, t) + table(300, 1200, 440)
        return o
    def wifi(x, y, s=1.0, bars=3, col="#1c7ed6"):
        o = ""
        for k in range(3):
            c = col if k < bars else "#ced4da"
            o += f'<path d="M{-80 - 50 * k},{-40 - 30 * k} A{90 + 50 * k},{90 + 50 * k} 0 0,1 {80 + 50 * k},{-40 - 30 * k}" fill="none" stroke="{c}" stroke-width="26" stroke-linecap="round"/>'
        return g(o + circ(0, 0, 22, col if bars > 0 else "#ced4da"), x, y, s)
    def spinner(x, y, t, s=1.0):
        return g("".join(circ(90 * math.cos(k * 0.785), 90 * math.sin(k * 0.785), 16, "#495057", f'opacity="{((k - int(t * 8)) % 8) / 8:.2f}"') for k in range(8)), x, y, s)
    def clock_fast(x, y, t, s=1.0): return clock(x, y, int(t * 2) % 12, int(t * 120) % 60, s)

    # ---- plans ; chaque phrase a le sien, parfois deux
    def sh(i, fn, tr="whip", split=None):
        a = S[i] - 0.05; b = S[i + 1] - 0.05 if i + 1 < len(S) else st.TOTAL + 1
        if split is None: return [(a, b, fn, tr)]
        m = a + (b - a) * split[0]; return [(a, m, fn, tr), (m, b, split[1], split[2])]

    def s_shadow_late(tl, d, t):
        o = street(t); o += sun(900, 300, 90)
        o += shadow(560, 1150, 1.5, t, 3.0) + char(t, 400, 1150, 1.5, "talk", "point", "hip", mouth=0, cable=False, face=1)
        o += moth_near(t, 520, 850, 1.8)
        if tl > 1.3: o += bigtext("3 s LATE", 540, 500, 130, "#fff", eout((tl - 1.3) / 0.2), -4)
        return o, cam(1.0 + 0.06 * tl, 480, 1050)
    def s_clearly(txt):
        def f(tl, d, t):
            o = grad("#212529", "#000")
            o += char(t, 540, 1200, 1.6, "idea", "point", "hip", mouth=0, cable=False, rays=1.0) + moth_near(t, 740, 900, 1.8)
            o += bigtext("CLEARLY,", 540, 420, 120, "#adb5bd", eout(tl / 0.15), -3) + bigtext(txt, 540, 580, 130, "#ffd43b", eout((tl - 0.25) / 0.2), 2)
            return o, cam(1.0 + 0.05 * tl, sh=2 * (tl < 0.2))
        return f
    def s_sued(txt="SO HE SUED."):
        def f(tl, d, t):
            o = grad("#c92a2a", "#5c0b0b") + floor(1450, "#000", .3)
            o += g(rect(-200, -260, 400, 520, "#fdf6e3", 10, f'stroke="{K}" stroke-width="8"') + "".join(ln(f"M-150,{-180 + k * 50} L150,{-180 + k * 50}", 6, "#adb5bd") for k in range(8)) + f'<text x="0" y="-200" text-anchor="middle" font-family="Inter" font-weight="900" font-size="44" fill="#c92a2a">LAWSUIT</text>', 540, 760, back(clamp(tl / 0.25)), -6)
            o += char(t, 540, 1300, 1.3, "angry", "up", "hip", mouth=0, cable=False) + moth_near(t, 740, 1000, 1.6)
            o += bigtext(txt, 540, 1120, 150, "#fff", eout((tl - 0.1) / 0.2), -4)
            return o, cam(1.0 + 0.08 * ease(tl / d), sh=5 * (tl < 0.25))
        return f
    def s_court_arrive(tl, d, t):
        o = court(t)
        lx = lerp(-200, 300, eout(tl / 1.0))
        o += g(person(0, 0, 1.4, "#1f1f28") + rect(-30, -220, 60, 40, "#495057", 6), lx, 1450) + g(rect(-60, -40, 120, 80, "#7f5539", 8, f'stroke="{K}" stroke-width="5"'), lx + 70, 1350)
        sx = lerp(-360, 150, eout((tl - 0.6) / 1.0))
        o += shadow(sx, 1300, 1.3, t, 0.0)
        o += char(t, 880, 1300, 1.3, "talk", "chest", "chest", mouth=0, cable=False, face=-1) + moth_near(t, 800, 1000, 1.5)
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_judge(txt, mood="talk"):
        def f(tl, d, t):
            o = court(t) + judge_bang(t, tl)
            o += bigtext(txt, 540, 480, 120, "#fff", eout((tl - 0.2) / 0.2), -3)
            o += char(t, 300, 1300, 1.2, mood, "shrug", "shrug", mouth=0, cable=False) + moth_near(t, 420, 1020, 1.5)
            return o, cam(1.05 + 0.05 * tl, 540, 900, sh=3 * (tl < 0.2))
        return f
    def s_appeal(tl, d, t):
        o = court(t)
        o += char(t, 420, 1300, 1.3, "angry", "up", "up", mouth=0, cable=False) + moth_near(t, 600, 1000, 1.5)
        o += g(rect(-120, -160, 240, 320, "#fdf6e3", 8, f'stroke="{K}" stroke-width="7"') + f'<text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="46" fill="{K}">APPEAL</text>', 420 + 40 * eout(tl / 0.3), 960 - 100 * eout(tl / 0.3), 1.0, -8)
        return o, cam(1.0 + 0.06 * tl, 540, 1000)
    def s_appeal_late(tl, d, t):
        o = court(t)
        o += char(t, 420, 1300, 1.3, "talk", "rest", "rest", mouth=0, cable=False, eyes="wide") + moth_near(t, 600, 1000, 1.5)
        o += clock_fast(820, 480, t * 0.0 + 1.5, 1.1)
        u = eout((tl - 0.9) / 0.4)
        o += g(rect(-120, -160, 240, 320, "#fdf6e3", 8, f'stroke="{K}" stroke-width="7"') + f'<text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="46" fill="{K}">APPEAL</text>', lerp(1300, 760, u), 960, 1.0, -8)
        o += bigtext("3 s LATE", 540, 650, 110, "#ffd43b", eout((tl - 1.2) / 0.2)) if tl > 1.2 else ""
        return o, cam(1.0 + 0.04 * tl, 540, 1000)
    def s_dismissed(tl, d, t):
        o = court(t) + judge_bang(t, tl)
        o += char(t, 300, 1300, 1.2, "sad", "hang", "hang", mouth=0, cable=False, tilt=12, lit=0.6) + shadow(520, 1300, 1.2, t, 3.0, "sad")
        o += moth_near(t, 420, 1020, 1.5)
        o += bigtext("DISMISSED.", 540, 480, 130, "#ff6b6b", eout((tl - 0.1) / 0.2), -3)
        return o, cam(1.05 + 0.08 * ease(tl / d), 540, 900, sh=4 * (tl < 0.2))
    def s_letter(tl, d, t):
        o = home(t)
        u = eout(tl / 0.6)
        o += char(t, 360, 1150, 1.5, "talk", "hold", "hold", mouth=0, cable=False, tilt=6) + moth_near(t, 520, 850, 1.8)
        o += g(rect(-170, -110, 340, 220, "#fdf6e3", 8, f'stroke="{K}" stroke-width="7"') + ln("M-170,-110 L0,20 L170,-110", 7) + f'<text x="0" y="90" text-anchor="middle" font-family="Inter" font-weight="900" font-size="34" fill="{K}">FROM: YOU (2041)</text>', 700, lerp(400, 1000, u), 1.0, -8)
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_letter_text(tl, d, t):
        o = grad("#fdf6e3", "#e9dcc3") + letter(230, 380, 620, 900, 1.0, 1.0, -2)
        o += typed("DO NOT OPEN THIS.", 540, 760, 70, tl / 0.8, "#c92a2a", "Inter", "middle", maxw=560)
        o += typed("- you, later", 540, 1060, 50, (tl - 0.9) / 0.5, "#868e96", "Inter", "middle")
        return o, cam(1.0 + 0.05 * tl, 540, 850)
    def s_opened(tl, d, t):
        o = home(t)
        o += char(t, 420, 1150, 1.5, "fear", "hold", "hold", mouth=0, cable=False, eyes="wide", shiver=0.3) + moth_near(t, 600, 850, 1.8)
        o += g(rect(-170, -110, 340, 220, "#fdf6e3", 8, f'stroke="{K}" stroke-width="7"') + f'<path d="M-170,-110 L0,-260 L170,-110 Z" fill="#fdf6e3" stroke="{K}" stroke-width="7"/>', 760, 1000, 1.0, -8)
        if tl > 0.8: o += bigtext("oops.", 540, 480, 150, "#fff", eout((tl - 0.8) / 0.2), -5)
        return o, cam(1.0 + 0.06 * tl, 540, 1000)
    def s_sue_self(tl, d, t):
        o = court(t)
        o += char(t, 330, 1300, 1.2, "angry", "point", "hip", mouth=0, cable=False, face=1) + char(t + 0.5, 760, 1300, 1.2, "angry", "point", "hip", mouth=0, cable=False, face=-1)
        o += moth_near(t, 540, 980, 1.5)
        o += bigtext("vs.", 540, 1050, 120, "#ffd43b", eout((tl - 0.3) / 0.2))
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_won_lost(won):
        def f(tl, d, t):
            o = court(t) + judge_bang(t, tl)
            if won: o += char(t, 330, 1300, 1.2, "happy", "up", "up", mouth=0, cable=False) + char(t + 0.5, 760, 1300, 1.2, "sad", "hang", "hang", mouth=0, cable=False, face=-1, lit=0.6)
            else: o += char(t, 330, 1300, 1.2, "sad", "hang", "hang", mouth=0, cable=False, lit=0.6) + char(t + 0.5, 760, 1300, 1.2, "happy", "up", "up", mouth=0, cable=False, face=-1)
            o += moth_near(t, 540, 980, 1.5)
            o += bigtext("HE WON." if won else "HE ALSO LOST.", 540, 480, 130 if won else 110, "#b2f2bb" if won else "#ff6b6b", eout((tl - 0.1) / 0.2), -3)
            return o, cam(1.05 + 0.05 * tl, 540, 900, sh=3 * (tl < 0.2))
        return f
    def s_forty(tl, d, t):
        o = court(t)
        o += char(t, 330, 1300, 1.2, "talk", "hold", "hold", mouth=0, cable=False) + char(t + 0.5, 760, 1300, 1.2, "talk", "hold", "hold", mouth=0, cable=False, face=-1)
        u = eout((tl - 0.5) / 0.4)
        o += g(rect(-150, -70, 300, 140, "#b2f2bb", 10, f'stroke="{K}" stroke-width="7"') + f'<text x="0" y="18" text-anchor="middle" font-family="Inter" font-weight="900" font-size="60" fill="{K}">$40</text>', lerp(330, 760, u), 1050 - 120 * math.sin(u * math.pi), 1.0)
        o += moth_near(t, 540, 900, 1.5)
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_waiting(tl, d, t):
        o = home(t)
        o += char(t, 420, 1150, 1.5, "sad", "rest", "rest", mouth=0, cable=False, tilt=8, lit=0.7) + moth(560, 880 + 6 * math.sin(t * 2), 0, 1.8, 0.2)
        o += g(rect(-110, -140, 220, 280, "#dfe3ea", 8, f'stroke="{K}" stroke-width="7"') + ln("M-60,-40 L60,-40 M-60,0 L60,0 M-60,40 L20,40", 8, "#868e96"), 760, 1000, 1.0)
        o += clock_fast(840, 420, tl * 3, 1.0)
        if tl > 1.0: o += bigtext("still waiting.", 540, 600, 100, "#fff", eout((tl - 1.0) / 0.2), -2)
        return o, cam(1.0 + 0.08 * ease(tl / d), 540, 1000)
    def s_wifi_down(tl, d, t):
        o = home(t)
        bars = 3 if tl < 0.5 else 0
        o += char(t, 420, 1150, 1.5, "talk" if tl < 0.5 else "fear", "hold", "hold", mouth=0, cable=False, eyes="wide" if tl > 0.5 else None, shiver=0.6 * (tl > 0.5)) + moth_near(t, 600, 850, 1.8)
        o += wifi(800, 500, 1.0, bars, "#1c7ed6" if bars else "#e03131")
        if tl > 0.5: o += bigtext("1 MINUTE", 540, 760, 130, "#ff6b6b", eout((tl - 0.5) / 0.2), -3)
        return o, cam(1.0 + 0.05 * tl, 540, 1000, sh=5 * (0.5 < tl < 0.8))
    def s_sue_internet(tl, d, t):
        o = court(t)
        o += char(t, 330, 1300, 1.2, "angry", "point", "hip", mouth=0, cable=False) + moth_near(t, 460, 1000, 1.5)
        o += g(rect(-200, -60, 400, 120, "#fff", 16, f'stroke="{K}" stroke-width="7"') + f'<text x="0" y="18" text-anchor="middle" font-family="Inter" font-weight="900" font-size="50" fill="{K}">THE INTERNET</text>', 760, 1150, back(clamp(tl / 0.3)))
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_no_show(tl, d, t):
        o = court(t)
        o += char(t, 330, 1300, 1.2, "talk", "rest", "rest", mouth=0, cable=False) + moth_near(t, 460, 1000, 1.5)
        o += rect(640, 1100, 300, 300, "#000", 20, 'opacity=".25"') + f'<text x="790" y="1270" text-anchor="middle" font-family="Inter" font-weight="900" font-size="70" fill="#fff" opacity=".6">?</text>'
        return o, cam(1.0 + 0.05 * tl, 540, 1000)
    def s_buffering(tl, d, t):
        o = grad("#212529", "#000") + spinner(540, 860, t, 1.3)
        o += bigtext("buffering...", 540, 1150, 110, "#adb5bd", eout(tl / 0.2))
        o += f'<text x="540" y="1300" text-anchor="middle" font-family="JetBrains Mono" font-weight="800" font-size="60" fill="#495057">{min(99, int(tl * 7)):02d}%</text>'
        return o, cam(1.0 + 0.04 * tl)
    def s_judge_waits(tl, d, t):
        o = court(t)
        o += char(t, 330, 1300, 1.2, "talk", "rest", "rest", mouth=0, cable=False) + moth(460, 1000 + 6 * math.sin(t * 2), 0, 1.5, 0.2)
        o += clock_fast(820, 480, tl * 4, 1.1) + spinner(760, 1150, t, 0.6)
        return o, cam(1.0 + 0.06 * ease(tl / d), 540, 1000)
    def s_old(tl, d, t):
        o = court(cl("#5c4a3b", "#2b2d42", ease(tl / d)), cl("#2f2620", "#0b0c12", ease(tl / d)))
        u = ease(tl / (d - 0.4))
        o += char(t, 330, 1300, 1.2, "sad" if u < 0.8 else "off", "hang", "hang", mouth=0, cable=False, tilt=lerp(0, 22, u), lit=lerp(0.9, 0.0, u))
        o += g(ln("M0,0 L0,-140", 12, "#adb5bd") + ln("M-30,0 L30,0", 12, "#adb5bd"), 420, 1440, u)
        o += moth(460 + 0 * u, 1000 - 400 * u, 0, 1.5, abs(math.sin(t * 30)), 1 - 0.7 * u)
        o += clock_fast(820, 480, tl * 12, 1.1)
        if u > 0.85: o += bigtext("R.I.P.", 540, 700, 120, "#adb5bd", eout((u - 0.85) / 0.15))
        return o, cam(1.0 + 0.06 * tl, 540, 1000)
    def s_notif(tl, d, t):
        o = grad("#0b0c12", "#000") + phone(540, 960, 2.0)
        o += rect(300, 400, 480, 1120, "#111", 20)
        u = back(clamp((tl - 0.2) / 0.3))
        o += g(rect(-220, -70, 440, 140, "#f8f9fa", 24) + wifi(-150, 5, 0.25, 3) + f'<text x="-90" y="-10" font-family="Inter" font-weight="900" font-size="30" fill="{K}">Network</text><text x="-90" y="36" font-family="Inter" font-weight="700" font-size="30" fill="#495057">Connection restored.</text>', 540, 620, u)
        return o, cam(1.0 + 0.05 * tl, 540, 800)
    def s_restored(tl, d, t):
        o = grad("#1c7ed6", "#0b3d91") + wifi(540, 700, 1.6, 3, "#fff")
        o += bigtext("CONNECTION", 540, 1000, 120, "#fff", eout(tl / 0.2), -3) + bigtext("RESTORED.", 540, 1150, 130, "#b2f2bb", eout((tl - 0.2) / 0.2), 2)
        return o, cam(1.0 + 0.05 * tl, sh=4 * (tl < 0.2))
    def s_grandson(tl, d, t):
        o = court(t)
        o += char(t, 330, 1340, 0.95, "angry", "point", "hip", mouth=0, cable=False) + moth_near(t, 440, 1100, 1.2)
        o += g(rect(-200, -60, 400, 120, "#fff", 16, f'stroke="{K}" stroke-width="7"') + f'<text x="0" y="18" text-anchor="middle" font-family="Inter" font-weight="900" font-size="50" fill="{K}">THE INTERNET</text>', 760, 1150, 1.0)
        o += bigtext("HIS GRANDSON SUED.", 540, 480, 96, "#ffd43b", eout((tl - 0.3) / 0.2), -3)
        return o, cam(1.0 + 0.1 * ease(tl / 2.5), 540, 950)

    shots = []
    shots += sh(0, s_shadow_late, "cut")
    shots += sh(1, s_clearly("NEGLIGENCE."), "whip")
    shots += sh(2, s_sued(), "flash")
    shots += sh(3, s_court_arrive, "whip")
    shots += sh(4, s_judge("JET LAG."), "cut")
    shots += sh(5, s_appeal, "whip")
    shots += sh(6, s_appeal_late, "cut")
    shots += sh(7, s_dismissed, "flash")
    shots += sh(8, s_letter, "whip")
    shots += sh(9, s_letter_text, "zoom")
    shots += sh(10, s_opened, "whip")
    shots += sh(11, s_clearly("BREACH OF CONTRACT."), "whip")
    shots += sh(12, s_sued("SO HE SUED HIMSELF."), "flash")
    shots += sh(13, s_won_lost(True), "whip")
    shots += sh(14, s_won_lost(False), "cut")
    shots += sh(15, s_forty, "whip")
    shots += sh(16, s_waiting, "whip")
    shots += sh(17, s_wifi_down, "whip")
    shots += sh(18, s_clearly("AN ACT OF WAR."), "whip")
    shots += sh(19, s_sue_internet, "flash")
    shots += sh(20, s_no_show, "whip")
    shots += sh(21, s_buffering, "zoom")
    shots += sh(22, s_judge_waits, "whip")
    shots += sh(23, s_old, "cut")
    shots += sh(24, s_notif, "whip")
    shots += sh(25, s_restored, "flash")
    shots += sh(26, s_grandson, "whip")

    gavel = lambda: s_thud(400, 120, 0.12)
    buzz_s = np.concatenate([s_buzz(0.12, 60), np.zeros(int(0.1 * SR))] * 2)
    sfx = [(S[0] + 1.3, s_pop(900, 1300, 0.08), 0.6), (S[2], s_paper(), 1.0), (S[3] + 0.6, s_steps(3, 0.3), 0.9), (S[4] + 0.2, gavel(), 1.2),
           (S[6] + 1.2, s_pop(300, 200, 0.12), 0.7), (S[7] + 0.1, gavel(), 1.3), (S[8] + 0.3, s_paper(), 0.8), (S[9], s_ticktock(8, 0.08), 0.4),
           (S[10] + 0.8, s_pop(400, 250, 0.15), 0.8), (S[12], s_paper(), 1.0), (S[13] + 0.1, gavel(), 1.2), (S[13] + 0.3, s_sparkle(), 0.6), (S[14] + 0.1, gavel(), 1.2), (S[14] + 0.3, s_thud(80, 30, 0.6), 0.9),
           (S[15] + 0.5, s_pop(700, 1100, 0.1), 0.7), (S[16] + 0.2, s_ticktock(8, 0.3), 0.6), (S[17] + 0.5, s_zap(), 0.9), (S[17] + 0.5, s_thud(), 0.8),
           (S[19], s_paper(), 1.0), (S[20] + 0.6, s_pop(300, 200, 0.15), 0.6), (S[21], s_ticktock(6, 0.25), 0.4), (S[22], s_ticktock(10, 0.2), 0.6), (S[23], s_ticktock(14, 0.14), 0.7),
           (S[23] + 1.4, s_thud(60, 25, 0.9), 1.0), (S[24] + 0.2, buzz_s, 1.0), (S[25], s_ding(), 0.8), (S[26] + 0.3, s_paper(), 1.0), (S[26] + 0.5, gavel(), 1.2)]
    return st, shots, sfx, "funk", None

if __name__ == "__main__": main(build)
