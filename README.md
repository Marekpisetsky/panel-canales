# Panel de canales

Dashboard ejecutivo (GitHub Pages) de los canales automatizados: suscriptores y vistas de cada canal lado a lado,
retención media, estado del robot (punto verde/rojo), curvas diarias y últimos 5 videos por retención. Se regenera cada 6 h.

| Archivo | Qué hace |
|---|---|
| `config.json` | Canales: nombre, color, @handle de YouTube, repo y workflow del robot. Se edita desde el propio panel (**+ Añadir / Gestionar canales**). `cuenta_google`, `proyecto_gcp` y `horario` quedan solo como notas. |
| `historico.json` | Suscriptores, vistas y retención por día y canal. Lo escribe y sube el workflow; de aquí salen los gráficos. |
| `actualizar_dashboard.py` | Consulta GitHub Actions + YouTube, anota el histórico y escribe `index.html` (solo biblioteca estándar). |
| `plantilla.html` | Diseño del panel, editor de canales y gráficos (Chart.js). |
| `autorizar_analytics.py` | Renueva los tokens OAuth de Analytics y guarda el secret (abre el navegador). |
| `test_dashboard.py` | Autocomprobación sin red; el workflow la ejecuta antes de publicar. |
| `.github/workflows/panel.yml` | Cada 6 h (y en cada push) genera el HTML, lo despliega en Pages y guarda `historico.json`. |

Secrets del repo: `GH_PAT` (lectura de Actions en los repos de los robots), `YT_API_KEY` (YouTube Data API v3) y
`YT_ANALYTICS_TOKENS_JSON` (retención, YouTube Analytics API): `{"Nombre del canal": {"client_id", "client_secret",
"refresh_token"}}` con scope `yt-analytics.readonly`. Un canal sin entrada muestra la retención como «—».
Para renovarlos: `python autorizar_analytics.py` (abre el navegador por canal y guarda el secret).

## Vista previa local

```powershell
$env:GH_PAT = gh auth token; $env:YT_API_KEY = "TU_CLAVE"; python actualizar_dashboard.py; start index.html
```
Ojo: en local también se anota `historico.json`; no lo subas a mano, el workflow lo mantiene.
