"""D2 — The bicycle prototype: how it was built (top strip) and what runs on the phone (flow + real screens). 1600 x 770, white."""
import json, math, os
from lib import *

W, H = 1600, 790
s = SVG(W, H)
REVEAL = "img/p_reveal.png" if os.path.exists("img/p_reveal.png") else "img/p_reveal_old.png"

def label(x, y, t):
    s.text(x, y, t, size=13, weight=600, color=MUTED, tracking=1.4)

# =====================================================================
# TOP STRIP — how we built it
# =====================================================================
label(40, 36, "HOW WE BUILT IT  ·  OFFLINE, ON A MAC")
TY, TH = 52, 212
TX = [40, 380, 760, 1160]
TWS = [300, 340, 360, 400]
for x, w in zip(TX, TWS):
    s.rect(x, TY, w, TH, fill="#fff", stroke=HAIR, sw=1.25, r=8)
for x, w in list(zip(TX, TWS))[:-1]:
    s.path(f"M{x + w + 8},{TY + TH / 2} L{x + w + 32},{TY + TH / 2}", sw=1.5)

def tile_title(x, t):
    s.text(x, TY + 32, t, size=20, weight=600)

# ---- tile 1: ride --------------------------------------------------
x = TX[0]
tile_title(x + 16, "Ride")
# bicycle pictogram (geometry only)
bx, by = x + 60, TY + 40
def bike(ox, oy, k=1.0, stroke=INK):
    def P(px, py): return (ox + px * k, oy + py * k)
    for cx, cy in ((30, 66), (118, 66)):
        s.circle(*P(cx, cy), 24 * k, fill="none", stroke=stroke, sw=1.6)
        s.circle(*P(cx, cy), 2 * k, fill=stroke)
    pts = [((64, 68), (56, 30)), ((64, 68), (100, 34)), ((56, 30), (100, 34)), ((30, 66), (64, 68)), ((30, 66), (56, 30)),
           ((100, 34), (118, 66)), ((100, 34), (104, 24)), ((56, 30), (54, 22))]
    for (a, b) in pts:
        s.line(*P(*a), *P(*b), stroke=stroke, sw=1.6, marker=False)
    s.line(*P(46, 22), *P(62, 22), stroke=stroke, sw=2.4, marker=False)   # saddle
    s.line(*P(98, 22), *P(110, 20), stroke=stroke, sw=2.4, marker=False)  # bar
    # phone on the down tube (rotated rect)
    mx, my = P(83, 51); ang = math.degrees(math.atan2(34 - 68, 100 - 64))
    s.add(f'<g transform="translate({mx},{my}) rotate({ang:.1f})"><rect x="{-11*k}" y="{-6*k}" width="{22*k}" height="{12*k}" rx="{2*k}" fill="{AMBER_FILL}" stroke="{AMBER_STROKE}" stroke-width="1.5"/></g>')
if os.path.exists("img/bike.jpg"):
    s.image("img/bike.jpg", x + 16, TY + 42, 268, 96, r=6, clip_id="clbike")
else:
    bike(bx, by, 0.95)
    s.text(bx + 62, by + 86, "phone", size=11, weight=500, color=AMBER_TEXT, anchor="middle")
s.lines(x + 16, TY + 158, [
    "A bicycle on campus roads. Galaxy S23",
    "Ultra seated in the bottle cage, frame-",
    "fixed. No wheel sensor, no vehicle link."], size=14, color=MUTED, lh=18)

# ---- tile 2: log ---------------------------------------------------
x = TX[1]
tile_title(x + 16, "Log")
s.image("img/logger.png", x + 16, TY + 44, 88, 152, r=6, clip_id="clg")
s.rect(x + 16, TY + 44, 88, 152, fill="none", stroke=HAIR, sw=1, r=6)
# real IMU window (2.56 s, route-2 run 4, 90 s into the ride)
d = json.load(open("imu_window.json"))
gx0, gy0, gw, gh = x + 122, TY + 46, 200, 96
s.rect(gx0, gy0, gw, gh, fill=PANEL, stroke="none", r=4)
rows = [("acc", 0), ("acc", 1), ("acc", 2), ("gyr", 0), ("gyr", 1), ("gyr", 2)]
for i, (k, ch) in enumerate(rows):
    v = [r[ch] for r in d[k]]
    step = max(1, len(v) // 220)
    v = v[::step]
    lo, hi = min(v), max(v); rng = (hi - lo) or 1
    rowh = gh / 6
    pts = " ".join(f"{gx0 + 4 + (j / (len(v) - 1)) * (gw - 8):.1f},{gy0 + i * rowh + rowh - 2 - (val - lo) / rng * (rowh - 4):.1f}" for j, val in enumerate(v))
    col = INK if k == "acc" else MUTED
    s.add(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="0.9" opacity="{0.9 if k == "acc" else 0.75}"/>')
s.text(gx0 + gw, gy0 + gh + 14, "2.56 s of real ride · acc + gyro", size=11.5, weight=500, color=MUTED, anchor="end")
s.lines(x + 122, TY + 178, [
    "IDR Logger · 22 sensor streams",
    "IMU 419 Hz · GNSS 1 Hz · one clock"], size=14.5, color=MUTED, lh=19)

# ---- tile 3: rides --------------------------------------------------
x = TX[2]
tile_title(x + 16, "30 rides")
r1 = json.load(open("corridor_route1.json")); r2 = json.load(open("corridor_route2.json"))
OFF = (340.3, -351.3)  # route-1 start relative to route-2 start, metres
r1 = [(px + OFF[0], py + OFF[1]) for px, py in r1]
allp = r1 + r2
minx, maxx = min(p[0] for p in allp), max(p[0] for p in allp)
miny, maxy = min(p[1] for p in allp), max(p[1] for p in allp)
mw, mh = 140, 140
mx0, my0 = x + 18, TY + 48
sc = min(mw / (maxx - minx), mh / (maxy - miny))
def M(p): return (mx0 + (p[0] - minx) * sc, my0 + (maxy - p[1]) * sc)
def poly(pts, col, sw):
    s.add(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in map(M, pts))}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
poly(r1, MUTED, 2.2)
poly(r2, INK, 3)
for pts, lab in ((r2, "2"), (r1, "1")):
    for p in (pts[0], pts[-1]):
        s.circle(*M(p), 3.6, fill="#fff", stroke=INK if lab == "2" else MUTED, sw=1.8)
a2, b2 = M(r2[0]), M(r2[-1]); a1, b1 = M(r1[0]), M(r1[-1])
s.text(a2[0] - 6, a2[1] + 4, "A", size=11, weight=600, anchor="end")
s.text(b2[0] + 7, b2[1] + 4, "B", size=11, weight=600)
s.text(a1[0] + 9, a1[1] + 4, "road 1", size=11, weight=500, color=MUTED)
tp = M(r2[10]); s.text(tp[0] + 7, tp[1] + 4, "120° turn", size=11, weight=500, color=MUTED)
lp = M(r2[27]); s.text(lp[0] - 8, lp[1] + 4, "road 2", size=11, weight=600, color=INK, anchor="end")
# scale bar 100 m
sbx, sby = mx0, my0 + mh + 10
s.line(sbx, sby, sbx + 100 * sc, sby, sw=1.2, marker=False)
s.text(sbx + 100 * sc + 5, sby + 4, "100 m", size=10.5, weight=500, color=MUTED)
s.lines(x + 178, TY + 62, [
    "2 campus roads, ridden",
    "A→B and B→A as",
    "separate runs",
    "",
    "30 kept rides, legs of",
    "265 m and 660 m, with a",
    "15 s still stand at each",
    "end for calibration"], size=14, color=MUTED, lh=18)

# ---- tile 4: train + test --------------------------------------------
x = TX[3]
tile_title(x + 16, "Train and test")
# CNN schematic: window -> 4 conv -> v ± sigma
cx0, cy0 = x + 18, TY + 56
s.rect(cx0, cy0, 44, 64, fill=PANEL, stroke="none", r=3)
for i, (k, ch) in enumerate(rows):
    v = [r[ch] for r in d[k]][::8]
    lo, hi = min(v), max(v); rng = (hi - lo) or 1
    rh = 64 / 6
    pts = " ".join(f"{cx0 + 3 + (j / (len(v) - 1)) * 38:.1f},{cy0 + i * rh + rh - 1.5 - (val - lo) / rng * (rh - 3):.1f}" for j, val in enumerate(v))
    s.add(f'<polyline points="{pts}" fill="none" stroke="{INK if k == "acc" else MUTED}" stroke-width="0.7"/>')
s.text(cx0 + 22, cy0 + 78, "256 × 6", size=10.5, weight=500, color=MUTED, anchor="middle")
s.line(cx0 + 48, cy0 + 32, cx0 + 60, cy0 + 32, sw=1.2)
hh = [56, 44, 34, 26]
for i, h_ in enumerate(hh):
    s.rect(cx0 + 64 + i * 15, cy0 + 32 - h_ / 2, 11, h_, fill=AMBER_FILL, stroke=AMBER_STROKE, sw=1, r=2)
s.text(cx0 + 93, cy0 + 78, "conv × 4", size=10.5, weight=500, color=AMBER_TEXT, anchor="middle")
s.line(cx0 + 126, cy0 + 32, cx0 + 138, cy0 + 32, sw=1.2)
s.text(cx0 + 142, cy0 + 37, "v ± σ", size=14, weight=600)
s.lines(x + 16, TY + 166, [
    "Speed CNN · 57 k params · 240 KB",
    "trained on the 30 rides with",
    "GNSS speed as the label"], size=13.5, color=MUTED, lh=17)
s.lines(x + 212, TY + 62, [
    ("Held out on road 2, 10 rides", 600, INK),
    "GNSS withheld from 30 s after",
    "motion start, 600–850 m outages:",
    "",
    ("drift 1.52 % median", 600, INK),
    ("5.73 % worst · 10 of 10 < 10 %", 600, INK),
    "road-2 model · leave-one-out"], size=14, color=MUTED, lh=18)

# =====================================================================
# BOTTOM — what runs on the phone
# =====================================================================
label(40, 306, "WHAT RUNS ON THE PHONE  ·  LIVE, 10 Hz, OFFLINE MAP")
FY = 322
F1, F1W = 40, 172
F2, F2W = 242, 192
F3, F3W = 464, 196
K, KW = 690, 232

s.block(F1, FY, F1W, 92, "Accelerometer", ["+ gyroscope, 419 Hz", "phone frame"], title_size=18, body_size=14)
s.block(F1, FY + 250, F1W, 80, "GNSS", ["1 Hz fixes, 3.8 m", "Doppler speed"], kind="green", title_size=18, body_size=14)

s.block(F2, FY, F2W, 126, "Resample + align", [
    "causal 40 Hz filter → 100 Hz",
    "gravity → tilt; pedalling",
    "sway → forward axis",
    "phone frame → bike frame"], title_size=18, body_size=14)
s.block(F2, FY + 250, F2W, 108, "GNSS gate", [
    "withheld inside the test band,",
    "or a real outage: gap > 1.5 s,",
    "accuracy > 30 m, < 4 satellites"], kind="green", title_size=18, body_size=14)

s.block(F3, FY, F3W, 108, "Speed CNN", [
    "last 2.56 s, 6 channels",
    "→ speed ± σ · LiteRT 0.07 ms",
    "stop rule forces v = 0"], kind="ai", ai=True, title_size=18, body_size=14)
s.block(F3, FY + 124, F3W, 108, "Gyro heading", [
    "quaternion at 100 Hz",
    "bias from the 15 s stand",
    "course-corrected while locked"], title_size=18, body_size=14)
s.block(F3, FY + 250, F3W, 108, "Road geometry", [
    "corridor recognised from the",
    "first fixes → 1-D constraint",
    "campus map: match, display only"], title_size=18, body_size=14)

# hub
KH = 358
s.rect(K, FY, KW, KH, fill="#fff", stroke=INK, sw=2.25, r=8)
s.text(K + 16, FY + 30, "Fusion filter", size=20, weight=700)
s.text(K + 16, FY + 50, "Kotlin · 0.16 ms per 10 Hz tick", size=13, weight=500, color=MUTED)
s.line(K + 16, FY + 62, K + KW - 16, FY + 62, stroke=HAIR, sw=1, marker=False)
s.lines(K + 16, FY + 84, [
    "corridor mode: s along the road, v",
    "general mode: x, y, v"], size=14, color=MUTED, lh=18)
s.text(K + 16, FY + 132, "Measurements", size=13.5, weight=600)
KP = {}
for name, py, t in [("cnn", FY + 156, "speed ± σ from the CNN"),
                    ("gyro", FY + 182, "heading from the gyro"),
                    ("gnss", FY + 208, "GNSS position + speed, if accepted"),
                    ("road", FY + 234, "road polyline as the track")]:
    s.circle(K + 1, py - 5, 4.5, fill="#fff", stroke=INK, sw=2)
    s.text(K + 18, py, t, size=13.5, weight=500)
    KP[name] = py - 5
s.line(K + 16, FY + 252, K + KW - 16, FY + 252, stroke=HAIR, sw=1, marker=False)
s.lines(K + 16, FY + 274, [
    "5σ gate on every update",
    "GNSS back: inflated for 3 s, no jump",
    "the drawn trail is never rewritten",
    "→ position, heading, mode, σ at 10 Hz"], size=13, color=MUTED, lh=17)

# arrows
def mid(y, h): return y + h / 2
s.line(F1 + F1W, mid(FY, 92), F2 - 3, mid(FY, 92))
s.elbow(F2 + F2W, mid(FY, 126), F3 - 3, mid(FY, 108), xm=F2 + F2W + 16)
s.elbow(F2 + F2W, mid(FY, 126), F3 - 3, mid(FY + 124, 108), xm=F2 + F2W + 16)
s.elbow(F3 + F3W, mid(FY, 108), K - 6, KP["cnn"], xm=F3 + F3W + 14, stroke=AMBER_STROKE, sw=1.75)
s.elbow(F3 + F3W, mid(FY + 124, 108), K - 6, KP["gyro"], xm=F3 + F3W + 8)
s.line(F1 + F1W, mid(FY + 250, 80), F2 - 3, mid(FY + 250, 80), stroke=GREEN_STROKE, sw=1.75)
s.elbow(F2 + F2W, mid(FY + 250, 108), K - 6, KP["gnss"], xm=F3 + F3W + 20, stroke=GREEN_STROKE, sw=1.75, halo=True)
s.elbow(F3 + F3W, mid(FY + 250, 108), K - 6, KP["road"], xm=F3 + F3W + 14)

# hub -> screens
OX = K + KW
s.line(OX, FY + 60, OX + 48, FY + 60, sw=1.75)

# =====================================================================
# SCREENS — three real frames from the app
# =====================================================================
PX = [978, 1178, 1378]; PW, PH = 182, 333; PY = FY + 24
shots = [("img/p_locked.png", GREEN_STROKE, "GNSS locked · test band ahead"),
         ("img/p_dr.png", AMBER_STROKE, "GNSS withheld · dead reckoning"),
         (REVEAL, GREEN_STROKE, "GNSS back · off by 17.3 m")]
for (href, col, cap), px in zip(shots, PX):
    s.circle(px + 5, FY + 5, 4, fill=col)
    s.text(px + 15, FY + 9, cap, size=12.5, weight=600, color=INK)
    s.image(href, px, PY, PW, PH, r=14, clip_id=f"clip{px}")
    s.rect(px, PY, PW, PH, fill="none", stroke="#8A939E", sw=1.5, r=14)
for i in range(2):
    s.path(f"M{PX[i] + PW + 3},{PY + PH / 2} L{PX[i + 1] - 4},{PY + PH / 2}", sw=1.25, stroke=MUTED)
s.lines(PX[0], PY + PH + 20, [
    "On-device replay of a recorded ride on road 2. SIM = GNSS withheld by the test, not lost. The marker keeps moving",
    "through the 120° turn on motion sensors alone; when GNSS returns, the withheld track is revealed and the miss is",
    "printed on screen. A live ride uses the same engine and the same screens."], size=11.5, weight=400, color=MUTED, lh=15)

# footer evidence
s.text(40, 772, "Bicycle prototype · Python engine for evaluation; the Kotlin port on the phone matches it to 7 mm on the reference ride · speed model 240 KB TFLite · engine tick 0.16 ms, model 0.07 ms on a Galaxy S23 Ultra.", size=13, weight=400, color=MUTED)

open("d2_prototype.html", "w").write(page(s.render(), W, H, "Bicycle prototype"))
print("ok")
