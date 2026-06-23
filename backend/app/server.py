from __future__ import annotations

from http.server import ThreadingHTTPServer

from .api import ApiHandler
from .config import load_settings
from .database import Database


def run() -> None:
    settings = load_settings()
    database = Database(settings.db_path)
    database.initialize()
    ApiHandler.database = database
    ApiHandler.cors_origin = settings.cors_origin
    ApiHandler.session_hours = settings.session_hours
    server = ThreadingHTTPServer((settings.host, settings.port), ApiHandler)
    print(f"UBPD Indicadores API: http://{settings.host}:{settings.port}")
    print(f"Base de datos: {settings.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
