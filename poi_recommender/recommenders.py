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
        # Crowding is now the *instantaneous* occupancy at the current simulated time,
        # not the cumulative all-day visit count. This makes congestion time-dependent.
        crowd = model.current_crowding(poi)
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

    def __init__(self, strength: float = 1.0, weights: dict[str, float] | None = None) -> None:
        # `strength` scales every sustainability-oriented term relative to interest match.
        # strength=1.0 is the default behaviour; strength=0.0 collapses to an
        # interest+accessibility recommender (used by the sensitivity analysis).
        self.strength = strength
        # Per-mechanism multipliers, used by the ablation study. Each defaults to
        # 1.0 so the standard recommender is unchanged:
        #   value     -> sustainability + local + cultural value (and anti-popularity)
        #   spread    -> under-visited-district bonus (geographic spreading)
        #   decongest -> low instantaneous-crowding bonus
        mechanism = {"value": 1.0, "spread": 1.0, "decongest": 1.0}
        if weights:
            mechanism.update(weights)
        self.mechanism = mechanism

    def score(self, poi: POI, tourist, model) -> float:
        price_penalty, distance_penalty, crowd_penalty = self.common_penalties(poi, tourist, model)
        interest_match = sum(tourist.interests[tag] for tag in poi.tags) / len(poi.tags)
        district_visits = model.district_visits[poi.district]
        mean_district_visits = max(1.0, sum(model.district_visits.values()) / len(model.districts))
        under_visited_bonus = max(0.0, 1.0 - district_visits / (mean_district_visits * 1.25))
        current_crowding = model.current_crowding(poi)
        low_crowding_bonus = max(0.0, 1.0 - current_crowding)
        family_bonus = 0.08 if tourist.travel_with_kids and poi.family_friendly else 0.0
        outdoor_bonus = 0.06 if tourist.outdoor_preference > 0.6 and poi.outdoor else 0.0
        sustainable_weight = 0.18 + 0.22 * tourist.sustainability_sensitivity
        s = self.strength
        wv = self.mechanism["value"]
        wsp = self.mechanism["spread"]
        wd = self.mechanism["decongest"]
        return (
            0.42 * interest_match
            + s * wv * sustainable_weight * poi.sustainability
            + s * wv * 0.16 * poi.local_value
            + s * wv * 0.14 * poi.cultural_value
            + s * wsp * 0.22 * under_visited_bonus
            + s * wd * 0.18 * low_crowding_bonus
            + 0.06 * poi.accessibility
            + family_bonus
            + outdoor_bonus
            - 0.25 * price_penalty
            - 0.18 * distance_penalty
            - 0.45 * crowd_penalty
            - s * wv * 0.06 * poi.popularity
        )


class CrowdAwareRecommender(BaseRecommender):
    """Interest-matching recommender that actively routes around current crowding
    but has no sustainability, local-value or district-spreading objective.

    Acts as the congestion-only competitor to the sustainable recommender: the
    gap between this and `sustainable` isolates the contribution of the
    sustainability/fairness terms net of decongestion.
    """

    name = "crowd_aware"

    def score(self, poi: POI, tourist, model) -> float:
        price_penalty, distance_penalty, crowd_penalty = self.common_penalties(poi, tourist, model)
        interest_match = sum(tourist.interests[tag] for tag in poi.tags) / len(poi.tags)
        low_crowding_bonus = max(0.0, 1.0 - model.current_crowding(poi))
        family_bonus = 0.10 if tourist.travel_with_kids and poi.family_friendly else 0.0
        outdoor_bonus = 0.08 if tourist.outdoor_preference > 0.6 and poi.outdoor else 0.0
        return (
            0.58 * interest_match
            + 0.14 * poi.popularity
            + 0.24 * low_crowding_bonus
            + 0.06 * poi.accessibility
            + family_bonus
            + outdoor_bonus
            - 0.25 * price_penalty
            - 0.18 * distance_penalty
            - 0.55 * crowd_penalty
        )


class RandomRecommender(BaseRecommender):
    """Null baseline: ranks POIs at random (using the model RNG for
    reproducibility). Feasibility is still enforced downstream by the model.

    Useful as a lower bound: random routing tends to achieve low spatial
    inequality simply by scattering tourists, which shows that a low district
    Gini is trivial on its own -- the real achievement is low inequality *while*
    keeping tourist satisfaction high.
    """

    name = "random"

    def score(self, poi: POI, tourist, model) -> float:
        return float(model.rng.random())


# Single-mechanism weight sets for the ablation study.
_ABLATION_WEIGHTS = {
    "sust_all": {"value": 1.0, "spread": 1.0, "decongest": 1.0},
    "sust_value": {"value": 1.0, "spread": 0.0, "decongest": 0.0},
    "sust_spread": {"value": 0.0, "spread": 1.0, "decongest": 0.0},
    "sust_decongest": {"value": 0.0, "spread": 0.0, "decongest": 1.0},
}


def get_recommender(name: str, sustainability_strength: float = 1.0) -> BaseRecommender:
    if name in _ABLATION_WEIGHTS:
        return SustainableRecommender(
            strength=sustainability_strength, weights=_ABLATION_WEIGHTS[name]
        )
    recommenders = {
        "popularity": PopularityRecommender(),
        "personalized": PersonalizedRecommender(),
        "sustainable": SustainableRecommender(strength=sustainability_strength),
        "crowd_aware": CrowdAwareRecommender(),
        "random": RandomRecommender(),
    }
    return recommenders[name]


def entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    probs = [count / total for count in counts if count > 0]
    return -sum(p * math.log(p) for p in probs)


def gini(counter: Counter | dict[str, int] | dict[str, float]) -> float:
    values = sorted(counter.values())
    n = len(values)
    total = sum(values)
    if n == 0 or total == 0:
        return 0.0
    weighted = sum((i + 1) * value for i, value in enumerate(values))
    return (2 * weighted) / (n * total) - (n + 1) / n
