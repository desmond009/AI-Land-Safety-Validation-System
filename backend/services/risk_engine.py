from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import Point

from services.geo_loader import GeoDataLoader, GeoLayer

WATER_INSIDE_SCORE = 50
WATER_NEAR_SCORE = 40
FOREST_INSIDE_SCORE = 50
RESTRICTED_NEAR_SCORE = 30

NEAR_DISTANCE_METERS = 100


@dataclass
class LayerCheck:
    inside: bool
    distance_m: float


class RiskEngine:
    def __init__(self, loader: GeoDataLoader) -> None:
        self.loader = loader

    def analyze(self, latitude: float, longitude: float) -> dict:
        point = Point(longitude, latitude)
        point_metric = gpd.GeoSeries([point], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]

        water = self._check_layer(point, point_metric, self.loader.get_layer("water"))
        forest = self._check_layer(point, point_metric, self.loader.get_layer("forest"))
        restricted = self._check_layer(point, point_metric, self.loader.get_layer("restricted"))

        score = 0
        flags: list[str] = []
        reasons: list[str] = []

        if water.inside:
            score += WATER_INSIDE_SCORE
            flags.append("Inside water body")
            reasons.append("The selected point lies inside a mapped water-body polygon.")
        elif water.distance_m <= NEAR_DISTANCE_METERS:
            score += WATER_NEAR_SCORE
            flags.append("Near water body")
            reasons.append(
                f"The location is only {water.distance_m:.1f}m from the nearest water body."
            )

        if forest.inside:
            score += FOREST_INSIDE_SCORE
            flags.append("Inside forest zone")
            reasons.append("The location intersects a forest protection polygon.")

        if restricted.inside:
            score += RESTRICTED_NEAR_SCORE
            flags.append("Inside restricted land")
            reasons.append("The point is inside a government/restricted land polygon.")
        elif restricted.distance_m <= NEAR_DISTANCE_METERS:
            score += RESTRICTED_NEAR_SCORE
            flags.append("Near restricted land")
            reasons.append(
                f"The location is {restricted.distance_m:.1f}m from restricted land."
            )

        bounded_score = min(score, 100)
        risk_level = self._classify_score(bounded_score)

        if reasons:
            explanation = " ".join(reasons) + f" Final risk level is {risk_level}."
        else:
            explanation = (
                "No immediate intersections or nearby high-sensitivity polygons were found. "
                f"Final risk level is {risk_level}."
            )

        return {
            "risk_level": risk_level,
            "risk_score": bounded_score,
            "flags": flags,
            "explanation": explanation,
            "distance_summary_m": {
                "water": round(water.distance_m, 2),
                "forest": round(forest.distance_m, 2),
                "restricted": round(restricted.distance_m, 2),
            },
        }

    def _check_layer(self, point: Point, point_metric: Point, layer: GeoLayer) -> LayerCheck:
        candidate_ids = list(layer.sindex_4326.intersection(point.bounds))
        inside = False
        if candidate_ids:
            inside = bool(layer.gdf_4326.iloc[candidate_ids].intersects(point).any())

        # Use indexed bbox search for nearby candidates before exact distance calculation.
        near_bbox = point_metric.buffer(NEAR_DISTANCE_METERS).bounds
        near_ids = list(layer.sindex_3857.intersection(near_bbox))
        if near_ids:
            distance_m = float(layer.gdf_3857.iloc[near_ids].distance(point_metric).min())
        else:
            distance_m = float(layer.gdf_3857.distance(point_metric).min())

        return LayerCheck(inside=inside, distance_m=distance_m)

    @staticmethod
    def _classify_score(score: int) -> str:
        if score <= 30:
            return "Low"
        if score <= 70:
            return "Medium"
        return "High"
