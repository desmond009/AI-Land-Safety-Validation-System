from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import geopandas as gpd


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

    # KGIS reference services discovered from the public layers API.
    KGIS_SERVICE_ENDPOINTS = {
        "water": [
            "https://kgis.ksrsac.in/kgismaps1/rest/services/NR_V2/Hydrology_F/MapServer/3",  # Lake Pond
            "https://kgis.ksrsac.in/kgismaps1/rest/services/NR_V2/Hydrology_F/MapServer/5",  # River
        ],
        "forest": [
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Forest/MapServer/0",  # Forest Boundary
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Forest/MapServer/2",  # Eco Sensitive Zone Boundary
        ],
        "restricted": [
            "https://kgis.ksrsac.in/kgismaps2/rest/services/Forest/Notified_Forest/MapServer/0",  # Notified Forest
        ],
    }

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._layers: Dict[str, GeoLayer] = {}
        self._cache_dir = self.data_dir / "_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Live KGIS can be large and slow; keep it opt-in to avoid API startup stalls.
        self._use_live_kgis = os.getenv("KGIS_USE_LIVE", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._max_live_features = int(os.getenv("KGIS_MAX_FEATURES", "5000"))

    def load_all(self) -> None:
        for layer_name in self.LAYER_FILES:
            self._layers[layer_name] = self._load_layer(layer_name)

    def get_layer(self, layer_name: str) -> GeoLayer:
        if layer_name not in self._layers:
            self._layers[layer_name] = self._load_layer(layer_name)
        return self._layers[layer_name]

    def get_geojson(self, layer_name: str) -> dict:
        return self.get_layer(layer_name).geojson

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
        if cache_file.exists():
            with cache_file.open("r", encoding="utf-8") as file:
                return json.load(file)

        source_env_name = self.LAYER_SOURCE_URL_ENV[layer_name]
        source_url = os.getenv(source_env_name, "").strip()
        if source_url:
            try:
                geojson = self._fetch_geojson_from_url(source_url)
                self._write_cache(layer_name, geojson)
                return geojson
            except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                # Fall back to local layer when remote source is unavailable.
                print(
                    f"[GeoDataLoader] Failed to fetch {layer_name} from {source_url}: {exc}. "
                    "Falling back to local data file."
                )

        if self._use_live_kgis:
            try:
                geojson = self._fetch_layer_from_kgis_services(layer_name)
                self._write_cache(layer_name, geojson)
                return geojson
            except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                print(
                    f"[GeoDataLoader] Failed live KGIS fetch for {layer_name}: {exc}. "
                    "Falling back to local data file."
                )

        local_file = self.data_dir / self.LAYER_FILES[layer_name]
        with local_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _fetch_layer_from_kgis_services(self, layer_name: str) -> dict:
        service_urls = self.KGIS_SERVICE_ENDPOINTS.get(layer_name, [])
        if not service_urls:
            raise ValueError(f"No KGIS service configured for layer '{layer_name}'")

        merged_features: list[dict] = []
        for service_url in service_urls:
            fc = self._fetch_geojson_from_arcgis_service(service_url)
            merged_features.extend(fc.get("features", []))

        if not merged_features:
            raise ValueError(f"KGIS service returned no features for '{layer_name}'")

        return {"type": "FeatureCollection", "features": merged_features}

    @staticmethod
    def _fetch_geojson_from_url(url: str) -> dict:
        request = Request(url, headers={"User-Agent": "AI-Land-Safety-Validation-System"})
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")

        data = json.loads(payload)
        if data.get("type") != "FeatureCollection":
            raise ValueError("Remote payload is not a GeoJSON FeatureCollection")
        return data

    def _fetch_geojson_from_arcgis_service(self, service_url: str) -> dict:
        base = service_url.strip()

        ids_payload = self._http_get_json(
            f"{base}/query?{urlencode({'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'})}"
        )
        object_ids = ids_payload.get("objectIds") or []
        if object_ids and len(object_ids) > self._max_live_features:
            object_ids = object_ids[: self._max_live_features]

        features: list[dict] = []
        if object_ids:
            # ArcGIS limits query payload size; batch object IDs to fetch all records.
            batch_size = 250
            for start in range(0, len(object_ids), batch_size):
                batch = object_ids[start : start + batch_size]
                params = {
                    "objectIds": ",".join(str(oid) for oid in batch),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "geojson",
                }
                payload = self._http_get_json(f"{base}/query?{urlencode(params)}")
                features.extend(payload.get("features", []))
        else:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
            }
            payload = self._http_get_json(f"{base}/query?{urlencode(params)}")
            features.extend(payload.get("features", []))

        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _http_get_json(url: str) -> dict:
        request = Request(url, headers={"User-Agent": "AI-Land-Safety-Validation-System"})
        with urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")

        data = json.loads(payload)
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"ArcGIS service returned error: {data['error']}")
        return data

    def _write_cache(self, layer_name: str, geojson: dict) -> None:
        cache_file = self._cache_dir / f"{layer_name}.json"
        with cache_file.open("w", encoding="utf-8") as file:
            json.dump(geojson, file)
