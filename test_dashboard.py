"""Autocomprobación sin red: python test_dashboard.py"""
import datetime as dt
import json
import os
import re
from pathlib import Path

import actualizar_dashboard as p

# Valores editados a mano en el navegador no llegan a la URL de la API si no tienen forma de repo/workflow.
os.environ["GH_PAT"] = "x"
assert "no válido" in p.datos_github({"repo": "a/b/../c", "workflow": "x.yml"})["error"]
assert "no válido" in p.datos_github({"repo": "a/b", "workflow": "x.yml?evil=1"})["error"]

# Histórico: la última lectura del día manda, un canal con error no borra su dato previo y no se anotan días vacíos.
h = {"2026-11-21": {"A": {"suscriptores": 1, "vistas": 10}}}
ok = lambda s, v: {"gh": {}, "yt": {"suscriptores": s, "vistas": v}}
mal = {"gh": {}, "yt": {"error": "x"}}
h = p.anotar_historico(h, {"A": ok(2, 20), "B": mal}, "2026-11-22")
h = p.anotar_historico(h, {"A": mal, "B": ok(5, 50)}, "2026-11-22")
assert h == {"2026-11-21": {"A": {"suscriptores": 1, "vistas": 10}},
             "2026-11-22": {"A": {"suscriptores": 2, "vistas": 20}, "B": {"suscriptores": 5, "vistas": 50}}}, h
assert "2026-11-23" not in p.anotar_historico(h, {"A": mal}, "2026-11-23")
assert list(p.anotar_historico({"2026-11-23": {}, "2026-11-01": {"A": {}}}, {"A": ok(1, 1)}, "2026-11-15")) == \
    ["2026-11-01", "2026-11-15", "2026-11-23"]

# Retención: se suma al dato del día sin pisar suscriptores/vistas, y sin Analytics no se anota nada nuevo.
r = p.anotar_historico({}, {"A": ok(1, 1)}, "d")
r = p.anotar_historico(r, {"A": {"yt": {"error": "x"}, "an": {"retencion": 41.5}}}, "d")
assert r == {"d": {"A": {"suscriptores": 1, "vistas": 1, "retencion": 41.5}}}, r
assert p.anotar_historico({}, {"A": {"yt": {"error": "x"}, "an": {"retencion": None}}}, "d") == {}

# Analytics sin secreto o sin token para ese canal: respaldo limpio, sin tocar la red.
os.environ.pop("YT_ANALYTICS_TOKENS_JSON", None)
assert p.datos_analytics({"nombre": "A"}, {"id": "UC"}, None) == {"error": "Analytics sin configurar"}
os.environ["YT_ANALYTICS_TOKENS_JSON"] = '{"B": {}}'
assert p.datos_analytics({"nombre": "A"}, {"id": "UC"}, None) == {"error": "Analytics sin configurar"}
os.environ["YT_ANALYTICS_TOKENS_JSON"] = "{roto"
assert "no es JSON" in p.datos_analytics({"nombre": "A"}, {"id": "UC"}, None)["error"]

# Duraciones ISO 8601 de YouTube.
assert [p.segundos(x) for x in ("PT45S", "PT1M5S", "PT1H0M2S", "P1DT1S", "P0D", "PT", "")] == [45, 65, 3602, 86401, 0, None, None]

# Render: un texto con </script> no puede cerrar los bloques de datos; config, datos e histórico vuelven intactos.
config = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
malo = "</script><script>alert(1)</script>"
datos = {"Archivo Cero": {"gh": {"error": malo}, "yt": {"error": "Falta YT_API_KEY"}}}
salida = p.generar_html(config, datos, h, dt.datetime(2026, 11, 22, tzinfo=dt.timezone.utc))
assert malo not in salida and "__" not in re.sub(r"<script.*?</script>", "", salida, flags=re.S)
bloque = lambda i: json.loads(re.search(rf'id="{i}">(.*?)</script>', salida, re.S).group(1))
assert bloque("config-json") == config and bloque("datos-json") == datos and bloque("historico-json") == h
print("OK")
