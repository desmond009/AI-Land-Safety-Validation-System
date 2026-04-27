from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.geo_loader import GeoDataLoader
from services.risk_engine import RiskEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("land-safety-api")

DATA_DIR = Path(__file__).resolve().parent / "data"
loader = GeoDataLoader(DATA_DIR)
risk_engine = RiskEngine(loader)


@asynccontextmanager
async def lifespan(_: FastAPI):
    preload_layers = os.getenv("PRELOAD_LAYERS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if preload_layers:
        loader.load_all()
        logger.info("Loaded GIS layers: %s", ", ".join(loader.LAYER_FILES.keys()))
    else:
        logger.info("Layer preloading disabled; GIS layers will load lazily on first use")
    yield


app = FastAPI(title="AI Land Safety Validation System", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class AnalyzeResponse(BaseModel):
    risk_level: str
    risk_score: int
    flags: list[str]
    explanation: str
    distance_summary_m: dict[str, float]
    data_source: dict[str, Any]


@app.middleware("http")
async def log_response_time(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s completed in %.2f ms", request.method, request.url.path, elapsed_ms)
    response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.2f}"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze-location", response_model=AnalyzeResponse)
def analyze_location(payload: AnalyzeRequest) -> dict:
    result = risk_engine.analyze(payload.latitude, payload.longitude)
    result["data_source"] = {
        name: loader.get_layer_meta(name)
        for name in loader.LAYER_FILES
    }
    return result


@app.get("/layers/{layer_name}")
def get_layer(layer_name: str) -> dict:
    if layer_name not in loader.LAYER_FILES:
        raise HTTPException(status_code=404, detail="Layer not found")
    return loader.get_geojson(layer_name)
