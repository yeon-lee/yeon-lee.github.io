#!/usr/bin/env python3
"""Generate the clickable research map (an inline SVG) for _pages/research.md.

Usage:  python3 bin/make_research_map.py > _includes/research_map.svg
(the page wrapper and click behaviour live in _includes/research_map.liquid)

Edit HUBS / SATELLITES / LINKS below and re-run. Each node links to the
section of the research page with the matching id (data-topic); the small
script in _includes/research_map.liquid opens that section on click.
Positions are in a 960x620 coordinate system; the SVG scales to the page width.
"""

# id: (cx, cy, [label lines], fill colour)
HUBS = {
    "information": (480, 128, ["many-body physics of", "quantum information"], "#8dd3c7"),
    "error-correction": (690, 268, ["quantum error", "correction"], "#fb8072"),
    "dynamics": (612, 486, ["non-equilibrium dynamics", "& quantum control"], "#fdb462"),
    "criticality": (346, 486, ["exotic quantum phases", "& criticality"], "#bebada"),
    "topology": (268, 268, ["topological bands &", "correlated physics"], "#80b1d3"),
}

# (label, hub id, cx, cy)
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


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mix(hex_color, white_fraction):
    """Blend a hex colour towards white (0 = colour, 1 = white)."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    f = white_fraction
    return "#{:02x}{:02x}{:02x}".format(
        round(r + (255 - r) * f), round(g + (255 - g) * f), round(b + (255 - b) * f)
    )


def darken(hex_color, fraction):
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(
        round(r * (1 - fraction)), round(g * (1 - fraction)), round(b * (1 - fraction))
    )


def hub_box(cx, cy, lines):
    w = max(len(l) for l in lines) * HUB_CHAR + 34
    h = len(lines) * (HUB_FONT + 6) + 18
    return cx - w / 2, cy - h / 2, w, h


def sat_box(cx, cy, label):
    w = len(label) * SAT_CHAR + 22
    h = SAT_FONT + 14
    return cx - w / 2, cy - h / 2, w, h


out = []
out.append(
    f'<svg class="rmap" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
    'role="img" aria-labelledby="rmap-title">'
)
out.append('<title id="rmap-title">Map of research topics; click a topic to read more.</title>')

# edges first (behind the nodes)
out.append('<g class="rmap-edges">')
for a, b in LINKS:
    ax, ay = HUBS[a][:2]
    bx, by = HUBS[b][:2]
    out.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" class="rmap-edge rmap-edge-hub"/>')
for label, hub, cx, cy in SATELLITES:
    hx, hy = HUBS[hub][:2]
    out.append(f'<line x1="{hx}" y1="{hy}" x2="{cx}" y2="{cy}" class="rmap-edge" data-topic="{hub}"/>')
out.append("</g>")

# satellites
out.append('<g class="rmap-sats">')
for label, hub, cx, cy in SATELLITES:
    x, y, w, h = sat_box(cx, cy, label)
    color = HUBS[hub][3]
    out.append(
        f'<a href="#{hub}" class="rmap-node rmap-sat" data-topic="{hub}">'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" '
        f'fill="{mix(color, 0.72)}" stroke="{mix(color, 0.35)}" stroke-width="1"/>'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central">{esc(label)}</text>'
        "</a>"
    )
out.append("</g>")

# hubs
out.append('<g class="rmap-hubs">')
for hid, (cx, cy, lines, color) in HUBS.items():
    x, y, w, h = hub_box(cx, cy, lines)
    out.append(f'<a href="#{hid}" class="rmap-node rmap-hub" data-topic="{hid}">')
    out.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" '
        f'fill="{color}" stroke="{darken(color, 0.25)}" stroke-width="1.2"/>'
    )
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (i - (n - 1) / 2) * (HUB_FONT + 6)
        out.append(
            f'<text x="{cx}" y="{cy + dy:.1f}" text-anchor="middle" dominant-baseline="central">{esc(line)}</text>'
        )
    out.append("</a>")
out.append("</g>")
out.append("</svg>")

print("\n".join(out))
