import io
import re
import math
import os
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
from qrcode.image.styles.colormasks import (
    SolidFillColorMask,
    RadialGradiantColorMask,
    VerticalGradiantColorMask,
    HorizontalGradiantColorMask,
    SquareGradiantColorMask,
)
from PIL import Image, ImageDraw, ImageFont
from flask import current_app
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


# ─── Modulos custom premium (assets de Romano: pez, ola, escudo) ───
# Reemplazan SOLO modulos de datos. Finder patterns (ojos), timing y alignment
# quedan como cuadrados solidos para garantizar escaneabilidad (validado con zxing).


def is_function_module(r, c, n):
    """True si la celda (r,c) es un modulo de funcion (finder/timing/alignment).
    Los modulos de funcion NO deben ser reemplazados por formas custom."""
    # Finder patterns: 3 cuadrados 7x7 en las esquinas + separador 8x8
    if (r < 8 and c < 8) or (r < 8 and c >= n - 8) or (r >= n - 8 and c < 8):
        return True
    # Timing patterns: fila 6 / columna 6 (salvo dentro de finder)
    if (r == 6 and 8 <= c < n - 8) or (c == 6 and 8 <= r < n - 8):
        return True
    # Alignment patterns: para la version tipica (25x25 / 29x29) estan en:
    #   TL busca de esquina con su finder (4,4 a 6,6) y otros en cruce timing.
    # Regla generica: cruces donde fila y columna pertenecen a {n-7} dentro del interior.
    # Aproximamos como los centros de alineacion estandar: filas/cols = [6, n-7] (v2)
    alignment_positions = [6, n - 7] if n >= 25 else []
    for ar in alignment_positions:
        for ac in alignment_positions:
            if (4 <= r - ar <= 4) and (4 <= c - ac <= 4):
                # evitar solaparse con finder TL (el alignment (6,6) coincide con finder)
                if not (ar == 6 and ac == 6):
                    return True
    return False


class ImageModuleDrawer(ModuleDrawer):
    """Dibuja modulos de datos con la silueta de una imagen PNG (pez, ola, escudo).
    Los modulos de funcion se dibujan como cuadrados solidos.
    La silueta redimensionada se cachea por tamano de celda (clave: box_size)
    para que la generacion 4K no abra/resize el PNG por cada modulo."""

    def __init__(self, module_path=None, color=(15, 58, 117)):
        self.module_path = module_path
        self.color = color
        self._cache = {}
        self._matrix_n_cache = None

    def _module_for(self, box_size):
        """Silueta recoloreada + redimensionada para un box_size (cacheada)."""
        if box_size in self._cache:
            return self._cache[box_size]
        try:
            mod = Image.open(self.module_path).convert('RGBA')
            target = int(box_size * 1.05)
            mod = mod.resize((target, target), Image.LANCZOS)
            alpha = mod.split()[3]
            col_img = Image.new('RGBA', mod.size, (*self.color, 255))
            masked = Image.composite(col_img, Image.new('RGBA', mod.size, (0, 0, 0, 0)), alpha)
        except Exception:
            masked = None
        self._cache[box_size] = masked
        return masked

    def _matrix_n(self, box_size):
        """Tamano de matriz calculado una sola vez por imagen."""
        if self._matrix_n_cache is None:
            self._matrix_n_cache = _matrix_size(self.img, box_size)
        return self._matrix_n_cache

    def drawrect(self, box, is_black):
        if not is_black:
            return
        (x1, y1), (x2, y2) = box
        box_size = x2 - x1
        # Derivar row/col desde la posicion (asumiendo border=4)
        border = 4
        row = int(round(y1 / box_size)) - border
        col = int(round(x1 / box_size)) - border
        d = ImageDraw.Draw(self.img)
        if not self.module_path or is_function_module(row, col, self._matrix_n(box_size)):
            d.rectangle([x1, y1, x2, y2], fill=0)
            return
        masked = self._module_for(box_size)
        if masked is None:
            d.rectangle([x1, y1, x2, y2], fill=0)
            return
        target = masked.width
        ox = x1 + (box_size - target) // 2
        oy = y1 + (box_size - target) // 2
        self.img.paste(masked, (ox, oy), masked)


def _matrix_size(img, box_size):
    """Estima tamano de la matriz QR desde las dimensiones de la imagen."""
    try:
        w, h = img.size
        return int(round((min(w, h) / box_size)) - 8)
    except Exception:
        return 25



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
    'pez': lambda: ImageModuleDrawer(_module_path('qr_module_pez_1024.png')),
    'ola': lambda: ImageModuleDrawer(_module_path('qr_module_ola_1024.png')),
    'escudo': lambda: ImageModuleDrawer(_module_path('qr_module_escudo_1024.png')),
}

# Estilos que usan siluetas de imagen (se upscalean con LANCZOS para suavizar)
IMAGE_STYLES = frozenset({'pez', 'ola', 'escudo'})


def _module_path(filename):
    """Ruta absoluta de un modulo custom (assets de Romano en static/modules)."""
    return _asset_path('modules', filename)



COLOR_MASKS = {
    'none': SolidFillColorMask,
    'radial': RadialGradiantColorMask,
    'vertical': VerticalGradiantColorMask,
    'horizontal': HorizontalGradiantColorMask,
    'square': SquareGradiantColorMask,
}


def _build_color_mask(mask_name, fg, bg, gradient_to=None):
    """Construye el colormask segun el tipo de gradiente."""
    mask_name = mask_name or 'none'
    if mask_name == 'radial':
        return RadialGradiantColorMask(center_color=fg, edge_color=gradient_to or bg)
    if mask_name == 'vertical':
        return VerticalGradiantColorMask(top_color=fg, bottom_color=gradient_to or bg)
    if mask_name == 'horizontal':
        return HorizontalGradiantColorMask(left_color=fg, right_color=gradient_to or bg)
    if mask_name == 'square':
        return SquareGradiantColorMask(center_color=fg, edge_color=gradient_to or bg)
    return SolidFillColorMask(front_color=fg, back_color=bg)


def generate_qr_image(data, size=400, logo_path=None,
                      fill_color='#000000', back_color='#ffffff',
                      style='square', outer_shape='square',
                      gradient='none', gradient_to='#1954A2',
                      transparent_bg=False, sticker='none'):
    # Generar a resolucion eficiente y upscalar al final: un QR es binario,
    # el upscale no pierde escaneabilidad y evita 17M px nativos (39s+ en 4K).
    gen_size = min(size, 2048)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H if logo_path else qrcode.constants.ERROR_CORRECT_M,
        box_size=max(1, gen_size // 40),
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    drawer_entry = MODULE_DRAWERS.get(style, SquareModuleDrawer)
    try:
        drawer = drawer_entry()
    except TypeError:
        drawer = drawer_entry  # ya es instancia (lambda que devuelve instance)
    fg = _hex_to_rgb(fill_color)
    bg = _hex_to_rgb(back_color)
    gradient_to_rgb = _hex_to_rgb(gradient_to) if gradient_to else bg

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=_build_color_mask(gradient, fg, bg, gradient_to_rgb),
    )

    if transparent_bg:
        img = img.convert('RGBA')
        data_img = img.getdata()
        new_data = []
        for item in data_img:
            if item[0] == bg[0] and item[1] == bg[1] and item[2] == bg[2]:
                new_data.append((bg[0], bg[1], bg[2], 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
    else:
        img = img.convert('RGB')

    if logo_path:
        try:
            logo = Image.open(logo_path)
            if logo.mode in ('RGBA', 'LA') or (logo.mode == 'P' and 'transparency' in logo.info):
                logo = logo.convert('RGBA')
            else:
                logo = logo.convert('RGB')
            logo_max = int(gen_size * 0.25)
            logo.thumbnail((logo_max, logo_max), Image.LANCZOS)
            pos = ((img.width - logo.width) // 2, (img.height - logo.height) // 2)
            if img.mode == 'RGBA':
                img.paste(logo, pos, logo)
            else:
                img.paste(logo, pos)
        except Exception:
            pass

    img = apply_outer_shape(img, outer_shape, gen_size)

    if sticker and sticker != 'none':
        img = apply_sticker(img, sticker, gen_size, fill_color, back_color, logo_path)

    # Upscale final al tamano pedido (NEAREST mantiene bordes nitidos para
    # modulos cuadrados; LANCZOS suaviza siluetas de modulos imagen/marcos).
    if size > gen_size and img.width != size:
        resample = Image.LANCZOS if (style in IMAGE_STYLES or sticker != 'none') else Image.NEAREST
        img = img.resize((size, size), resample)

    output = io.BytesIO()
    img.save(output, format='PNG', quality=95)
    output.seek(0)
    return output


# ─── Envio por correo electronico ───

def send_qr_email(recipient, qr, app_base_url, subject=None):
    """Envia el QR por correo electronico usando SMTP configurado en la app.
    Retorna (bool, mensaje).
    """
    import smtplib
    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr
    from flask import current_app as app
    import io

    try:
        settings = app.config
        smtp_host = settings.get('MAIL_SERVER', 'smtp.gmail.com')
        smtp_port = settings.get('MAIL_PORT', 587)
        smtp_user = settings.get('MAIL_USERNAME', 'ifopdoma@gmail.com')
        smtp_pass = settings.get('MAIL_PASSWORD', '')
        sender = settings.get('MAIL_DEFAULT_SENDER', 'IFOP QR Manager <ifopdoma@gmail.com>')

        if not smtp_pass:
            return False, 'SMTP no configurado (falta MAIL_PASSWORD).'

        # Generar QR PNG
        logo_path = None
        if qr.logo_filename:
            lp = os.path.join(app.root_path, 'static', 'uploads', qr.logo_filename)
            if os.path.exists(lp):
                logo_path = lp

        qr_img = generate_qr_image(
            qr.get_qr_data(), size=1024, logo_path=logo_path,
            fill_color=qr.qr_fg_color or '#000000',
            back_color=qr.qr_bg_color or '#ffffff',
            style=qr.qr_style or 'square',
            outer_shape=qr.qr_outer_shape or 'square',
            gradient=qr.qr_gradient or 'none',
            gradient_to=qr.qr_gradient_to or '#1954A2',
            sticker=qr.qr_sticker or 'none',
            transparent_bg=bool(qr.qr_transparent_bg),
        )

        msg = MIMEMultipart('related')
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = subject or f'Codigo QR: {qr.title}'

        base_url = app_base_url.rstrip('/')
        qr_edit_url = f'{base_url}/admin/qr/{qr.id}'

        html = f'''
        <html><body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1954A2;">Codigo QR: {qr.title}</h2>
        <p><img src="cid:qr_image" alt="QR" style="max-width:500px;border:1px solid #ccc;border-radius:8px;"></p>
        <p><strong>Slug:</strong> <a href="{qr.full_url}">{qr.slug}</a></p>
        <p><strong>URL:</strong> <a href="{qr.full_url}">{qr.full_url}</a></p>
        <hr>
        <p style="font-size:0.85rem;color:#777;">Generado por IFOP QR Manager | <a href="{qr_edit_url}">Administrar</a></p>
        </body></html>'''

        msg_alt = MIMEMultipart('alternative')
        msg_alt.attach(MIMEText(f'Codigo QR: {qr.title}\nSlug: {qr.slug}\nURL: {qr.full_url}', 'plain', 'utf-8'))
        msg_alt.attach(MIMEText(html, 'html', 'utf-8'))
        msg.attach(msg_alt)

        qr_png = MIMEImage(qr_img.getvalue())
        qr_png.add_header('Content-ID', '<qr_image>')
        qr_png.add_header('Content-Disposition', 'inline', filename=f'{qr.slug}.png')
        msg.attach(qr_png)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(settings.get('MAIL_USERNAME', smtp_user), [recipient], msg.as_string())

        return True, 'Correo enviado exitosamente.'
    except Exception as e:
        return False, f'Error al enviar: {str(e)}'


def _load_font(size_px):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf',
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def apply_sticker(img, sticker, size, fg_hex='#000000', bg_hex='#ffffff', logo_path=None):
    """Agrega un marco/sticker alrededor del QR (estilo qrcodechimp)."""
    fg = _hex_to_rgb(fg_hex)
    bg = _hex_to_rgb(bg_hex)
    base = img if img.mode == 'RGBA' else img.convert('RGBA')
    qr_w, qr_h = base.size

    if sticker == 'classic':
        pad = max(qr_w // 8, 24)
        canvas = Image.new('RGBA', (qr_w + pad * 2, qr_h + pad * 2), (*bg, 255))
        canvas.paste(base, (pad, pad))
        d = ImageDraw.Draw(canvas)
        r = pad // 2
        d.rounded_rectangle([0, 0, canvas.width - 1, canvas.height - 1], radius=r,
                            outline=(*fg, 255), width=max(qr_w // 60, 4))
        return canvas

    if sticker == 'dots':
        pad = max(qr_w // 8, 24)
        canvas = Image.new('RGBA', (qr_w + pad * 2, qr_h + pad * 2), (*bg, 255))
        canvas.paste(base, (pad, pad))
        d = ImageDraw.Draw(canvas)
        dot_r = max(qr_w // 50, 3)
        step = max(qr_w // 18, 10)
        for x in range(pad // 2, canvas.width - pad // 2, step):
            d.ellipse([x - dot_r, pad // 3 - dot_r, x + dot_r, pad // 3 + dot_r], fill=(*fg, 255))
            d.ellipse([x - dot_r, canvas.height - pad // 3 - dot_r, x + dot_r, canvas.height - pad // 3 + dot_r], fill=(*fg, 255))
        for y in range(pad // 2, canvas.height - pad // 2, step):
            d.ellipse([pad // 3 - dot_r, y - dot_r, pad // 3 + dot_r, y + dot_r], fill=(*fg, 255))
            d.ellipse([canvas.width - pad // 3 - dot_r, y - dot_r, canvas.width - pad // 3 + dot_r, y + dot_r], fill=(*fg, 255))
        return canvas

    if sticker == 'cta':
        pad = max(qr_w // 10, 24)
        banner_h = max(qr_h // 6, 48)
        canvas = Image.new('RGBA', (qr_w + pad * 2, qr_h + pad * 2 + banner_h), (*bg, 255))
        canvas.paste(base, (pad, pad))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, canvas.height - banner_h, canvas.width, canvas.height], fill=(*fg, 255))
        font = _load_font(max(banner_h // 2, 18))
        text = 'ESCANEA AQUI'
        bbox = d.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        d.text(((canvas.width - tw) // 2, canvas.height - banner_h + (banner_h - th) // 2 - bbox[1]),
               text, fill=(*bg, 255), font=font)
        return canvas

    if sticker == 'ifop':
        pad = max(qr_w // 10, 24)
        banner_h = max(qr_h // 7, 56)
        canvas = Image.new('RGBA', (qr_w + pad * 2, qr_h + pad * 2 + banner_h), (*bg, 255))
        canvas.paste(base, (pad, pad))
        d = ImageDraw.Draw(canvas)
        azul_ifop = (25, 84, 162)  # #1954A2
        d.rectangle([0, 0, canvas.width, banner_h], fill=azul_ifop)
        d.rectangle([0, canvas.height - banner_h // 3, canvas.width, canvas.height], fill=azul_ifop)
        # Logo central en la franja superior si existe
        if logo_path:
            try:
                l = Image.open(logo_path).convert('RGBA')
                l.thumbnail((banner_h * 3, banner_h - 8), Image.LANCZOS)
                canvas.paste(l, ((canvas.width - l.width) // 2, (banner_h - l.height) // 2), l)
            except Exception:
                pass
        else:
            font = _load_font(max(banner_h // 3, 16))
            text = 'IFOP'
            bbox = d.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            d.text(((canvas.width - tw) // 2, (banner_h - th) // 2 - bbox[1]),
                   text, fill=(255, 255, 255, 255), font=font)
        return canvas

    if sticker == 'wave':
        pad = max(qr_w // 8, 24)
        banner_h = max(qr_h // 8, 44)
        canvas = Image.new('RGBA', (qr_w + pad * 2, qr_h + pad * 2 + banner_h), (*bg, 255))
        canvas.paste(base, (pad, pad))
        d = ImageDraw.Draw(canvas)
        azul = (25, 84, 162)
        celeste = (120, 180, 220)
        # olas superiores
        for i, (col, y0) in enumerate([(celeste, 0), (azul, banner_h // 2)]):
            pts = []
            w = canvas.width
            for x in range(0, w + 1, max(w // 40, 4)):
                yy = y0 + banner_h // 4 + int(8 * math.sin(x * math.pi * 2 / (w / 2.0)))
                pts.append((x, yy))
            pts += [(w, y0 + banner_h), (0, y0 + banner_h)]
            d.polygon(pts, fill=col)
        return canvas

    # ─── Marcos premium IFOP (assets de Romano) ───
    _FRAME_MAP = {
        'institucional': ('qr_frame_ifop_institucional_1024.png', 768, (512, 512)),
        'cta_ifop': ('qr_frame_ifop_cta_1024.png', 640, (512, 504)),
        'marino': ('qr_frame_ifop_marino_1024.png', 640, (512, 512)),
    }
    if sticker in _FRAME_MAP:
        frame_file, qr_size, center = _FRAME_MAP[sticker]
        frame_path = _asset_path('frames', frame_file)
        if frame_path and os.path.exists(frame_path):
            try:
                frame = Image.open(frame_path).convert('RGBA')
                # Forzar fondo blanco sobre el QR (no transparente) para contraste en el hueco
                qr_solid = Image.new('RGB', base.size, (255, 255, 255))
                qr_solid.paste(base, (0, 0), base if base.mode == 'RGBA' else None)
                qr_resized = qr_solid.resize((qr_size, qr_size), Image.LANCZOS)
                pos = (center[0] - qr_size // 2, center[1] - qr_size // 2)
                # El hueco del marco es transparente: el QR (fondo blanco) cubre el area
                frame.paste(qr_resized, pos)
                return frame
            except Exception as e:
                print('apply_sticker frame error:', e)

    return base


def _asset_path(subdir, filename):
    """Ruta de un asset (frames/modules). Funciona dentro y fuera de app context."""
    # El paquete app/ contiene static/<subdir>/ — la base es la carpeta app/
    here = os.path.dirname(os.path.abspath(__file__))  # .../app
    p = os.path.join(here, 'static', subdir, filename)
    if os.path.exists(p):
        return p
    try:
        from flask import current_app
        p = os.path.join(current_app.root_path, 'static', subdir, filename)
        if os.path.exists(p):
            return p
    except Exception:
        pass
    return None


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
