from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from poi_recommender.model import TourismModel


def run_scenario(tourists: int, recommender: str, seed: int, visits_per_tourist: int) -> TourismModel:
    model = TourismModel(
        n_tourists=tourists,
        recommender_name=recommender,
        seed=seed,
        visits_per_tourist=visits_per_tourist,
    )
    model.step()
    return model


def plot_metrics(summary: pd.DataFrame, output_dir: Path) -> None:
    metrics = [
        "avg_satisfaction",
        "avg_sustainability",
        "poi_coverage",
        "district_entropy",
        "district_gini",
        "max_poi_utilization",
        "over_capacity_share",
        "avg_travel_km",
        "precision_at_5",
        "recall_at_5",
        "diversity_at_5",
        "novelty_at_5",
        "exposure_gini",
    ]
    plot_data = summary.melt(id_vars=["recommender", "run"], value_vars=metrics, var_name="metric", value_name="value")
    sns.set_theme(style="whitegrid")
    grid = sns.catplot(
        data=plot_data,
        x="recommender",
        y="value",
        hue="recommender",
        col="metric",
        kind="bar",
        col_wrap=4,
        sharey=False,
        height=3.0,
        aspect=1.1,
        errorbar="sd",
        palette="Set2",
        legend=False,
    )
    grid.set_xticklabels(rotation=30)
    grid.set_titles("{col_name}")
    grid.figure.tight_layout()
    grid.figure.savefig(output_dir / "metrics_comparison.png", dpi=180)
    plt.close(grid.figure)


def plot_neighbourhoods(neighbourhoods: pd.DataFrame, output_dir: Path) -> None:
    top = (
        neighbourhoods.groupby("neighbourhood", as_index=False)["visits"].sum()
        .sort_values("visits", ascending=False)
        .head(18)["neighbourhood"]
    )
    data = neighbourhoods[neighbourhoods["neighbourhood"].isin(top)]
    plt.figure(figsize=(13, 7))
    sns.barplot(data=data, x="visits", y="neighbourhood", hue="recommender", estimator="mean", errorbar=None, palette="Set2")
    plt.title("Average neighbourhood visits by recommender")
    plt.xlabel("Visits")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_dir / "neighbourhood_distribution.png", dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Barcelona sustainable POI recommender simulation.")
    parser.add_argument("--tourists", type=int, default=5000)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--visits-per-tourist", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    args.output.mkdir(exist_ok=True)
    summary_rows = []
    poi_rows = []
    neighbourhood_rows = []
    recommendation_rows = []
    itinerary_rows = []
    recommenders = ["popularity", "personalized", "sustainable"]

    for run in range(args.runs):
        for recommender in recommenders:
            seed = 1000 + run
            print(f"Running {recommender} run {run + 1}/{args.runs} with {args.tourists} tourists")
            model = run_scenario(args.tourists, recommender, seed, args.visits_per_tourist)
            summary = model.summary_metrics()
            summary["run"] = run
            summary_rows.append(summary)
            for row in model.poi_rows():
                row["run"] = run
                poi_rows.append(row)
            for row in model.neighbourhood_rows():
                row["run"] = run
                neighbourhood_rows.append(row)
            for row in model.recommendation_rows():
                row["run"] = run
                recommendation_rows.append(row)
            for row in model.itinerary_rows():
                row["run"] = run
                itinerary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    poi_df = pd.DataFrame(poi_rows)
    neighbourhood_df = pd.DataFrame(neighbourhood_rows)
    recommendation_df = pd.DataFrame(recommendation_rows)
    itinerary_df = pd.DataFrame(itinerary_rows)

    summary_df.to_csv(args.output / "summary_metrics.csv", index=False)
    poi_df.to_csv(args.output / "poi_visits.csv", index=False)
    neighbourhood_df.to_csv(args.output / "neighbourhood_visits.csv", index=False)
    recommendation_df.to_csv(args.output / "recommendations.csv", index=False)
    itinerary_df.to_csv(args.output / "itineraries.csv", index=False)
    recommendation_df.groupby(["recommender", "run"], group_keys=False).head(250).to_csv(
        args.output / "recommendations_sample.csv",
        index=False,
    )
    itinerary_df.groupby(["recommender", "from_district", "to_district"], as_index=False).agg(
        transitions=("tourist_id", "count"),
        avg_distance_km=("distance_km", "mean"),
        avg_travel_time_hours=("travel_time_hours", "mean"),
    ).to_csv(args.output / "movement_transitions.csv", index=False)
    movement_summary = []
    for recommender, group in itinerary_df.groupby("recommender"):
        movement_summary.append({
            "recommender": recommender,
            "avg_distance_km": group["distance_km"].mean(),
            "avg_travel_time_hours": group["travel_time_hours"].mean(),
            "cross_district_share": (
                (group["from_district"] != "Start") & (group["from_district"] != group["to_district"])
            ).mean(),
            "unique_transitions": group[["from_district", "to_district"]].drop_duplicates().shape[0],
            "total_legs": len(group),
        })
    pd.DataFrame(movement_summary).to_csv(args.output / "movement_summary.csv", index=False)
    plot_metrics(summary_df, args.output)
    plot_neighbourhoods(neighbourhood_df, args.output)

    means = summary_df.groupby("recommender").mean(numeric_only=True).round(3)
    print("\nMean results by recommender:")
    print(means[[
        "avg_satisfaction",
        "avg_sustainability",
        "poi_coverage",
        "district_entropy",
        "district_gini",
        "max_poi_utilization",
        "over_capacity_share",
        "avg_travel_km",
        "precision_at_5",
        "recall_at_5",
        "diversity_at_5",
        "novelty_at_5",
        "exposure_gini",
    ]])
    print(f"\nSaved outputs to {args.output.resolve()}")


if __name__ == "__main__":
    main()
