import os, sys, re
# Cargar qr_adm.env manualmente (el archivo no es bash valido: espacios sin comillas)
for _line in open("/Data2/qr_adm/qr_adm.env"):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from app import create_app, db
from app.models import User, QRCode, ApiKey

app = create_app("production")
T = "prueba_csrf_"

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  OK  {name}")
    else: fail += 1; print(f"  FAIL {name}")

with app.app_context():
    for u in User.query.filter(User.username.like(T + "%")).all():
        for k in list(u.api_keys):
            db.session.delete(k)
        db.session.delete(u)
    db.session.commit()
    u = User(username=T + "admin", email=T + "admin@ifop.cl", full_name="Test Admin",
             role="admin", is_active_user=True, is_approved=True)
    u.set_password("PruebaPass123!")
    db.session.add(u); db.session.commit()
    uid = u.id
    print(f"Usuario de prueba: id={uid}")

with app.test_client() as c:
    r = c.get("/login"); check("GET /login 200", r.status_code == 200)
    r = c.post("/login", data={"_csrf_token": "x"})
    check("POST sin CSRF -> 400", r.status_code == 400)

    html = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    check("CSRF token en login", bool(m))
    if m:
        r = c.post("/login", data={"_csrf_token": m.group(1), "username": T + "admin", "password": "PruebaPass123!"})
        check("login OK -> 302", r.status_code == 302)

    r = c.get("/admin/"); check("GET /admin/ (dashboard) 200", r.status_code == 200)
    r = c.get("/admin/analytics"); check("GET /admin/analytics 200", r.status_code == 200)
    a = r.get_data(as_text=True)
    check("analytics tiene mapa+charts", "map-scans" in a and "chart.umd.min.js" in a)
    r = c.get("/admin/auditoria"); check("GET /admin/auditoria 200", r.status_code == 200)
    r = c.get("/admin/api-docs"); check("GET /admin/api-docs 200", r.status_code == 200)
    r = c.get("/admin/usuarios"); check("GET /admin/usuarios 200", r.status_code == 200)

    r = c.post(f"/admin/usuarios/{uid}/aprobar")
    check("POST admin sin CSRF -> 400", r.status_code == 400)

    html = c.get("/admin/usuarios").get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    check("CSRF token en usuarios", bool(m))
    if m:
        r = c.post(f"/admin/usuarios/{uid}/aprobar", data={"_csrf_token": m.group(1)})
        check("aprobar con CSRF -> 302", r.status_code == 302)

        r = c.post("/admin/qr/nuevo", data={
            "_csrf_token": m.group(1), "title": "Test QR CSRF", "qr_type": "url",
            "content_url": "https://www.ifop.cl", "is_active": "on",
        })
        check("crear QR con CSRF -> 302", r.status_code == 302)

    with app.app_context():
        q = QRCode.query.filter_by(title="Test QR CSRF").first()
    if q:
        r = c.get(f"/admin/qr/{q.id}/scans/export")
        check(f"export scans -> {r.status_code}", r.status_code == 200)
        check("export es CSV", "text/csv" in r.content_type)

    with app.app_context():
        raw = ApiKey.generate_key()
        k = ApiKey(user_id=uid, name="test-key", key_prefix=raw[:8], key_hash=ApiKey.hash_key(raw))
        db.session.add(k); db.session.commit()
    h = {"Authorization": f"Bearer {raw}"}
    r = c.get("/api/v1/qrs", headers=h)
    check(f"API list qrs -> {r.status_code}", r.status_code == 200)
    r = c.post("/api/v1/qrs", headers=h, json={"title": "API Test", "qr_type": "url", "content_url": "https://x.cl"})
    check(f"API create qr -> {r.status_code}", r.status_code == 201)
    r = c.post("/api/v1/qrs", headers=h, json={"title": "dup", "qr_type": "url", "slug": "api-test"})
    check("API create con slug explicito -> 201", r.status_code == 201)
    r = c.post("/api/v1/qrs", headers=h, json={"title": "dup2", "qr_type": "url", "slug": "api-test"})
    check("API slug duplicado -> 400", r.status_code == 400)
    r = c.post("/api/v1/qrs", headers=h, json={"title": "badtype", "qr_type": "hacker"})
    check("API qr_type invalido -> 400", r.status_code == 400)
    r = c.post("/api/v1/qrs", headers=h, json={"title": "badmax", "qr_type": "url", "max_scans": "abc"})
    check("API max_scans invalido -> 400", r.status_code == 400)
    r = c.get("/api/v1/qrs?per_page=99999", headers=h)
    check("API per_page tope -> 100", r.json.get("per_page") == 100)
    r = c.get("/api/v1/health")
    check("API health publico -> 200", r.status_code == 200)

    with app.app_context():
        q = QRCode.query.filter_by(title="API Test").first()
        slug = q.slug if q else "none"
    r = c.get(f"/temp-token/{slug}", headers=h)
    check(f"temp-token -> {r.status_code}", r.status_code == 200)
    tok = r.json.get("token") if r.status_code == 200 else None
    if tok:
        r = c.get(f"/{slug}/download?token={tok}", headers=h)
        check(f"download con token -> {r.status_code}", r.status_code == 200)
        r = c.get(f"/{slug}/download?token={tok}")
        check("token de un solo uso -> 401", r.status_code == 401)

    with app.app_context():
        for u in User.query.filter(User.username.like(T + "%")).all():
            for k in list(u.api_keys):
                db.session.delete(k)
            db.session.delete(u)
        db.session.commit()

print(f"\nRESULTADO: {ok} OK / {fail} FAIL")
sys.exit(1 if fail else 0)
