import io
import re
import math
import hashlib
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer,
    GappedSquareModuleDrawer,
    CircleModuleDrawer,
    RoundedModuleDrawer,
    VerticalBarsDrawer,
    HorizontalBarsDrawer,
)
from qrcode.image.styles.moduledrawers.base import QRModuleDrawer as ModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
from user_agents import parse as ua_parse
from app.models import ConditionalRedirect


# ─── Custom Module Drawers ───

class DiamondModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        d.polygon([(cx, y1), (x2, cy), (cx, y2), (x1, cy)], fill=0)


class StarModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        r1 = (x2 - x1) // 2
        r2 = max(r1 // 2, 1)
        d.polygon([
            (cx, y1), (cx + r2, cy - r2), (x2, cy),
            (cx + r2, cy + r2), (cx, y2),
            (cx - r2, cy + r2), (x1, cy),
            (cx - r2, cy - r2),
        ], fill=0)


class CrossModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        m = min(x2 - x1, y2 - y1) // 4
        d.rectangle([x1 + m, y1, x2 - m, y2], fill=0)
        d.rectangle([x1, y1 + m, x2, y2 - m], fill=0)


class DropModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        r = (x2 - x1) // 2
        d.ellipse([cx - r, cy, cx + r, cy + r], fill=0)
        d.polygon([(cx - r, cy), (cx + r, cy), (cx, y1)], fill=0)


class TriangleModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx = (x1 + x2) // 2
        d.polygon([(cx, y1), (x2, y2), (x1, y2)], fill=0)


class CloverModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        r = max(min(x2 - x1, y2 - y1) // 4, 1)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
        off = r + 1
        d.ellipse([cx - off - r, cy - r, cx - off + r, cy + r], fill=0)
        d.ellipse([cx + off - r, cy - r, cx + off + r, cy + r], fill=0)
        d.ellipse([cx - r, cy - off - r, cx + r, cy - off + r], fill=0)
        d.ellipse([cx - r, cy + off - r, cx + r, cy + off + r], fill=0)


class ShieldModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx = (x1 + x2) // 2
        split = y1 + (y2 - y1) * 2 // 3
        d.rectangle([x1, y1, x2, split], fill=0)
        d.polygon([(x1, split), (x2, split), (cx, y2)], fill=0)


class CloudModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        r = max(min(x2 - x1, y2 - y1) // 3, 1)
        d.ellipse([cx - r, cy - r//2, cx + r, cy + r], fill=0)
        d.ellipse([cx - r - r//2, cy, cx - r + r//2, cy + r], fill=0)
        d.ellipse([cx + r - r//2, cy, cx + r + r//2, cy + r], fill=0)
        d.ellipse([cx - r//2, cy - r, cx + r//2, cy], fill=0)
        d.rectangle([cx - r - r//2, cy + r//2, cx + r + r//2, cy + r], fill=0)


class FishModuleDrawer(ModuleDrawer):
    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        d = ImageDraw.Draw(self.img)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        w, h = x2 - x1, y2 - y1

        body_r = min(w, h) // 3
        body_cx = cx + w // 8
        by, bh = cy - body_r, body_r * 2
        d.ellipse([body_cx - body_r, by, body_cx + body_r, by + bh], fill=0)

        tx = body_cx + body_r
        tl = max(w // 3, 1)
        d.polygon([(tx, cy - body_r // 2), (tx + tl, cy), (tx, cy + body_r // 2)], fill=0)

        snout = max(w // 5, 1)
        body_left = body_cx - body_r
        d.polygon([(body_left, cy - h // 4), (body_left - snout, cy), (body_left, cy + h // 4)], fill=0)

        if w >= 10:
            er = max(w // 12, 1)
            d.ellipse([cx - w // 4 - er, cy - h // 4 - er,
                       cx - w // 4 + er, cy - h // 4 + er], fill=255)


OUTER_SHAPE_PADDING = 4


def apply_outer_shape(img, shape, size):
    if shape == 'square' or not shape:
        return img

    s = min(size, img.width, img.height)
    mask = Image.new('L', (s, s), 0)
    d = ImageDraw.Draw(mask)
    p = OUTER_SHAPE_PADDING

    if shape == 'circle':
        d.ellipse([p, p, s - p - 1, s - p - 1], fill=255)

    elif shape == 'rounded-rect':
        r = s // 5
        d.rounded_rectangle([p, p, s - p - 1, s - p - 1], radius=r, fill=255)

    elif shape == 'heart':
        cx, cy = s // 2, s // 3
        r = s // 4
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        d.ellipse([cx, cy - r, cx + r * 2, cy + r], fill=255)
        d.polygon([
            (cx - r, cy + r // 2),
            (cx + r * 2, cy + r // 2),
            (cx + r // 2, s - p),
        ], fill=255)

    elif shape == 'cloud':
        cx, cy = s // 2, s // 2
        r = s // 5
        d.ellipse([cx - r, cy - r // 2, cx + r, cy + r], fill=255)
        d.ellipse([cx - r - r // 2, cy, cx - r + r // 2, cy + r], fill=255)
        d.ellipse([cx + r - r // 2, cy, cx + r + r // 2, cy + r], fill=255)
        d.ellipse([cx - r // 2, cy - r, cx + r // 2, cy], fill=255)
        d.rectangle([cx - r - r // 2, cy + r // 2, cx + r + r // 2, cy + r], fill=255)
        d.ellipse([cx - r // 2, cy - r * 2 // 3, cx + r // 2, cy], fill=255)

    elif shape == 'fish':
        cx, cy = s // 2, s // 2
        m = s // 2 - p - 1

        d.polygon([
            (cx - m, cy),                                 # 0  nose
            (cx - int(m * 0.72), cy - int(m * 0.32)),     # 1  top head
            (cx - int(m * 0.15), cy - int(m * 0.30)),     # 2  body top
            (cx + int(m * 0.08), cy - int(m * 0.42)),     # 3  dorsal peak
            (cx + int(m * 0.30), cy - int(m * 0.24)),     # 4  back slope
            (cx + int(m * 0.55), cy - int(m * 0.20)),     # 5  tail base top
            (cx + int(m * 0.78), cy - int(m * 0.38)),     # 6  upper tail
            (cx + int(m * 0.82), cy),                     # 7  tail center
            (cx + int(m * 0.78), cy + int(m * 0.38)),     # 8  lower tail
            (cx + int(m * 0.55), cy + int(m * 0.20)),     # 9  tail base bot
            (cx + int(m * 0.22), cy + int(m * 0.20)),     # 10 belly
            (cx - int(m * 0.40), cy + int(m * 0.26)),     # 11 bottom head
            (cx - int(m * 0.72), cy + int(m * 0.20)),     # 12 lower jaw
        ], fill=255)

        eye_r = max(int(m * 0.05), 2)
        d.ellipse([
            cx - int(m * 0.42) - eye_r, cy - int(m * 0.06) - eye_r,
            cx - int(m * 0.42) + eye_r, cy - int(m * 0.06) + eye_r,
        ], fill=255)

    elif shape == 'diamond':
        d.polygon([
            (s // 2, p), (s - p - 1, s // 2),
            (s // 2, s - p - 1), (p, s // 2),
        ], fill=255)

    elif shape == 'shield':
        split = s * 3 // 5
        d.rectangle([p, p, s - p - 1, split], fill=255)
        d.polygon([
            (p, split), (s - p - 1, split),
            (s // 2, s - p - 1),
        ], fill=255)

    elif shape == 'drop':
        cx, cy = s // 2, s // 2
        r = s // 3
        d.ellipse([cx - r, cy, cx + r, cy + r], fill=255)
        d.polygon([(cx - r, cy), (cx + r, cy), (cx, p)], fill=255)

    elif shape == 'leaf':
        cx, cy = s // 2, s // 2
        rx, ry = s // 2 - p, s // 2 - p
        d.pieslice([cx - rx, cy - ry, cx + rx, cy + ry], 45, 135, fill=255)
        d.pieslice([cx - rx, cy - ry, cx + rx, cy + ry], 225, 315, fill=255)
        d.polygon([
            (cx - rx, cy), (cx, cy - ry),
            (cx + rx, cy), (cx, cy + ry),
        ], fill=255)

    elif shape == 'star':
        cx, cy = s // 2, s // 2
        r_outer = s // 2 - p
        r_inner = r_outer // 2
        pts = []
        for i in range(10):
            angle = math.radians(i * 36 - 90)
            r = r_outer if i % 2 == 0 else r_inner
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        d.polygon(pts, fill=255)

    result = Image.new('RGBA', (s, s), (255, 255, 255, 0))
    result.paste(img.crop((0, 0, s, s)), (0, 0), mask)
    return result


MODULE_DRAWERS = {
    'square': SquareModuleDrawer,
    'gapped-square': GappedSquareModuleDrawer,
    'circle': CircleModuleDrawer,
    'rounded': RoundedModuleDrawer,
    'vertical-bars': VerticalBarsDrawer,
    'horizontal-bars': HorizontalBarsDrawer,
    'diamond': DiamondModuleDrawer,
    'star': StarModuleDrawer,
    'cross': CrossModuleDrawer,
    'drop': DropModuleDrawer,
    'triangle': TriangleModuleDrawer,
    'clover': CloverModuleDrawer,
    'shield': ShieldModuleDrawer,
    'cloud': CloudModuleDrawer,
    'fish': FishModuleDrawer,
}


def generate_qr_image(data, size=400, logo_path=None,
                      fill_color='#000000', back_color='#ffffff',
                      style='square', outer_shape='square'):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H if logo_path else qrcode.constants.ERROR_CORRECT_M,
        box_size=max(1, size // 40),
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    drawer_cls = MODULE_DRAWERS.get(style, SquareModuleDrawer)
    fg = _hex_to_rgb(fill_color)
    bg = _hex_to_rgb(back_color)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer_cls(),
        color_mask=SolidFillColorMask(back_color=bg, front_color=fg),
    ).convert('RGB')

    if logo_path:
        try:
            logo = Image.open(logo_path)
            logo_max = int(size * 0.25)
            logo.thumbnail((logo_max, logo_max), Image.LANCZOS)
            pos = ((img.width - logo.width) // 2, (img.height - logo.height) // 2)
            img.paste(logo, pos)
        except Exception:
            pass

    img = apply_outer_shape(img, outer_shape, size)

    output = io.BytesIO()
    img.save(output, format='PNG', quality=95)
    output.seek(0)
    return output


def generate_qr_svg(data, fill_color='#000000', back_color='#ffffff'):
    import qrcode.image.svg
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    factory = qrcode.image.svg.SvgPathImage
    img = qr.make_image(fill_color=fill_color, back_color=back_color, image_factory=factory)
    output = io.BytesIO()
    img.save(output)
    output.seek(0)
    return output


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# ─── Proxy / Relay Detection ───
PROXY_PATTERNS = [
    (r'cloudflare', 'cloudflare'),
    (r'privaterelay|icloud', 'icloud_private_relay'),
    (r'vpn', 'vpn'),
    (r'proxy|proxify', 'generic_proxy'),
]

KNOWN_PROXY_UA_FRAGMENTS = [
    'cloudflare', 'privaterelay', 'icloud-private-relay',
    'Akamai', 'Fastly', 'Vercel',
]


def detect_proxy(user_agent_str, ip=None):
    if not user_agent_str:
        return False, None
    ua_lower = user_agent_str.lower()
    for pattern, ptype in PROXY_PATTERNS:
        if re.search(pattern, ua_lower):
            return True, ptype
    for frag in KNOWN_PROXY_UA_FRAGMENTS:
        if frag.lower() in ua_lower:
            return True, frag.lower().replace(' ', '_')
    return False, None


def detect_conditional_redirect(qr, device_type, user_agent_str):
    if not qr.conditional_redirects.count():
        return None
    redirects = qr.conditional_redirects.filter_by(is_active=True).order_by(
        ConditionalRedirect.priority.desc()
    ).all()
    ua_lower = (user_agent_str or '').lower()
    for cr in redirects:
        if cr.device_type and cr.device_type != device_type:
            continue
        if cr.user_agent_pattern:
            if not re.search(cr.user_agent_pattern, ua_lower, re.IGNORECASE):
                continue
        return cr.target_url
    return None


def parse_device_info(user_agent_str):
    if not user_agent_str:
        return 'unknown', 'unknown', 'unknown'
    ua = ua_parse(user_agent_str)
    if ua.is_mobile:
        device = 'mobile'
    elif ua.is_tablet:
        device = 'tablet'
    elif ua.is_pc:
        device = 'desktop'
    elif ua.is_bot:
        device = 'bot'
    else:
        device = 'unknown'
    browser = ua.browser.family or 'unknown'
    os_name = ua.os.family or 'unknown'
    return device, browser, os_name
