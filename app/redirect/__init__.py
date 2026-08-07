import requests
from flask import Blueprint, redirect, request, abort, render_template, current_app
from datetime import datetime, timezone
from app import db, limiter
from app.models import QRCode, ScanLog, Domain
from app.utils import detect_proxy, parse_device_info, detect_conditional_redirect

redirect_bp = Blueprint('redirect', __name__)

GEO_CACHE = {}

# Hosts propios de la app (la app vive bajo sapogis.ifop.cl/qr/)
APP_HOSTS = {
    'sapogis.ifop.cl', 'qr.ifop.cl', 'giscc.ifop.cl',
    'localhost', '127.0.0.1',
}


def _host_allowed(host):
    """Valida que el QR solo se sirva desde hosts autorizados:
    - hosts propios de la app (sapogis/qr.ifop.cl/giscc)
    - rangos internos (pruebas)
    - dominios activos configurados en la BD (multi-dominio)
    """
    host = (host or '').split(':')[0].strip().lower()
    if not host:
        return True
    if host in APP_HOSTS:
        return True
    if host.startswith(('10.', '172.16.', '172.17.', '172.18.', '172.19.',
                        '172.20.', '172.21.', '172.22.', '172.23.',
                        '172.24.', '172.25.', '172.26.', '172.27.',
                        '172.28.', '172.29.', '172.30.', '172.31.',
                        '192.168.', '127.')):
        return True
    return Domain.query.filter_by(domain=host, is_active=True).first() is not None


def get_geo_from_ip(ip):
    """Geo (pais, ciudad, region, lat, lon) con cache en memoria."""
    if not ip or ip.startswith(('10.', '172.16.', '192.168.', '127.')):
        return None, None, None, None, None
    if ip in GEO_CACHE:
        return GEO_CACHE[ip]
    try:
        r = requests.get(
            f'https://ip-api.com/json/{ip}?fields=country,city,region,lat,lon',
            timeout=3,
        )
        if r.ok:
            data = r.json()
            result = (
                data.get('country'), data.get('city'), data.get('region'),
                data.get('lat'), data.get('lon'),
            )
            GEO_CACHE[ip] = result
            return result
    except Exception:
        pass
    return None, None, None, None, None


@redirect_bp.route('/<slug>')
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_SCAN', '60/minute'))
def handle_redirect(slug):
    # Validacion de host: solo se sirve desde hosts autorizados
    if not _host_allowed(request.host):
        abort(404)

    qr = QRCode.query.filter_by(slug=slug, is_deleted=False).first()
    if not qr:
        abort(404)

    if not qr.is_active or qr.is_expired:
        if qr.inactive_redirect_url:
            return redirect(qr.inactive_redirect_url)
        return render_template('inactive.html', qr=qr), 410

    if qr.max_scans and qr.scan_count >= qr.max_scans:
        qr.is_active = False
        db.session.commit()
        if qr.inactive_redirect_url:
            return redirect(qr.inactive_redirect_url)
        return render_template('inactive.html', qr=qr), 410

    user_agent_str = request.headers.get('User-Agent', '')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()

    device_type, browser, os_name = parse_device_info(user_agent_str)
    is_proxy, proxy_type = detect_proxy(user_agent_str, ip)
    country, city, region, lat, lon = get_geo_from_ip(ip)

    target_url = detect_conditional_redirect(qr, device_type, user_agent_str)

    if not target_url:
        target_url = qr.get_qr_data()

    if qr.qr_type == QRCode.TYPE_URL and qr.content_url:
        target_url = qr.content_url

    scan = ScanLog(
        qr_id=qr.id,
        scanned_at=datetime.now(timezone.utc),
        ip_address=ip,
        user_agent=user_agent_str,
        device_type=device_type,
        browser=browser,
        os_name=os_name,
        country=country,
        city=city,
        region=region,
        latitude=lat,
        longitude=lon,
        is_proxy=is_proxy,
        proxy_type=proxy_type,
        redirect_url=target_url,
        hit_conditional=bool(detect_conditional_redirect(qr, device_type, user_agent_str)),
    )

    qr.scan_count = (qr.scan_count or 0) + 1
    db.session.add(scan)
    db.session.commit()

    if qr.qr_type in (QRCode.TYPE_TEXT, QRCode.TYPE_JSON):
        return render_template('show_content.html', qr=qr, data=target_url)
    if qr.qr_type == QRCode.TYPE_WIFI:
        return render_template('show_wifi.html', qr=qr)

    return redirect(target_url or '/')
