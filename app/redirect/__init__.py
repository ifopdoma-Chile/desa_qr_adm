import requests
from flask import Blueprint, redirect, request, abort, render_template
from datetime import datetime, timezone
from app import db
from app.models import QRCode, ScanLog
from app.utils import detect_proxy, parse_device_info, detect_conditional_redirect

redirect_bp = Blueprint('redirect', __name__)

GEO_CACHE = {}


def get_geo_from_ip(ip):
    if not ip or ip.startswith(('10.', '172.16.', '192.168.', '127.')):
        return None, None, None
    if ip in GEO_CACHE:
        return GEO_CACHE[ip]
    try:
        r = requests.get(f'https://ip-api.com/json/{ip}?fields=country,city,region', timeout=3)
        if r.ok:
            data = r.json()
            result = (data.get('country'), data.get('city'), data.get('region'))
            GEO_CACHE[ip] = result
            return result
    except Exception:
        pass
    return None, None, None


@redirect_bp.route('/<slug>')
def handle_redirect(slug):
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
    country, city, region = get_geo_from_ip(ip)

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
