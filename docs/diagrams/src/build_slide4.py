"""Builds ../slide4_tech_method.html - one self-contained 1280x720 slide that already
carries the SIH template's header and footer, so it drops straight into the deck.
Logos are base64-embedded; the IMU trace is drawn from a real ride."""
import base64, io, json, os
from PIL import Image

SCR   = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad"
MEDIA = f"{SCR}/logos/ppt/media"          # from "logo slide (organised).pptx"
DECK  = f"{SCR}/deck/ppt/media"           # from "SIH2026_OFFGRID architecture.pptx"

LOGOS = [("android","image15.png",34),("kotlin","image11.png",23),("pytorch","image2.png",26),
         ("litert","image10.png",23),("maplibre","image16.png",24),("osm","image17.png",26)]

def b64(name, disp_h, root=MEDIA):
    im = Image.open(os.path.join(root, name)).convert("RGBA")
    h = disp_h * 3
    im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

SIH = b64("image1.png", 112, DECK)        # the SIH logo out of the user's own template
logo_html = "".join(
    f'      <img class="logo" style="height:{h}px" alt="{k}" src="data:image/png;base64,{b64(f,h)}">\n'
    for k, f, h in LOGOS)

# --- a real 2.56 s IMU window -> six traces ---------------------------------
d = json.load(open("imu_window.json"))
W, H = 190, 56; rh = H / 6
traces = []
for i, (kk, ch) in enumerate([("acc",0),("acc",1),("acc",2),("gyr",0),("gyr",1),("gyr",2)]):
    v = [r[ch] for r in d[kk]][::4]
    lo, hi = min(v), max(v); rng = (hi - lo) or 1
    pts = " ".join(f"{(j/(len(v)-1))*W:.1f},{i*rh + rh-1.4 - (val-lo)/rng*(rh-2.8):.1f}"
                   for j, val in enumerate(v))
    traces.append(f'<polyline points="{pts}" fill="none" stroke="{"var(--ink)" if kk=="acc" else "var(--faint)"}" '
                  f'stroke-width="1" vector-effect="non-scaling-stroke"/>')
TRACE = f'<svg class="glyph" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(traces)}</svg>'

# --- the conv stack ---------------------------------------------------------
bars = "".join(f'<rect x="{i*21}" y="{(56-h)/2:.0f}" width="14" height="{h}" rx="3.5" '
               f'fill="#fff" stroke="var(--accent-2)" stroke-width="2"/>'
               for i, h in enumerate((52, 40, 30, 22)))
CONV = (f'<svg class="glyph" viewBox="0 0 98 56" width="98" height="56">{bars}</svg>'
        f'<svg class="glyph" viewBox="0 0 22 56" width="22" height="56" style="margin:0 5px">'
        f'<path d="M2,28 L15,28" stroke="var(--ink)" stroke-width="2"/>'
        f'<path d="M12,23 L20,28 L12,33 z" fill="var(--ink)"/></svg>')

# --- three measurements merging into one tracked position -------------------
FUSE = ('<svg class="glyph" viewBox="0 0 190 56" width="190" height="56">'
        '<path d="M76,26 L188,15 L188,43 L76,32 z" fill="var(--rule)" opacity=".55"/>'
        + "".join(f'<path d="M2,{y} L44,{y} L74,29" fill="none" stroke="var(--faint)" stroke-width="2"/>'
                  for y in (7, 29, 51))
        + '<path d="M76,29 L188,29" fill="none" stroke="var(--ink)" stroke-width="3"/>'
          '<circle cx="142" cy="29" r="6.5" fill="var(--accent)" stroke="#fff" stroke-width="2.5"/></svg>')

# --- the app screen: solid trail, then dead-reckoned dashes, marker at the end
MAP = ('<svg class="glyph" viewBox="0 0 190 56" width="190" height="56">'
       '<rect x="1.5" y="1.5" width="86" height="53" rx="9" fill="#fff" stroke="var(--ink)" stroke-width="2"/>'
       '<path d="M12,46 C25,39 22,28 38,23" fill="none" stroke="var(--ink)" stroke-width="2.5"/>'
       '<path d="M38,23 C50,18 55,13 74,11" fill="none" stroke="var(--faint)" stroke-width="2.5" stroke-dasharray="5 5"/>'
       '<circle cx="74" cy="11" r="6" fill="var(--accent)" stroke="#fff" stroke-width="2.5"/></svg>')

HTML = """<!doctype html>
<!--
  SIH 2026 / PS 26168 - OFFGRID - deck slide: TECHNICAL APPROACH
  1280 x 720, self-contained, already carrying the SIH template header + footer.
  Open in Chrome -> Print -> Save as PDF, "Background graphics" ON -> place in PowerPoint.

  WHAT TO EDIT
  ------------
  Team logo ...... <div class="team-logo">    replace with  <img class="team-logo-img" src="...">
  Deck title ..... <h2 class="chrome-title">
  Slide number ... <span class="slide-no">
  Headline ....... <h1 class="headline">
  Hero stat ...... <div class="stat-value"> / <div class="stat-label">
  Box labels ..... <div class="box-title">    (3 words max)
  Box detail ..... <div class="box-sub">      (one short line each)
  CNN output ..... <div class="cnn-out">
  Build steps .... <p class="build">
  Tech logos ..... <img class="logo">         (base64; swap src or delete one)
  Palette ........ :root { --accent, --accent-2, --chrome-blue, ... }
-->
<html lang="en">
<head>
<meta charset="utf-8">
<title>OFFGRID - Technical approach</title>
<style>
:root{
  /* ---- palette: two accents, everything else neutral ---- */
  --accent:      #1B7F4B;      /* the result          */
  --accent-2:    #C9821F;      /* the learned model   */
  --accent-2-bg: #FDF5E8;
  --ink:   #14181F;
  --muted: #58626F;
  --faint: #97A0AC;
  --rule:  #DDE2E7;
  --page:  #FFFFFF;
  --chrome-blue: #0070C0;      /* the SIH template's footer band */

  /* ---- type ---- */
  --font:  "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", Arial, sans-serif;
  --title-font: "Times New Roman", Times, serif;
  --brand-font: "Century Gothic", Futura, "Avenir Next", "Segoe UI", sans-serif;
  --fs-headline: 33px;
  --fs-stat:     44px;
  --fs-title:    23px;
  --fs-sub:      19px;
  --fs-small:    19px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#5A6472}
body{display:flex;align-items:center;justify-content:center;min-height:100vh}
.slide{position:relative;width:1280px;height:720px;overflow:hidden;
  background:var(--page);color:var(--ink);font-family:var(--font)}

/* ================= SIH template chrome ================= */
.sih-logo{position:absolute;left:1027px;top:0;width:236px;height:112px}
.team-logo{position:absolute;left:36px;top:30px;height:52px;display:flex;align-items:center;
  font-family:var(--brand-font);font-size:33px;font-weight:700;letter-spacing:-.015em;color:var(--ink)}
.team-logo-img{position:absolute;left:36px;top:26px;height:60px;width:auto}
.chrome-title{position:absolute;left:64px;top:0;width:1152px;height:112px;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--title-font);font-size:48px;font-weight:700;letter-spacing:.005em}
.footerbar{position:absolute;left:0;top:667px;width:1280px;height:53px;background:var(--chrome-blue)}
.footer-text{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);
  text-align:center;font-size:16px;color:#fff}
.slide-no{position:absolute;right:64px;top:50%;transform:translateY(-50%);
  font-size:16px;font-weight:700;color:#fff}

/* ================= the slide's own content ================= */
.content{position:absolute;left:58px;right:58px;top:122px;bottom:78px;display:flex;flex-direction:column}

.header{display:flex;justify-content:space-between;align-items:flex-start;gap:40px}
.headline{font-size:var(--fs-headline);font-weight:700;line-height:1.1;letter-spacing:-.015em;max-width:730px}
.stat{text-align:right;flex:none}
.stat-value{font-size:var(--fs-stat);font-weight:700;line-height:.94;letter-spacing:-.02em;color:var(--accent)}
.stat-label{font-size:var(--fs-small);color:var(--muted);line-height:1.25;margin-top:7px;
  max-width:395px;margin-left:auto}

.body{flex:1;display:flex;flex-direction:column;justify-content:center}
.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:40px}
.box{position:relative;border:2px solid var(--rule);border-radius:15px;
  padding:17px 18px 16px;height:214px;display:flex;flex-direction:column}
.box--model{border-color:var(--accent-2);background:var(--accent-2-bg)}
.box--hub{border-color:var(--ink);border-width:3px}
.box-title{font-size:var(--fs-title);font-weight:700;line-height:1.1;letter-spacing:-.006em}
.box-sub{font-size:var(--fs-sub);color:var(--muted);line-height:1.28;margin-top:auto}
.badge{position:absolute;top:15px;right:15px;font-size:13px;font-weight:700;letter-spacing:.09em;
  color:var(--accent-2);border:2px solid var(--accent-2);border-radius:6px;padding:0 6px;background:var(--page)}
.art{flex:1;display:flex;align-items:center;justify-content:flex-start;padding:9px 0 7px}
.glyph{display:block;overflow:visible}
.cnn-out{font-size:22px;font-weight:700;color:var(--ink);white-space:nowrap}

.box:not(:last-child)::after{content:"";position:absolute;top:50%;right:-40px;width:40px;height:2px;background:var(--rule)}
.box:not(:last-child)::before{content:"";position:absolute;top:50%;right:-39px;transform:translateY(-50%);
  border-left:10px solid var(--rule);border-top:6.5px solid transparent;border-bottom:6.5px solid transparent}

.build{margin-top:28px;font-size:var(--fs-small);color:var(--faint);letter-spacing:.01em}
.build b{color:var(--muted);font-weight:700}
.build .n{color:var(--accent);font-weight:700}

.stack{padding-top:20px;border-top:1.5px solid var(--rule);
  display:flex;justify-content:center;align-items:center;gap:48px}
.logo{display:block;width:auto;opacity:.92}

@page{size:1280px 720px;margin:0}
@media print{
  html,body{background:#fff}
  body{display:block;min-height:0}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
</style>
</head>
<body>

<div class="slide">

  <!-- ---------- SIH template chrome ---------- -->
  <div class="team-logo">offgrid</div>
  <img class="sih-logo" alt="Smart India Hackathon" src="data:image/png;base64,__SIH__">
  <h2 class="chrome-title">TECHNICAL APPROACH</h2>

  <!-- ---------- slide content ---------- -->
  <div class="content">

    <div class="header">
      <h1 class="headline">GNSS drops. Navigation keeps working.</h1>
      <div class="stat">
        <div class="stat-value">1.52&thinsp;%</div>
        <div class="stat-label">median drift, GNSS withheld&nbsp;600&ndash;850&nbsp;m</div>
      </div>
    </div>

    <div class="body">
      <div class="flow">

        <div class="box">
          <div class="box-title">Phone sensors</div>
          <div class="art">__TRACE__</div>
          <div class="box-sub">Accelerometer + gyroscope, 419&nbsp;Hz</div>
        </div>

        <div class="box box--model">
          <span class="badge">AI</span>
          <div class="box-title">1&#8209;D CNN</div>
          <div class="art">__CONV__<div class="cnn-out">v&nbsp;&plusmn;&nbsp;&sigma;</div></div>
          <div class="box-sub">Speed from motion alone &mdash; 57&nbsp;k weights, 240&nbsp;KB</div>
        </div>

        <div class="box box--hub">
          <div class="box-title">Fusion filter</div>
          <div class="art">__FUSE__</div>
          <div class="box-sub">Speed + heading + GNSS when trusted, 10&nbsp;Hz</div>
        </div>

        <div class="box">
          <div class="box-title">Live map</div>
          <div class="art">__MAP__</div>
          <div class="box-sub">The marker never freezes. Fully offline.</div>
        </div>

      </div>

      <p class="build">
        <span class="n">1</span> <b>Log 30 rides</b> &nbsp;&rarr;&nbsp;
        <span class="n">2</span> <b>Train the CNN</b> &nbsp;&rarr;&nbsp;
        <span class="n">3</span> <b>Test on a held-out road</b> &nbsp;&rarr;&nbsp;
        <span class="n">4</span> <b>Ship on-device</b>
      </p>
    </div>

    <div class="stack">
__LOGOS__    </div>

  </div>

  <!-- ---------- SIH template footer ---------- -->
  <div class="footerbar">
    <span class="footer-text">@SIH Idea submission- Template</span>
    <span class="slide-no">4</span>
  </div>

</div>

</body>
</html>
"""

out = (HTML.replace("__TRACE__", TRACE).replace("__CONV__", CONV)
           .replace("__FUSE__", FUSE).replace("__MAP__", MAP)
           .replace("__LOGOS__", logo_html).replace("__SIH__", SIH))
open("../slide4_tech_method.html", "w").write(out)
print("written", len(out) // 1024, "KB")
