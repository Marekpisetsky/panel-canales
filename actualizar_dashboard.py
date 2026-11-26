"""Genera index.html: el panel ejecutivo de los canales automatizados y su histórico diario.

Lee config.json y consulta:
- GitHub Actions (GH_PAT): si la última ejecución de cada robot salió bien (punto verde/rojo).
- YouTube Data API v3 (YT_API_KEY, solo clave pública): suscriptores, vistas y últimos 5 videos de cada canal.
- YouTube Analytics API (YT_ANALYTICS_TOKENS_JSON, OAuth yt-analytics.readonly): retención de los últimos 28 días.
  Formato: {"Nombre del canal": {"client_id", "client_secret", "refresh_token"}}; un canal sin token sale con "—".
Guarda en historico.json los suscriptores, vistas y retención de cada canal por día (la última lectura del día manda);
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


def pedir_json(url, cabeceras=None, formulario=None):
    datos = urllib.parse.urlencode(formulario).encode() if formulario else None  # con formulario es un POST
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": "panel-canales", **(cabeceras or {})})
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
    items = youtube("channels", part="statistics,contentDetails", **filtro).get("items", [])
    if not items:
        return {"error": f"Canal no encontrado: {ident}"}
    s = items[0]["statistics"]
    return {
        "url": f"https://www.youtube.com/channel/{items[0]['id']}",
        "suscriptores": None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount", 0)),
        "vistas": int(s.get("viewCount", 0)),
        "id": items[0]["id"],
        # no se mira videoCount: en canales nuevos tarda días en dejar de valer 0 aunque ya haya videos
        "videos": ultimos_videos(items[0]["contentDetails"]["relatedPlaylists"]["uploads"]),
    }


def ultimos_videos(lista_subidas, n=5):
    try:
        items = youtube("playlistItems", part="contentDetails", playlistId=lista_subidas, maxResults=n).get("items", [])
    except RuntimeError as e:
        if not str(e).startswith("HTTP 404"):
            raise
        items = []  # sin videos públicos la lista de subidas no existe (404 playlistNotFound)
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    vids = youtube("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", [])
    return sorted(({"id": v["id"], "titulo": v["snippet"]["title"], "fecha": v["snippet"]["publishedAt"],
                    "duracion": segundos(v["contentDetails"].get("duration", "")),
                    "vistas": int(v["statistics"].get("viewCount", 0)),
                    "likes": int(v["statistics"]["likeCount"]) if "likeCount" in v["statistics"] else None}
                   for v in vids), key=lambda v: v["fecha"], reverse=True)


def segundos(iso):
    """Duración ISO 8601 de YouTube (PT1H2M3S) → segundos; None si no se reconoce."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    return None if not m or not iso.strip("PT") else sum(int(n or 0) * k for n, k in zip(m.groups(), (86400, 3600, 60, 1)))


def datos_analytics(canal, yt, ahora):
    """Retención media del canal y de cada video en los últimos 28 días (Analytics va con ~2 días de retraso)."""
    if "error" in yt:
        return {"error": "Sin canal de YouTube"}
    try:
        cred = json.loads(secreto("YT_ANALYTICS_TOKENS_JSON") or "{}").get(canal["nombre"])
    except ValueError:
        return {"error": "YT_ANALYTICS_TOKENS_JSON no es JSON válido"}
    if not cred:
        return {"error": "Analytics sin configurar"}
    token = pedir_json("https://oauth2.googleapis.com/token", formulario={
        "grant_type": "refresh_token", **{k: cred[k] for k in ("client_id", "client_secret", "refresh_token")}})["access_token"]

    def informe(**params):
        params.update(ids=f"channel=={yt['id']}", startDate=f"{ahora - dt.timedelta(days=28):%Y-%m-%d}", endDate=f"{ahora:%Y-%m-%d}")
        r = pedir_json(f"https://youtubeanalytics.googleapis.com/v2/reports?{urllib.parse.urlencode(params)}",
                       {"Authorization": f"Bearer {token}"})
        cols = [c["name"] for c in r["columnHeaders"]]
        return [dict(zip(cols, fila)) for fila in r.get("rows") or []]

    total = (informe(metrics="views,averageViewPercentage,averageViewDuration") or [{}])[0]
    if not total.get("views"):  # sin vistas Google da 0 %, que parecería una retención real
        total = {}
    # un video sin vistas en los 28 días no aparece y queda sin retención
    por_video = {f["video"]: round(f["averageViewPercentage"], 1)
                 for f in informe(dimensions="video", metrics="views,averageViewPercentage", sort="-views", maxResults=200)}
    curvas = {}
    for v in yt["videos"]:
        if v["id"] not in por_video:
            continue  # sin vistas en 28 días no hay curva
        try:  # una curva que falle no se lleva la retención del canal
            # audienceWatchRatio: fracción de espectadores que sigue viendo en cada 1 % del video (>1 si se re-ve)
            puntos = informe(dimensions="elapsedVideoTimeRatio", metrics="audienceWatchRatio", filters=f"video=={v['id']}")
        except RuntimeError:
            continue
        if puntos:
            curvas[v["id"]] = [[f["elapsedVideoTimeRatio"], round(f["audienceWatchRatio"], 3)] for f in puntos]
    return {
        "curvas": curvas,
        "retencion": None if total.get("averageViewPercentage") is None else round(total["averageViewPercentage"], 1),
        "duracion": total.get("averageViewDuration"),
        "por_video": {v["id"]: por_video[v["id"]] for v in yt["videos"] if v["id"] in por_video},
    }


def recoger(fuente, *args):
    """Un fallo de una API no tumba el panel: se muestra en la tarjeta de ese canal."""
    try:
        return fuente(*args)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def anotar_historico(historico, datos, dia):
    """{fecha: {canal: {suscriptores, vistas, retencion}}}; solo lecturas válidas, sin borrar lo ya guardado del día."""
    hoy = historico.setdefault(dia, {})
    for nombre, d in datos.items():
        fila = {} if "error" in d["yt"] else {"suscriptores": d["yt"]["suscriptores"], "vistas": d["yt"]["vistas"]}
        if d.get("an", {}).get("retencion") is not None:
            fila["retencion"] = d["an"]["retencion"]
        if fila:
            hoy[nombre] = {**hoy.get(nombre, {}), **fila}
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
    datos = {}
    for c in config["canales"]:
        if not c.get("proximamente"):
            yt = recoger(datos_youtube, c)
            datos[c["nombre"]] = {"gh": recoger(datos_github, c), "yt": yt, "an": recoger(datos_analytics, c, yt, ahora)}
    for nombre, d in datos.items():
        print(f"{nombre}: GitHub {d['gh'].get('error', 'ok')} | YouTube {d['yt'].get('error', 'ok')} | "
              f"Analytics {d['an'].get('error', 'ok')}")
    historico = json.loads(HISTORICO.read_text(encoding="utf-8")) if HISTORICO.exists() else {}
    historico = anotar_historico(historico, datos, f"{ahora:%Y-%m-%d}")
    HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "index.html"
    destino.write_text(generar_html(config, datos, historico, ahora), encoding="utf-8")
    print(f"Escrito {destino} · histórico: {len(historico)} días")


if __name__ == "__main__":
    main()
