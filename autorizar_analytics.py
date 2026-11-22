"""Crea/renueva el secret YT_ANALYTICS_TOKENS_JSON (scope yt-analytics.readonly) del panel.

python autorizar_analytics.py                  autoriza todos los canales de CLIENTES
python autorizar_analytics.py "Clear Ledger"   solo ese canal (los demás se conservan)

Por cada canal abre el navegador: entra con la cuenta de Google del canal y elige ese canal de YouTube.
Usa el cliente OAuth de cada robot, pero un token aparte: el TOKEN_JSON de los robots no se toca.
Los tokens se guardan en tokens_analytics.json (ignorado por git) y se suben con `gh secret set`.
Necesita google-auth-oauthlib (ya instalado para los robots) y gh con sesión iniciada.
"""
import json
import subprocess
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

RAIZ = Path(__file__).parent
ESCRITORIO = RAIZ.parent
CLIENTES = {  # nombre del canal en config.json → client secrets del robot (su proyecto de Google Cloud)
    "Archivo Cero": ESCRITORIO / "robot_videos" / "client_secrets.json",  # robotshorts-515415
    "Clear Ledger": ESCRITORIO / "clear_ledger" / "client_secret.json",   # clearledger-515513
}
SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
LOCAL = RAIZ / "tokens_analytics.json"
REPO = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))["repo_panel"]


def main():
    tokens = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    for nombre in sys.argv[1:] or CLIENTES:
        print(f"\n== {nombre}: inicia sesión con la cuenta de ese canal y elige el canal «{nombre}»")
        flujo = InstalledAppFlow.from_client_secrets_file(str(CLIENTES[nombre]), [SCOPE])
        # prompt=consent: Google solo entrega refresh_token si se muestra la pantalla de permisos
        cred = flujo.run_local_server(port=0, prompt="consent", access_type="offline",
                                      authorization_prompt_message="Abriendo el navegador: {url}",
                                      success_message=f"Listo ({nombre}). Ya puedes cerrar esta pestaña.")
        if not cred.refresh_token:
            sys.exit(f"{nombre}: Google no devolvió refresh_token; revoca el acceso en myaccount.google.com/permissions y repite")
        tokens[nombre] = {"client_id": cred.client_id, "client_secret": cred.client_secret, "refresh_token": cred.refresh_token}
        LOCAL.write_text(json.dumps(tokens, indent=1), encoding="utf-8")
    subprocess.run(["gh", "secret", "set", "YT_ANALYTICS_TOKENS_JSON", "-R", REPO],
                   input=json.dumps(tokens), text=True, check=True)
    print(f"\nSecret YT_ANALYTICS_TOKENS_JSON guardado en {REPO} con: {', '.join(tokens)}")


if __name__ == "__main__":
    main()
