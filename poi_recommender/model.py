from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
from mesa import Agent, Model

from .data import INTERESTS, POI, load_barcelona_pois
from .recommenders import entropy, get_recommender, gini, haversine_km


CITY_CENTER = (41.3874, 2.1686)


class TouristAgent(Agent):
    def __init__(self, model: "TourismModel") -> None:
        super().__init__(model)
        rng = model.rng
        self.interests = self._sample_interests(rng)
        self.budget = float(rng.choice([0, 8, 15, 25, 40], p=[.10, .20, .30, .25, .15]))
        self.mobility_mode = str(rng.choice(["walking", "public_transport", "taxi"], p=[.42, .48, .10]))
        base_walk = {"walking": 4.2, "public_transport": 2.4, "taxi": 1.4}[self.mobility_mode]
        self.walking_tolerance = float(max(0.6, rng.normal(base_walk, 0.9)))
        self.crowd_aversion = float(rng.beta(2.0, 2.2))
        self.sustainability_sensitivity = float(rng.beta(2.0, 2.0))
        self.outdoor_preference = float(rng.beta(2.0, 2.0))
        self.travel_with_kids = bool(rng.random() < 0.22)
        self.time_available = float(rng.normal(7.0, 1.4))
        self.current_lat, self.current_lon = CITY_CENTER
        self.visited: list[POI] = []
        self.satisfaction_scores: list[float] = []
        self.travel_km = 0.0
        self.elapsed_time = 0.0
        self.tourist_id = 0

    @staticmethod
    def _sample_interests(rng: np.random.Generator) -> dict[str, float]:
        profile = str(rng.choice(
            ["mainstream", "culture", "food", "nature", "family", "nightlife"],
            p=[.32, .24, .14, .12, .10, .08],
        ))
        weights = {interest: float(rng.beta(1.5, 3.0)) for interest in INTERESTS}
        boosts = {
            "mainstream": ["architecture", "history", "food"],
            "culture": ["museums", "history", "religion", "architecture"],
            "food": ["food", "shopping", "nightlife"],
            "nature": ["nature", "beach", "family"],
            "family": ["family", "nature", "museums"],
            "nightlife": ["nightlife", "food", "beach"],
        }
        for interest in boosts[profile]:
            weights[interest] = min(1.0, weights[interest] + float(rng.uniform(.35, .65)))
        return weights

    def step(self) -> None:
        recommender = self.model.recommender
        remaining_time = self.time_available
        visited_ids = set()
        for sequence in range(self.model.visits_per_tourist):
            candidates = [poi for poi in recommender.recommend(self, self.model, k=self.model.recommendation_k + 4) if poi.id not in visited_ids]
            recommendations = candidates[: self.model.recommendation_k]
            chosen = self._choose_visit(recommendations, remaining_time)
            self.model.record_recommendation(self, sequence, recommendations, chosen)
            if chosen is None:
                break
            distance = haversine_km(self.current_lat, self.current_lon, chosen.lat, chosen.lon)
            travel_time = self._travel_time(distance)
            previous = self.visited[-1] if self.visited else None
            remaining_time -= chosen.duration + travel_time
            self.travel_km += distance
            self.current_lat, self.current_lon = chosen.lat, chosen.lon
            visited_ids.add(chosen.id)
            self.visited.append(chosen)
            self.satisfaction_scores.append(self._satisfaction(chosen, distance))
            self.model.record_itinerary(self, sequence, previous, chosen, distance, travel_time)
            self.model.record_visit(chosen)
            self.elapsed_time += chosen.duration + travel_time

    def _choose_visit(self, candidates: list[POI], remaining_time: float) -> POI | None:
        feasible = []
        for poi in candidates[: self.model.recommendation_k]:
            distance = haversine_km(self.current_lat, self.current_lon, poi.lat, poi.lon)
            if poi.duration + self._travel_time(distance) > remaining_time:
                continue
            if poi.price > self.budget and self.model.rng.random() < 0.80:
                continue
            crowding = self.model.poi_visits[poi.id] / poi.capacity
            skip_probability = min(0.75, crowding * self.crowd_aversion * 0.55)
            if self.model.rng.random() < skip_probability:
                continue
            feasible.append(poi)
        return feasible[0] if feasible else None

    def _travel_time(self, distance_km: float) -> float:
        speeds = {"walking": 4.2, "public_transport": 12.0, "taxi": 18.0}
        return distance_km / speeds[self.mobility_mode]

    def _satisfaction(self, poi: POI, distance_km: float) -> float:
        interest_match = self.interest_match(poi)
        price_fit = 1.0 if poi.price <= self.budget else max(0.0, 1 - (poi.price - self.budget) / 40)
        crowding = self.model.poi_visits[poi.id] / poi.capacity
        distance_fit = max(0.0, 1 - max(0.0, distance_km - self.walking_tolerance) / 8)
        return float(np.clip(
            0.56 * interest_match + 0.15 * price_fit + 0.14 * distance_fit + 0.15 * (1 - min(1.0, crowding)),
            0,
            1,
        ))

    def interest_match(self, poi: POI) -> float:
        return sum(self.interests[tag] for tag in poi.tags) / len(poi.tags)

    def primary_interests(self) -> str:
        ranked = sorted(self.interests.items(), key=lambda item: item[1], reverse=True)
        return "|".join(interest for interest, _ in ranked[:3])


class TourismModel(Model):
    def __init__(
        self,
        n_tourists: int,
        recommender_name: str,
        seed: int = 42,
        visits_per_tourist: int = 3,
        recommendation_k: int = 5,
    ) -> None:
        super().__init__(rng=seed)
        self.rng = np.random.default_rng(seed)
        self.pois = load_barcelona_pois()
        self.districts = sorted({poi.district for poi in self.pois})
        self.recommender = get_recommender(recommender_name)
        self.recommender_name = recommender_name
        self.visits_per_tourist = visits_per_tourist
        self.recommendation_k = recommendation_k
        self.poi_visits: Counter[int] = Counter()
        self.district_visits: Counter[str] = Counter({district: 0 for district in self.districts})
        self.neighbourhood_visits: Counter[str] = Counter()
        self.poi_satisfaction: defaultdict[int, list[float]] = defaultdict(list)
        self.recommendation_events: list[dict[str, float | str | int]] = []
        self.itinerary_events: list[dict[str, float | str | int]] = []
        self.agents_by_id = [TouristAgent(self) for _ in range(n_tourists)]
        for tourist_id, agent in enumerate(self.agents_by_id):
            agent.tourist_id = tourist_id

    def step(self) -> None:
        for agent in self.agents_by_id:
            agent.step()

    def record_visit(self, poi: POI) -> None:
        self.poi_visits[poi.id] += 1
        self.district_visits[poi.district] += 1
        self.neighbourhood_visits[poi.neighbourhood] += 1

    def record_recommendation(self, tourist: TouristAgent, sequence: int, recommendations: list[POI], chosen: POI | None) -> None:
        relevant = [poi for poi in recommendations if tourist.interest_match(poi) >= 0.55]
        all_relevant = [poi for poi in self.pois if tourist.interest_match(poi) >= 0.55]
        visited_recommended = chosen is not None and chosen.id in {poi.id for poi in recommendations}
        self.recommendation_events.append({
            "recommender": self.recommender_name,
            "tourist_id": tourist.tourist_id,
            "sequence": sequence,
            "primary_interests": tourist.primary_interests(),
            "budget": tourist.budget,
            "mobility_mode": tourist.mobility_mode,
            "crowd_aversion": tourist.crowd_aversion,
            "sustainability_sensitivity": tourist.sustainability_sensitivity,
            "recommended_pois": "|".join(poi.name for poi in recommendations),
            "recommended_districts": "|".join(poi.district for poi in recommendations),
            "chosen_poi": chosen.name if chosen else "",
            "chosen_district": chosen.district if chosen else "",
            "precision_at_k": len(relevant) / len(recommendations) if recommendations else 0.0,
            "hit": int(visited_recommended),
            "recall_at_k": len(relevant) / len(all_relevant) if all_relevant else 0.0,
            "diversity_at_k": recommendation_diversity(recommendations),
            "novelty_at_k": float(np.mean([1 - poi.popularity for poi in recommendations])) if recommendations else 0.0,
            "avg_recommended_sustainability": float(np.mean([poi.sustainability for poi in recommendations])) if recommendations else 0.0,
        })

    def record_itinerary(
        self,
        tourist: TouristAgent,
        sequence: int,
        previous: POI | None,
        chosen: POI,
        distance_km: float,
        travel_time_hours: float,
    ) -> None:
        self.itinerary_events.append({
            "recommender": self.recommender_name,
            "tourist_id": tourist.tourist_id,
            "sequence": sequence,
            "from_poi": previous.name if previous else "City center",
            "from_district": previous.district if previous else "Start",
            "to_poi": chosen.name,
            "to_district": chosen.district,
            "distance_km": distance_km,
            "travel_time_hours": travel_time_hours,
            "arrival_hour": 9.0 + tourist.elapsed_time + travel_time_hours,
            "mobility_mode": tourist.mobility_mode,
        })

    def summary_metrics(self) -> dict[str, float | str | int]:
        all_satisfaction = [score for agent in self.agents_by_id for score in agent.satisfaction_scores]
        total_visits = sum(self.poi_visits.values())
        poi_counts = [self.poi_visits[poi.id] for poi in self.pois]
        utilizations = [self.poi_visits[poi.id] / poi.capacity for poi in self.pois]
        over_capacity_visits = sum(max(0, self.poi_visits[poi.id] - poi.capacity) for poi in self.pois)
        sustainability = [
            poi.sustainability
            for poi in self.pois
            for _ in range(self.poi_visits[poi.id])
        ]
        recommendation_exposure = Counter()
        for event in self.recommendation_events:
            for poi_name in str(event["recommended_pois"]).split("|"):
                if poi_name:
                    recommendation_exposure[poi_name] += 1
        exposure_with_zeros = {poi.name: recommendation_exposure[poi.name] for poi in self.pois}
        return {
            "recommender": self.recommender_name,
            "tourists": len(self.agents_by_id),
            "total_visits": total_visits,
            "avg_visits_per_tourist": total_visits / len(self.agents_by_id),
            "avg_satisfaction": float(np.mean(all_satisfaction)) if all_satisfaction else 0.0,
            "avg_sustainability": float(np.mean(sustainability)) if sustainability else 0.0,
            "poi_coverage": sum(count > 0 for count in poi_counts) / len(self.pois),
            "neighbourhood_coverage": len([v for v in self.neighbourhood_visits.values() if v > 0]) / len({poi.neighbourhood for poi in self.pois}),
            "poi_entropy": entropy(poi_counts),
            "district_entropy": entropy(list(self.district_visits.values())),
            "district_gini": gini(self.district_visits),
            "max_poi_utilization": max(utilizations),
            "over_capacity_share": over_capacity_visits / total_visits if total_visits else 0.0,
            "avg_travel_km": float(np.mean([agent.travel_km for agent in self.agents_by_id])),
            "precision_at_5": float(np.mean([event["precision_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "recall_at_5": float(np.mean([event["recall_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "hit_rate_at_5": float(np.mean([event["hit"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "diversity_at_5": float(np.mean([event["diversity_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "novelty_at_5": float(np.mean([event["novelty_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "recommendation_coverage": len(recommendation_exposure) / len(self.pois),
            "exposure_gini": gini(exposure_with_zeros),
        }

    def poi_rows(self) -> list[dict[str, float | str | int]]:
        rows = []
        for poi in self.pois:
            visits = self.poi_visits[poi.id]
            rows.append({
                "recommender": self.recommender_name,
                "poi": poi.name,
                "district": poi.district,
                "neighbourhood": poi.neighbourhood,
                "lat": poi.lat,
                "lon": poi.lon,
                "visits": visits,
                "capacity": poi.capacity,
                "utilization": visits / poi.capacity,
                "popularity": poi.popularity,
                "sustainability": poi.sustainability,
                "local_value": poi.local_value,
            })
        return rows

    def neighbourhood_rows(self) -> list[dict[str, float | str | int]]:
        total = max(1, sum(self.neighbourhood_visits.values()))
        neighbourhoods = sorted({poi.neighbourhood for poi in self.pois})
        return [
            {
                "recommender": self.recommender_name,
                "neighbourhood": neighbourhood,
                "visits": self.neighbourhood_visits[neighbourhood],
                "share": self.neighbourhood_visits[neighbourhood] / total,
            }
            for neighbourhood in neighbourhoods
        ]

    def recommendation_rows(self) -> list[dict[str, float | str | int]]:
        return self.recommendation_events

    def itinerary_rows(self) -> list[dict[str, float | str | int]]:
        return self.itinerary_events


def recommendation_diversity(recommendations: list[POI]) -> float:
    if len(recommendations) < 2:
        return 0.0
    distances = []
    for left, right in combinations(recommendations, 2):
        left_tags = set(left.tags)
        right_tags = set(right.tags)
        distances.append(1 - len(left_tags & right_tags) / len(left_tags | right_tags))
    return float(np.mean(distances))
