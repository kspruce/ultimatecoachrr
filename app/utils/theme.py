"""Team colours: validation, presets and the CSS variables built from them.

A team picks two colours (primary and accent). Everything else the theme
needs, such as readable text on top of each colour and a lighter primary for
links in dark mode, is worked out here so any pair stays legible.
"""
import re

DEFAULT_PRIMARY = '#6E1F2F'
DEFAULT_ACCENT = '#C79A3B'

# (name, primary, accent) shown as one-click choices on the colours page
PRESETS = [
    ('Claret & gold', '#6E1F2F', '#C79A3B'),
    ('Navy & tangerine', '#1D3461', '#E8833A'),
    ('Forest & straw', '#1F4D3A', '#E2C25B'),
    ('Teal & coral', '#0F5E63', '#F28C6B'),
    ('Black & pink', '#1C1B20', '#FF5C8A'),
    ('Purple & mint', '#3B2C6B', '#9FD8CB'),
    ('Red & cream', '#9E2A2B', '#F2E8CF'),
    ('Slate & mustard', '#264653', '#E9C46A'),
]

_HEX = re.compile(r'^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')
LIGHT_TEXT = '#FBF6EC'
DARK_TEXT = '#1E1A18'


def normalize_hex(value):
    """'#abc', 'ABC123' or '#aabbcc' -> '#AABBCC'; None if it isn't a colour."""
    match = _HEX.match((value or '').strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = ''.join(c * 2 for c in digits)
    return '#' + digits.upper()


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return '#' + ''.join(f'{max(0, min(255, round(c))):02X}' for c in rgb)


def _luminance(hex_colour):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(hex_colour):
    """Cream or near-black, whichever reads better on top of the colour."""
    if contrast_ratio(hex_colour, LIGHT_TEXT) >= contrast_ratio(hex_colour, DARK_TEXT):
        return LIGHT_TEXT
    return DARK_TEXT


def _mix(a, b, weight):
    """weight of a, (1 - weight) of b."""
    return _hex(tuple(x * weight + y * (1 - weight) for x, y in zip(_rgb(a), _rgb(b))))


def readable_on(hex_colour, background, minimum=4.5):
    """Lighten or darken a colour until text in it reads on the background."""
    towards = '#FFFFFF' if _luminance(background) < 0.2 else '#000000'
    colour = hex_colour
    for step in range(1, 11):
        if contrast_ratio(colour, background) >= minimum:
            break
        colour = _mix(hex_colour, towards, 1 - step / 10)
    return colour


# Page backgrounds the theme sits on (see static/css/theme.css)
LIGHT_PAPER = '#FBF8F2'
DARK_CARD = '#1F1B19'


def team_palette(settings=None):
    """The colours for a team's settings row (or the defaults)."""
    primary = normalize_hex(getattr(settings, 'primary_color', None)) or DEFAULT_PRIMARY
    accent = normalize_hex(getattr(settings, 'accent_color', None)) or DEFAULT_ACCENT
    ink_light = readable_on(primary, LIGHT_PAPER)
    ink_dark = readable_on(primary, DARK_CARD)
    return {
        'primary': primary,
        'accent': accent,
        'on_primary': text_on(primary),
        'on_accent': text_on(accent),
        'ink_light': ink_light,
        'ink_dark': ink_dark,
        'accent_ink_light': readable_on(accent, LIGHT_PAPER, 3),
        'accent_ink_dark': readable_on(accent, DARK_CARD, 3),
        'show_stripe': getattr(settings, 'show_kit_stripe', True) is not False,
    }


def theme_css(palette):
    """The :root variables injected into every page."""
    def rgb(h):
        return ', '.join(str(c) for c in _rgb(h))
    p = palette
    return (
        ':root{'
        f"--club:{p['primary']};--club-rgb:{rgb(p['primary'])};"
        f"--accent:{p['accent']};--accent-rgb:{rgb(p['accent'])};"
        f"--on-club:{p['on_primary']};--on-accent:{p['on_accent']};"
        f"--club-ink-light:{p['ink_light']};--club-ink-light-rgb:{rgb(p['ink_light'])};"
        f"--club-ink-dark:{p['ink_dark']};--club-ink-dark-rgb:{rgb(p['ink_dark'])};"
        f"--accent-ink-light:{p['accent_ink_light']};--accent-ink-dark:{p['accent_ink_dark']};"
        '}'
    )
