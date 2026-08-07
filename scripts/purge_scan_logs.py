#!/usr/bin/env python3
"""Purga de scan_logs antiguos (retencion configurable, default 12 meses).

Uso:
    python purge_scan_logs.py [--meses N] [--dry-run]

Se conecta con la misma DATABASE_URL de la app (qr_adm.env).
Los registros mas antiguos que N meses se eliminan en lotes para no
bloquear la tabla. Corre via cron mensual (ver cron_* en este repo).
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

def load_env(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    load_env(os.path.join(here, "..", "qr_adm.env"))

    from app import create_app
    from app.models import ScanLog
    from app import db

    app = create_app("production")
    with app.app_context():
        cutoff = datetime.now(timezone.utc) - timedelta(days=30 * args.meses)
        total = ScanLog.query.filter(ScanLog.scanned_at < cutoff).count()
        print(f"scan_logs anteriores a {cutoff:%Y-%m-%d}: {total}")
        if args.dry_run or total == 0:
            print("dry-run: no se borra nada" if args.dry_run else "nada que purgar")
            return
        # Lotes de 5000 para no saturar
        deleted = 0
        while True:
            batch = ScanLog.query.filter(ScanLog.scanned_at < cutoff).limit(5000).all()
            if not batch:
                break
            ids = [s.id for s in batch]
            n = ScanLog.query.filter(ScanLog.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
            deleted += n
            print(f"  lote: {n} eliminados (total {deleted})")
        print(f"PURGA COMPLETA: {deleted} registros eliminados")

if __name__ == "__main__":
    main()
