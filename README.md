# Panel de canales

Centro de control estático (GitHub Pages) de los robots de YouTube. Se regenera cada 6 h.

| Archivo | Qué hace |
|---|---|
| `config.json` | Canales: cuenta, proyecto GCP, repo, workflow, canal de YouTube, horario, minutos estimados. **Añadir un canal = editar este archivo.** |
| `actualizar_dashboard.py` | Consulta GitHub Actions + YouTube y escribe `index.html` (solo biblioteca estándar). |
| `plantilla.html` | Diseño del panel. |
| `test_dashboard.py` | Autocomprobación sin red; el workflow la ejecuta antes de publicar. |
| `.github/workflows/panel.yml` | Cada 6 h (y en cada push) genera el HTML y lo despliega en Pages. |

## Vista previa local

```powershell
$env:GH_PAT = gh auth token; $env:YT_API_KEY = "TU_CLAVE"; python actualizar_dashboard.py; start index.html
```

## Añadir Canal 3 / Canal 4 (enero)

En `config.json`, sustituye `"proximamente": "Enero 2027"` por los mismos campos que tienen Archivo Cero y Clear Ledger
(`cuenta_google`, `proyecto_gcp`, `repo`, `workflow`, `youtube`, `horario`, `minutos_estimados`).
Si el repo nuevo es privado, el token `GH_PAT` también necesita acceso a él.
