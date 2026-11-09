# server.py
# Web frontend for IMPETUS. Run:   python server.py
# then open http://127.0.0.1:8000
#
# To let other devices on the same network use it:   python server.py --lan
# then open http://<this computer's IP>:8000 on them (the address is printed at startup).
# --lan runs several worker processes so many people can use it at once; set the number with --workers.
# Only use --lan on a network you trust: there is no login, and anyone on it can export files.
# (The PyQt app, GUI.py, still works on its own.)
import argparse
import os
import socket

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import web_backend

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

app = FastAPI(title="IMPETUS")


class TrackRequest(BaseModel):
    section: str
    type: str | None = None
    value: float | None = None


class PhysicsBody(BaseModel):
    friction: dict | None = None   # {"enabled": bool, "mu": float}
    air: dict | None = None        # {"enabled": bool, "cd": float, "area": float, "mass": float}


class PreviewBody(BaseModel):
    tracks: list[TrackRequest]
    physics: PhysicsBody | None = None


class ExportBody(PreviewBody):
    section_folder: str = "Test_Section"
    coaster_name: str = "Test_Coaster"
    overwrite: bool = False


class RecommendBody(BaseModel):
    start_type: str
    start_value: float
    physics: PhysicsBody | None = None
    tracks: list[TrackRequest] | None = None   # current picks: set each section's entry speed with losses


def _physics(body):
    return body.model_dump() if body else None


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except web_backend.BuildError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:   # a track function failed for these values
        raise HTTPException(status_code=422, detail=f"Could not build this track: {e}")


@app.get("/api/options")
def get_options():
    return web_backend.options()


@app.post("/api/preview")
def post_preview(body: PreviewBody):
    return _run(web_backend.preview, [t.model_dump() for t in body.tracks], _physics(body.physics))


@app.post("/api/export")
def post_export(body: ExportBody):
    return _run(web_backend.export, [t.model_dump() for t in body.tracks],
                body.section_folder, body.coaster_name, body.overwrite, _physics(body.physics))


@app.post("/api/recommendations")
def post_recommendations(body: RecommendBody):
    return _run(web_backend.recommendations, body.start_type, body.start_value, _physics(body.physics),
                [t.model_dump() for t in body.tracks or []])


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")


def _lan_ip():
    # The address other devices use to reach this computer (no data is actually sent)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "<this computer's IP>"


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="IMPETUS web frontend")
    parser.add_argument("--lan", action="store_true",
                        help="allow other devices on the local network to connect")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=None,
                        help="worker processes (default: 1, or up to 4 with --lan)")
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    workers = args.workers or (min(4, os.cpu_count() or 1) if args.lan else 1)

    print(f"IMPETUS running on this computer:  http://127.0.0.1:{args.port}")
    if args.lan:
        print(f"Other devices on the network:      http://{_lan_ip()}:{args.port}")
        print("(If they can't connect, allow Python through Windows Firewall on private networks.)")
    print(f"Worker processes: {workers}")

    # "server:app" (not app) so uvicorn can start several worker processes
    uvicorn.run("server:app", host=host, port=args.port, workers=workers,
                app_dir=os.path.dirname(os.path.abspath(__file__)))
