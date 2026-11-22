"""Genera index.html: el panel de control de todos los canales automatizados.

Lee config.json y consulta:
- GitHub Actions (GH_PAT): última ejecución de cada robot y minutos consumidos este mes.
- YouTube Data API v3 (YT_API_KEY, solo clave pública): suscriptores, vistas y últimos 5 videos.
Sin GH_PAT o sin YT_API_KEY el panel se genera igual y muestra qué falta.
Python solo reúne datos y los incrusta en plantilla.html; las tarjetas las dibuja el navegador, así el editor de
canales de la propia página (localStorage) se ve reflejado al instante.

python actualizar_dashboard.py              escribe index.html
python actualizar_dashboard.py salida.html  escribe en otra ruta
Solo usa la biblioteca estándar: no hay requirements.txt.
"""
import calendar
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent


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
        raise RuntimeError(f"HTTP {e.code}: {motivo or e.reason}") from None


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


def fecha(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def minutos_facturables(runs):
    # shortcut: usa la duración de la ejecución (run_started_at → updated_at) en vez de pedir los jobs uno a uno;
    # vale porque cada robot tiene un solo job. Si algún workflow pasa a tener varios jobs, sumar /runs/{id}/jobs.
    return sum(math.ceil((fecha(r["updated_at"]) - fecha(r["run_started_at"])).total_seconds() / 60)
               for r in runs if r.get("status") == "completed" and r.get("run_started_at"))


def datos_github(canal, ahora):
    if not secreto("GH_PAT"):
        return {"error": "Falta GH_PAT"}
    # config.json se edita a mano desde el navegador: estos valores acaban dentro de la URL de la API
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", canal.get("repo", "")):
        return {"error": "Repositorio vacío o no válido (formato usuario/repo)"}
    if not re.fullmatch(r"[\w.-]+\.ya?ml", canal.get("workflow", "")):
        return {"error": "Workflow vacío o no válido (nombre del .yml)"}
    ruta = f"/repos/{canal['repo']}/actions/workflows/{canal['workflow']}/runs"
    base = f"{ruta}?per_page=100&created=%3E%3D{ahora:%Y-%m-01}"
    runs, pagina = [], 1
    while True:
        lote = github(f"{base}&page={pagina}")["workflow_runs"]
        runs += lote
        if len(lote) < 100:
            break
        pagina += 1
    # mes recién empezado: muestra igualmente la última ejecución conocida
    ultima = runs[0] if runs else next(iter(github(f"{ruta}?per_page=1")["workflow_runs"]), None)
    usados = minutos_facturables(runs)
    dias_mes = calendar.monthrange(ahora.year, ahora.month)[1]
    return {
        "ultima": ultima and {k: ultima[k] for k in ("status", "conclusion", "html_url", "run_number", "created_at")},
        "minutos_mes": usados,
        "proyeccion": round(usados / ahora.day * dias_mes),
        "fallos_mes": sum(r.get("conclusion") == "failure" for r in runs),
        "ejecuciones_mes": len(runs),
    }


def datos_youtube(canal):
    if not secreto("YT_API_KEY"):
        return {"error": "Falta YT_API_KEY"}
    ident = canal.get("youtube", "").strip()
    if not ident:
        return {"error": "Falta el @handle del canal"}
    # ID de canal (UC + 22 caracteres) → id; cualquier otra cosa es un handle, que se envía sin la @
    filtro = {"id": ident} if re.fullmatch(r"UC[\w-]{22}", ident) else {"forHandle": ident.lstrip("@")}
    items = youtube("channels", part="snippet,statistics,contentDetails", **filtro).get("items", [])
    if not items:
        return {"error": f"Canal no encontrado: {ident}"}
    c = items[0]
    subidas = c["contentDetails"]["relatedPlaylists"]["uploads"]
    lista = youtube("playlistItems", part="contentDetails", playlistId=subidas, maxResults=5).get("items", [])
    ids = ",".join(i["contentDetails"]["videoId"] for i in lista)
    videos = youtube("videos", part="snippet,statistics", id=ids).get("items", []) if ids else []
    return {
        "url": f"https://www.youtube.com/channel/{c['id']}",
        "suscriptores": None if c["statistics"].get("hiddenSubscriberCount") else int(c["statistics"].get("subscriberCount", 0)),
        "vistas": int(c["statistics"].get("viewCount", 0)),
        "num_videos": int(c["statistics"].get("videoCount", 0)),
        "videos": [{"id": v["id"], "titulo": v["snippet"]["title"], "fecha": v["snippet"]["publishedAt"],
                    "vistas": int(v["statistics"].get("viewCount", 0))} for v in videos],
    }


def recoger(fuente, *args):
    """Un fallo de una API no tumba el panel: se muestra en la tarjeta de ese canal."""
    try:
        return fuente(*args)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def json_en_script(obj):
    """JSON seguro dentro de <script>: un título de video con '</script>' no puede romper la página."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def generar_html(config, datos, ahora):
    return ((RAIZ / "plantilla.html").read_text(encoding="utf-8")
            .replace("__CONFIG__", json_en_script(config))
            .replace("__DATOS__", json_en_script(datos))
            .replace("__GENERADO__", ahora.strftime("%Y-%m-%dT%H:%M:%SZ")))


def main():
    config = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    ahora = dt.datetime.now(dt.timezone.utc)
    datos = {c["nombre"]: {"gh": recoger(datos_github, c, ahora), "yt": recoger(datos_youtube, c)}
             for c in config["canales"] if not c.get("proximamente")}
    for nombre, d in datos.items():
        print(f"{nombre}: GitHub {d['gh'].get('error', 'ok')} | YouTube {d['yt'].get('error', 'ok')}")
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "index.html"
    destino.write_text(generar_html(config, datos, ahora), encoding="utf-8")
    print(f"Escrito {destino}")


if __name__ == "__main__":
    main()
