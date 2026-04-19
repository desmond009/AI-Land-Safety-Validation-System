from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    inside_features: list[str]
    nearest_feature: str | None


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
            water_names = ", ".join(water.inside_features) if water.inside_features else "mapped water layer"
            flags.append(f"Inside water body ({water_names})")
            reasons.append(
                f"The selected point lies inside a mapped water-body polygon from the water layer: {water_names}."
            )
        elif water.distance_m <= NEAR_DISTANCE_METERS:
            score += WATER_NEAR_SCORE
            nearest_water = water.nearest_feature or "nearest water polygon"
            flags.append(f"Within 100m of water body ({nearest_water})")
            reasons.append(
                f"The location is {water.distance_m:.1f}m from water body feature: {nearest_water}."
            )

        if forest.inside:
            score += FOREST_INSIDE_SCORE
            forest_names = ", ".join(forest.inside_features) if forest.inside_features else "mapped forest layer"
            flags.append(f"Inside forest zone ({forest_names})")
            reasons.append(
                f"The location intersects a forest/eco-sensitive polygon from forest layer: {forest_names}."
            )

        if restricted.inside:
            score += RESTRICTED_NEAR_SCORE
            restricted_names = ", ".join(restricted.inside_features) if restricted.inside_features else "mapped restricted layer"
            flags.append(f"Inside restricted land ({restricted_names})")
            reasons.append(
                f"The point is inside a government/restricted land polygon: {restricted_names}."
            )
        elif restricted.distance_m <= NEAR_DISTANCE_METERS:
            score += RESTRICTED_NEAR_SCORE
            nearest_restricted = restricted.nearest_feature or "nearest restricted polygon"
            flags.append(f"Near restricted land ({nearest_restricted})")
            reasons.append(
                f"The location is {restricted.distance_m:.1f}m from restricted land feature: {nearest_restricted}."
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
        inside_features: list[str] = []
        if candidate_ids:
            inside_candidates = layer.gdf_4326.iloc[candidate_ids]
            inside_rows = inside_candidates[inside_candidates.intersects(point)]
            inside = not inside_rows.empty
            if inside:
                inside_features = [self._feature_name(props) for _, props in inside_rows.iterrows()]

        # Use indexed bbox search for nearby candidates before exact distance calculation.
        near_bbox = point_metric.buffer(NEAR_DISTANCE_METERS).bounds
        near_ids = list(layer.sindex_3857.intersection(near_bbox))
        nearest_feature: str | None = None
        if near_ids:
            candidates_3857 = layer.gdf_3857.iloc[near_ids]
            distances = candidates_3857.distance(point_metric)
            nearest_idx = int(distances.idxmin())
            distance_m = float(distances.min())
            nearest_feature = self._feature_name(layer.gdf_4326.loc[nearest_idx])
        else:
            distances = layer.gdf_3857.distance(point_metric)
            nearest_idx = int(distances.idxmin())
            distance_m = float(distances.min())
            nearest_feature = self._feature_name(layer.gdf_4326.loc[nearest_idx])

        return LayerCheck(
            inside=inside,
            distance_m=distance_m,
            inside_features=inside_features,
            nearest_feature=nearest_feature,
        )

    @staticmethod
    def _feature_name(feature_row: Any) -> str:
        for key in ("name", "NAME", "title", "id"):
            value = feature_row.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return "Unnamed feature"

    @staticmethod
    def _classify_score(score: int) -> str:
        if score <= 30:
            return "LOW"
        if score <= 70:
            return "MEDIUM"
        return "HIGH"
