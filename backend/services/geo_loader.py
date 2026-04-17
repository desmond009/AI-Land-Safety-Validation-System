from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

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

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._layers: Dict[str, GeoLayer] = {}

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

        file_path = self.data_dir / self.LAYER_FILES[layer_name]
        with file_path.open("r", encoding="utf-8") as file:
            geojson = json.load(file)

        gdf_4326 = gpd.read_file(file_path)
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
