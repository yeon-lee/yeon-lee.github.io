#!/usr/bin/env python3
"""Generate the clickable research map for _pages/research.md.

Usage:
    python3 bin/make_research_map.py --style STYLE > _includes/research_map.svg

STYLE is one of: ink, glow, radial, pastel  (SVG) or cards (HTML).
The page wrapper and click behaviour live in _includes/research_map.liquid.

Edit HUBS / SATELLITES / LINKS below and re-run. Each node links to the section
of the research page with the matching id (data-topic); the script in
research_map.liquid opens that section on click. Every style embeds its own
<style> block, so no site CSS is needed for the map itself.
"""
import argparse
import math

# id: (cx, cy, [label lines], colour, [short label lines for the radial style])
HUBS = {
    "information": (480, 128, ["many-body physics of", "quantum information"], "#8dd3c7", ["quantum", "information"]),
    "error-correction": (690, 268, ["quantum error", "correction"], "#fb8072", ["error", "correction"]),
    "dynamics": (612, 486, ["non-equilibrium dynamics", "& quantum control"], "#fdb462", ["non-equilibrium", "dynamics"]),
    "criticality": (346, 486, ["exotic quantum phases", "& criticality"], "#bebada", ["exotic phases", "& criticality"]),
    "topology": (268, 268, ["topological bands &", "correlated physics"], "#80b1d3", ["topology &", "correlations"]),
}
HUB_ORDER = ["information", "error-correction", "dynamics", "criticality", "topology"]

# (label, hub id, cx, cy) — positions are used by the pastel/ink/glow styles
SATELLITES = [
    ("mixed-state phases", "information", 300, 52),
    ("coherent information", "information", 480, 36),
    ("decoherence", "information", 640, 60),
    ("strong-to-weak SSB", "information", 760, 130),
    ("entanglement bootstrap", "information", 232, 138),
    ("toric code", "information", 612, 190),
    ("quantum LDPC codes", "error-correction", 866, 250),
    ("fault tolerance", "error-correction", 888, 322),
    ("addressable logicals", "error-correction", 862, 392),
    ("error thresholds", "error-correction", 772, 190),
    ("measurement-induced phases", "dynamics", 842, 472),
    ("Lindbladian dynamics", "dynamics", 826, 556),
    ("Floquet phases", "dynamics", 665, 600),
    ("Rydberg simulators", "dynamics", 735, 422),
    ("deconfined criticality", "criticality", 160, 548),
    ("spin liquids", "criticality", 108, 455),
    ("gauge theories", "criticality", 228, 604),
    ("symmetry-enriched topological order", "criticality", 445, 588),
    ("non-Hermitian topology", "topology", 100, 200),
    ("moiré materials", "topology", 84, 292),
    ("quantum Monte Carlo", "topology", 116, 378),
]

# extra hub-to-hub connections (shared themes)
LINKS = [
    ("information", "error-correction"),
    ("information", "dynamics"),
    ("information", "topology"),
    ("criticality", "topology"),
    ("dynamics", "criticality"),
    ("error-correction", "dynamics"),
]

W, H = 960, 620
HUB_FONT, SAT_FONT = 17, 14.5
HUB_CHAR, SAT_CHAR = 8.6, 7.1  # rough px per character (Georgia)
FONT = 'Georgia, "Times New Roman", Times, serif'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hexrgb(c):
    return tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))


def mix(c, white_fraction):
    """Blend a hex colour towards white (0 = colour, 1 = white)."""
    r, g, b = hexrgb(c)
    f = white_fraction
    return "#{:02x}{:02x}{:02x}".format(round(r + (255 - r) * f), round(g + (255 - g) * f), round(b + (255 - b) * f))


def darken(c, fraction):
    r, g, b = hexrgb(c)
    return "#{:02x}{:02x}{:02x}".format(round(r * (1 - fraction)), round(g * (1 - fraction)), round(b * (1 - fraction)))


def hub_box(cx, cy, lines, pad_x=34, pad_y=18):
    w = max(len(l) for l in lines) * HUB_CHAR + pad_x
    h = len(lines) * (HUB_FONT + 6) + pad_y
    return cx - w / 2, cy - h / 2, w, h


def sat_box(cx, cy, label, pad_x=22, pad_y=14):
    w = len(label) * SAT_CHAR + pad_x
    h = SAT_FONT + pad_y
    return cx - w / 2, cy - h / 2, w, h


def text(x, y, s, cls="", anchor="middle", extra=""):
    c = f' class="{cls}"' if cls else ""
    return f'<text{c} x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="central"{extra}>{esc(s)}</text>'


COMMON_CSS = f"""
.rmap {{ font-family: {FONT}; }}
.rmap a {{ cursor: pointer; outline: none; }}
.rmap text {{ pointer-events: none; }}
.rmap .rmap-edge {{ transition: stroke .15s ease, stroke-opacity .15s ease; }}
"""


# ----------------------------------------------------------------------------- styles
def render_pastel():
    out = [f"<style>{COMMON_CSS}"
           ".rmap .rmap-edge{stroke:#d4d4d4;stroke-width:1.2}"
           ".rmap .rmap-edge-hub{stroke:#c4c4c4;stroke-width:1.4;stroke-dasharray:4 4}"
           ".rmap .rmap-edge.is-active{stroke:#8a8a8a;stroke-width:1.6}"
           ".rmap text{fill:#222}.rmap .rmap-sat text{font-size:14.5px}.rmap .rmap-hub text{font-size:17px;font-weight:700}"
           ".rmap a:hover rect,.rmap a:focus-visible rect{filter:brightness(.94)}"
           ".rmap a.is-active rect,.rmap a:focus-visible rect{stroke:#222;stroke-width:2}"
           "</style>"]
    out.append('<g class="rmap-edges">')
    for a, b in LINKS:
        ax, ay = HUBS[a][:2]
        bx, by = HUBS[b][:2]
        out.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" class="rmap-edge rmap-edge-hub"/>')
    for label, hub, cx, cy in SATELLITES:
        hx, hy = HUBS[hub][:2]
        out.append(f'<line x1="{hx}" y1="{hy}" x2="{cx}" y2="{cy}" class="rmap-edge" data-topic="{hub}"/>')
    out.append("</g>")
    for label, hub, cx, cy in SATELLITES:
        x, y, w, h = sat_box(cx, cy, label)
        color = HUBS[hub][3]
        out.append(
            f'<a href="#{hub}" class="rmap-node rmap-sat" data-topic="{hub}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" fill="{mix(color, 0.72)}" stroke="{mix(color, 0.35)}" stroke-width="1"/>'
            + text(cx, cy, label) + "</a>"
        )
    for hid in HUB_ORDER:
        cx, cy, lines, color, _ = HUBS[hid]
        x, y, w, h = hub_box(cx, cy, lines)
        out.append(f'<a href="#{hid}" class="rmap-node rmap-hub" data-topic="{hid}">')
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" fill="{color}" stroke="{darken(color, 0.25)}" stroke-width="1.2"/>')
        n = len(lines)
        for i, line in enumerate(lines):
            out.append(text(cx, cy + (i - (n - 1) / 2) * (HUB_FONT + 6), line))
        out.append("</a>")
    return out


def render_ink():
    """Outlined hubs, plain-text keywords, hairline edges: the quietest option."""
    out = [f"<style>{COMMON_CSS}"
           ".rmap .rmap-edge{stroke:#cfd3d8;stroke-width:1}"
           ".rmap .rmap-edge-hub{stroke:#d9dcdf;stroke-width:1;stroke-dasharray:3 4}"
           ".rmap .rmap-edge.is-active{stroke:#7a7f85;stroke-width:1.4}"
           ".rmap .rmap-sat text{font-size:14.5px;fill:#3a3f45;transition:fill .15s ease}"
           ".rmap .rmap-sat rect{fill:#fff}"
           ".rmap .rmap-sat circle{transition:r .15s ease}"
           ".rmap .rmap-sat:hover text,.rmap .rmap-sat.is-active text{fill:#111;text-decoration:underline}"
           ".rmap .rmap-hub text{font-size:17px;font-weight:700;fill:#1c1c1c}"
           ".rmap .rmap-hub rect{fill:#fff;stroke-width:2;transition:fill .15s ease}"
           ".rmap .rmap-hub:hover rect,.rmap .rmap-hub.is-active rect,.rmap .rmap-hub:focus-visible rect{fill:var(--tint-light)}"
           "</style>"]
    out.append('<g class="rmap-edges">')
    for a, b in LINKS:
        ax, ay = HUBS[a][:2]
        bx, by = HUBS[b][:2]
        out.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" class="rmap-edge rmap-edge-hub"/>')
    for label, hub, cx, cy in SATELLITES:
        hx, hy = HUBS[hub][:2]
        out.append(f'<line x1="{hx}" y1="{hy}" x2="{cx}" y2="{cy}" class="rmap-edge" data-topic="{hub}"/>')
    out.append("</g>")
    for label, hub, cx, cy in SATELLITES:
        x, y, w, h = sat_box(cx, cy, label, pad_x=10, pad_y=6)
        color = HUBS[hub][3]
        # white halo so the edge stops short of the words, plus a small coloured dot on the hub side
        hx, hy = HUBS[hub][:2]
        dx, dy = hx - cx, hy - cy
        d = math.hypot(dx, dy) or 1
        px, py = cx + dx / d * (w / 2 + 4), cy + dy / d * (h / 2 + 4)
        out.append(
            f'<a href="#{hub}" class="rmap-node rmap-sat" data-topic="{hub}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4"/>'
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="{darken(color, 0.15)}"/>'
            + text(cx, cy, label) + "</a>"
        )
    for hid in HUB_ORDER:
        cx, cy, lines, color, _ = HUBS[hid]
        x, y, w, h = hub_box(cx, cy, lines, pad_x=30, pad_y=14)
        out.append(f'<a href="#{hid}" class="rmap-node rmap-hub" data-topic="{hid}" style="--tint-light:{mix(color, 0.8)}">')
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" stroke="{darken(color, 0.1)}"/>')
        n = len(lines)
        for i, line in enumerate(lines):
            out.append(text(cx, cy + (i - (n - 1) / 2) * (HUB_FONT + 5), line))
        out.append("</a>")
    return out


def render_glow():
    """The QuantumGroup@UGent look: soft-shadowed hub boxes, keywords with a warm glow."""
    out = ["<defs>"
           '<filter id="rmap-glow" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>'
           '<filter id="rmap-shadow" x="-20%" y="-30%" width="140%" height="160%"><feDropShadow dx="0" dy="1.5" stdDeviation="3" flood-color="#000" flood-opacity=".18"/></filter>'
           "</defs>",
           f"<style>{COMMON_CSS}"
           ".rmap .rmap-edge{stroke:#f3e88f;stroke-width:1.8}"
           ".rmap .rmap-edge-hub{stroke:#f3e88f;stroke-width:1.8}"
           ".rmap .rmap-edge.is-active{stroke:#d8c93a}"
           ".rmap .rmap-sat text{font-size:15px;fill:#333}"
           ".rmap .rmap-sat rect{fill:#fff59a;opacity:.85;transition:opacity .15s ease}"
           ".rmap .rmap-sat:hover rect,.rmap .rmap-sat.is-active rect{opacity:1;fill:#ffe95c}"
           ".rmap .rmap-hub text{font-size:17px;font-weight:700;fill:#222}"
           ".rmap .rmap-hub rect{transition:filter .15s ease}"
           ".rmap .rmap-hub:hover rect,.rmap .rmap-hub.is-active rect{filter:url(#rmap-shadow) brightness(.95)}"
           "</style>"]
    out.append('<g class="rmap-edges">')
    for a, b in LINKS:
        ax, ay = HUBS[a][:2]
        bx, by = HUBS[b][:2]
        out.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" class="rmap-edge rmap-edge-hub"/>')
    for label, hub, cx, cy in SATELLITES:
        hx, hy = HUBS[hub][:2]
        out.append(f'<line x1="{hx}" y1="{hy}" x2="{cx}" y2="{cy}" class="rmap-edge" data-topic="{hub}"/>')
    out.append("</g>")
    for label, hub, cx, cy in SATELLITES:
        x, y, w, h = sat_box(cx, cy, label, pad_x=16, pad_y=10)
        out.append(
            f'<a href="#{hub}" class="rmap-node rmap-sat" data-topic="{hub}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" filter="url(#rmap-glow)"/>'
            + text(cx, cy, label) + "</a>"
        )
    for hid in HUB_ORDER:
        cx, cy, lines, color, _ = HUBS[hid]
        x, y, w, h = hub_box(cx, cy, lines, pad_x=30, pad_y=16)
        out.append(f'<a href="#{hid}" class="rmap-node rmap-hub" data-topic="{hid}">')
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{color}" filter="url(#rmap-shadow)"/>')
        n = len(lines)
        for i, line in enumerate(lines):
            out.append(text(cx, cy + (i - (n - 1) / 2) * (HUB_FONT + 6), line))
        out.append("</a>")
    return out


def wrap(label, limit=19):
    if len(label) <= limit:
        return [label]
    words = label.split()
    best, line = [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > limit:
            best.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    best.append(line)
    return best


def render_radial():
    """Hubs on a ring around the group, keywords fanning out with curved spokes."""
    global W, H
    W, H = 1100, 700
    cx0, cy0 = 550, 350
    hub_rx, hub_ry, hub_r = 205, 150, 50
    sat_rx, sat_ry = 415, 292
    angles = {"information": -90, "error-correction": -18, "dynamics": 54, "criticality": 126, "topology": 198}
    out = [f"<style>{COMMON_CSS}"
           ".rmap .rmap-spoke{stroke:#d7d7d7;stroke-width:1.2}"
           ".rmap .rmap-edge{fill:none;stroke-width:1.3;stroke-opacity:.55}"
           ".rmap .rmap-edge.is-active{stroke-opacity:1;stroke-width:1.8}"
           ".rmap .rmap-center circle{fill:#26292c}.rmap .rmap-center text{fill:#fff;font-size:15px;font-weight:700}"
           ".rmap .rmap-sat text{font-size:14.5px;fill:#333;transition:fill .15s ease}"
           ".rmap .rmap-sat:hover text,.rmap .rmap-sat.is-active text{fill:#000;text-decoration:underline}"
           ".rmap .rmap-sat circle{stroke:#fff;stroke-width:1.5}"
           ".rmap .rmap-hub text{font-size:14.5px;font-weight:700;fill:#1c1c1c}"
           ".rmap .rmap-hub circle{stroke:#fff;stroke-width:3;transition:filter .15s ease}"
           ".rmap .rmap-hub:hover circle,.rmap .rmap-hub.is-active circle,.rmap .rmap-hub:focus-visible circle{filter:brightness(.93);stroke:#222;stroke-width:2}"
           "</style>"]
    pos = {}
    for hid in HUB_ORDER:
        a = math.radians(angles[hid])
        pos[hid] = (cx0 + hub_rx * math.cos(a), cy0 + hub_ry * math.sin(a))
    # spokes centre -> hub
    out.append('<g class="rmap-edges">')
    for hid in HUB_ORDER:
        hx, hy = pos[hid]
        out.append(f'<line x1="{cx0}" y1="{cy0}" x2="{hx:.1f}" y2="{hy:.1f}" class="rmap-spoke"/>')
    # satellites: spread each hub's keywords over +-34 degrees around the hub angle
    sat_pos = []
    for hid in HUB_ORDER:
        items = [s for s in SATELLITES if s[1] == hid]
        n = len(items)
        spread = {6: 78, 5: 66, 4: 54, 3: 40}.get(n, 50)
        for i, (label, hub, _, _) in enumerate(items):
            ang = angles[hid] + (-spread / 2 + spread * i / (n - 1) if n > 1 else 0)
            a = math.radians(ang)
            sx, sy = cx0 + sat_rx * math.cos(a), cy0 + sat_ry * math.sin(a)
            sat_pos.append((label, hid, sx, sy, ang))
            hx, hy = pos[hid]
            # quadratic curve bulging slightly outward
            mx, my = (hx + sx) / 2, (hy + sy) / 2
            qx, qy = cx0 + (mx - cx0) * 1.12, cy0 + (my - cy0) * 1.12
            out.append(f'<path d="M{hx:.1f},{hy:.1f} Q{qx:.1f},{qy:.1f} {sx:.1f},{sy:.1f}" class="rmap-edge" data-topic="{hid}" stroke="{darken(HUBS[hid][3], 0.1)}"/>')
    out.append("</g>")
    for label, hid, sx, sy, ang in sat_pos:
        color = HUBS[hid][3]
        c = math.cos(math.radians(ang))
        anchor = "middle" if abs(c) < 0.3 else ("start" if c > 0 else "end")
        tx = sx + (0 if anchor == "middle" else (10 if anchor == "start" else -10))
        lines = wrap(label, 16)
        n = len(lines)
        # labels above/below the dot near the top/bottom, beside it elsewhere
        if anchor == "middle":
            up = math.sin(math.radians(ang)) < 0
            base_y = sy + (-(8 + 8.5 * n) if up else (8 + 8.5 * n))
        else:
            base_y = sy
        out.append(f'<a href="#{hid}" class="rmap-node rmap-sat" data-topic="{hid}">')
        out.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4.5" fill="{darken(color, 0.1)}"/>')
        for i, line in enumerate(lines):
            out.append(text(tx, base_y + (i - (n - 1) / 2) * 17, line, anchor=anchor))
        out.append("</a>")
    for hid in HUB_ORDER:
        hx, hy = pos[hid]
        color = HUBS[hid][3]
        lines = HUBS[hid][4]
        out.append(f'<a href="#{hid}" class="rmap-node rmap-hub" data-topic="{hid}">')
        out.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{hub_r}" fill="{color}"/>')
        n = len(lines)
        for i, line in enumerate(lines):
            out.append(text(hx, hy + (i - (n - 1) / 2) * 18, line))
        out.append("</a>")
    out.append('<g class="rmap-center"><circle cx="{0}" cy="{1}" r="46"/>{2}{3}</g>'.format(
        cx0, cy0, text(cx0, cy0 - 9, "Lee Group"), text(cx0, cy0 + 10, "@ UIUC")))
    return out


def render_cards():
    """Not a graph: one card per direction with its keywords, responsive on phones."""
    css = f"""
<style>
.rmap.rcards{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.8rem;margin:.5rem 0 .75rem;font-family:{FONT}}}
@media (max-width:991.98px){{.rmap.rcards{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}
@media (max-width:575.98px){{.rmap.rcards{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
.rmap .rcard{{display:block;color:inherit;text-decoration:none;border:1px solid rgba(0,0,0,.1);border-top:5px solid var(--tint);border-radius:6px;padding:.7rem .75rem .8rem;background:#fff;transition:box-shadow .15s ease,transform .15s ease,background .15s ease}}
.rmap .rcard:hover,.rmap .rcard:focus-visible{{text-decoration:none;color:inherit;box-shadow:0 4px 14px rgba(0,0,0,.09);transform:translateY(-2px);outline:none}}
.rmap .rcard.is-active{{background:var(--tint-light);border-color:var(--tint)}}
.rmap .rcard-title{{font-weight:700;font-size:.98rem;line-height:1.25;margin-bottom:.55rem}}
.rmap .rcard-tags{{display:flex;flex-wrap:wrap;gap:.3rem}}
.rmap .rcard-tags span{{font-size:.76rem;line-height:1.2;padding:.18rem .45rem;border-radius:999px;background:#f1f2f4;color:#444}}
.rmap .rcard.is-active .rcard-tags span{{background:#fff}}
</style>"""
    out = [css, '<div class="rmap rcards">']
    for hid in HUB_ORDER:
        _, _, lines, color, _ = HUBS[hid]
        title = " ".join(lines).replace("&", "&amp;")
        tags = "".join(f"<span>{esc(s[0])}</span>" for s in SATELLITES if s[1] == hid)
        out.append(
            f'<a class="rmap-node rcard" href="#{hid}" data-topic="{hid}" style="--tint:{color};--tint-light:{mix(color, 0.82)}">'
            f'<div class="rcard-title">{title}</div><div class="rcard-tags">{tags}</div></a>'
        )
    out.append("</div>")
    return out


STYLES = {"pastel": render_pastel, "ink": render_ink, "glow": render_glow, "radial": render_radial, "cards": render_cards}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", choices=sorted(STYLES), default="ink")
    args = ap.parse_args()
    body = STYLES[args.style]()
    if args.style == "cards":
        print("\n".join(body))
        return
    print(f'<svg class="rmap rmap-{args.style}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="rmap-title">')
    print('<title id="rmap-title">Map of research topics; click a topic to read more.</title>')
    print("\n".join(body))
    print("</svg>")


if __name__ == "__main__":
    main()
