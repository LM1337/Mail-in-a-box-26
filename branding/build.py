#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Mail-in-a-box-26 logo (variant AB1, amber band): build all branding assets.

The finished files are committed next to this script, so running it is optional; it is
only needed after a change to the geometry or the colours. Usage, from anywhere:

    uvx --with pillow --with fonttools --with skia-pathops --from cairosvg \
        python branding/build.py [OUTDIR]

OUTDIR defaults to the directory of this script (branding/). The wordmark and the social
preview need DejaVu Sans Bold and DejaVu Sans (Debian/Ubuntu: fonts-dejavu-core); set
DEJAVU_DIR if the fonts are somewhere other than /usr/share/fonts/truetype/dejavu. On
Ubuntu, cairosvg also needs libcairo2.
"""
import base64, io, math, os, sys

import cairosvg
import pathops
from PIL import Image
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else HERE
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ palette
NAVY = "#0F2C4C"      # tile, M, digits, wordmark text (light)
TEAL = "#2EC4B1"      # lid (top face)
TEAL_D = "#1D8F82"    # side face (shade of the lid)
PAPER = "#F3F7FA"     # front face, wordmark text (dark)
BAND = "#FDB52E"      # label band (amber, slightly softened from #FFB320)
ACC_L = "#B87A00"     # "-26" in the wordmark on light backgrounds (same hue, darker)
ACC_D = BAND          # "-26" on dark backgrounds
TITLE = "variant AB1, amber band"
DIGITS = NAVY
DARK_BG, LIGHT_BG = "#0D1117", "#FFFFFF"


# ------------------------------------------------------------------ path helpers (skia-pathops)
def arc_into(p, cx, cy, r, a0, a1, move=False):
    """Circular arc as cubics; angles in degrees, counter-clockwise, y axis pointing up."""
    n = max(1, math.ceil(abs(a1 - a0) / 90))
    da = (a1 - a0) / n
    for i in range(n):
        t0, t1 = math.radians(a0 + i * da), math.radians(a0 + (i + 1) * da)
        h = 4 / 3 * math.tan((t1 - t0) / 4) * r
        x0, y0 = cx + r * math.cos(t0), cy - r * math.sin(t0)
        x3, y3 = cx + r * math.cos(t1), cy - r * math.sin(t1)
        if move and i == 0:
            p.moveTo(x0, y0)
        p.cubicTo(x0 - h * math.sin(t0), y0 - h * math.cos(t0),
                  x3 + h * math.sin(t1), y3 + h * math.cos(t1), x3, y3)
    return p


def poly(pts):
    p = pathops.Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    p.close()
    return p


def rect(x, y, w, h):
    return poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def rrect_bottom(x, y, w, h, r):
    p = pathops.Path()
    p.moveTo(x, y); p.lineTo(x + w, y); p.lineTo(x + w, y + h - r)
    arc_into(p, x + w - r, y + h - r, r, 0, -90)
    p.lineTo(x + r, y + h)
    arc_into(p, x + r, y + h - r, r, -90, -180)
    p.close()
    return p


def stroke(p, w, join=pathops.LineJoin.MITER_JOIN, ml=10):
    q = pathops.Path(); q.addPath(p)
    q.stroke(w, pathops.LineCap.BUTT_CAP, join, ml)
    return pathops.simplify(q, fix_winding=True)


def op(a, b, kind):
    return pathops.op(a, b, kind, fix_winding=True)


def union(*ps):
    out = ps[0]
    for q in ps[1:]:
        out = op(out, q, pathops.PathOp.UNION)
    return out


def minus(a, *bs):
    for q in bs:
        a = op(a, q, pathops.PathOp.DIFFERENCE)
    return a


def isect(a, b):
    return op(a, b, pathops.PathOp.INTERSECTION)


def d(p):
    pen = SVGPathPen(None, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    p.draw(pen)
    return pen.getCommands()


# ------------------------------------------------------------------ master geometry (512 grid)
# Cube of variant A: front face 64..352 x 160..448, depth offset (+96,-96).
# Faces separated by an even 16-unit gap (= exactly 1 px at 32 px).
G = 16
S = G / math.sqrt(2)
TOP = poly([(64 + G, 160 - G), (160, 64), (448 - S, 64), (368 - S, 160 - G)])
SIDE = poly([(352 + G, 160 - G + S), (448, 64 + S), (448, 352), (352 + G, 432)])
FRONT = rrect_bottom(64, 160, 288, 288, 16)
BAND_TOP = 336                                  # band = lower 112 of the 288 front
BAND_SHAPE = isect(FRONT, rect(64, BAND_TOP, 288, 448 - BAND_TOP))
PAPER_SHAPE = rect(64, 160, 288, BAND_TOP + 8 - 160)   # runs under the band: no seam


def make_m(x0=112, x1=304, y0=200, y1=296, sw=24, t=20, depth=0.82):
    """Monoline M: vertical stems, flat tops, thinner diagonals meeting in a deep V (the flap)."""
    xm, yv = (x0 + x1) / 2, y0 + (y1 - y0) * depth
    stems = union(rect(x0, y0, sw, y1 - y0), rect(x1 - sw, y0, sw, y1 - y0))
    a, c = (x0 + sw / 2, y0), (x1 - sw / 2, y0)
    dx, dy = xm - a[0], yv - a[1]
    L, e = math.hypot(dx, dy), 60
    p = pathops.Path()
    p.moveTo(a[0] - dx / L * e, a[1] - dy / L * e)
    p.lineTo(xm, yv)
    p.lineTo(c[0] + dx / L * e, c[1] - dy / L * e)
    m = union(stems, stroke(p, t))
    return isect(m, rect(x0, y0, x1 - x0, 400))


def make_two(x, base, H, W, sw, a0=160):
    """Geometric 2: circular bowl, tangent straight diagonal, flat foot."""
    h2, r = sw / 2, (W - sw) / 2
    cx, cy = x + W - h2 - r, base - H + h2 + r
    P = (x + h2 * 0.2, base - h2)
    dx, dy = P[0] - cx, P[1] - cy
    ea = math.degrees(math.atan2(-dy, dx)) + math.degrees(math.acos(r / math.hypot(dx, dy)))
    ea = ea - 360 if ea > 0 else ea
    p = pathops.Path()
    arc_into(p, cx, cy, r, a0, ea, move=True)
    p.lineTo(*P); p.lineTo(x + W + 5, base - h2)
    return isect(stroke(p, sw, ml=20), rect(x, base - H - 50, W, H + 50))


def make_six(x, base, H, W, sw):
    """Geometric 6: circular bowl plus one large arc tangent to its left side."""
    h2, rb = sw / 2, (W - sw) / 2
    cx, cy = x + W / 2, base - h2 - rb
    bowl = stroke(arc_into(pathops.Path(), cx, cy, rb, 0, 360, move=True), sw)
    R = W * 0.95
    a = math.degrees(math.asin(min(1, (cy - (base - H + h2)) / R)))
    p = arc_into(pathops.Path(), x + h2 + R, cy, R, 180, 180 - a, move=True)
    return union(bowl, stroke(p, sw))


def make_26(cx, base, H, swr=0.186, wr=0.66, gapr=0.2):
    W, sw, gap = H * wr, H * swr, H * gapr
    x = cx - (2 * W + gap) / 2
    return union(make_two(x, base, H, W, sw), make_six(x + W + gap, base, H, W, sw))


M_SHAPE = make_m()
DIG_H = 64
DIG_SHAPE = make_26(208, (BAND_TOP + 448) / 2 + DIG_H / 2, DIG_H)


def glyph_color():
    return (f'<path d="{d(TOP)}" fill="{TEAL}"/><path d="{d(SIDE)}" fill="{TEAL_D}"/>'
            f'<path d="{d(PAPER_SHAPE)}" fill="{PAPER}"/><path d="{d(BAND_SHAPE)}" fill="{BAND}"/>'
            f'<path d="{d(M_SHAPE)}" fill="{NAVY}"/><path d="{d(DIG_SHAPE)}" fill="{DIGITS}"/>')


def icon_svg(rx=96, tile=NAVY):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            '<title>Mail-in-a-box-26</title>'
            f'<rect width="512" height="512" rx="{rx}" fill="{tile}"/>{glyph_color()}</svg>\n')


def mono_path():
    """One colour, no tile: faces split by the gaps, band split from the label by a gap,
    M and 26 cut out (real holes)."""
    upper = minus(isect(FRONT, rect(64, 160, 288, BAND_TOP - G / 2 - 160)), M_SHAPE)
    lower = minus(isect(FRONT, rect(64, BAND_TOP + G / 2, 288, 448)), DIG_SHAPE)
    return union(TOP, SIDE, upper, lower)


MONO = mono_path()


def mono_svg(color="currentColor"):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<title>Mail-in-a-box-26</title><path d="{d(MONO)}" fill="{color}"/></svg>\n')


# ------------------------------------------------------------------ pixel-hinted favicons
def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, k):
    """colour a over b with coverage k"""
    a, b = hex2rgb(a), hex2rgb(b)
    return tuple(round(a[i] * k + b[i] * (1 - k)) for i in range(3)) + (255,)


def favicon16():
    """Hand-made 16 px, painted pixel by pixel (no downscaling): front 9x9 px, M 7x5 px with
    1 px strokes, band as a plain 2 px stripe (a "26" cannot be legible in 9x3 px, and the
    M needs the extra row). Edge pixels of the slanted faces are blended by hand."""
    im = render('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                f'<rect width="16" height="16" rx="3" fill="{NAVY}"/></svg>', 16)
    put = im.putpixel
    top = {2: [(4, .5)] + [(c, 1) for c in range(5, 12)] + [(12, .8)],
           3: [(3, .5)] + [(c, 1) for c in range(4, 11)] + [(11, .8)]}
    for r, cells in top.items():
        for c, k in cells:
            put((c, r), mix(TEAL, NAVY, k))
    side = {12: [(4, .8)] + [(r, 1) for r in range(5, 12)] + [(12, .5)],
            13: [(3, .8)] + [(r, 1) for r in range(4, 11)] + [(11, .5)]}
    for c, cells in side.items():
        for r, k in cells:
            put((c, r), mix(TEAL_D, NAVY, k))
    for r in range(5, 14):
        for c in range(2, 11):
            put((c, r), mix(PAPER if r < 12 else BAND, NAVY, 1))
    put((2, 13), mix(BAND, NAVY, .7)); put((10, 13), mix(BAND, NAVY, .7))
    M = ["X.....X",
         "XX...XX",
         "X.X.X.X",
         "X..X..X",
         "X.....X"]
    for j, row in enumerate(M):
        for i, ch in enumerate(row):
            if ch == "X":
                put((3 + i, 6 + j), mix(NAVY, NAVY, 1))
    return im


def favicon32_svg():
    """Hand-hinted 32 px (1 unit = 1 px): the master cube already sits on the pixel grid here
    (16-unit gaps = 1 px). M redrawn with 2 px stems on whole pixels, digits as a 4x5 pixel
    figure set with 1 px strokes."""
    TWO = [".XX.", "X..X", "..X.", ".X..", "XXXX"]
    SIX = [".XX.", "X...", "XXX.", "X..X", ".XX."]

    def pix(rows, ox, oy):
        return "".join(f'<rect x="{ox + i}" y="{oy + j}" width="1" height="1"/>'
                       for j, row in enumerate(rows) for i, ch in enumerate(row) if ch == "X")
    m = make_m(7 * 16, 19 * 16, M32[0] * 16, M32[1] * 16, 32, M32[2], M32[3])
    s = 1 / 16
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">'
            f'<rect width="32" height="32" rx="6" fill="{NAVY}"/>'
            f'<g transform="scale({s})"><path d="{d(TOP)}" fill="{TEAL}"/><path d="{d(SIDE)}" fill="{TEAL_D}"/>'
            f'</g><rect x="4" y="10" width="18" height="11.5" fill="{PAPER}"/>'
            f'<path d="M4 21H22V27.5A0.5 0.5 0 0 1 21.5 28H4.5A0.5 0.5 0 0 1 4 27.5Z" fill="{BAND}"/>'
            f'<g transform="scale({s})"><path d="{d(m)}" fill="{NAVY}"/></g>'
            f'<g fill="{NAVY}" shape-rendering="crispEdges">{pix(TWO, 8, 22)}{pix(SIX, 14, 22)}</g></svg>')


M32 = (12, 18, 24, 0.82)   # M rows 12..18, 2 px stems, diagonals 1.5 px


# ------------------------------------------------------------------ text to paths (DejaVu)
FONTS = {}


def font(path):
    if path not in FONTS:
        f = TTFont(path)
        FONTS[path] = (f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm, f["hmtx"])
    return FONTS[path]


DEJAVU_DIR = os.environ.get("DEJAVU_DIR", "/usr/share/fonts/truetype/dejavu")
BOLD = os.path.join(DEJAVU_DIR, "DejaVuSans-Bold.ttf")
BOOK = os.path.join(DEJAVU_DIR, "DejaVuSans.ttf")


def text_path(text, x, baseline, size, tracking=0.0, fontfile=BOLD):
    gs, cmap, upm, hmtx = font(fontfile)
    scale, parts, cx = size / upm, [], x
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, baseline)))
        parts.append(pen.getCommands())
        cx += hmtx[g][0] * scale + tracking * size
    return " ".join(p for p in parts if p), cx - x - tracking * size


def wordmark_svg(dark=False):
    """Icon + "Mail-in-a-box" + "-26" in the band colour (style of B), all outlined."""
    H, FS = 160, 60
    isz = 128
    x0 = 16 + isz + 30
    base = 80 + FS * 0.729 / 2
    d1, w1 = text_path("Mail-in-a-box", x0, base, FS, -0.005)
    d2, w2 = text_path("-26", x0 + w1 - 0.005 * FS, base, FS, -0.005)
    W = int(x0 + w1 + w2 + 24)
    word, acc = (PAPER, ACC_D) if dark else (NAVY, ACC_L)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            '<title>Mail-in-a-box-26</title>'
            f'<g transform="translate(16 16) scale({isz / 512})"><rect width="512" height="512" rx="96" fill="{NAVY}"/>'
            f'{glyph_color()}</g>'
            f'<path d="{d1}" fill="{word}"/><path d="{d2}" fill="{acc}"/></svg>\n'), W, H


def social_svg():
    S = 300
    ix = 120
    tx = ix + S + 64
    d_t, w_t = text_path("Mail-in-a-box", tx, 302, 76, -0.005)
    d_n, _ = text_path("-26", tx + w_t - 0.005 * 76, 302, 76, -0.005)
    sub1, _ = text_path("Unofficial community fork of Mail-in-a-Box", tx, 370, 28, 0, BOOK)
    sub2, _ = text_path("for Ubuntu 26.04 LTS", tx, 408, 28, 0, BOOK)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" width="1280" height="640">'
            f'<rect width="1280" height="640" fill="{NAVY}"/>'
            f'<g transform="translate({ix} {320 - S / 2}) scale({S / 512})">'
            f'<rect width="512" height="512" rx="96" fill="#143759"/>{glyph_color()}</g>'
            f'<path d="{d_t}" fill="{PAPER}"/><path d="{d_n}" fill="{ACC_D}"/>'
            f'<rect x="{tx + 2}" y="328" width="56" height="3" fill="{ACC_D}"/>'
            f'<path d="{sub1}" fill="#A9BCCF"/><path d="{sub2}" fill="#A9BCCF"/></svg>')


# ------------------------------------------------------------------ raster helpers
def render(svg, w, h=None):
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=w, output_height=h or w)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def b64(img):
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def on(bg, img):
    base = Image.new("RGBA", img.size, bg); base.alpha_composite(img); return base


def up(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def main():
    icon, mono = icon_svg(), mono_svg()
    wm, wmW, wmH = wordmark_svg()
    wmd, _, _ = wordmark_svg(dark=True)
    for n, c in {"icon.svg": icon, "icon-mono.svg": mono,
                 "logo-wordmark.svg": wm, "logo-wordmark-dark.svg": wmd}.items():
        with open(os.path.join(OUT, n), "w") as fh:
            fh.write(c)

    f16, f32, f48 = favicon16(), render(favicon32_svg(), 32), render(icon, 48)
    f16.save(os.path.join(OUT, "favicon-16.png"))
    f32.save(os.path.join(OUT, "favicon-32.png"))
    f48.save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)],
             append_images=[f16, f32])
    render(icon_svg(rx=0), 180).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))
    render(social_svg(), 1280, 640).convert("RGB").save(os.path.join(OUT, "social-preview.png"))

    # -------------------------------------------------------------- preview sheet
    W, H = 1400, 900
    big = render(icon, 240)
    m16L, m16D = render(mono_svg(NAVY), 16), render(mono_svg(PAPER), 16)
    m32L, m32D = render(mono_svg(NAVY), 32), render(mono_svg(PAPER), 32)
    wm_img = render(wm, 620, int(620 * wmH / wmW))
    wmd_img = render(wmd, 620, int(620 * wmH / wmW))
    L = 'font-family="DejaVu Sans" font-size="14" fill="#5B6B7C"'

    def img(x, y, im):
        return f'<image x="{x}" y="{y}" width="{im.width}" height="{im.height}" href="{b64(im)}"/>'

    def card(x, y, w, h, fill=LIGHT_BG):
        st = ' stroke="#DCE2E8"' if fill == LIGHT_BG else ''
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}"{st}/>'

    def tab(x, y, w, fill, txt, f):
        return (f'<path d="M{x} {y + 34}V{y + 10}a10 10 0 0 1 10-10h{w - 20}a10 10 0 0 1 10 10v24z" fill="{fill}"/>'
                + img(x + 16, y + 9, f)
                + f'<text x="{x + 42}" y="{y + 22}" font-family="DejaVu Sans" font-size="13" fill="{txt}">Mail-in-a-box-26 · Control Panel</text>')

    pal = f"Navy {NAVY} · Teal {TEAL} / {TEAL_D} · Paper {PAPER} · Amber {BAND} · Text accent {ACC_L}"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         f'<rect width="{W}" height="{H}" fill="#EEF1F4"/>',
         f'<text x="40" y="50" font-family="DejaVu Sans" font-weight="bold" font-size="24" fill="{NAVY}">Mail-in-a-box-26 · {TITLE}</text>',
         f'<text x="40" y="74" {L}>{pal} · Wordmark: DejaVu Sans Bold, converted to paths</text>',
         card(40, 96, 300, 300), img(70, 126, big),
         card(356, 96, 300, 300, DARK_BG), img(386, 126, big),
         f'<text x="40" y="416" {L}>icon.svg on light / dark</text>',
         card(680, 96, 220, 220), img(710, 126, render(mono_svg(NAVY), 160)),
         card(910, 96, 220, 220, DARK_BG), img(940, 126, render(mono_svg(PAPER), 160)),
         card(1140, 96, 220, 220, TEAL), img(1170, 126, render(mono_svg(NAVY), 160)),
         f'<text x="680" y="336" {L}>icon-mono.svg: one colour (currentColor), M and 26 cut out</text>',
         card(680, 350, 680, 110), img(710, 350 + (110 - wm_img.height) // 2, wm_img),
         card(680, 470, 680, 110, DARK_BG), img(710, 470 + (110 - wmd_img.height) // 2, wmd_img),
         f'<text x="680" y="600" {L}>logo-wordmark.svg / logo-wordmark-dark.svg</text>',
         card(40, 432, 616, 440),
         f'<text x="60" y="458" {L}>1:1 on light</text>',
         img(60, 486, f16), img(86, 478, f32), img(128, 470, f48), img(186, 486, m16L),
         f'<rect x="226" y="444" width="150" height="70" rx="6" fill="{DARK_BG}"/>',
         f'<text x="236" y="460" font-family="DejaVu Sans" font-size="12" fill="#9FB3C8">1:1 on dark</text>',
         img(238, 476, f16), img(264, 468, f32), img(306, 476, m16D),
         f'<text x="400" y="480" {L}>16 · 32 · 48 · mono 16</text>',
         f'<text x="60" y="540" {L}>favicon-16 × 8</text>', img(60, 552, up(f16, 8)),
         f'<text x="210" y="540" {L}>mono 32 × 4</text>', img(210, 552, up(on(LIGHT_BG, m32L), 4)),
         img(210, 690, up(on(DARK_BG, m32D), 4)),
         f'<text x="370" y="540" {L}>favicon-32 × 8 (detail)</text>',
         img(370, 552, up(f32, 8).crop((0, 32, 266, 288))),
         f'<text x="370" y="842" {L}>16 and 32 px hinted by hand</text>',
         f'<text x="60" y="842" {L}>apple-touch-icon (180)</text>', img(60, 690, render(icon_svg(rx=0), 132).convert("RGB")),
         card(680, 620, 680, 252, "#DEE1E6"),
         f'<text x="700" y="644" {L}>Browser tabs light + dark, favicon-16 at 1:1</text>',
         tab(700, 658, 300, "#FFFFFF", "#202124", f16),
         f'<text x="975" y="680" font-family="DejaVu Sans" font-size="13" fill="#5F6368">×</text>',
         f'<rect x="700" y="692" width="640" height="44" fill="#FFFFFF"/>',
         f'<rect x="716" y="702" width="608" height="24" rx="12" fill="#F1F3F4"/>',
         f'<text x="736" y="719" font-family="DejaVu Sans" font-size="12" fill="#5F6368">https://box.example.org/admin</text>',
         f'<rect x="700" y="752" width="640" height="104" rx="8" fill="#202124"/>',
         tab(712, 764, 300, "#35363A", "#E8EAED", f16),
         f'<rect x="712" y="798" width="616" height="44" fill="#35363A"/>',
         f'<rect x="728" y="808" width="584" height="24" rx="12" fill="#202124"/>',
         f'<text x="748" y="825" font-family="DejaVu Sans" font-size="12" fill="#9AA0A6">https://box.example.org/mail</text>',
         '</svg>']
    render("".join(p), W, H).convert("RGB").save(os.path.join(OUT, "preview.png"))
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
