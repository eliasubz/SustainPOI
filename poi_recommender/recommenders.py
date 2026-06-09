from __future__ import annotations

import math
from collections import Counter

from .data import POI


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0
    d_lat = math.radians(b_lat - a_lat)
    d_lon = math.radians(b_lon - a_lon)
    lat1 = math.radians(a_lat)
    lat2 = math.radians(b_lat)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def minmax_distance_penalty(distance_km: float, walking_tolerance: float) -> float:
    if distance_km <= walking_tolerance:
        return 0.0
    return min(1.0, (distance_km - walking_tolerance) / 8.0)


class BaseRecommender:
    name = "base"

    def recommend(self, tourist, model, k: int = 5) -> list[POI]:
        scored = [(self.score(poi, tourist, model), poi) for poi in model.pois]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [poi for _, poi in scored[:k]]

    def score(self, poi: POI, tourist, model) -> float:
        raise NotImplementedError

    @staticmethod
    def common_penalties(poi: POI, tourist, model) -> tuple[float, float, float]:
        crowd = model.poi_visits[poi.id] / poi.capacity
        price_penalty = max(0.0, (poi.price - tourist.budget) / 40.0)
        distance = haversine_km(tourist.current_lat, tourist.current_lon, poi.lat, poi.lon)
        distance_penalty = minmax_distance_penalty(distance, tourist.walking_tolerance)
        crowd_penalty = crowd * tourist.crowd_aversion
        return price_penalty, distance_penalty, crowd_penalty


class PopularityRecommender(BaseRecommender):
    name = "popularity"

    def score(self, poi: POI, tourist, model) -> float:
        price_penalty, distance_penalty, crowd_penalty = self.common_penalties(poi, tourist, model)
        return poi.popularity - 0.35 * price_penalty - 0.08 * distance_penalty - 0.12 * crowd_penalty


class PersonalizedRecommender(BaseRecommender):
    name = "personalized"

    def score(self, poi: POI, tourist, model) -> float:
        price_penalty, distance_penalty, crowd_penalty = self.common_penalties(poi, tourist, model)
        interest_match = sum(tourist.interests[tag] for tag in poi.tags) / len(poi.tags)
        family_bonus = 0.12 if tourist.travel_with_kids and poi.family_friendly else 0.0
        outdoor_bonus = 0.10 if tourist.outdoor_preference > 0.6 and poi.outdoor else 0.0
        accessibility_bonus = 0.08 * poi.accessibility
        return (
            0.62 * interest_match
            + 0.16 * poi.popularity
            + family_bonus
            + outdoor_bonus
            + accessibility_bonus
            - 0.32 * price_penalty
            - 0.22 * distance_penalty
            - 0.32 * crowd_penalty
        )


class SustainableRecommender(BaseRecommender):
    name = "sustainable"

    def score(self, poi: POI, tourist, model) -> float:
        price_penalty, distance_penalty, crowd_penalty = self.common_penalties(poi, tourist, model)
        interest_match = sum(tourist.interests[tag] for tag in poi.tags) / len(poi.tags)
        district_visits = model.district_visits[poi.district]
        mean_district_visits = max(1.0, sum(model.district_visits.values()) / len(model.districts))
        under_visited_bonus = max(0.0, 1.0 - district_visits / (mean_district_visits * 1.25))
        current_crowding = model.poi_visits[poi.id] / poi.capacity
        low_crowding_bonus = max(0.0, 1.0 - current_crowding)
        family_bonus = 0.08 if tourist.travel_with_kids and poi.family_friendly else 0.0
        outdoor_bonus = 0.06 if tourist.outdoor_preference > 0.6 and poi.outdoor else 0.0
        sustainable_weight = 0.18 + 0.22 * tourist.sustainability_sensitivity
        return (
            0.42 * interest_match
            + sustainable_weight * poi.sustainability
            + 0.16 * poi.local_value
            + 0.14 * poi.cultural_value
            + 0.22 * under_visited_bonus
            + 0.18 * low_crowding_bonus
            + 0.06 * poi.accessibility
            + family_bonus
            + outdoor_bonus
            - 0.25 * price_penalty
            - 0.18 * distance_penalty
            - 0.45 * crowd_penalty
            - 0.06 * poi.popularity
        )


def get_recommender(name: str) -> BaseRecommender:
    recommenders = {
        "popularity": PopularityRecommender(),
        "personalized": PersonalizedRecommender(),
        "sustainable": SustainableRecommender(),
    }
    return recommenders[name]


def entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    probs = [count / total for count in counts if count > 0]
    return -sum(p * math.log(p) for p in probs)


def gini(counter: Counter | dict[str, int]) -> float:
    values = sorted(counter.values())
    n = len(values)
    total = sum(values)
    if n == 0 or total == 0:
        return 0.0
    weighted = sum((i + 1) * value for i, value in enumerate(values))
    return (2 * weighted) / (n * total) - (n + 1) / n
