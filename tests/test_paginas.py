import os, sys, re
for line in open("/Data2/qr_adm/qr_adm.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from app import create_app, db
from app.models import User, QRCode

app = create_app("production")
T = "prueba_pages_"

with app.app_context():
    for u in User.query.filter(User.username.like(T + "%")).all():
        for k in list(u.api_keys):
            db.session.delete(k)
        db.session.delete(u)
    db.session.commit()
    u = User(username=T + "admin", email=T + "admin@ifop.cl", full_name="Test",
             role="admin", is_active_user=True, is_approved=True)
    u.set_password("PruebaPass123!")
    db.session.add(u)
    db.session.commit()
    uid = u.id

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  OK  {name}")
    else: fail += 1; print(f"  FAIL {name}")

with app.test_client() as c:
    html = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    c.post("/login", data={"_csrf_token": m.group(1), "username": T + "admin", "password": "PruebaPass123!"})

    pages = ["/admin/", "/admin/qr", "/admin/papelera", "/admin/tags", "/admin/dominios",
             "/admin/api-keys", "/admin/import-export", "/admin/usuarios",
             "/admin/usuarios/nuevo", "/admin/analytics", "/admin/auditoria", "/admin/api-docs",
             "/admin/qr/nuevo"]
    for p in pages:
        r = c.get(p)
        check(f"GET {p} -> {r.status_code}", r.status_code == 200)

    # qr_detail con un QR real
    with app.app_context():
        q = QRCode.query.filter_by(is_deleted=False).first()
    if q:
        r = c.get(f"/admin/qr/{q.id}")
        check(f"qr_detail {q.slug} -> {r.status_code}", r.status_code == 200)
        body = r.get_data(as_text=True)
        check("qr_detail tiene boton Exportar CSV", "Exportar CSV" in body)

    # logout
    r = c.get("/logout")
    check("logout -> 302", r.status_code == 302)

    with app.app_context():
        for u in User.query.filter(User.username.like(T + "%")).all():
            for k in list(u.api_keys):
                db.session.delete(k)
            db.session.delete(u)
        db.session.commit()

print(f"\nRESULTADO: {ok} OK / {fail} FAIL")
sys.exit(1 if fail else 0)
