"""
Local development server that mirrors the Vercel deployment:
the FastAPI app from api/index.py plus the static UI from public/.

Run:  python dev_server.py   ->  http://localhost:8000
"""

import os

import uvicorn
from fastapi.staticfiles import StaticFiles

from api.index import app

app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "public"), html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
