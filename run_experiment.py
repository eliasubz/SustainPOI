from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from poi_recommender.model import TourismModel
import stats as stats_module


RECOMMENDERS = ["popularity", "personalized", "sustainable"]

# Metrics shown in the printed table and the small-multiple comparison plot.
REPORT_METRICS = [
    "avg_satisfaction",
    "avg_sustainability",
    "poi_coverage",
    "district_entropy",
    "district_gini",
    "max_poi_utilization",
    "peak_occupancy_ratio",
    "temporal_overcap_share",
    "intra_tourist_diversity",
    "wealth_gini",
    "local_spend_share",
    "avg_travel_km",
    "precision_at_5",
    "recall_at_5",
    "diversity_at_5",
    "novelty_at_5",
    "exposure_gini",
]


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
    metrics = [m for m in REPORT_METRICS if m in summary.columns]
    plot_data = summary.melt(
        id_vars=["recommender", "run"], value_vars=metrics, var_name="metric", value_name="value"
    )
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
        errorbar=("ci", 95),
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
    sns.barplot(
        data=data, x="visits", y="neighbourhood", hue="recommender",
        estimator="mean", errorbar=None, palette="Set2",
    )
    plt.title("Average neighbourhood visits by recommender")
    plt.xlabel("Visits")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_dir / "neighbourhood_distribution.png", dpi=180)
    plt.close()


def plot_district_spending(district_df: pd.DataFrame, output_dir: Path) -> None:
    """Where tourist money lands, by district, for each recommender."""
    data = district_df.groupby(["recommender", "district"], as_index=False)["spend_share"].mean()
    plt.figure(figsize=(12, 7))
    sns.barplot(
        data=data, x="spend_share", y="district", hue="recommender",
        estimator="mean", errorbar=None, palette="Set2",
    )
    plt.title("Average share of tourist spending by district")
    plt.xlabel("Share of total spending")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_dir / "district_spending.png", dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Barcelona sustainable POI recommender simulation.")
    parser.add_argument("--tourists", type=int, default=4000)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--visits-per-tourist", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--no-stats", action="store_true", help="Skip statistical analysis step.")
    args = parser.parse_args()

    args.output.mkdir(exist_ok=True)
    summary_rows: list[dict] = []
    poi_rows: list[dict] = []
    neighbourhood_rows: list[dict] = []
    district_rows: list[dict] = []
    recommendation_rows: list[dict] = []
    itinerary_rows: list[dict] = []

    for run in range(args.runs):
        # One seed per run, shared by all three recommenders: identical tourist
        # populations per run (matched/blocked design enabling paired tests).
        seed = args.seed_base + run
        for recommender in RECOMMENDERS:
            print(f"Running {recommender} run {run + 1}/{args.runs} with {args.tourists} tourists")
            model = run_scenario(args.tourists, recommender, seed, args.visits_per_tourist)
            summary = model.summary_metrics()
            summary["run"] = run
            summary_rows.append(summary)
            for collection, rows in (
                (model.poi_rows(), poi_rows),
                (model.neighbourhood_rows(), neighbourhood_rows),
                (model.district_rows(), district_rows),
                (model.recommendation_rows(), recommendation_rows),
                (model.itinerary_rows(), itinerary_rows),
            ):
                for row in collection:
                    row["run"] = run
                    rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    poi_df = pd.DataFrame(poi_rows)
    neighbourhood_df = pd.DataFrame(neighbourhood_rows)
    district_df = pd.DataFrame(district_rows)
    recommendation_df = pd.DataFrame(recommendation_rows)
    itinerary_df = pd.DataFrame(itinerary_rows)

    summary_df.to_csv(args.output / "summary_metrics.csv", index=False)
    poi_df.to_csv(args.output / "poi_visits.csv", index=False)
    neighbourhood_df.to_csv(args.output / "neighbourhood_visits.csv", index=False)
    district_df.to_csv(args.output / "district_spending.csv", index=False)
    recommendation_df.to_csv(args.output / "recommendations.csv", index=False)
    itinerary_df.to_csv(args.output / "itineraries.csv", index=False)
    recommendation_df.groupby(["recommender", "run"], group_keys=False).head(250).to_csv(
        args.output / "recommendations_sample.csv", index=False,
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
    plot_district_spending(district_df, args.output)

    means = summary_df.groupby("recommender").mean(numeric_only=True).round(3)
    table_cols = [m for m in REPORT_METRICS if m in means.columns]
    print("\nMean results by recommender:")
    print(means[table_cols].to_string())

    if not args.no_stats:
        stats_module.analyse(summary_df, args.output)

    print(f"\nSaved outputs to {args.output.resolve()}")


if __name__ == "__main__":
    main()