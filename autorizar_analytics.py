"""Crea/renueva el secret YT_ANALYTICS_TOKENS_JSON (scope yt-analytics.readonly) del panel.

python autorizar_analytics.py                  autoriza todos los canales de CLIENTES
python autorizar_analytics.py "Clear Ledger"   solo ese canal (los demás se conservan)

Por cada canal abre el navegador: entra con la cuenta de Google del canal y elige ese canal de YouTube
(si es un canal de marca, elígelo en «cuenta de marca»); si eliges otro, el script lo detecta y vuelve a preguntar.
Usa el cliente OAuth de cada robot, pero un token aparte: el TOKEN_JSON de los robots no se toca.
Los tokens se guardan en tokens_analytics.json (ignorado por git) y se suben con `gh secret set`.
Necesita google-auth-oauthlib (ya instalado para los robots) y gh con sesión iniciada.
"""
import json
import subprocess
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from actualizar_dashboard import pedir_json

RAIZ = Path(__file__).parent
ESCRITORIO = RAIZ.parent
CLIENTES = {  # nombre del canal en config.json → client secrets del robot (su proyecto de Google Cloud)
    "Archivo Cero": ESCRITORIO / "robot_videos" / "client_secrets.json",  # robotshorts-515415
    "Clear Ledger": ESCRITORIO / "clear_ledger" / "client_secret.json",   # clearledger-515513
}
# youtube.readonly: hace que Google pregunte qué canal (personal o de marca) y permite comprobar el elegido
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly", "https://www.googleapis.com/auth/youtube.readonly"]
LOCAL = RAIZ / "tokens_analytics.json"
CONFIG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
REPO = CONFIG["repo_panel"]
HANDLES = {c["nombre"]: c.get("youtube", "").lower() for c in CONFIG["canales"]}


def autorizar(nombre):
    """Repite hasta que se elija el canal de config.json: un token de otro canal da 403 Forbidden en el panel."""
    while True:
        flujo = InstalledAppFlow.from_client_secrets_file(str(CLIENTES[nombre]), SCOPES)
        # prompt=consent: Google solo entrega refresh_token si se muestra la pantalla de permisos
        cred = flujo.run_local_server(port=0, prompt="consent select_account", access_type="offline",
                                      authorization_prompt_message="Abriendo el navegador: {url}",
                                      success_message=f"Listo ({nombre}). Ya puedes cerrar esta pestaña.")
        canal = (pedir_json("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                            {"Authorization": f"Bearer {cred.token}"}).get("items") or [{}])[0]
        elegido = canal.get("snippet", {}).get("customUrl", "").lower()
        if elegido and elegido in (HANDLES[nombre], "@" + HANDLES[nombre].lstrip("@")) or canal.get("id") == HANDLES[nombre]:
            return cred
        print(f"Has elegido {elegido or 'una cuenta sin canal'}, pero {nombre} es {HANDLES[nombre]}: vuelve a intentarlo "
              "y en «Elige una cuenta o una cuenta de marca» pulsa el canal correcto.")


def main():
    tokens = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    for nombre in sys.argv[1:] or CLIENTES:
        print(f"\n== {nombre}: inicia sesión con la cuenta de ese canal y elige el canal «{nombre}»")
        cred = autorizar(nombre)
        if not cred.refresh_token:
            sys.exit(f"{nombre}: Google no devolvió refresh_token; revoca el acceso en myaccount.google.com/permissions y repite")
        tokens[nombre] = {"client_id": cred.client_id, "client_secret": cred.client_secret, "refresh_token": cred.refresh_token}
        LOCAL.write_text(json.dumps(tokens, indent=1), encoding="utf-8")
    subprocess.run(["gh", "secret", "set", "YT_ANALYTICS_TOKENS_JSON", "-R", REPO],
                   input=json.dumps(tokens), text=True, check=True)
    print(f"\nSecret YT_ANALYTICS_TOKENS_JSON guardado en {REPO} con: {', '.join(tokens)}")


if __name__ == "__main__":
    main()
