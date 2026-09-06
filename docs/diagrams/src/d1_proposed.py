"""D1 — Proposed architecture (GOD_DOC S04), distilled to the mechanism. 1600 x 700, white."""
from lib import *

W, H = 1600, 708
s = SVG(W, H)

C1, W1 = 40, 240
C2, W2 = 320, 260
C3, W3 = 620, 270
C4, W4 = 930, 350
C5, W5 = 1320, 240
TOP = 58
GY = 500          # bottom row
GH = 116          # bottom row height

def coltitle(x, t):
    s.text(x, 36, t, size=13, weight=600, color=MUTED, tracking=1.4)

coltitle(C1, "SENSORS")
coltitle(C2, "FRONT END  ·  IMU RATE")
coltitle(C3, "AIDING  ·  10 Hz")
coltitle(C4, "FUSION CORE")
coltitle(C5, "OUTPUT  ·  DEPLOYMENT")

# ---------------- C1 sensors ----------------
s.block(C1, TOP, W1, 112, "Accelerometer + gyro", [
    "200 Hz, uncalibrated",
    "phone MEMS, or an external",
    "FOG IMU through the edge config"])
s.block(C1, TOP + 126, W1, 84, "Magnetometer · barometer", [
    "gated aids only: field check,",
    "level change in a car park"])
s.text(C1, TOP + 250, "No OBD-II · no CAN bus · no wheel ticks", size=15, weight=600, color=INK)
s.text(C1, TOP + 270, "no link to the vehicle of any kind", size=15, weight=500, color=MUTED)
s.block(C1, GY, W1, GH, "GNSS receiver", [
    "fix, C/N0, satellites used",
    "raw Doppler velocity",
    "per-band AGC — reported",
    "even when there is no fix"], kind="green", body_size=15)

# ---------------- C2 front end ----------------
y = TOP
s.block(C2, y, W2, 84, "Clock discipline", [
    "one monotonic timeline",
    "GNSS–IMU offset kept as a state"]); CLK = (y, 84); y += 96
s.block(C2, y, W2, 84, "Gyro denoiser", [
    "dilated causal CNN, < 50 k params",
    "loss on orientation increments"], kind="ai", ai=True); DEN = (y, 84); y += 96
s.block(C2, y, W2, 106, "Alignment engine", [
    "gravity levels roll and pitch at t = 0",
    "closed-form GNSS-aided yaw",
    "mount rotation carried as a state"]); ALN = (y, 106); y += 118
s.block(C2, y, W2, 106, "Motion context gate", [
    "stationary · idling · moving · shock",
    "engine idle line at 12.5 / 25 Hz",
    "shocks inflate noise, never smoothed"], kind="ai", ai=True); GATE = (y, 106)
FE_BOTTOM = y + 106

# ---------------- C3 aiding ----------------
y = TOP
s.block(C3, y, W3, 130, "Speed + heading head", [
    "causal TCN, 1–2 s of body-frame IMU",
    "+ attitude embedding + band power",
    "→  forward speed  v ± σᵥ",
    "→  yaw-rate bias  δψ ± σψ"], kind="ai", ai=True); HEAD = (y, 130); y += 142
s.block(C3, y, W3, 106, "Noise adapter", [
    "→  σQ, σR, σNHC for the filter",
    "σ = σ₀ · exp(clip(net)) — bounded, so a",
    "failed net is a stable, mistuned filter"], kind="ai", ai=True); ADP = (y, 106); y += 118
s.block(C3, y, W3, 106, "Kinematic constraints", [
    "NHC: lateral = up = 0, with lever arm",
    "ZUPT · ZIHR · ZARU when stopped",
    "switched by the motion context"]); CON = (y, 106)

s.block(C2, GY, C3 + W3 - C2, GH, "GNSS quality monitor", [
    "NIS gate · C/N0 · per-band AGC — the AGC drop comes about a second before the fix is lost",
    "trust falls → σR → ∞ : dead reckoning is a weight change, not a mode switch",
    "flags jamming (AGC and C/N0 both drop) and spoofing (AGC drops, C/N0 rises)"], kind="green", body_size=14.5)

# ---------------- C4 hub ----------------
HUB_H = 406
s.rect(C4, TOP, W4, HUB_H, fill="#fff", stroke=INK, sw=2.25, r=8)
s.text(C4 + 16, TOP + 30, "Error-state filter", size=22, weight=700)
s.text(C4 + 16, TOP + 52, "idr-core · C++17 · runs at IMU rate · never re-initialised", size=14, weight=500, color=MUTED)
s.line(C4 + 16, TOP + 64, C4 + W4 - 16, TOP + 64, stroke=HAIR, sw=1, marker=False)
s.lines(C4 + 16, TOP + 88, [
    "Strapdown mechanization → 21 error states + mount,",
    "invariant error, Joseph-form covariance"], size=15, color=MUTED, lh=19)
s.rich(C4 + 16, TOP + 142, [
    ("δp  δv  φ", "n"), ("   ·   b", "n"), ("g", "sub"), ("  b", "n"), ("a", "sub"), ("  s", "n"), ("g", "sub"), ("  s", "n"), ("a", "sub"),
    ("   ·   θ", "n"), ("mount", "sub"), ("  ℓ", "n"), ("   ·   τ", "n"), ("clk", "sub")], size=17, weight=600)
s.text(C4 + 16, TOP + 164, "position · velocity · attitude · biases · scale factors · mount · lever arm · clock", size=12.5, weight=500, color=MUTED)

s.text(C4 + 16, TOP + 200, "Measurement updates, each with its own covariance", size=14, weight=600, color=INK)
PORT = {}
for name, py, label in [
    ("head", TOP + 226, "speed  v ± σᵥ   and   heading  δψ ± σψ"),
    ("adp", TOP + 254, "process and measurement noise  Q, R"),
    ("con", TOP + 282, "NHC · ZUPT · ZIHR · ZARU"),
    ("gnss", TOP + 310, "GNSS position + Doppler, weighted by σR"),
    ("map", TOP + 338, "road centreline offset + bearing, weight ∝ drift"),
]:
    s.circle(C4 + 1, py - 5, 4.5, fill="#fff", stroke=INK, sw=2)
    s.text(C4 + 18, py, label, size=14.5, weight=500, color=INK)
    PORT[name] = py - 5
s.line(C4 + 16, TOP + 356, C4 + W4 - 16, TOP + 356, stroke=HAIR, sw=1, marker=False)
s.lines(C4 + 16, TOP + 378, [
    "Reacquisition: fixed-lag smoother over the outage,",
    "10–30 s, run once when GNSS returns — no jump"], size=14, color=MUTED, lh=18)

s.block(C4, GY, W4, GH, "Offline road map", [
    "OpenStreetMap, compiled: 2–10 MB per city",
    "HMM / Viterbi match in a 50 m window",
    "explicit off-road hypothesis, so a",
    "wrong road is always escapable"], body_size=15)

# ---------------- C5 output + deployment ----------------
s.block(C5, TOP, W5, 150, "10 Hz pose + covariance", [
    "map icon, always moving",
    "95 % error ellipse",
    "“Dead reckoning · GNSS lost",
    "  0:42 · ± 38 m”",
    "log + replay of the same binary"], body_size=15)
s.block(C5, TOP + 166, W5, 240, "One core, two targets", [
    ("Smartphone", 600, INK),
    "Android AAR under a Kotlin app",
    "phone IMU 200 Hz → 10 Hz out",
    "Earth-rate terms off",
    "",
    ("Edge engine", 600, INK),
    "Linux library, Python bindings",
    "FOG IMU, filter at 200 Hz",
    "learned heads decimated",
    "Earth-rate terms on"], body_size=15)
s.block(C5, GY, W5, GH, "Models", [
    "PyTorch → ExecuTorch, int8",
    "XNNPACK CPU · causal TCN",
    "no recurrence · < 5 MB in total",
    "≈ 11 ms of work per 100 ms tick"], body_size=15)

# ---------------- arrows ----------------
def cy(blk): return blk[0] + blk[1] / 2
# sensors -> front end
s.line(C1 + W1, TOP + 56, C2 - 3, TOP + 56)
s.line(C1 + W1, TOP + 168, C2 - 3, TOP + 168)
# front end -> aiding (elbows into the block centres)
s.elbow(C2 + W2, cy(DEN), C3 - 3, cy(HEAD), xm=C2 + W2 + 20)
s.line(C2 + W2, cy(ALN) - 20, C3 - 3, cy(ALN) - 20)
s.elbow(C2 + W2, cy(GATE), C3 - 3, cy(CON), xm=C2 + W2 + 20)
# IMU-rate stream bus: front end -> hub mechanization (under the aiding column)
BUS_Y = 484
s.path(f"M{C2 + W2 - 60},{FE_BOTTOM} L{C2 + W2 - 60},{BUS_Y} L{C4 - 3},{BUS_Y}", sw=1.5)
s.text(C3, BUS_Y - 7, "aligned IMU stream, 200 Hz  →  mechanization", size=12.5, weight=500, color=MUTED)
# aiding -> hub ports (amber for the learned ones)
s.elbow(C3 + W3, cy(HEAD), C4 - 6, PORT["head"], xm=C3 + W3 + 22, stroke=AMBER_STROKE, sw=1.75)
s.elbow(C3 + W3, cy(ADP), C4 - 6, PORT["adp"], xm=C3 + W3 + 22, stroke=AMBER_STROKE, sw=1.75)
s.elbow(C3 + W3, cy(CON), C4 - 6, PORT["con"], xm=C3 + W3 + 6, sw=1.5)
# GNSS -> monitor -> hub (crosses the bus with a hop)
s.line(C1 + W1, GY + GH / 2, C2 - 3, GY + GH / 2, stroke=GREEN_STROKE, sw=1.75)
s.elbow(C3 + W3, GY + GH / 2, C4 - 6, PORT["gnss"], xm=C4 - 22, stroke=GREEN_STROKE, sw=1.75, halo=True)
# map <-> hub
MX = C4 + 110
s.path(f"M{MX},{GY} L{MX},{TOP + HUB_H + 3}", sw=1.5)
s.text(MX + 10, GY - 12, "matched segment + confidence", size=12.5, weight=500, color=MUTED)
DX = C4 + W4 - 34
s.path(f"M{DX},{TOP + HUB_H} L{DX},{GY - 3}", sw=1, dash="3 3")
s.text(DX + 8, GY - 12, "pose, covariance", size=12.5, weight=500, color=MUTED)
# hub -> output
s.line(C4 + W4, TOP + 60, C5 - 3, TOP + 60, sw=1.75)

# ---------------- legend + caption ----------------
LY = 652
s.rect(C1, LY - 12, 18, 14, fill=AMBER_FILL, stroke=AMBER_STROKE, sw=1, r=3)
s.text(C1 + 26, LY, "learned module — four of them; every output is bounded, so the filter stays stable if one fails", size=13.5, weight=500, color=MUTED)
s.rect(C1 + 640, LY - 12, 18, 14, fill=GREEN_FILL, stroke=GREEN_STROKE, sw=1, r=3)
s.text(C1 + 666, LY, "GNSS path — a measurement whose weight goes to zero, never a mode", size=13.5, weight=500, color=MUTED)
s.circle(C1 + 1130, LY - 5, 4.5, fill="#fff", stroke=INK, sw=2)
s.text(C1 + 1144, LY, "measurement port into the one continuous filter", size=13.5, weight=500, color=MUTED)
s.text(C1, 688, "Proposed architecture · one continuous error-state filter at IMU rate; learning attaches at four bounded points; GNSS and the road map enter as weighted measurements, so a blackout changes weights, not modes.", size=13, weight=400, color=MUTED)

open("d1_proposed.html", "w").write(page(s.render(), W, H, "Proposed architecture"))
print("ok")
