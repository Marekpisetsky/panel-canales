"""Autocomprobación sin red: python test_dashboard.py"""
import datetime as dt
import json
import os
import re
from pathlib import Path

import actualizar_dashboard as p

# Minutos: cada ejecución se redondea hacia arriba (como factura GitHub); las que siguen en curso no cuentan.
runs = [
    {"status": "completed", "run_started_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:20Z"},  # 1
    {"status": "completed", "run_started_at": "2026-11-01T13:00:00Z", "updated_at": "2026-11-01T13:13:01Z"},  # 14
    {"status": "in_progress", "run_started_at": "2026-11-01T14:00:00Z", "updated_at": "2026-11-01T14:30:00Z"},
]
assert p.minutos_facturables(runs) == 15, p.minutos_facturables(runs)

# Valores editados a mano en el navegador no llegan a la URL de la API si no tienen forma de repo/workflow.
os.environ["GH_PAT"] = "x"
ahora = dt.datetime(2026, 11, 22, tzinfo=dt.timezone.utc)
assert "no válido" in p.datos_github({"repo": "a/b/../c", "workflow": "x.yml"}, ahora)["error"]
assert "no válido" in p.datos_github({"repo": "a/b", "workflow": "x.yml?evil=1"}, ahora)["error"]

# Render: un título con </script> no puede cerrar el bloque de datos; config y datos vuelven intactos.
config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
malo = "</script><script>alert(1)</script>"
datos = {"Archivo Cero": {"gh": {"error": "Falta GH_PAT"}, "yt": {"videos": [{"titulo": malo}]}}}
salida = p.generar_html(config, datos, ahora)
assert malo not in salida and "__" not in re.sub(r"<script>.*?</script>", "", salida, flags=re.S).split("<body>")[1]
bloque = lambda i: json.loads(re.search(rf'id="{i}">(.*?)</script>', salida, re.S).group(1))
assert bloque("config-json") == config and bloque("datos-json") == datos
print("OK")
