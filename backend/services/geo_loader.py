from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import geopandas as gpd

CACHE_TTL_SECONDS = 86_400  # 24 hours

# Default spatial filter covers all of Karnataka.
# Override with env var KGIS_BBOX=minlon,minlat,maxlon,maxlat
KARNATAKA_BBOX = "74.0,11.5,78.6,18.5"


@dataclass(frozen=True)
class GeoLayer:
    name: str
    geojson: dict
    gdf_4326: gpd.GeoDataFrame
    gdf_3857: gpd.GeoDataFrame
    sindex_4326: object
    sindex_3857: object


class GeoDataLoader:
    """Loads GeoJSON layers once and keeps spatial indexes hot for fast lookups."""

    LAYER_FILES = {
        "water": "water.json",
        "forest": "forest.json",
        "restricted": "restricted.json",
    }

    LAYER_SOURCE_URL_ENV = {
        "water": "KGIS_WATER_GEOJSON_URL",
        "forest": "KGIS_FOREST_GEOJSON_URL",
        "restricted": "KGIS_RESTRICTED_GEOJSON_URL",
    }

    KGIS_SERVICE_ENDPOINTS = {
        "water": [
            "https://kgis.ksrsac.in/kgismaps1/rest/services/NR_V2/Hydrology_F/MapServer/3",  # Lake Pond
            "https://kgis.ksrsac.in/kgismaps1/rest/services/NR_V2/Hydrology_F/MapServer/5",  # River
        ],
        "forest": [
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Forest/MapServer/0",  # Forest Boundary
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Forest/MapServer/2",  # Eco Sensitive Zone
        ],
        "restricted": [
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Notified_Forest/MapServer/0",
        ],
    }

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._layers: Dict[str, GeoLayer] = {}
        self._layer_meta: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._cache_dir = self.data_dir / "_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._use_live_kgis = os.getenv("KGIS_USE_LIVE", "false").strip().lower() in {
            "1", "true", "yes", "on",
        }
        self._max_live_features = int(os.getenv("KGIS_MAX_FEATURES", "5000"))

    # ------------------------------------------------------------------ public

    def load_all(self) -> None:
        for layer_name in self.LAYER_FILES:
            self._layers[layer_name] = self._load_layer(layer_name)

    def get_layer(self, layer_name: str) -> GeoLayer:
        if layer_name not in self._layers:
            with self._lock:
                if layer_name not in self._layers:
                    self._layers[layer_name] = self._load_layer(layer_name)
        return self._layers[layer_name]

    def get_geojson(self, layer_name: str) -> dict:
        return self.get_layer(layer_name).geojson

    def get_layer_meta(self, layer_name: str) -> dict[str, Any]:
        """Return source provenance for a layer (source label + ISO-8601 timestamp)."""
        entry = self._layer_meta.get(layer_name, {})
        fetched_at = entry.get("fetched_at")
        iso = (
            datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat()
            if fetched_at
            else None
        )
        return {"source": entry.get("source", "unknown"), "fetched_at": iso}

    # ----------------------------------------------------------------- private

    def _load_layer(self, layer_name: str) -> GeoLayer:
        if layer_name not in self.LAYER_FILES:
            raise ValueError(f"Unknown layer '{layer_name}'")

        geojson = self._load_layer_geojson(layer_name)
        features = geojson.get("features", [])
        if not isinstance(features, list):
            raise ValueError(f"Layer '{layer_name}' is missing a valid feature list")

        gdf_4326 = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        if gdf_4326.empty:
            raise ValueError(f"Layer '{layer_name}' has no features")

        if gdf_4326.crs is None:
            gdf_4326 = gdf_4326.set_crs(epsg=4326)
        else:
            gdf_4326 = gdf_4326.to_crs(epsg=4326)

        gdf_4326 = gdf_4326.explode(ignore_index=True)
        gdf_3857 = gdf_4326.to_crs(epsg=3857)

        return GeoLayer(
            name=layer_name,
            geojson=geojson,
            gdf_4326=gdf_4326,
            gdf_3857=gdf_3857,
            sindex_4326=gdf_4326.sindex,
            sindex_3857=gdf_3857.sindex,
        )

    def _load_layer_geojson(self, layer_name: str) -> dict:
        cache_file = self._cache_dir / f"{layer_name}.json"
        stored_meta = self._read_cache_meta()

        # Serve from cache when the file exists and has not exceeded the TTL.
        if cache_file.exists():
            entry = stored_meta.get(layer_name, {})
            age = time.time() - entry.get("fetched_at", 0)
            if age < CACHE_TTL_SECONDS:
                self._layer_meta[layer_name] = {
                    "source": entry.get("source", "cache"),
                    "fetched_at": entry.get("fetched_at"),
                }
                with cache_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            # Cache is stale — remove it and re-fetch below.
            cache_file.unlink(missing_ok=True)

        # Try a user-supplied GeoJSON URL.
        source_url = os.getenv(self.LAYER_SOURCE_URL_ENV[layer_name], "").strip()
        if source_url:
            try:
                geojson = self._fetch_geojson_from_url(source_url)
                self._write_cache(layer_name, geojson, source="env_url")
                self._layer_meta[layer_name] = {"source": "env_url", "fetched_at": time.time()}
                return geojson
            except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                print(
                    f"[GeoDataLoader] Failed to fetch {layer_name} from {source_url}: {exc}. "
                    "Falling back to local data file."
                )

        # Try live KGIS ArcGIS REST services (opt-in).
        if self._use_live_kgis:
            try:
                geojson = self._fetch_layer_from_kgis_services(layer_name)
                self._write_cache(layer_name, geojson, source="live_kgis")
                self._layer_meta[layer_name] = {"source": "live_kgis", "fetched_at": time.time()}
                return geojson
            except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                print(
                    f"[GeoDataLoader] Failed live KGIS fetch for {layer_name}: {exc}. "
                    "Falling back to local data file."
                )

        # Fall back to the local file shipped with the repository.
        local_file = self.data_dir / self.LAYER_FILES[layer_name]
        mtime = local_file.stat().st_mtime if local_file.exists() else None
        self._layer_meta[layer_name] = {"source": "local_file", "fetched_at": mtime}
        with local_file.open("r", encoding="utf-8") as f:
            return json.load(f)

    # --------------------------------------------------------- KGIS bbox filter

    def _build_kgis_spatial_filter(self) -> dict:
        """
        Build an ArcGIS-compatible geometry filter from KGIS_BBOX env var.
        Format: minlon,minlat,maxlon,maxlat  (WGS-84 decimal degrees)
        Defaults to the Karnataka state bounding box.
        """
        raw = os.getenv("KGIS_BBOX", KARNATAKA_BBOX)
        try:
            lo0, la0, lo1, la1 = (float(x.strip()) for x in raw.split(","))
        except (ValueError, TypeError):
            lo0, la0, lo1, la1 = (float(x) for x in KARNATAKA_BBOX.split(","))
        bbox_json = json.dumps(
            {"xmin": lo0, "ymin": la0, "xmax": lo1, "ymax": la1,
             "spatialReference": {"wkid": 4326}}
        )
        return {
            "geometry": bbox_json,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
        }

    # -------------------------------------------------------- KGIS fetch logic

    def _fetch_layer_from_kgis_services(self, layer_name: str) -> dict:
        service_urls = self.KGIS_SERVICE_ENDPOINTS.get(layer_name, [])
        if not service_urls:
            raise ValueError(f"No KGIS service configured for layer '{layer_name}'")

        merged: list[dict] = []
        for url in service_urls:
            fc = self._fetch_geojson_from_arcgis_service(url)
            merged.extend(fc.get("features", []))

        if not merged:
            raise ValueError(f"KGIS service returned no features for '{layer_name}'")

        return {"type": "FeatureCollection", "features": merged}

    @staticmethod
    def _fetch_geojson_from_url(url: str) -> dict:
        req = Request(url, headers={"User-Agent": "AI-Land-Safety-Validation-System"})
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError("Remote payload is not a GeoJSON FeatureCollection")
        return data

    def _fetch_geojson_from_arcgis_service(self, service_url: str) -> dict:
        base = service_url.strip()
        spatial = self._build_kgis_spatial_filter()

        # Step 1: get matching object IDs within the bbox.
        ids_payload = self._http_get_json(
            f"{base}/query?{urlencode({'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json', **spatial})}"
        )
        object_ids: list = ids_payload.get("objectIds") or []
        if len(object_ids) > self._max_live_features:
            object_ids = object_ids[: self._max_live_features]

        features: list[dict] = []
        if object_ids:
            # Step 2: fetch geometry in batches (ArcGIS caps payload per request).
            for start in range(0, len(object_ids), 250):
                batch = object_ids[start : start + 250]
                params = {
                    "objectIds": ",".join(str(o) for o in batch),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "geojson",
                }
                payload = self._http_get_json(f"{base}/query?{urlencode(params)}")
                features.extend(payload.get("features", []))
        else:
            # Fallback: direct feature query with spatial filter applied.
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                **spatial,
            }
            payload = self._http_get_json(f"{base}/query?{urlencode(params)}")
            features.extend(payload.get("features", []))

        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _http_get_json(url: str) -> dict:
        req = Request(url, headers={"User-Agent": "AI-Land-Safety-Validation-System"})
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"ArcGIS service returned error: {data['error']}")
        return data

    # ------------------------------------------------------------ cache helpers

    def _read_cache_meta(self) -> dict:
        meta_file = self._cache_dir / "_meta.json"
        if meta_file.exists():
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_cache(self, layer_name: str, geojson: dict, source: str) -> None:
        # Atomically write the layer data.
        cache_file = self._cache_dir / f"{layer_name}.json"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._cache_dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(geojson, f)
            os.replace(tmp_path, cache_file)
        except Exception:
            os.unlink(tmp_path)
            raise

        # Atomically update the shared meta file.
        meta = self._read_cache_meta()
        meta[layer_name] = {"source": source, "fetched_at": time.time()}
        meta_file = self._cache_dir / "_meta.json"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._cache_dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.replace(tmp_path, meta_file)
        except Exception:
            os.unlink(tmp_path)
            raise
