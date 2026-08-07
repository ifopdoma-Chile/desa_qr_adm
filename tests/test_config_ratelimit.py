# Test de configuracion admin (limite QR por usuario) y rate limit por usuario.
# Se ejecuta como parte de run_tests.sh (43 + estos = 47 tests).
import os, sys, re

for line in open("/Data2/qr_adm/qr_adm.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
os.environ["RATELIMIT_STORAGE_URL"] = "memory://"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from app import create_app, db
from app.models import User, Setting

app = create_app("production")
T = "prueba_conf_"
TOKEN_RE = re.compile(r'name="_csrf_token" value="([^"]+)"')

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  OK  {name}")
    else: fail += 1; print(f"  FAIL {name}")

with app.app_context():
    Setting.query.filter_by(key="qr_max_per_user").delete()
    db.session.commit()
    for u in User.query.filter(User.username.like(T + "%")).all():
        db.session.delete(u)
    db.session.commit()
    admin = User(username=T + "admin", email=T + "admin@ifop.cl", full_name="Test Admin",
                 role="admin", is_active_user=True, is_approved=True)
    admin.set_password("PruebaPass123!")
    viewer = User(username=T + "viewer", email=T + "viewer@ifop.cl", full_name="Test Viewer",
                  role="viewer", is_active_user=True, is_approved=True)
    viewer.set_password("PruebaPass123!")
    db.session.add_all([admin, viewer])
    db.session.commit()
    admin_id, viewer_id = admin.id, viewer.id

# ── Configuracion admin ──
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = str(admin_id); s["_fresh"] = True
    r = c.get("/admin/configuracion")
    check("GET /admin/configuracion admin -> 200", r.status_code == 200)
    html = r.get_data(as_text=True)
    m = TOKEN_RE.search(html)
    r2 = c.post("/admin/configuracion", data={"_csrf_token": m.group(1), "qr_max_per_user": "12"})
    check("POST configuracion=12 -> 302", r2.status_code == 302)
    with app.app_context():
        check("Setting guardado = 12", Setting.get("qr_max_per_user") == "12")
    r3 = c.post("/admin/configuracion", data={"qr_max_per_user": "99"})
    check("POST sin CSRF -> 400", r3.status_code == 400)
    r4 = c.post("/admin/configuracion", data={"_csrf_token": m.group(1), "qr_max_per_user": "abc"})
    check("POST valor invalido -> 302 (rechazado)", r4.status_code == 302)
    with app.app_context():
        check("Setting sigue en 12 (invalido no pisa)", Setting.get("qr_max_per_user") == "12")

with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = str(viewer_id); s["_fresh"] = True
    r = c.get("/admin/configuracion")
    check("GET /admin/configuracion viewer -> 302 (no autorizado)", r.status_code == 302)

# ── Rate limit por usuario (misma IP) ──
def fresh(ip):
    c = app.test_client()
    c.environ_base["REMOTE_ADDR"] = ip
    m = TOKEN_RE.search(c.get("/login").get_data(as_text=True))
    return c, m.group(1)

def intentos(ip, username, n=11):
    c, tok = fresh(ip)
    out = []
    for _ in range(n):
        out.append(c.post("/login", data={"_csrf_token": tok, "username": username,
                                          "password": "mala"}).status_code)
    return out

a = intentos("203.0.113.50", "rate_a@test.cl")
check("Usuario A: 10 fallidos + 11vo 429", a[:10] == [200]*10 and a[10] == 429)
b = intentos("203.0.113.50", "rate_b@test.cl")
check("Usuario B (misma IP): cuota propia 10 + 429", b[:10] == [200]*10 and b[10] == 429)
c, tok = fresh("203.0.113.50")
rc = c.post("/login", data={"_csrf_token": tok, "username": "rate_c@test.cl", "password": "mala"})
check("Usuario C (misma IP): 1er intento NO 429", rc.status_code == 200)

# ── Limpieza ──
with app.app_context():
    Setting.query.filter_by(key="qr_max_per_user").delete()
    db.session.commit()
    for u in User.query.filter(User.username.like(T + "%")).all():
        db.session.delete(u)
    db.session.commit()

print(f"\nRESULTADO: {ok} OK / {fail} FAIL")
sys.exit(1 if fail else 0)
