from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
from shapely.geometry import Point

from services.geo_loader import GeoDataLoader, GeoLayer

WATER_INSIDE_SCORE = 50
WATER_NEAR_SCORE = 40
FOREST_INSIDE_SCORE = 50
FOREST_NEAR_SCORE = 30
RESTRICTED_INSIDE_SCORE = 30
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
            water_names = ", ".join(water.inside_features) if water.inside_features else "a water body"
            flags.append(f"Inside water body ({water_names})")
            reasons.append(
                f"This land is located inside a protected water body ({water_names}). "
                "Karnataka land revenue and water conservation rules prohibit construction "
                "on or immediately adjacent to water bodies."
            )
        elif water.distance_m <= NEAR_DISTANCE_METERS:
            score += WATER_NEAR_SCORE
            nearest_water = water.nearest_feature or "a nearby water body"
            flags.append(f"Within 100 m of water body ({nearest_water})")
            reasons.append(
                f"This land is within {water.distance_m:.0f} m of a water body ({nearest_water}). "
                "Setback regulations in Karnataka typically restrict development activity "
                "within 30–100 m of water bodies."
            )

        if forest.inside:
            score += FOREST_INSIDE_SCORE
            forest_names = ", ".join(forest.inside_features) if forest.inside_features else "a forest zone"
            flags.append(f"Inside forest zone ({forest_names})")
            reasons.append(
                f"This land falls inside a designated forest zone ({forest_names}). "
                "The Karnataka Forest Act 1963 prohibits non-forest activities, construction, "
                "or industrial use inside forest areas without prior government approval."
            )
        elif forest.distance_m <= NEAR_DISTANCE_METERS:
            score += FOREST_NEAR_SCORE
            nearest_forest = forest.nearest_feature or "a forest zone"
            flags.append(f"Within 100 m of forest zone ({nearest_forest})")
            reasons.append(
                f"This land is within {forest.distance_m:.0f} m of a forest or eco-sensitive zone "
                f"({nearest_forest}). Proposals in this buffer may require environmental clearance "
                "under the Environment Protection Act 1986."
            )

        if restricted.inside:
            score += RESTRICTED_INSIDE_SCORE
            restricted_names = ", ".join(restricted.inside_features) if restricted.inside_features else "a restricted area"
            flags.append(f"Inside restricted land ({restricted_names})")
            reasons.append(
                f"This land is inside a government-notified restricted area ({restricted_names}). "
                "Prior written approval from the Karnataka Forest Department is mandatory. "
                "Development may be prohibited under the Wildlife Protection Act 1972."
            )
        elif restricted.distance_m <= NEAR_DISTANCE_METERS:
            score += RESTRICTED_NEAR_SCORE
            nearest_restricted = restricted.nearest_feature or "a restricted zone"
            flags.append(f"Near restricted land ({nearest_restricted})")
            reasons.append(
                f"This land is within {restricted.distance_m:.0f} m of a notified restricted zone "
                f"({nearest_restricted}). Contact the local Revenue or Forest Department "
                "before initiating any development activity."
            )

        bounded_score = min(score, 100)
        risk_level = self._classify_score(bounded_score)

        if reasons:
            explanation = " ".join(reasons) + f" Overall risk level: {risk_level}."
        else:
            explanation = (
                "This location does not overlap any mapped water body, forest zone, or "
                "government-restricted area. Standard building regulations and local "
                f"development plans still apply. Overall risk level: {risk_level}."
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
        # sindex.query(geometry, predicate=) uses exact spatial predicate, not just bbox.
        candidate_ids = list(layer.sindex_4326.query(point, predicate="intersects"))
        inside = False
        inside_features: list[str] = []
        if candidate_ids:
            inside_rows = layer.gdf_4326.iloc[candidate_ids]
            inside = not inside_rows.empty
            if inside:
                inside_features = [self._feature_name(props) for _, props in inside_rows.iterrows()]

        near_buffer = point_metric.buffer(NEAR_DISTANCE_METERS)
        near_ids = list(layer.sindex_3857.query(near_buffer))
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
        # Priority: known KGIS domain fields first, then generic fallbacks.
        for key in (
            "Lake_Pondname", "WBNAME",                       # water
            "ForestName", "RangeName", "Forest_type",        # forest
            "FOREST_NAM", "FL_STATUS",                       # restricted
            "name", "NAME", "title",                         # generic GeoJSON
        ):
            value = feature_row.get(key)
            # Guard against pandas NaN, None, and empty strings.
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            text = str(value).strip()
            if text:
                return text
        # Fall back to a readable numeric identifier rather than "Unnamed feature"
        for key in ("OBJECTID", "OBJECTID_1", "KGISLake_PondID", "FOREST_ID"):
            value = feature_row.get(key)
            if value is not None:
                return f"Feature #{value}"
        return "Unnamed feature"

    @staticmethod
    def _classify_score(score: int) -> str:
        if score <= 30:
            return "LOW"
        if score <= 70:
            return "MEDIUM"
        return "HIGH"
