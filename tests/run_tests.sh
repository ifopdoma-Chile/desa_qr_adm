#!/usr/bin/env bash
# Ejecuta la suite de tests de QR Admin contra el entorno local.
# Requiere: variables de la app en /Data2/qr_adm/qr_adm.env (produccion)
# o configuracion equivalente. NO toca datos reales: crea y borra
# registros de prueba (prefijo prueba_*).
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"
PY=$(command -v /Data/anaconda3/bin/python || command -v python3)
echo "== Test funcional =="
"$PY" tests/test_funcional.py
echo "== Test de paginas =="
"$PY" tests/test_paginas.py
echo "== TODO VERDE =="
