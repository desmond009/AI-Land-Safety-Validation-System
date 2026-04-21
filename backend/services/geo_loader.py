from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._layers: Dict[str, GeoLayer] = {}
        self._cache_dir = self.data_dir / "_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

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

        local_file = self.data_dir / self.LAYER_FILES[layer_name]
        with local_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _fetch_geojson_from_url(url: str) -> dict:
        request = Request(url, headers={"User-Agent": "AI-Land-Safety-Validation-System"})
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")

        data = json.loads(payload)
        if data.get("type") != "FeatureCollection":
            raise ValueError("Remote payload is not a GeoJSON FeatureCollection")
        return data

    def _write_cache(self, layer_name: str, geojson: dict) -> None:
        cache_file = self._cache_dir / f"{layer_name}.json"
        with cache_file.open("w", encoding="utf-8") as file:
            json.dump(geojson, file)
