"""Report generation: PNG charts and a strict-OOXML .docx dossier.

Stdlib only (zip + zlib PNG). Every chart carries its formula, data and
assumptions in the caption; DOCX labels each section's evidence quality.
No chart value is invented: inputs come from research results or the caller's
financial inputs only.
"""
import json
import os
import re
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

# ----------------------------------------------------------------- DOCX
# Clickable links: every URL in a line becomes an OOXML hyperlink
# (external relationship), so it opens directly in Word/LibreOffice/Google Docs.
_DOC_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _hyperlink_run(rid, url):
    return ('<w:hyperlink r:id="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:r><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r></w:hyperlink>' % (rid, _escape(url)))

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
    """images: list of (media_name, width_px, height_px, caption).

    Document is titled 'Proposal for Business Plan' and de-branded. Every URL
    in any content line becomes a clickable OOXML hyperlink (external rel).
    """
    from pathlib import Path
    out_path = Path(out_path)
    now = datetime.now(timezone.utc)
    title = dossier.get("title") or "Proposal for Business Plan"
    body = []
    body.append(_para(_run(title), style="Title"))
    body.append(_para(_run("Generated %s UTC · Evidence-first: labels describe evidence quality, not truth." % now.strftime("%Y-%m-%d %H:%M")),
                      style="Caption"))
    body.append(_para(_run(dossier["notice"], italic=True, size=18, color="64748B")))

    # Collect every unique URL first so rels ids are stable.
    url_set = []
    def reg(url):
        if url not in url_set:
            url_set.append(url)
        return url_set.index(url)
    for meta in dossier["sections"].values():
        for line in meta.get("content", []):
            for m in _DOC_URL_RE.finditer(str(line)):
                reg(m.group(0))

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
    # hyperlink rels continue after image rels
    for uidx, url in enumerate(url_set):
        rid = "rId%d" % (2 + len(images) + uidx)
        rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="%s" TargetMode="External"/>' % (rid, url))
    url_rid = {url: "rId%d" % (2 + len(images) + i) for i, url in enumerate(url_set)}

    def line_runs(text, size=20):
        """Runs for one content line; URLs become clickable hyperlinks."""
        text = str(text)
        out = []
        pos = 0
        for m in _DOC_URL_RE.finditer(text):
            if m.start() > pos:
                out.append(_run(text[pos:m.start()], size=size))
            out.append(_hyperlink_run(url_rid[m.group(0)], m.group(0)))
            pos = m.end()
        if pos < len(text):
            out.append(_run(text[pos:], size=size))
        return "".join(out)

    img_cursor = 0
    for key, meta in dossier["sections"].items():
        body.append(_para(_run(meta["title"].upper()), style="Heading1"))
        label = meta.get("label", "assumed")
        body.append(_para(_run("Evidence label: %s" % label.upper(), bold=True, size=20,
                               color={"verified": "16A34A", "estimated": "B45309",
                                      "assumed": "64748B", "unavailable": "DC2626"}[label])))
        for line in meta.get("content", []):
            body.append(_para(line_runs(line), style=None))
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

def _pdf_images_for(images, charts_dir, section_of=None):
    """Convert (name, w_px, h_px, caption) image tuples into the PDF engine's
    (section_key, abs_png_path, w_pt, h_pt, url) tuples. 640px wide -> ~460pt."""
    section_of = section_of or {}
    out = []
    for name, w_px, h_px, cap in images:
        path = os.path.join(charts_dir, name)
        w_pt = 460
        h_pt = int(h_px / w_px * w_pt) if w_px else int(h_px * 0.72)
        out.append((section_of.get(cap, cap), path, w_pt, h_pt, ""))
    return out


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
    docx_path = build_docx(dossier, result, os.path.join(out_dir, "proposal.docx"), images=images)
    pdf_path = None
    try:
        pdf_path = render_pdf(dossier, os.path.join(out_dir, "proposal.pdf"),
                              images=_pdf_images_for(images, charts_dir,
                                                     section_of={"scores": "opportunity_ranking",
                                                                 "metrics": "opportunity_ranking",
                                                                 "scenarios": "financial_forecast"}))
    except Exception:
        pdf_path = None
    report = {
        "schema_version": dossier.get("schema_version", 2),
        "generated_at": dossier.get("generated_at"),
        "topic": dossier.get("topic"),
        "country": dossier.get("country"),
        "capital_band": dossier.get("capital_band"),
        "docx": docx_path,
        "pdf": pdf_path,
        "charts": [os.path.join(charts_dir, name) for name, _, _, _ in images],
        "summary": {
            "candidates": len(candidates),
            "top_score": (top or {}).get("score", {}).get("total"),
            "sections": {k: v.get("label") for k, v in dossier.get("sections", {}).items()},
        },
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return {"docx": docx_path, "pdf": pdf_path, "report": os.path.join(out_dir, "report.json"),
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
    docx_path = build_docx(dossier, {"candidates": []}, os.path.join(out_dir, "proposal.docx"),
                           images=images)
    pdf_path = None
    try:
        pdf_path = render_pdf(dossier, os.path.join(out_dir, "proposal.pdf"),
                              images=_pdf_images_for(images, charts_dir,
                                                     section_of={"flow": "flow",
                                                                 "budget": "financial_forecast",
                                                                 "risk": "risk"}))
    except Exception:
        pdf_path = None
    sig = plan.get("signals") or {}
    report = {
        "schema_version": dossier.get("schema_version", 1),
        "generated_at": dossier.get("generated_at"),
        "kind": "business_implementation_plan",
        "topic": dossier.get("topic"),
        "country": dossier.get("country"),
        "capital_band": dossier.get("capital_band"),
        "docx": docx_path,
        "pdf": pdf_path,
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
    return {"docx": docx_path, "pdf": pdf_path, "report": os.path.join(out_dir, "report.json"),
            "charts": report["charts"], "summary": report["summary"]}
# ----------------------------------------------------------------- PDF (locked, RC4 R2, clickable links)
PDF_W, PDF_H = 612, 792
PDF_MARGIN = 54
PDF_TOP = PDF_H - PDF_MARGIN
PDF_BOTTOM = 66

_PAD = bytes([0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00,
              0x4E, 0x56, 0xFF, 0xFA, 0x01, 0x08, 0x2E, 0x2E, 0x00, 0xB6,
              0xD0, 0x68, 0x3E, 0x80, 0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53,
              0x69, 0x7A])


def _rc4(key, data):
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    i = j = 0
    out = bytearray()
    for b in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)


def _pdf_md5(data):
    import hashlib
    return hashlib.md5(data).digest()


def _pdf_pad(data):
    return (data + _PAD)[:32]


def _compute_file_key(password, o_entry, perms, docid):
    """Algorithm 2 (R2): file key = MD5(pad(pw) + O + P(le32) + ID1)[:5].
    Revision 2 has NO 50-iteration MD5 loop and NO XOR-RC4 final stage."""
    h = _pdf_md5(_pdf_pad(password) + o_entry + perms.to_bytes(4, "little") + docid)
    return h[:5]


def _compute_o(o_pw, u_pw):
    """Algorithm 3 (R2): O = RC4(first5(MD5(pad(owner_pw))), pad(user_pw))."""
    okey = _pdf_md5(_pdf_pad(o_pw))[:5]
    return _rc4(okey, _pdf_pad(u_pw))


def _compute_u(key):
    """Algorithm 4 (R2): U = RC4_5byte(32-byte padding) -> 32 bytes."""
    return _rc4(key, _PAD)


def _obj_key(file_key, obj_num, gen_num=0, is_stream=False):
    """Algorithm 1: per-object RC4 key, first (n+5)=10 bytes for R2.
    Stream objects additionally append 0xFFFFFFFF before the MD5."""
    h = _pdf_md5(file_key + obj_num.to_bytes(3, "little")
                 + gen_num.to_bytes(2, "little")
                 + (b"\xff\xff\xff\xff" if is_stream else b""))
    return h[:10]


def _obj_perms(perms):
    # /P: bits 1-12 = perms, bits 13-32 = 1. Return as signed 32-bit.
    p_full = (0xFFFFF000 | (perms & 0x0FFF)) & 0xFFFFFFFF
    return p_full - 0x100000000 if p_full >= 0x80000000 else p_full


def _perms_full(perms):
    return (0xFFFFF000 | (perms & 0x0FFF)) & 0xFFFFFFFF


def _pdf_octal_str(raw):
    """Serialize raw bytes as a PDF literal string: any non-alnum byte becomes
    \\ooo octal, so the reader can always find the real closing ')' even after
    RC4 encryption scrambles the value bytes."""
    out = bytearray()
    for byte in raw:
        if 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122 or byte == 32:
            out += bytes([byte])
        else:
            out += b"\\%03o" % byte
    return bytes(out)


def _unescape_literal(content):
    """Recover the raw value bytes from a PDF literal-string body (escapes)."""
    out = bytearray()
    i, n = 0, len(content)
    simple = {0x6E: 0x0A, 0x72: 0x0D, 0x74: 0x09, 0x62: 0x08, 0x66: 0x0C,
              0x28: 0x28, 0x29: 0x29, 0x5C: 0x5C}
    while i < n:
        c = content[i]
        if c == 0x5C and i + 1 < n:
            nxt = content[i + 1]
            if 48 <= nxt <= 55:  # 0-7 -> up to 3 octal digits
                octal = b""
                j = i + 1
                while j < n and 48 <= content[j] <= 55 and len(octal) < 3:
                    octal += bytes([content[j]])
                    j += 1
                out.append(int(octal, 8) & 0xFF)
                i = j
                continue
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def _encrypt_strings(body, key):
    """RC4-encrypt only string VALUES in a PDF object body (structure/operators/
    numbers stay plaintext). Literal strings are unescaped -> RC4 -> re-serialized
    with \\ooo octal escaping (reader-safe). Hex strings are decoded -> RC4 ->
    written as an octal literal. Non-string bytes pass through unchanged."""
    out = bytearray()
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c == 0x28:  # ( literal string
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                cj = body[j]
                if cj == 0x5C and j + 1 < n:
                    j += 2
                    continue
                if cj == 0x28:
                    depth += 1
                elif cj == 0x29:
                    depth -= 1
                j += 1
            value = _unescape_literal(body[i + 1:j - 1])
            out += b"(" + _pdf_octal_str(_rc4(key, value)) + b")"
            i = j
        elif c == 0x3C:  # < : dict delimiter << or a hex string
            if i + 1 < n and body[i + 1] == 0x3C:
                out += b"<"
                i += 1
                continue
            k = i + 1
            while k < n and body[k] in b" \t\r\n":
                k += 1
            if k < n and (48 <= body[k] <= 57 or 65 <= body[k] <= 70 or 97 <= body[k] <= 102):
                j = body.find(b">", i + 1)
                if j == -1:
                    out += b"<"
                    i += 1
                    continue
                hexpart = body[i + 1:j].replace(b" ", b"")
                if len(hexpart) % 2:
                    hexpart += b"0"
                value = bytes.fromhex(hexpart.decode("ascii"))
                out += b"(" + _pdf_octal_str(_rc4(key, value)) + b")"
                i = j + 1
            else:
                out += b"<"
                i += 1
        else:
            out += bytes([c])
            i += 1
    return bytes(out)


def _pdf_escape(text):
    return (str(text).replace("\\", r"\\").replace("(", r"\(")
            .replace(")", r"\)"))


def _pdf_winansi(text):
    """Map to WinAnsi; unknown chars become ? (Helvetica has no glyph)."""
    out = []
    for ch in str(text):
        o = ord(ch)
        if o < 0x80:
            out.append(ch)
        elif o in (0x2014, 0x2013):
            out.append("-")
        elif o in (0x2018, 0x2019):
            out.append("'")
        elif o in (0x201C, 0x201D):
            out.append('"')
        elif o == 0x2026:
            out.append("...")
        elif o in (0x00B7, 0x2022):
            out.append("*")
        elif o == 0x2122:
            out.append("(TM)")
        elif 0x80 <= o <= 0xFF:
            out.append(chr(o))
        else:
            out.append("?")
    return "".join(out)


def _pdf_wrap(text, width=92):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            while len(w) > width:
                lines.append(w[:width])
                w = w[width:]
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _png_decode(data):
    """Decode an 8-bit RGB/RGBA PNG -> (width, height, raw_rgb_bytes)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w, h, ctype = 8, b"", None, None, None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h, _bit, ctype = struct.unpack(">IIBB", chunk[:10])
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        pos += 12 + ln
    if w is None or h is None or ctype not in (2, 6):
        raise ValueError("unsupported PNG (need 8-bit RGB/RGBA)")
    raw = zlib.decompress(idat)
    bpp = 3 if ctype == 2 else 4
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    rowstart = 0
    for _ in range(h):
        f = raw[rowstart]
        rowstart += 1
        cur = bytearray(raw[rowstart:rowstart + stride])
        rowstart += stride
        if f == 1:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + a) & 0xFF
        elif f == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b2 = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b2 - c
                pa, pb, pc = abs(p - a), abs(p - b2), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b2 if pb <= pc and pb <= pc else c)
                cur[i] = (cur[i] + pr) & 0xFF
        if bpp == 4:
            cur = bytes(cur[i] for i in range(0, len(cur), 4))
        out += cur
        prev = bytearray(cur)
    return w, h, bytes(out)


def _pdf_title(dossier):
    t = (dossier.get("topic") or "Business Opportunity").strip()
    return "Proposal for Business Plan - %s" % t[:70]


def _pdf_meta_pages(dossier, title):
    """Dossier sections -> ordered (section_key, sectitle, [lines])."""
    scope = dossier.get("scope") or dossier.get("country") or "Global"
    pages = []
    pages.append(("__meta", "Executive Summary", [
        "Topic: %s | Scope: %s | Capital band: %s" % (
            dossier.get("topic", ""), scope, dossier.get("capital_band", "all")),
        "Evidence-first: every line is labeled by evidence quality, not truth.",
        "REVIEW_REQUIRED until each ASSUMED/ESTIMATED item is confirmed with a primary source.",
        "This is a fixed, locked PDF; the editable full edition ships as DOCX.",
    ]))
    for key, sec in dossier.get("sections", {}).items():
        lines = [sec.get("title", key)]
        for ln in sec.get("content", []):
            lines.append(str(ln))
        pages.append((key, sec.get("title", key), lines))
    return title, pages


def _split_pages(pages, per_page=26):
    """Split (key, title, lines) logical pages into physical pages honouring a
    per-page line budget. A section that overflows continues onto the next
    physical page with the same key (so charts still land on the right page)."""
    out = []
    for key, title, lines in pages:
        if not lines:
            continue
        body = lines[1:]
        header = lines[0]
        chunks = [body[i:i + per_page] for i in range(0, len(body), per_page)] or [[""]]
        for i, ch in enumerate(chunks):
            if i == 0:
                out.append((key, header, ch))
            else:
                out.append((key, header + " (cont.)", ch))
    return out


def render_pdf(dossier, out_path, title=None, pages=None, images=()):
    """Render a locked, paginated PDF from a sectioned dossier.

    `images` = list of (section_key, abs_png_path, width_pt, height_pt, url).
    Every URL in the body becomes a clickable /URI link; each chart image is
    clickable to its URL. RC4-encrypted (V1/R2, 40-bit) with a restrictive /P
    (view/print allowed, edit/annotate blocked). Returns the output path.
    """
    import hashlib
    title = title or dossier.get("title") or _pdf_title(dossier)
    if pages is None:
        title, pages = _pdf_meta_pages(dossier, title)
    pages = _split_pages(pages, per_page=26)
    n = len(pages)

    img_of = {}
    for entry in images:
        key, png, wpt, hpt, url = entry
        img_of.setdefault(key, []).append((png, wpt, hpt, url))

    page_of_key = {}
    for pidx, (key, _t, _l) in enumerate(pages):
        page_of_key.setdefault(key, pidx)
    page_imgs = {}
    for key, lst in img_of.items():
        tgt = page_of_key.get(key)
        if tgt is None:
            continue
        page_imgs.setdefault(tgt, []).extend(lst)

    url_re = re.compile(r"https?://[A-Za-z0-9._~:/?#@!$&'*+,;=%-]+")

    page_streams = []
    page_annots = []
    chart_list = []  # (page_index, png_path)
    gen = (dossier.get("generated_at") or "2026-10-28")[:10]
    for pidx, (key, sectitle, lines) in enumerate(pages):
        ops = []
        annots = []
        cy = PDF_TOP - 8
        ops.append("BT /F2 8 Tf 0.70 0.70 0.74 rg 1 0 0 1 56 %d Tm "
                   "(Generated %s | page %d of %d | CONFIDENTIAL - FOR REVIEW) Tj ET"
                   % (PDF_BOTTOM - 22, gen, pidx + 1, n))
        for tl in _pdf_wrap(sectitle, 64):
            ops.append("BT /F1 15 Tf 0.09 0.14 0.33 rg 1 0 0 1 %d %d Tm (%s) Tj ET"
                       % (PDF_MARGIN, cy, _pdf_escape(_pdf_winansi(tl))))
            cy -= 20
        cy -= 6
        ops.append("0.70 0.74 0.84 RG 1 w %d %d m %d %d l S"
                   % (PDF_MARGIN, cy, PDF_W - PDF_MARGIN, cy))
        cy -= 16
        for ln in lines:
            if cy < PDF_BOTTOM + 8:
                break
            text = _pdf_winansi(ln)
            if not text.strip():
                cy -= 7
                continue
            if text.startswith("   "):
                t = text.lstrip()
                url_matches = list(url_re.finditer(t))
                if url_matches:
                    # indented line containing URL(s) -> clickable segments
                    segs = []; pos = 0
                    for m in url_matches:
                        if m.start() > pos:
                            segs.append((t[pos:m.start()], None))
                        segs.append((m.group(0), m.group(0)))
                        pos = m.end()
                    if pos < len(t):
                        segs.append((t[pos:], None))
                    x = 74
                    parts = []
                    for s, u in segs:
                        if u:
                            parts.append("(%s)" % _pdf_escape(s))
                            wpt = max(10.0, len(s) * 4.0)
                            annots.append(b"<< /Type /Annot /Subtype /Link /Rect [%d %d %d %d] "
                                          b"/Border [0 0 0] /A << /S /URI /URI (%s) >> >>"
                                          % (x, cy - 1, int(x + wpt), cy + 9,
                                             _pdf_escape(u).encode("latin-1")))
                            x += wpt
                        else:
                            parts.append("(%s)" % _pdf_escape(s))
                            x += len(s) * 4.0
                    ops.append("BT /F4 8.5 Tf 1 0 0 1 74 %d Tm [%s] TJ ET"
                               % (cy, " ".join(parts)))
                else:
                    ops.append("BT /F4 8.5 Tf 0.22 0.24 0.30 rg 1 0 0 1 74 %d Tm (%s) Tj ET"
                               % (cy, _pdf_escape(t)))
                cy -= 12
            elif text[0] in ("*", "\u2022") or url_re.match(text) or \
                    (len(text) >= 3 and text[0].isdigit() and text[1] == "." and text[2] == " "):
                segs = []
                pos = 0
                for m in url_re.finditer(text):
                    if m.start() > pos:
                        segs.append((text[pos:m.start()], None))
                    segs.append((m.group(0), m.group(0)))
                    pos = m.end()
                if pos < len(text):
                    segs.append((text[pos:], None))
                if not segs:
                    segs = [(text, None)]
                x = PDF_MARGIN
                parts = []
                for s, u in segs:
                    if u:
                        parts.append("(%s)" % _pdf_escape(s))
                        wpt = max(10.0, len(s) * 4.6)
                        annots.append(b"<< /Type /Annot /Subtype /Link /Rect [%d %d %d %d] "
                                      b"/Border [0 0 0] /A << /S /URI /URI (%s) >> >>"
                                      % (x, cy - 1, int(x + wpt), cy + 10,
                                         _pdf_escape(u).encode("latin-1")))
                        x += wpt
                    else:
                        parts.append("(%s)" % _pdf_escape(s))
                        x += len(s) * 4.6
                ops.append("BT /F4 9 Tf 0.12 0.13 0.18 rg 1 0 0 1 %d %d Tm [%s] TJ ET"
                           % (PDF_MARGIN, cy, " ".join(parts)))
                cy -= 13
            else:
                ops.append("BT /F4 9 Tf 0.12 0.13 0.18 rg 1 0 0 1 %d %d Tm (%s) Tj ET"
                           % (PDF_MARGIN, cy, _pdf_escape(text)))
                cy -= 13
        for png, wpt, hpt, url in page_imgs.get(pidx, []):
            if cy - hpt < PDF_BOTTOM:
                cy = PDF_TOP - 28
            if not os.path.exists(png):
                continue
            chart_list.append((pidx, png))
            idx = len(chart_list) - 1
            ytop = cy
            ybot = cy - hpt
            if url:
                annots.append(b"<< /Type /Annot /Subtype /Link /Rect [%d %d %d %d] "
                              b"/Border [0 0 0] /A << /S /URI /URI (%s) >> >>"
                              % (PDF_MARGIN, ybot, PDF_MARGIN + int(wpt), ytop,
                                 _pdf_escape(url).encode("latin-1")))
            ops.append("IMG%d %d %d %d %d" % (idx, wpt, hpt, PDF_MARGIN, ybot))
            cy = ybot - 16
        page_streams.append("\n".join(ops).encode("latin-1", "replace"))
        page_annots.append(annots)
    return _finalize_pdf(out_path, page_streams, page_annots, chart_list, title, dossier)


def _finalize_pdf(out_path, page_streams, page_annots, chart_list, title, dossier):
    """Assemble the PDF object graph with RC4 standard security (V1/R2, 40-bit)."""
    import hashlib
    n = len(page_streams)

    docid = hashlib.sha1(
        (title + str(dossier.get("generated_at", ""))).encode("utf-8")).digest()[:16]
    perms = 0x04  # bit 2 (print) only; edit/annotate/form off
    u_pw = b""
    o = _compute_o(u_pw, u_pw)  # owner password == user password (empty)
    key = _compute_file_key(u_pw, o, _perms_full(perms), docid)
    uval = _compute_u(key)

    objects = {}

    def font(base, bold=False, italic=False):
        fn = "/Helvetica" + ("-Bold" if bold else "") + ("-Oblique" if italic else "")
        return ("<< /Type /Font /Subtype /Type1 /BaseFont %s "
                "/Encoding /WinAnsiEncoding >>" % fn).encode("latin-1")

    objects[1] = b"<< /Type /Catalog /Pages 7 0 R >>"
    objects[3] = font("Helvetica", bold=True)
    objects[4] = font("Helvetica")
    objects[5] = font("Helvetica", italic=True)
    objects[6] = font("Helvetica", bold=True, italic=True)

    # number plan: 7=Pages, then 2 objects per page (content, page), then images
    page_num = 7
    cursor = 8
    content_obj_ids = [cursor + 2 * i for i in range(n)]
    page_obj_ids = [cursor + 2 * i + 1 for i in range(n)]
    cursor += 2 * n
    image_obj_ids = list(range(cursor, cursor + len(chart_list)))
    cursor += len(chart_list)
    info_id = cursor
    cursor += 1
    encrypt_id = cursor

    all_kids = " ".join("%d 0 R" % p for p in page_obj_ids)
    objects[page_num] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                         % (all_kids, n)).encode("latin-1")

    decoded = {}
    for i, (pidx, png) in enumerate(chart_list):
        data = open(png, "rb").read()
        w, h, rgb = _png_decode(data)
        decoded[i] = (w, h, zlib.compress(rgb))

    for pidx in range(n):
        ops = page_streams[pidx].decode("latin-1", "replace")
        for i, (cpidx, png) in enumerate(chart_list):
            if cpidx != pidx:
                continue
            for m in re.finditer(r"IMG%d \d+ \d+ \d+ \d+" % i, ops):
                tok = m.group(0)
                wpt_s, hpt_s, x_s, y_s = tok.split()[1:5]
                do = ("q %d 0 0 %d %d %d cm /Im%d Do Q"
                      % (int(wpt_s), int(hpt_s), int(x_s), int(y_s), i))
                ops = ops.replace(tok, do)
        content = ops.encode("latin-1", "replace")
        objects[content_obj_ids[pidx]] = (
            ("<< /Length %d >>\nstream\n" % len(content)).encode("latin-1")
            + content + b"\nendstream")
        res = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >>"
        page_imgs_here = [i for i, (cpidx, _p) in enumerate(chart_list) if cpidx == pidx]
        if page_imgs_here:
            res += " /XObject << %s >>" % " ".join(
                "/Im%d %d 0 R" % (i, image_obj_ids[i]) for i in page_imgs_here)
        res += " >>"
        an = ""
        if page_annots[pidx]:
            an = " /Annots [%s]" % " ".join(
                a.decode("latin-1") for a in page_annots[pidx])
        objects[page_obj_ids[pidx]] = (
            "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            "/Resources %s /Contents %d 0 R%s >>"
            % (page_num, PDF_W, PDF_H, res, content_obj_ids[pidx], an)
        ).encode("latin-1")

    for i, (pidx, png) in enumerate(chart_list):
        w, h, scaled = decoded[i]
        objects[image_obj_ids[i]] = (
            ("<< /Type /XObject /Subtype /Image /Width %d /Height %d "
             "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
             "/Length %d >>\nstream\n" % (w, h, len(scaled))).encode("latin-1")
            + scaled + b"\nendstream")

    objects[info_id] = (
        "<< /Title (%s) /Producer (proposal-report-engine) "
        "/Creator (proposal-report-engine) /CreationDate (D:20261028) >>"
        % _pdf_escape(_pdf_winansi(title))).encode("latin-1")
    objects[encrypt_id] = (
        "<< /Filter /Standard /V 1 /R 2 /O <%s> /U <%s> /P %d /Length 40 >>"
        % (o.hex().upper(), uval.hex().upper(), _obj_perms(perms))).encode("latin-1")

    out = bytearray()
    out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offs = {}
    for num in sorted(objects):
        body = objects[num]
        offs[num] = len(out)
        out += ("%d 0 obj\n" % num).encode("latin-1")
        if num == encrypt_id:
            # The /Encrypt dictionary itself is NOT encrypted (spec 3.5.2).
            out += body + b"\nendobj\n"
            continue
        ok = _obj_key(key, num)                 # 10-byte per-object key (strings + streams)
        if b"stream\n" in body:
            # Any stream object: the dict string values AND the stream DATA are
            # both RC4-encrypted with the same 10-byte per-object key
            # (pypdf CryptRC4: rc4_key = MD5(file_key[:5] + obj3 + gen2)[:10]).
            head, rest = body.split(b"stream\n", 1)
            rest = rest[: -len(b"\nendstream")]
            out += _encrypt_strings(head, ok) + b"stream\n" + _rc4(ok, rest) \
                + b"\nendstream\nendobj\n"
        else:
            # Plain dict/object: encrypt only string values, keep structure.
            out += _encrypt_strings(body, ok) + b"\nendobj\n"
    xref = len(out)
    maxn = max(offs)
    out += ("xref\n0 %d\n" % (maxn + 1)).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, maxn + 1):
        if num in offs:
            out += ("%010d 00000 n \n" % offs[num]).encode("latin-1")
        else:
            out += b"0000000000 65535 f \n"
    out += ("trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R "
            "/ID [<%s> <%s>] /Encrypt %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (maxn + 1, info_id, docid.hex().upper(), docid.hex().upper(),
               encrypt_id, xref)).encode("latin-1")
    with open(out_path, "wb") as f:
        f.write(out)
    return str(out_path)
