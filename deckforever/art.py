"""
Steam library artwork for the entries this app creates, drawn with cairo at install time
(cairo and librsvg ship with SteamOS). Text-and-shape art only: no third-party logos.

Steam looks for, per non-Steam shortcut app id, in <steam>/userdata/<id3>/config/grid/:
    <appid>p.png       portrait tile   600x900
    <appid>.png        wide capsule    920x430
    <appid>_hero.png   hero banner    1920x620
    <appid>_logo.png   logo (transparent), shown over the hero
and the shortcut's own `icon` field points at a small square PNG.
"""
import math
import os

SIZES = {"p": (600, 900), "wide": (920, 430), "hero": (1920, 620), "logo": (1280, 400), "icon": (256, 256)}

THEMES = {
    "bnet": {"title": "Battle.net", "subtitle": "World of Warcraft: Forever",
             "bg": ((0.05, 0.10, 0.22), (0.02, 0.04, 0.10)), "accent": (0.20, 0.72, 1.00), "emblem": "orb"},
    "cf":   {"title": "CurseForge", "subtitle": "Addons for WoW Forever",
             "bg": ((0.16, 0.08, 0.04), (0.05, 0.03, 0.02)), "accent": (1.00, 0.52, 0.12), "emblem": "flame"},
    "app":  {"title": "DeckForever", "subtitle": "WoW Forever on Steam Deck",
             "bg": ((0.10, 0.12, 0.26), (0.03, 0.04, 0.10)), "accent": (0.96, 0.77, 0.26), "emblem": "shield"},
}


def available():
    try:
        import cairo  # noqa: F401
        return True
    except ImportError:
        return False


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _emblem(cr, kind, cx, cy, size, accent):
    """A simple geometric mark centred at (cx, cy), `size` = overall diameter."""
    r = size / 2
    cr.save()
    cr.set_line_width(max(2.0, size * 0.06))
    cr.set_source_rgb(*accent)
    if kind == "orb":
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.arc(cx, cy, r * 0.62, 0, 2 * math.pi)
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.35)
        cr.fill()
        cr.set_source_rgb(*accent)
        for a in (0.9, 2.2, 3.6, 5.0):
            cr.arc(cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62, size * 0.05, 0, 2 * math.pi)
            cr.fill()
    elif kind == "flame":
        cr.move_to(cx, cy - r)
        cr.curve_to(cx + r * 0.9, cy - r * 0.2, cx + r * 0.7, cy + r * 0.7, cx, cy + r)
        cr.curve_to(cx - r * 0.7, cy + r * 0.7, cx - r * 0.9, cy - r * 0.2, cx, cy - r)
        cr.close_path()
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.35)
        cr.fill_preserve()
        cr.set_source_rgb(*accent)
        cr.stroke()
        cr.move_to(cx, cy - r * 0.45)
        cr.curve_to(cx + r * 0.4, cy, cx + r * 0.3, cy + r * 0.5, cx, cy + r * 0.6)
        cr.curve_to(cx - r * 0.3, cy + r * 0.5, cx - r * 0.4, cy, cx, cy - r * 0.45)
        cr.fill()
    else:  # shield
        cr.move_to(cx, cy - r)
        cr.line_to(cx + r * 0.85, cy - r * 0.55)
        cr.line_to(cx + r * 0.85, cy + r * 0.1)
        cr.curve_to(cx + r * 0.85, cy + r * 0.7, cx + r * 0.3, cy + r * 0.95, cx, cy + r)
        cr.curve_to(cx - r * 0.3, cy + r * 0.95, cx - r * 0.85, cy + r * 0.7, cx - r * 0.85, cy + r * 0.1)
        cr.line_to(cx - r * 0.85, cy - r * 0.55)
        cr.close_path()
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.25)
        cr.fill_preserve()
        cr.set_source_rgb(*accent)
        cr.stroke()
        cr.select_font_face("DejaVu Sans", 0, 1)
        cr.set_font_size(size * 0.42)
        ext = cr.text_extents("DF")
        cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + ext.height / 2 - size * 0.02)
        cr.show_text("DF")
    cr.restore()


def _text(cr, text, x, y, size, rgb, bold=True, align="left", max_w=None):
    import cairo
    cr.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    ext = cr.text_extents(text)
    while max_w and ext.width > max_w and size > 8:
        size *= 0.92
        cr.set_font_size(size)
        ext = cr.text_extents(text)
    if align == "center":
        x = x - ext.width / 2 - ext.x_bearing
    cr.set_source_rgb(*rgb)
    cr.move_to(x, y)
    cr.show_text(text)
    return ext


def render(kind, theme, path):
    """Render one artwork `kind` (see SIZES) for `theme` (a THEMES entry) to a PNG at `path`."""
    import cairo
    w, h = SIZES[kind]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    accent = theme["accent"]
    white = (0.97, 0.97, 0.98)
    if kind != "logo":
        grad = cairo.LinearGradient(0, 0, w * 0.3, h)
        grad.add_color_stop_rgb(0, *theme["bg"][0])
        grad.add_color_stop_rgb(1, *theme["bg"][1])
        cr.set_source(grad)
        cr.paint()
        # soft accent glow top-right
        glow = cairo.RadialGradient(w * 0.85, h * 0.15, 0, w * 0.85, h * 0.15, max(w, h) * 0.6)
        glow.add_color_stop_rgba(0, accent[0], accent[1], accent[2], 0.28)
        glow.add_color_stop_rgba(1, accent[0], accent[1], accent[2], 0.0)
        cr.set_source(glow)
        cr.paint()
        # accent bar at the bottom
        cr.set_source_rgb(*accent)
        cr.rectangle(0, h - max(4, h * 0.012), w, max(4, h * 0.012))
        cr.fill()

    if kind == "p":
        _emblem(cr, theme["emblem"], w / 2, h * 0.40, w * 0.52, accent)
        _text(cr, theme["title"], w / 2, h * 0.76, w * 0.11, white, align="center", max_w=w * 0.9)
        _text(cr, theme["subtitle"], w / 2, h * 0.83, w * 0.05, (0.75, 0.78, 0.85), bold=False, align="center", max_w=w * 0.9)
    elif kind == "wide":
        _emblem(cr, theme["emblem"], w * 0.2, h / 2, h * 0.62, accent)
        _text(cr, theme["title"], w * 0.38, h * 0.52, h * 0.22, white, max_w=w * 0.58)
        _text(cr, theme["subtitle"], w * 0.38, h * 0.70, h * 0.10, (0.75, 0.78, 0.85), bold=False, max_w=w * 0.58)
    elif kind == "hero":
        _emblem(cr, theme["emblem"], w * 0.14, h / 2, h * 0.64, accent)
        cr.set_source_rgba(1, 1, 1, 0.06)
        _rounded_rect(cr, w * 0.26, h * 0.22, w * 0.5, h * 0.56, 24)
        cr.fill()
    elif kind == "logo":
        _emblem(cr, theme["emblem"], h * 0.5, h / 2, h * 0.8, accent)
        _text(cr, theme["title"], h * 1.05, h * 0.60, h * 0.42, white, max_w=w - h * 1.1)
    elif kind == "icon":
        _rounded_rect(cr, 0, 0, w, h, w * 0.18)
        cr.set_source_rgb(*theme["bg"][0])
        cr.fill()
        _emblem(cr, theme["emblem"], w / 2, h / 2, w * 0.68, accent)
    surf.write_to_png(path)
    return path


def render_set(theme_key, grid_dir, appid, renderer=render):
    """Write the four grid images plus the icon for one shortcut. Returns {kind: path}."""
    theme = THEMES[theme_key]
    os.makedirs(grid_dir, exist_ok=True)
    names = {"p": f"{appid}p.png", "wide": f"{appid}.png", "hero": f"{appid}_hero.png",
             "logo": f"{appid}_logo.png", "icon": f"{appid}_icon.png"}
    out = {}
    for kind, fn in names.items():
        path = os.path.join(grid_dir, fn)
        renderer(kind, theme, path)
        out[kind] = path
    return out
