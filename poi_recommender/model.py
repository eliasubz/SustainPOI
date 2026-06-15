from __future__ import annotations

import heapq
from collections import Counter, defaultdict
from itertools import combinations, count
from statistics import median

import numpy as np
from mesa import Agent, Model

from .data import INTERESTS, POI, load_barcelona_pois
from .recommenders import entropy, get_recommender, gini, haversine_km


CITY_CENTER = (41.3874, 2.1686)

# Reference window (hours) used to convert a POI's daily-throughput capacity into an
# instantaneous concurrent capacity via Little's Law:  L = daily_capacity * dwell / window.
# Roughly the span over which the simulated tourist population is active.
ACTIVE_DAY_WINDOW = 10.0

# Local-economy spend generated per visit on top of the entry price, scaled by the POI's
# local value (markets, neighbourhood high streets, etc. capture more local spending).
LOCAL_SPEND_SCALE = 18.0


def _sample_beta_mean(rng, mean, concentration = 6.0):
    mean = float(np.clip(mean, 1e-3, 1 - 1e-3))
    a = mean * concentration
    b = (1.0 - mean) * concentration
    return float(rng.beta(a, b))


class TouristAgent(Agent):
    def __init__(self, model):
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
        self.time_available = float(np.clip(rng.normal(7.0, 1.4), 3.0, 11.0))

        # Temporal: when the tourist starts their day and when it ends.
        self.start_hour = float(np.clip(rng.normal(10.0, 1.0), 8.5, 12.5))
        self.day_end = min(23.0, self.start_hour + self.time_available)

        # Behavioural realism: how reliably they follow the app, and how much they trust
        # a sustainability nudge that asks them to give up some personal utility.
        self.compliance = _sample_beta_mean(rng, model.compliance_mean)
        self.trust_in_sustainability = _sample_beta_mean(rng, model.trust_mean)

        self.current_lat, self.current_lon = CITY_CENTER
        self.visited: list[POI] = []
        self.visited_ids: set[int] = set()
        self.satisfaction_scores: list[float] = []
        self.travel_km = 0.0
        self.visits_done = 0
        self.last_arrival_hour = self.start_hour
        self.tourist_id = 0

        # A tourist's personal fallback set: their favourite POIs city-wide. A non-compliant
        # tourist ignores the app and gravitates to these instead.
        ranked = sorted(model.pois, key=self.interest_match, reverse=True)
        self.personal_candidates = ranked[:10]

    @staticmethod
    def _sample_interests(rng):
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


    def _travel_time(self, distance_km):
        speeds = {"walking": 4.2, "public_transport": 12.0, "taxi": 18.0}
        return distance_km / speeds[self.mobility_mode]

    def _follows_recommender(self, model):
        prob = self.compliance
        # Following a sustainability nudge requires trust, because it can cost personal utility.
        if model.recommender_name == "sustainable":
            prob *= 0.35 + 0.65 * self.trust_in_sustainability
        return bool(model.rng.random() < prob)

    def _feasible(self, poi, time_now, model):
        if poi.id in self.visited_ids:
            return False
        distance = haversine_km(self.current_lat, self.current_lon, poi.lat, poi.lon)
        arrival = time_now + self._travel_time(distance)
        # Opening hours: must arrive after opening and finish before closing.
        if arrival < poi.open_hour:
            return False
        finish = arrival + poi.duration
        if finish > poi.close_hour or finish > self.day_end:
            return False
        # Budget: a tourist usually skips POIs they cannot afford.
        if poi.price > self.budget and model.rng.random() < 0.80:
            return False
        # Crowd aversion: probabilistically skip POIs that are busy right now.
        crowding = model.current_crowding(poi)
        skip_probability = min(0.75, crowding * self.crowd_aversion * 0.55)
        if model.rng.random() < skip_probability:
            return False
        return True

    def decide(self, time_now, model):
        candidates = model.recommender.recommend(self, model, k=model.recommendation_k + 6)
        candidates = [poi for poi in candidates if poi.id not in self.visited_ids]
        recommendations = candidates[: model.recommendation_k]

        followed = self._follows_recommender(model)
        if followed:
            feasible = [poi for poi in recommendations if self._feasible(poi, time_now, model)]
            chosen = feasible[0] if feasible else None
        else:
            # Defect: consider the recommended list plus personal favourites, pick by own taste.
            pool = {poi.id: poi for poi in recommendations}
            for poi in self.personal_candidates:
                pool.setdefault(poi.id, poi)
            feasible = [poi for poi in pool.values() if self._feasible(poi, time_now, model)]
            feasible.sort(key=self.interest_match, reverse=True)
            chosen = feasible[0] if feasible else None
        return recommendations, chosen, followed

    def interest_match(self, poi):
        return sum(self.interests[tag] for tag in poi.tags) / len(poi.tags)

    def satisfaction(self, poi, distance_km, crowding):
        interest_match = self.interest_match(poi)
        price_fit = 1.0 if poi.price <= self.budget else max(0.0, 1 - (poi.price - self.budget) / 40)
        distance_fit = max(0.0, 1 - max(0.0, distance_km - self.walking_tolerance) / 8)
        return float(np.clip(
            0.56 * interest_match + 0.15 * price_fit + 0.14 * distance_fit + 0.15 * (1 - min(1.0, crowding)),
            0,
            1,
        ))

    def primary_interests(self):
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
        sustainability_strength: float = 1.0,
        compliance_mean: float = 0.72,
        trust_mean: float = 0.6,
    ) -> None:
        super().__init__(rng=seed)
        self.rng = np.random.default_rng(seed)
        self.pois = load_barcelona_pois()
        self.districts = sorted({poi.district for poi in self.pois})
        self.recommender = get_recommender(recommender_name, sustainability_strength=sustainability_strength)
        self.recommender_name = recommender_name
        self.visits_per_tourist = visits_per_tourist
        self.recommendation_k = recommendation_k
        self.sustainability_strength = sustainability_strength
        self.compliance_mean = compliance_mean
        self.trust_mean = trust_mean

        # Instantaneous concurrent capacity per POI (Little's Law from daily capacity).
        self.instant_capacity = {
            poi.id: max(1.0, poi.capacity * poi.duration / ACTIVE_DAY_WINDOW) for poi in self.pois
        }
        self.local_value_median = median(poi.local_value for poi in self.pois)

        # Live (instantaneous) state during the simulated day.
        self.occupancy: Counter[int] = Counter()
        self.peak_occupancy_ratio = 0.0
        self.over_capacity_arrivals = 0

        # Cumulative state used for end-of-day evaluation.
        self.poi_visits: Counter[int] = Counter()
        self.district_visits: Counter[str] = Counter({district: 0 for district in self.districts})
        self.neighbourhood_visits: Counter[str] = Counter()
        self.poi_satisfaction: defaultdict[int, list[float]] = defaultdict(list)
        self.district_spending: Counter[str] = Counter({district: 0.0 for district in self.districts})
        self.neighbourhood_spending: Counter[str] = Counter()
        self.total_spend = 0.0
        self.local_captured_spend = 0.0

        self.recommendation_events: list[dict[str, float | str | int]] = []
        self.itinerary_events: list[dict[str, float | str | int]] = []

        self.agents_by_id = [TouristAgent(self) for _ in range(n_tourists)]
        for tourist_id, agent in enumerate(self.agents_by_id):
            agent.tourist_id = tourist_id


    def current_crowding(self, poi):
        return self.occupancy[poi.id] / self.instant_capacity[poi.id]

    # Run a full simulated day as a time-ordered discrete-event simulation.
    def step(self):
        counter = count()
        heap: list[tuple[float, int, str, object]] = []
        for agent in self.agents_by_id:
            heapq.heappush(heap, (agent.start_hour, next(counter), "decide", agent))

        while heap:
            time_now, _, kind, payload = heapq.heappop(heap)
            if kind == "depart":
                self.occupancy[int(payload)] -= 1
                continue

            agent: TouristAgent = payload  # type: ignore[assignment]
            if agent.visits_done >= self.visits_per_tourist or time_now >= agent.day_end:
                continue

            recommendations, chosen, followed = agent.decide(time_now, self)
            self.record_recommendation(agent, agent.visits_done, recommendations, chosen, followed)
            if chosen is None:
                continue

            distance = haversine_km(agent.current_lat, agent.current_lon, chosen.lat, chosen.lon)
            travel_time = agent._travel_time(distance)
            arrival = time_now + travel_time
            previous = agent.visited[-1] if agent.visited else None

            occ_before = self.occupancy[chosen.id]
            if occ_before >= self.instant_capacity[chosen.id]:
                self.over_capacity_arrivals += 1
            self.occupancy[chosen.id] += 1
            ratio = self.occupancy[chosen.id] / self.instant_capacity[chosen.id]
            self.peak_occupancy_ratio = max(self.peak_occupancy_ratio, ratio)

            agent.current_lat, agent.current_lon = chosen.lat, chosen.lon
            agent.travel_km += distance
            agent.visited.append(chosen)
            agent.visited_ids.add(chosen.id)
            agent.satisfaction_scores.append(agent.satisfaction(chosen, distance, ratio))
            agent.visits_done += 1
            agent.last_arrival_hour = arrival

            self.record_visit(chosen)
            self.record_spending(chosen)
            self.poi_satisfaction[chosen.id].append(agent.satisfaction_scores[-1])
            self.record_itinerary(agent, agent.visits_done - 1, previous, chosen, distance, travel_time, arrival)

            depart_time = arrival + chosen.duration
            heapq.heappush(heap, (depart_time, next(counter), "depart", chosen.id))
            heapq.heappush(heap, (depart_time, next(counter), "decide", agent))


    def record_visit(self, poi):
        self.poi_visits[poi.id] += 1
        self.district_visits[poi.district] += 1
        self.neighbourhood_visits[poi.neighbourhood] += 1

    def record_spending(self, poi):
        spend = poi.price + LOCAL_SPEND_SCALE * poi.local_value
        self.district_spending[poi.district] += spend
        self.neighbourhood_spending[poi.neighbourhood] += spend
        self.total_spend += spend
        if poi.local_value >= self.local_value_median:
            self.local_captured_spend += spend

    def record_recommendation(
        self,
        tourist,
        sequence,
        recommendations,
        chosen,
        followed):

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
            "compliance": tourist.compliance,
            "trust": tourist.trust_in_sustainability,
            "followed": int(followed),
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
        tourist,
        sequence,
        previous,
        chosen,
        distance_km,
        travel_time_hours,
        arrival_hour):
    
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
            "arrival_hour": arrival_hour,
            "mobility_mode": tourist.mobility_mode,
        })


    def _intra_tourist_diversity(self):
        diversities = [
            recommendation_diversity(agent.visited)
            for agent in self.agents_by_id
            if len(agent.visited) >= 2
        ]
        return float(np.mean(diversities)) if diversities else 0.0

    def summary_metrics(self):
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
        recommendation_exposure: Counter[str] = Counter()
        for event in self.recommendation_events:
            for poi_name in str(event["recommended_pois"]).split("|"):
                if poi_name:
                    recommendation_exposure[poi_name] += 1
        exposure_with_zeros = {poi.name: recommendation_exposure[poi.name] for poi in self.pois}
        followed_flags = [event["followed"] for event in self.recommendation_events]
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
            "peak_occupancy_ratio": self.peak_occupancy_ratio,
            "temporal_overcap_share": self.over_capacity_arrivals / total_visits if total_visits else 0.0,
            "avg_travel_km": float(np.mean([agent.travel_km for agent in self.agents_by_id])),
            "intra_tourist_diversity": self._intra_tourist_diversity(),
            "wealth_gini": gini(self.district_spending),
            "wealth_entropy": entropy([int(round(v)) for v in self.district_spending.values()]),
            "neighbourhood_spend_gini": gini(self.neighbourhood_spending),
            "local_spend_share": self.local_captured_spend / self.total_spend if self.total_spend else 0.0,
            "avg_compliance": float(np.mean(followed_flags)) if followed_flags else 0.0,
            "precision_at_5": float(np.mean([event["precision_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "recall_at_5": float(np.mean([event["recall_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "hit_rate_at_5": float(np.mean([event["hit"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "diversity_at_5": float(np.mean([event["diversity_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "novelty_at_5": float(np.mean([event["novelty_at_k"] for event in self.recommendation_events])) if self.recommendation_events else 0.0,
            "recommendation_coverage": len(recommendation_exposure) / len(self.pois),
            "exposure_gini": gini(exposure_with_zeros),
        }

    def poi_rows(self):
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

    def neighbourhood_rows(self):
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

    def district_rows(self):
        total_visits = max(1, sum(self.district_visits.values()))
        total_spend = max(1e-9, self.total_spend)
        return [
            {
                "recommender": self.recommender_name,
                "district": district,
                "visits": self.district_visits[district],
                "visit_share": self.district_visits[district] / total_visits,
                "spend": self.district_spending[district],
                "spend_share": self.district_spending[district] / total_spend,
            }
            for district in self.districts
        ]

    def recommendation_rows(self):
        return self.recommendation_events

    def itinerary_rows(self):
        return self.itinerary_events


def recommendation_diversity(recommendations):
    if len(recommendations) < 2:
        return 0.0
    distances = []
    for left, right in combinations(recommendations, 2):
        left_tags = set(left.tags)
        right_tags = set(right.tags)
        distances.append(1 - len(left_tags & right_tags) / len(left_tags | right_tags))
    return float(np.mean(distances))
