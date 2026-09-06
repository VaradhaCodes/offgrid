"""Tiny SVG helper for the two architecture diagrams. White ground, Barlow, one grid."""
import html

INK = "#14171A"
MUTED = "#5B6470"
HAIR = "#C4CAD1"
AMBER_FILL = "#FFF0D8"
AMBER_STROKE = "#D99A3A"
AMBER_TEXT = "#8A5300"
GREEN_STROKE = "#2E9E6B"
GREEN_FILL = "#E8F6EE"
GREEN_TEXT = "#166B45"
RED = "#D64545"
RED_FILL = "#FBE9E9"
PANEL = "#F5F6F8"


def esc(s):
    return html.escape(str(s), quote=True)


class SVG:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    # ---- primitives -------------------------------------------------
    def rect(self, x, y, w, h, fill="#fff", stroke=INK, sw=1.25, r=6, dash=None, opacity=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} opacity="{opacity}"/>')

    def text(self, x, y, s, size=18, weight=400, color=INK, anchor="start", family="Barlow", tracking=0, italic=False, mono=False):
        st = f' font-style="italic"' if italic else ""
        fam = "'Barlow', 'Helvetica Neue', Arial, sans-serif" if not mono else "'JetBrains Mono', 'SF Mono', Menlo, monospace"
        ls = f' letter-spacing="{tracking}"' if tracking else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{st}{ls}>{esc(s)}</text>')

    def lines(self, x, y, lines, size=18, weight=400, color=INK, lh=None, anchor="start"):
        lh = lh or round(size * 1.3)
        for i, ln in enumerate(lines):
            if isinstance(ln, tuple):  # (text, weight, color)
                t, w, c = (ln + (None, None))[:3]
                self.text(x, y + i * lh, t, size=size, weight=w or weight, color=c or color, anchor=anchor)
            else:
                self.text(x, y + i * lh, ln, size=size, weight=weight, color=color, anchor=anchor)
        return y + len(lines) * lh

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.5, dash=None, marker=True, opacity=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        mk = {GREEN_STROKE: "arrg", AMBER_STROKE: "arra", RED: "arrr"}.get(stroke, "arr")
        m = f' marker-end="url(#{mk})"' if marker else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}{m} opacity="{opacity}"/>')

    def path(self, d, stroke=INK, sw=1.5, dash=None, marker=True, fill="none", opacity=1, mid=False):
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        mk = {GREEN_STROKE: "arrg", AMBER_STROKE: "arra", RED: "arrr"}.get(stroke, "arr")
        m = f' marker-end="url(#{mk})"' if marker else ""
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dd}{m} opacity="{opacity}" stroke-linejoin="round"/>')

    def circle(self, cx, cy, r, fill=INK, stroke="none", sw=1):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def tag(self, x, y, s, fill=AMBER_FILL, stroke=AMBER_STROKE, color=AMBER_TEXT, size=12, pad=6, h=18, weight=600):
        w = int(len(s) * size * 0.62 + pad * 2)
        self.rect(x - w, y, w, h, fill=fill, stroke=stroke, sw=1, r=4)
        self.text(x - w / 2, y + h - 5, s, size=size, weight=weight, color=color, anchor="middle", tracking=0.5)
        return w

    def image(self, href, x, y, w, h, r=0, clip_id=None):
        if r:
            cid = clip_id or f"clip{abs(hash((x, y, w, h)))}"
            self.add(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath>')
            self.add(f'<image href="{href}" x="{x}" y="{y}" width="{w}" height="{h}" clip-path="url(#{cid})" preserveAspectRatio="xMidYMid slice"/>')
        else:
            self.add(f'<image href="{href}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')

    # ---- compound ----------------------------------------------------
    def block(self, x, y, w, h, title, body, kind="plain", title_size=20, body_size=16, ai=False, pad=14, title_weight=600, hub=False):
        if kind == "ai":
            self.rect(x, y, w, h, fill=AMBER_FILL, stroke=AMBER_STROKE, sw=1.25)
        elif kind == "green":
            self.rect(x, y, w, h, fill=GREEN_FILL, stroke=GREEN_STROKE, sw=1.25)
        elif kind == "hub":
            self.rect(x, y, w, h, fill="#fff", stroke=INK, sw=2.25, r=8)
        elif kind == "panel":
            self.rect(x, y, w, h, fill=PANEL, stroke="none", sw=0, r=8)
        else:
            self.rect(x, y, w, h, fill="#fff", stroke=HAIR, sw=1.25)
        ty = y + pad + title_size * 0.8
        self.text(x + pad, ty, title, size=title_size, weight=title_weight, color=INK)
        if ai:
            self.tag(x + w - pad + 2, y + pad - 2, "AI")
        by = ty + body_size * 1.55
        self.lines(x + pad, by, body, size=body_size, color=MUTED, lh=round(body_size * 1.32))
        return by


    def rich(self, x, y, segs, size=17, weight=600, color=INK, anchor="start", sub_scale=0.62):
        """segs: list of (text, 'n'|'sub'|'sup'). Renders subscripts as tspans."""
        out=[]
        for t,k in segs:
            if k=='sub':
                out.append(f'<tspan font-size="{size*sub_scale}" dy="{size*0.28}">{esc(t)}</tspan><tspan dy="{-size*0.28}"> </tspan>')
            elif k=='sup':
                out.append(f'<tspan font-size="{size*sub_scale}" dy="{-size*0.4}">{esc(t)}</tspan><tspan dy="{size*0.4}"> </tspan>')
            else:
                out.append(esc(t))
        fam = "'Barlow', 'Helvetica Neue', Arial, sans-serif"
        self.add(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}" xml:space="preserve">{"".join(out)}</text>')

    def elbow(self, x1, y1, x2, y2, xm=None, stroke=INK, sw=1.5, halo=False, dash=None):
        """orthogonal: horizontal to xm, vertical, horizontal to (x2,y2). halo draws a white under-stroke (crossing hop)."""
        xm = xm if xm is not None else (x1 + x2) / 2
        d = f"M{x1},{y1} L{xm},{y1} L{xm},{y2} L{x2},{y2}"
        if halo:
            self.path(d, stroke="#ffffff", sw=sw + 6, marker=False)
        self.path(d, stroke=stroke, sw=sw, dash=dash)

    def render(self, extra_defs=""):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img">
<defs>
<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>
<marker id="arrg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{GREEN_STROKE}"/></marker>
<marker id="arra" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{AMBER_STROKE}"/></marker>
<marker id="arrr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{RED}"/></marker>
{extra_defs}
</defs>
<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>
{chr(10).join(self.parts)}
</svg>'''


def page(svg, w, h, title="diagram", font_dir="fonts"):
    ff = "".join(f"@font-face{{font-family:'Barlow';font-weight:{wt};src:url('{font_dir}/barlow_{wt}.woff2') format('woff2')}}" for wt in (400,500,600,700))
    ff += f"@font-face{{font-family:'Barlow Semi Condensed';font-weight:600;src:url('{font_dir}/barlowsemicondensed_600.woff2') format('woff2')}}"
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
{ff}
html,body{{margin:0;background:#fff}}
body{{width:{w}px;height:{h}px;overflow:hidden}}
svg{{display:block}}
</style></head><body>{svg}</body></html>'''
