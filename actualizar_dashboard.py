"""Genera index.html: el panel ejecutivo de los canales automatizados y su histórico diario.

Lee config.json y consulta:
- GitHub Actions (GH_PAT): si la última ejecución de cada robot salió bien (punto verde/rojo).
- YouTube Data API v3 (YT_API_KEY, solo clave pública): suscriptores y vistas de cada canal.
Guarda en historico.json los suscriptores y vistas de cada canal por día (la última lectura del día manda);
el workflow lo sube al repo para que las curvas sean reales.
Python solo reúne datos y los incrusta en plantilla.html; el navegador dibuja KPIs y gráficos, así el editor de
canales de la propia página (localStorage) se ve reflejado al instante.

python actualizar_dashboard.py              escribe index.html
python actualizar_dashboard.py salida.html  escribe en otra ruta
Solo usa la biblioteca estándar: no hay requirements.txt.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent
HISTORICO = RAIZ / "historico.json"


def pedir_json(url, cabeceras=None):
    req = urllib.request.Request(url, headers={"User-Agent": "panel-canales", **(cabeceras or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # el motivo real (clave inválida, API no activada, token caducado...) viene en el cuerpo, no en el código HTTP;
        # no se incluye la URL porque lleva la API key
        try:
            cuerpo = json.load(e)
        except ValueError:
            cuerpo = {}
        err = cuerpo.get("error")
        motivo = err.get("message") if isinstance(err, dict) else cuerpo.get("message")
        # Google pone la causa concreta (SERVICE_DISABLED, API_KEY_SERVICE_BLOCKED...) en details[].reason
        razones = {d.get("reason") for d in (err.get("details") or []) + (err.get("errors") or [])} - {None} if isinstance(err, dict) else set()
        raise RuntimeError(f"HTTP {e.code}: {motivo or e.reason}" + (f" [{', '.join(sorted(razones))}]" if razones else "")) from None


def secreto(nombre):
    """Los secrets pegados a mano suelen traer un salto de línea o espacios al final."""
    return os.getenv(nombre, "").strip()


def github(ruta):
    cab = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if secreto("GH_PAT"):
        cab["Authorization"] = f"Bearer {secreto('GH_PAT')}"
    return pedir_json(f"https://api.github.com{ruta}", cab)


def youtube(recurso, **params):
    params["key"] = secreto("YT_API_KEY")
    return pedir_json(f"https://www.googleapis.com/youtube/v3/{recurso}?{urllib.parse.urlencode(params)}")


def datos_github(canal):
    if not secreto("GH_PAT"):
        return {"error": "Falta GH_PAT"}
    # config.json se edita a mano desde el navegador: estos valores acaban dentro de la URL de la API
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", canal.get("repo", "")):
        return {"error": "Repositorio vacío o no válido (formato usuario/repo)"}
    if not re.fullmatch(r"[\w.-]+\.ya?ml", canal.get("workflow", "")):
        return {"error": "Workflow vacío o no válido (nombre del .yml)"}
    runs = github(f"/repos/{canal['repo']}/actions/workflows/{canal['workflow']}/runs?per_page=1")["workflow_runs"]
    if not runs:
        return {"ultima": None}
    return {"ultima": {k: runs[0][k] for k in ("status", "conclusion", "html_url", "created_at")}}


def datos_youtube(canal):
    if not secreto("YT_API_KEY"):
        return {"error": "Falta YT_API_KEY"}
    ident = canal.get("youtube", "").strip()
    if not ident:
        return {"error": "Falta el @handle del canal"}
    # ID de canal (UC + 22 caracteres) → id; cualquier otra cosa es un handle, que se envía sin la @
    filtro = {"id": ident} if re.fullmatch(r"UC[\w-]{22}", ident) else {"forHandle": ident.lstrip("@")}
    items = youtube("channels", part="statistics", **filtro).get("items", [])
    if not items:
        return {"error": f"Canal no encontrado: {ident}"}
    s = items[0]["statistics"]
    return {
        "url": f"https://www.youtube.com/channel/{items[0]['id']}",
        "suscriptores": None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount", 0)),
        "vistas": int(s.get("viewCount", 0)),
    }


def recoger(fuente, *args):
    """Un fallo de una API no tumba el panel: se muestra en la tarjeta de ese canal."""
    try:
        return fuente(*args)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def anotar_historico(historico, datos, dia):
    """{fecha: {canal: {suscriptores, vistas}}}; solo canales con lectura válida, sin borrar lo ya guardado del día."""
    hoy = historico.setdefault(dia, {})
    for nombre, d in datos.items():
        if "error" not in d["yt"]:
            hoy[nombre] = {"suscriptores": d["yt"]["suscriptores"], "vistas": d["yt"]["vistas"]}
    if not hoy:
        del historico[dia]
    return dict(sorted(historico.items()))


def json_en_script(obj):
    """JSON seguro dentro de <script>: ningún texto con '</script>' puede romper la página."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def generar_html(config, datos, historico, ahora):
    return ((RAIZ / "plantilla.html").read_text(encoding="utf-8")
            .replace("__CONFIG__", json_en_script(config))
            .replace("__DATOS__", json_en_script(datos))
            .replace("__HISTORICO__", json_en_script(historico))
            .replace("__GENERADO__", ahora.strftime("%Y-%m-%dT%H:%M:%SZ")))


def main():
    config = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    ahora = dt.datetime.now(dt.timezone.utc)
    datos = {c["nombre"]: {"gh": recoger(datos_github, c), "yt": recoger(datos_youtube, c)}
             for c in config["canales"] if not c.get("proximamente")}
    for nombre, d in datos.items():
        print(f"{nombre}: GitHub {d['gh'].get('error', 'ok')} | YouTube {d['yt'].get('error', 'ok')}")
    historico = json.loads(HISTORICO.read_text(encoding="utf-8")) if HISTORICO.exists() else {}
    historico = anotar_historico(historico, datos, f"{ahora:%Y-%m-%d}")
    HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "index.html"
    destino.write_text(generar_html(config, datos, historico, ahora), encoding="utf-8")
    print(f"Escrito {destino} · histórico: {len(historico)} días")


if __name__ == "__main__":
    main()
