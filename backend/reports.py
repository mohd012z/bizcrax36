"""Report generation: PNG charts and a strict-OOXML .docx dossier.

Stdlib only (zip + zlib PNG). Every chart carries its formula, data and
assumptions in the caption; DOCX labels each section's evidence quality.
No chart value is invented: inputs come from research results or the caller's
financial inputs only.
"""
import json
import os
import struct
import zipfile
import zlib
from datetime import datetime, timezone
from xml.sax.saxutils import escape as _escape

from backend.business_blueprint import financial_model
from backend.research_depth import sensitivity

# ---------------------------------------------------------------- PNG writer

def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

def write_png(width, height, rows):
    """rows: list of bytes, each row width*3 (RGB, top to bottom)."""
    raw = b"".join(b"\x00" + row for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))

class Canvas:
    def __init__(self, width, height, background=(250, 251, 252)):
        self.width = width
        self.height = height
        self.pixels = [bytearray(background * width) for _ in range(height)]

    def fill_rect(self, x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(self.height, y1)):
            row = self.pixels[y]
            for x in range(max(0, x0), min(self.width, x1)):
                i = x * 3
                row[i] = color[0]; row[i + 1] = color[1]; row[i + 2] = color[2]

    def dot(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            i = x * 3
            self.pixels[y][i] = color[0]; self.pixels[y][i + 1] = color[1]; self.pixels[y][i + 2] = color[2]

    def line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0); dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1; sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.dot(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    def text(self, x, y, string, color=(24, 24, 27), scale=1):
        cursor = x
        for ch in string:
            glyph = FONT.get(ch.upper()) or FONT.get(ch)
            if glyph is None:
                cursor += 6 * scale
                continue
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit:
                        self.fill_rect(cursor + gx * scale, y + gy * scale,
                                        cursor + (gx + 1) * scale, y + (gy + 1) * scale, color)
            cursor += 6 * scale
        return cursor

    def text_right(self, x, y, string, color=(24, 24, 27), scale=1):
        width = len(string) * 6 * scale
        self.text(x - width, y, string, color, scale)

    def bytes(self):
        return write_png(self.width, self.height, [bytes(r) for r in self.pixels])

# Minimal 5x7 bitmap font (uppercase; lowercase maps to uppercase).
_F = {
 "A": "01110 10001 10001 11111 10001 10001 10001".split(),
 "B": "11110 10001 10001 11110 10001 10001 11110".split(),
 "C": "01110 10001 10000 10000 10000 10001 01110".split(),
 "D": "11110 10001 10001 10001 10001 10001 11110".split(),
 "E": "11111 10000 10000 11110 10000 10000 11111".split(),
 "F": "11111 10000 10000 11110 10000 10000 10000".split(),
 "G": "01110 10001 10000 10111 10001 10001 01111".split(),
 "H": "10001 10001 10001 11111 10001 10001 10001".split(),
 "I": "01110 00100 00100 00100 00100 00100 01110".split(),
 "J": "00111 00010 00010 00010 00010 10010 01100".split(),
 "K": "10001 10010 10100 11000 10100 10010 10001".split(),
 "L": "10000 10000 10000 10000 10000 10000 11111".split(),
 "M": "10001 11011 10101 10101 10001 10001 10001".split(),
 "N": "10001 11001 10101 10011 10001 10001 10001".split(),
 "O": "01110 10001 10001 10001 10001 10001 01110".split(),
 "P": "11110 10001 10001 11110 10000 10000 10000".split(),
 "Q": "01110 10001 10001 10001 10101 10010 01101".split(),
 "R": "11110 10001 10001 11110 10100 10010 10001".split(),
 "S": "01111 10000 10000 01110 00001 00001 11110".split(),
 "T": "11111 00100 00100 00100 00100 00100 00100".split(),
 "U": "10001 10001 10001 10001 10001 10001 01110".split(),
 "V": "10001 10001 10001 10001 10001 01010 00100".split(),
 "W": "10001 10001 10001 10101 10101 10101 01010".split(),
 "X": "10001 10001 01010 00100 01010 10001 10001".split(),
 "Y": "10001 10001 01010 00100 00100 00100 00100".split(),
 "Z": "11111 00001 00010 00100 01000 10000 11111".split(),
 "0": "01110 10001 10011 10101 11001 10001 01110".split(),
 "1": "00100 01100 00100 00100 00100 00100 01110".split(),
 "2": "01110 10001 00001 00010 00100 01000 11111".split(),
 "3": "11111 00010 00100 00010 00001 10001 01110".split(),
 "4": "00010 00110 01010 10010 11111 00010 00010".split(),
 "5": "11111 10000 11110 00001 00001 10001 01110".split(),
 "6": "01110 10000 10000 11110 10001 10001 01110".split(),
 "7": "11111 00001 00010 00100 01000 01000 01000".split(),
 "8": "01110 10001 10001 01110 10001 10001 01110".split(),
 "9": "01110 10001 10001 01111 00001 00001 01110".split(),
 " ": ["00000"] * 7,
 ".": ["00000"] * 5 + ["00100", "00100"],
 ",": ["00000"] * 5 + ["00100", "01000"],
 ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
 "%": ["11001 11010 00010 00100 01000 01011 10011".split()],
 "/": ["00001 00010 00010 00100 01000 01000 10000".split()],
 "-": ["00000"] * 3 + ["11111"] + ["00000"] * 3,
 "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
 "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
 ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
 "#": ["01010", "01010", "11111", "01010", "11111", "01010", "01010"],
 "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
 "°": ["01110", "10001", "10001", "01110", "00000", "00000", "00000"],
 "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"],
 "!": ["00100"] * 5 + ["00000", "00100"],
 "=": ["00000"] * 2 + ["11111"] * 2 + ["00000"] * 3,
 "?": ["01110", "10001", "00001", "00110", "00100", "00000", "00100"],
}
FONT = {}
for _ch, _rows in _F.items():
    FONT[_ch] = [("1" in r) and [1 if b == "1" else 0 for b in r] or [0] * 5 for r in _rows]

INK = (37, 99, 235)
INK_ALT = (124, 58, 237)
GRID = (226, 232, 240)
LABEL = (51, 65, 85)
FAINT = (100, 116, 139)

def _save(path, canvas):
    path.write_bytes(canvas.bytes())
    return str(path)

def render_score_chart(candidates, path, title="TOP LEADS — PRELIMINARY SCORE /100", max_items=8):
    from pathlib import Path
    path = Path(path)
    rows_ = candidates[:max_items]
    height = 90 + len(rows_) * 44
    c = Canvas(640, height)
    c.text(16, 14, title, FAINT, 1)
    max_bar = 360
    for i, item in enumerate(rows_):
        y = 56 + i * 44
        score = (item.get("score") or {}).get("total", 0)
        verified = (item.get("verification") or {}).get("verified")
        label = (item["title"] or "?")[:32]
        c.text(16, y, label, LABEL, 1)
        x0 = 16
        bar_w = max(2, int(max_bar * score / 100.0))
        color = INK if verified else (148, 163, 184)
        c.fill_rect(x0, y + 16, x0 + bar_w, y + 30, color)
        c.text(x0 + bar_w + 8, y + 17, "%d/100" % score, INK if verified else FAINT, 1)
        if verified:
            c.text(16 + max_bar + 70, y + 1, "SRC-VERIFIED", (22, 101, 52), 1)
    caption = "Heuristic weighted score. Colors: blue = source fetched + title-matched, gray = review required."
    c.text(16, height - 18, caption[:78], FAINT, 1)
    return _save(path, c)

def render_metric_chart(candidate, path, title="SCORE METRICS — TOP LEAD"):
    from pathlib import Path
    path = Path(path)
    score = candidate.get("score") or {}
    metrics = score.get("metrics") or {}
    weights = score.get("weights") or {}
    c = Canvas(640, 90 + len(metrics) * 40)
    c.text(16, 14, title, FAINT, 1)
    c.text(16, 30, (candidate.get("title") or "?")[:70], LABEL, 1)
    y = 66
    for key, m in metrics.items():
        value = int(m.get("value", 0))
        basis = m.get("basis", "assumed")
        label = key.replace("_", " ")
        c.text(16, y, label[:22].title(), LABEL, 1)
        bar_w = max(2, int(280 * value / 100.0))
        color = INK if basis == "evidence" else (148, 163, 184)
        c.fill_rect(16, y + 16, 16 + bar_w, y + 27, color)
        c.text(16 + bar_w + 8, y + 16, "%d (w=%d, %s)" % (value, weights.get(key, 0), basis), FAINT, 1)
        y += 40
    c.text(16, 90 + len(metrics) * 40 - 18, "Blue = evidence-based, gray = assumed. Total = weighted sum /100.", FAINT, 1)
    return _save(path, c)

def render_scenario_chart(series, path, title="ILLUSTRATIVE CASH FLOW SCENARIOS (12 MO)", unit="RM"):
    from pathlib import Path
    path = Path(path)
    c = Canvas(640, 400)
    c.text(16, 14, title, FAINT, 1)
    plot = (120, 50, 560, 330)  # x0,y0,x1,y1
    values = [v for _, vals in series for v in vals] or [0]
    lo, hi = min(values), max(values)
    if lo == hi:
        hi = lo + 1
    c.fill_rect(plot[0], plot[1], plot[2], plot[3], (255, 255, 255))
    c.fill_rect(plot[0], plot[1], plot[2], plot[3], GRID)
    c.line(plot[0], plot[1], plot[2], plot[1], GRID)
    c.line(plot[0], plot[3], plot[2], plot[3], GRID)
    # zero line
    zero_y = int(plot[3] - (0 - lo) / (hi - lo) * (plot[3] - plot[1])) if 0 >= lo and 0 <= hi else None
    if zero_y is not None:
        c.line(plot[0], zero_y, plot[2], zero_y, (148, 163, 184))
    n = len(series[0][1]) if series else 0
    def xy(i, v):
        x = plot[0] + int(i / max(1, n - 1) * (plot[2] - plot[0]))
        y = plot[3] - int((v - lo) / (hi - lo) * (plot[3] - plot[1]))
        return x, y
    colors = [INK, INK_ALT, (16, 185, 129)]
    for si, (label, vals) in enumerate(series):
        color = colors[si % len(colors)]
        prev = None
        for i, v in enumerate(vals):
            x, y = xy(i, v)
            if prev:
                c.line(prev[0], prev[1], x, y, color)
            c.dot(x, y, color)
            prev = (x, y)
        c.text(plot[2] - len(label) * 6 - 4, 24 + si * 14, label, color, 1)
    c.text(plot[0], 336, "M1", FAINT, 1)
    c.text(plot[2] - 18, 336, "M12", FAINT, 1)
    c.text(16, 354, "Formula: cumulative net cash = (cash - startup) + monthly operating profit x months.", FAINT, 1)
    c.text(16, 370, "Scenario multipliers 0.5x / 1x / 1.5x of base volume. Illustrative, not a forecast.", FAINT, 1)
    c.text(16, 386, "Unit: %s. Inputs supplied by the user; no market data assumed." % unit, FAINT, 1)
    return _save(path, c)

def render_flow_chart(flow, path, title="IMPLEMENTATION FLOW"):
    from pathlib import Path
    path = Path(path)
    n = len(flow) or 1
    c = Canvas(640, 210)
    c.text(16, 14, title[:46], FAINT, 1)
    gap = 10
    x0, x1 = 16, 640 - 16
    bw = int((x1 - x0 - gap * (n - 1)) / n)
    y = 50
    x = x0
    for i, stage in enumerate(flow):
        color = INK if i % 2 == 0 else INK_ALT
        c.fill_rect(x, y, x + bw, y + 30, color)
        label = (stage.get("stage") or "?")[:max(4, bw // 6 - 1)]
        c.text(x + 3, y + 9, label, (255, 255, 255), 1)
        if i < n - 1:
            ax = x + bw
            c.line(ax + 1, y + 15, ax + gap, y + 15, (100, 116, 139))
            c.line(ax + gap - 3, y + 11, ax + gap, y + 15, (100, 116, 139))
            c.line(ax + gap - 3, y + 19, ax + gap, y + 15, (100, 116, 139))
        x += bw + gap
    # Stage outputs as a clean list below (avoids per-box label collision).
    c.text(16, 92, "STAGE OUTPUT (go/no-go gate):", LABEL, 1)
    ly = 108
    for stage in flow:
        c.text(16, ly, "- %s: %s" % (stage.get("stage", "?"),
                                     (stage.get("note") or "")[:60]), FAINT, 1)
        ly += 14
    c.text(16, ly + 2, "Each stage must produce evidence before the next begins.", FAINT, 1)
    return _save(path, c)


def render_budget_chart(budget, path, title="ILLUSTRATIVE BUDGET BY CATEGORY (MYR)"):
    from pathlib import Path
    path = Path(path)
    items = list((budget.get("items") or {}).items())
    c = Canvas(640, 90 + len(items) * 40)
    c.text(16, 14, title, FAINT, 1)
    total = sum(v for _, v in items) or 1
    max_bar = 340
    y = 50
    for k, v in items:
        label = k.replace("_", " ").title()[:22]
        c.text(16, y, label, LABEL, 1)
        bar_w = max(2, int(max_bar * v / total))
        c.fill_rect(16, y + 16, 16 + bar_w, y + 27, INK)
        c.text(16 + bar_w + 8, y + 17, "RM %s" % "{:,}".format(v), FAINT, 1)
        y += 40
    cap = "Estimated bands, not a quote. Total = sum of categories. Replace with real quotes."
    c.text(16, 90 + len(items) * 40 - 18, cap[:78], FAINT, 1)
    return _save(path, c)


def render_risk_chart(risks, path, title="RISK REGISTER — SCORE (SEVERITY x LIKELIHOOD)"):
    from pathlib import Path
    path = Path(path)
    rows_ = risks[:8]
    c = Canvas(640, 90 + len(rows_) * 44)
    c.text(16, 14, title, FAINT, 1)
    y = 50
    for r in rows_:
        s = int(r.get("score", 0))
        label = (r.get("risk") or "?")[:30]
        c.text(16, y, label, LABEL, 1)
        bar_w = max(2, int(340 * s / 9.0))
        color = (220, 38, 38) if s >= 6 else (180, 83, 9) if s >= 3 else (100, 116, 139)
        c.fill_rect(16, y + 16, 16 + bar_w, y + 27, color)
        c.text(16 + bar_w + 8, y + 17, "%d/9 [%s]" % (s, r.get("basis", "assumed")), FAINT, 1)
        y += 44
    c.text(16, 90 + len(rows_) * 44 - 18, "Score = severity x likelihood (each 1-3). Red>=6 amber>=3. Mitigations in DOCX.", FAINT, 1)
    return _save(path, c)


# ----------------------------------------------------------------- DOCX

_DOC_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '</Types>'
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>'
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="44"/><w:color w:val="1D4ED8"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="280" w:after="120"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="1D4ED8"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="200" w:after="80"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:i/><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr></w:style>'
    '</w:styles>'
)
_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
       'xmlns:rel="http://schemas.openxmlformats.org/package/2006/relationships"')

def _run(text, bold=False, italic=False, size=None, color=None):
    rpr = "<w:rPr>"
    if bold:
        rpr += "<w:b/>"
    if italic:
        rpr += "<w:i/>"
    if size:
        rpr += '<w:sz w:val="%d"/>' % size
    if color:
        rpr += '<w:color w:val="%s"/>' % color
    rpr += "</w:rPr>"
    return "<w:r>%s<w:t xml:space=\"preserve\">%s</w:t></w:r>" % (rpr, _escape(text))

def _para(runs, style=None, jc=None):
    ppr = ""
    inner = ""
    if style:
        inner += '<w:pStyle w:val="%s"/>' % style
    if jc:
        inner += '<w:jc w:val="%s"/>' % jc
    if inner:
        ppr = "<w:pPr>%s</w:pPr>" % inner
    return "<w:p>%s%s</w:p>" % (ppr, runs)

def _image_para(rid, width_px, height_px):
    emu_w = width_px * 9525
    emu_h = height_px * 9525
    return (
        '<w:p><w:r><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        '<wp:extent cx="%d" cy="%d"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:docPr id="1" name="chart"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="chart.png"/>'
        '<pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic>'
        '</wp:inline></w:drawing></w:r></w:p>'
    ) % (emu_w, emu_h, rid, emu_w, emu_h)

def build_docx(dossier, result, out_path, images=()):
    """images: list of (media_name, width_px, height_px, caption)."""
    from pathlib import Path
    out_path = Path(out_path)
    now = datetime.now(timezone.utc)
    body = []
    body.append(_para(_run("BizCrax36 — 360° Opportunity Dossier"), style="Title"))
    body.append(_para(_run("Generated %s UTC · Evidence-first: labels describe evidence quality, not truth." % now.strftime("%Y-%m-%d %H:%M")),
                      style="Caption"))
    body.append(_para(_run(dossier["notice"], italic=True, size=18, color="64748B")))

    # Place each image at its target section: sort by section order first.
    section_order = list(dossier["sections"].keys())
    target_of = {"scores": "opportunity_ranking", "metrics": "opportunity_ranking",
                 "scenarios": "financial_forecast",
                 "flow": "flow", "budget": "financial_forecast", "risk": "risk"}
    ordered_images = sorted(images, key=lambda img: section_order.index(
        target_of.get(img[3], section_order[-1])))
    image_rids = {}
    rels = []
    for idx, (name, w, h, cap) in enumerate(images, start=2):
        rid = "rId%d" % idx
        image_rids[name] = (rid, w, h, cap)
        rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/%s"/>' % (rid, name))

    img_cursor = 0
    for key, meta in dossier["sections"].items():
        body.append(_para(_run("%s — %s" % (key.upper(), meta["title"].upper())), style="Heading1"))
        label = meta.get("label", "assumed")
        body.append(_para(_run("Evidence label: %s" % label.upper(), bold=True, size=20,
                               color={"verified": "16A34A", "estimated": "B45309",
                                      "assumed": "64748B", "unavailable": "DC2626"}[label])))
        for line in meta.get("content", []):
            body.append(_para(_run(str(line), size=20)))
        while img_cursor < len(ordered_images):
            name, w, h, cap = ordered_images[img_cursor]
            if target_of.get(cap) != key:
                break
            rid, _, _, _ = image_rids[name]
            body.append(_image_para(rid, w, h))
            body.append(_para(_run("Figure: %s" % _figure_caption(cap)), style="Caption"))
            img_cursor += 1
    body.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
                'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document %s><w:body>%s</w:body></w:document>' % (_NS, "".join(body)))
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + "".join(rels) + '</Relationships>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _DOC_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/styles.xml", _STYLES)
        for name, w, h, cap in images:
            media = out_path.parent / "charts" / name
            if media.exists():
                zf.writestr("word/media/%s" % name, media.read_bytes())
    return str(out_path)

def _figure_caption(kind):
    return {
        "scores": "Preliminary weighted scores for top leads. Blue bars = source-verified leads.",
        "metrics": "Metric breakdown of the top lead with basis (evidence vs assumed) per metric.",
        "scenarios": "Illustrative cumulative cash flow at 0.5x/1x/1.5x volume. User-supplied inputs only.",
        "flow": "Implementation flow with go/no-go gates. Each stage must produce evidence before the next begins.",
        "budget": "Illustrative budget by category (MYR). Estimated bands — replace with real quotes before spending.",
        "risk": "Risk register scored by severity x likelihood. Red >= 6, amber >= 3. Mitigations in the DOCX body.",
    }.get(kind, kind)

# ----------------------------------------------------------------- pipeline

def scenario_series(financials):
    """Cumulative 12-month net cash for 0.5x/1x/1.5x volume scenarios."""
    base_model = financial_model(financials)
    if base_model["status"] != "scenario_only":
        return None
    from decimal import Decimal
    cash = Decimal(str(financials.get("cash_available", 0)))
    startup = Decimal(str(financials.get("startup_cost", 0)))
    rows = sensitivity(financials)["scenarios"]
    series = []
    for row in rows:
        monthly = Decimal(row["monthly_operating_profit"])
        start = cash - startup
        cumulative = [float(start)]
        for _ in range(1, 12):
            cumulative.append(cumulative[-1] + float(monthly))
        series.append(("%sx volume" % row["sales_multiplier"], cumulative))
    return series

def generate_report(dossier, result, out_dir, financials=None):
    """Build charts + DOCX + report.json. Returns paths dict (None entries = not produced)."""
    out_dir = str(out_dir)
    charts_dir = os.path.join(out_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    candidates = result.get("candidates") or []
    top = candidates[0] if candidates else None
    images = []
    if top is not None:
        render_score_chart(candidates, os.path.join(charts_dir, "scores.png"))
        images.append(("scores.png", 640, 90 + min(8, len(candidates)) * 44, "scores"))
        render_metric_chart(top, os.path.join(charts_dir, "metrics.png"))
        images.append(("metrics.png", 640, 90 + len((top.get("score") or {}).get("metrics") or {}), "metrics"))
    if financials:
        series = scenario_series(financials)
        if series:
            render_scenario_chart(series, os.path.join(charts_dir, "scenarios.png"))
            images.append(("scenarios.png", 640, 400, "scenarios"))
    docx_path = build_docx(dossier, result, os.path.join(out_dir, "report.docx"), images=images)
    report = {
        "schema_version": dossier.get("schema_version", 2),
        "generated_at": dossier.get("generated_at"),
        "topic": dossier.get("topic"),
        "country": dossier.get("country"),
        "capital_band": dossier.get("capital_band"),
        "docx": docx_path,
        "charts": [os.path.join(charts_dir, name) for name, _, _, _ in images],
        "summary": {
            "candidates": len(candidates),
            "top_score": (top or {}).get("score", {}).get("total"),
            "sections": {k: v.get("label") for k, v in dossier.get("sections", {}).items()},
        },
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return {"docx": docx_path, "report": os.path.join(out_dir, "report.json"),
            "charts": report["charts"], "summary": report["summary"]}


def generate_news_report(dossier, plan, out_dir):
    """Build flow/budget/risk charts + DOCX for a news-derived implementation plan."""
    out_dir = str(out_dir)
    charts_dir = os.path.join(out_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    images = []
    render_flow_chart(plan.get("flow") or [], os.path.join(charts_dir, "flow.png"))
    images.append(("flow.png", 640, 210, "flow"))
    budget = plan.get("budget") or {}
    render_budget_chart(budget, os.path.join(charts_dir, "budget.png"))
    images.append(("budget.png", 640, 90 + len((budget.get("items") or {})) * 40, "budget"))
    render_risk_chart(plan.get("risks") or [], os.path.join(charts_dir, "risk.png"))
    images.append(("risk.png", 640, 90 + min(8, len(plan.get("risks") or [])) * 44, "risk"))
    docx_path = build_docx(dossier, {"candidates": []}, os.path.join(out_dir, "report.docx"),
                           images=images)
    sig = plan.get("signals") or {}
    report = {
        "schema_version": dossier.get("schema_version", 1),
        "generated_at": dossier.get("generated_at"),
        "kind": "business_implementation_plan",
        "topic": dossier.get("topic"),
        "country": dossier.get("country"),
        "capital_band": dossier.get("capital_band"),
        "docx": docx_path,
        "charts": [os.path.join(charts_dir, name) for name, _, _, _ in images],
        "summary": {
            "source_url": plan.get("source_url"),
            "source_name": plan.get("source_name"),
            "sector": plan.get("sector"),
            "horizon": plan.get("horizon"),
            "potential_class": plan.get("potential_class"),
            "growth_score": sig.get("growth_score"),
            "budget_total": (plan.get("budget") or {}).get("total"),
            "risks": len(plan.get("risks") or []),
            "sections": {k: v.get("label") for k, v in dossier.get("sections", {}).items()},
        },
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return {"docx": docx_path, "report": os.path.join(out_dir, "report.json"),
            "charts": report["charts"], "summary": report["summary"]}
