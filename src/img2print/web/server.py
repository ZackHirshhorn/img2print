"""The web app: the API plus the built frontend. Run with `img2print-web` (needs img2print[web])."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .. import __version__
from .api import router

STATIC = Path(__file__).parent / "static"

NO_FRONTEND = """<!doctype html><meta charset="utf-8"><title>img2print</title>
<body style="font-family:system-ui;max-width:40em;margin:3em auto;padding:0 1em">
<h1>img2print</h1><p>The API is running, but the web frontend has not been built.</p>
<p>Build it once with <code>npm install</code> and <code>npm run build</code> in the
<code>web/</code> folder, or open the <a href="/docs">API docs</a>.</p></body>"""


def create_app() -> FastAPI:
    app = FastAPI(title="img2print", version=__version__,
                  description="Turn flat graphic designs into multi-colour 3D prints.")
    app.include_router(router)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        index = STATIC / "index.html"
        if not index.exists():
            return HTMLResponse(NO_FRONTEND)
        file = (STATIC / path).resolve()
        if path and file.is_file() and file.is_relative_to(STATIC.resolve()):
            # Built assets have content hashes in their names, so they can be cached for good.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})   # single-page app routes

    return app


app = create_app()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="img2print-web", description="Run the img2print web app.")
    ap.add_argument("--host", default="127.0.0.1",
                    help="address to listen on (default 127.0.0.1, this computer only; 0.0.0.0 for the network)")
    ap.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    ap.add_argument("--open", action="store_true", help="open the app in the browser")
    ap.add_argument("--openapi", metavar="FILE", help="write the API schema as JSON to FILE and exit")
    args = ap.parse_args(argv)
    if args.openapi:
        Path(args.openapi).write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
        return

    import uvicorn

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"img2print web app on {url}  (Ctrl+C to stop)")
    if args.open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
