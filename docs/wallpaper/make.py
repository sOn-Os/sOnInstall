"""sOnOs wallpaper: the website's look as a 16:9 poster.

Writes sonos-terminal.svg; sonos.svg is the same without the text and the nine marks.
Usage: make.py ../logo/sonos.svg sonos-terminal.svg
"""

import math
import re
import sys
from pathlib import Path

logo = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])
paths = re.findall(r'<path [^>]*/>', logo)

W, H = 3840, 2160
INK, RED, WHITE, SMOKE, LINE = '#0B0909', '#E53935', '#FFFFFF', '#A79C9D', '#2E2627'
SLANT = math.tan(math.radians(12))


def para(x: float, y: float, w: float, h: float, fill: str, extra: str = '') -> str:
	"""A parallelogram leaning like the logo, x is its bottom-left corner"""
	d = SLANT * h
	return f'<path d="M{x:.1f} {y + h:.1f} L{x + d:.1f} {y:.1f} L{x + d + w:.1f} {y:.1f} L{x + w:.1f} {y + h:.1f} Z" fill="{fill}"{extra}/>'


# Thin slanted lines across the whole picture, like a racing poster
hair = []
for x in range(-800, W + 800, 96):
	hair.append(f'<line x1="{x}" y1="{H}" x2="{x + SLANT * H:.1f}" y2="0" stroke="#171213" stroke-width="2"/>')

# The red band of the website, cut across the right side, with a thin echo next to it
bands = [
	para(2560, -40, 520, H + 80, RED),
	para(3150, -40, 40, H + 80, RED, ' opacity="0.85"'),
	para(3250, -40, 14, H + 80, RED, ' opacity="0.6"'),
]

# The wordmark: 186 x 68 units of the logo, scaled up and placed left of the band
scale = 11.5
mx, my = 330 - 74 * scale, 760 - 26 * scale
mark = f'<g transform="translate({mx:.1f} {my:.1f}) scale({scale})">' + ''.join(paths) + '</g>'
# Its shadow on the band side, so the white letters stand out where they cross the red
shadow = f'<g transform="translate({mx + 26:.1f} {my + 26:.1f}) scale({scale})" opacity="0.55">' + ''.join(
	re.sub(r'(fill|stroke)="#[0-9A-Fa-f]{6}"', fr'\1="{INK}"', p) for p in paths) + '</g>'

# The nine marks of the installer, six answered
ticks = ''.join(para(360 + i * 92, 1730, 64, 30, RED if i < 6 else 'none', '' if i < 6 else f' stroke="{RED}" stroke-width="4"') for i in range(9))

mono = "font-family='DejaVu Sans Mono, monospace' font-size='40' letter-spacing='6'"
text = (
	f"<text x='360' y='1660' {mono} fill='{RED}'>ARCH LINUX · ROLLING · X86_64</text>"
	f"<text x='360' y='1900' {mono} fill='{SMOKE}'>root@sOnOs ~ # <tspan fill='{WHITE}' font-weight='bold'>fastfetch</tspan></text>"
	f"<rect x='1082' y='1864' width='26' height='46' fill='{WHITE}'/>"
)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
<radialGradient id="glow" cx="0.72" cy="0.55" r="0.75">
<stop offset="0" stop-color="{RED}" stop-opacity="0.22"/>
<stop offset="0.55" stop-color="{RED}" stop-opacity="0.04"/>
<stop offset="1" stop-color="{RED}" stop-opacity="0"/>
</radialGradient>
<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="{INK}" stop-opacity="1"/>
<stop offset="0.6" stop-color="{INK}" stop-opacity="0"/>
</linearGradient>
<filter id="grain" x="0" y="0" width="100%" height="100%">
<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/>
<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.05 0"/>
</filter>
</defs>
<rect width="{W}" height="{H}" fill="{INK}"/>
{''.join(hair)}
<rect width="{W}" height="{H}" fill="url(#fade)"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
{''.join(bands)}
{shadow}
{mark}
{ticks}
{text}
<rect width="{W}" height="{H}" filter="url(#grain)"/>
</svg>
'''
out.write_text(svg)
