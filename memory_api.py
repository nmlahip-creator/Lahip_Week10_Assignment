from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI(title="Memory API")

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = Path(os.getenv("MEMORY_STORE_PATH", BASE_DIR / "memory_store.json"))
API_TOKEN = os.getenv("MEMORY_API_TOKEN", "").strip()


def _load_store() -> dict[str, Any]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_store(data: dict[str, Any]) -> None:
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _check_auth(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/memory")
def get_memory(_: None = Depends(_check_auth)) -> dict[str, Any]:
    data = _load_store()
    return data if isinstance(data, dict) else {}


@app.post("/memory")
def update_memory(payload: dict[str, Any], _: None = Depends(_check_auth)) -> dict[str, Any]:
    data = _load_store()
    if not isinstance(data, dict):
        data = {}
    data.update(payload or {})
    _save_store(data)
    return data


@app.delete("/memory")
def clear_memory(_: None = Depends(_check_auth)) -> dict[str, Any]:
    _save_store({})
    return {}
