# Fingerfruit Railway App

Railway deployable source for the Fingerfruit web app and fallback API.

## Runtime

- Start command: `python3 web_server.py 0.0.0.0 $PORT`
- Required secret: `FRUIT_AUTO_WEB_TOKEN`
- Optional state directory: `FRUIT_AUTO_DATA_DIR`
- Optional account/session bootstrap: `FRUIT_AUTO_SECRETS_JSON`

The app serves static files from `www/` and exposes the `/api/*` endpoints used by the Android/PWA clients.
