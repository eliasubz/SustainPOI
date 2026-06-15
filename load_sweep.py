from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from poi_recommender.model import TourismModel


RECOMMENDERS = ["random", "popularity", "personalized", "crowd_aware", "sustainable"]
COLORS = {"popularity": "#db4437", "personalized": "#4285f4", "sustainable": "#0f9d58",
          "crowd_aware": "#9c27b0", "random": "#78909c"}

CONGESTION = [
    ("temporal_overcap_share", "Temporal over-capacity share"),
    ("peak_occupancy_ratio", "Peak occupancy ratio"),
    ("over_capacity_share", "Daily over-capacity share"),
    ("max_poi_utilization", "Max POI utilization"),
]
STRUCTURE = [
    ("district_gini", "District Gini (lower = fairer)"),
    ("wealth_gini", "Wealth Gini (lower = fairer)"),
    ("local_spend_share", "Local spend share"),
    ("avg_satisfaction", "Avg satisfaction"),
]


def run_sweep(volumes, runs, visits_per_tourist, seed_base):
    rows = []
    for n in volumes:
        for recommender in RECOMMENDERS:
            for run in range(runs):
                model = TourismModel(
                    n_tourists=n,
                    recommender_name=recommender,
                    seed=seed_base + run,
                    visits_per_tourist=visits_per_tourist,
                )
                model.step()
                metrics = model.summary_metrics()
                metrics["run"] = run
                rows.append(metrics)
            sub = pd.DataFrame([r for r in rows if r["tourists"] == n and r["recommender"] == recommender])
            print(f"  N={n:6d} {recommender:13s} "
                  f"tempovr={sub['temporal_overcap_share'].mean():.3f}  "
                  f"dgini={sub['district_gini'].mean():.3f}  "
                  f"sat={sub['avg_satisfaction'].mean():.3f}")
    return pd.DataFrame(rows)


def _plot_panel(df, specs, suptitle, path):
    agg = df.groupby(["tourists", "recommender"], as_index=False).mean(numeric_only=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for ax, (metric, title) in zip(axes.ravel(), specs):
        for recommender in RECOMMENDERS:
            sub = agg[agg["recommender"] == recommender].sort_values("tourists")
            ax.plot(sub["tourists"], sub[metric], "o-", color=COLORS[recommender],
                    linewidth=2, label=recommender)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("number of tourists")
        ax.grid(True, alpha=0.3)
    axes.ravel()[0].legend(fontsize=9, loc="best")
    fig.suptitle(suptitle, fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Sweep tourist volume for all three recommenders.")
    parser.add_argument("--min", type=int, default=4000)
    parser.add_argument("--max", type=int, default=10000)
    parser.add_argument("--step", type=int, default=1000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--visits-per-tourist", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)

    volumes = list(range(args.min, args.max + 1, args.step))
    print(f"Sweeping tourist volume {volumes} ({args.runs} runs each, 3 recommenders)...")
    df = run_sweep(volumes, args.runs, args.visits_per_tourist, args.seed_base)

    df.to_csv(args.output / "load_sweep.csv", index=False)
    _plot_panel(df, CONGESTION,
                "Congestion metrics vs tourist volume (advantage saturates under load)",
                args.output / "load_congestion.png")
    _plot_panel(df, STRUCTURE,
                "Distributional metrics vs tourist volume (advantage persists under load)",
                args.output / "load_distribution.png")
    print(f"\nSaved load_sweep.csv, load_congestion.png and load_distribution.png to {args.output.resolve()}")


if __name__ == "__main__":
    main()
