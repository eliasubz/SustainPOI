"""Ablation of the sustainable recommender's mechanisms.

The sustainable recommender bundles three distinct mechanisms, all scaled
together by its strength parameter:

  * value     -- sustainability + local + cultural value (and a small
                 anti-popularity term);
  * spread    -- a bonus for under-visited districts (direct geographic
                 spreading);
  * decongest -- a bonus for low instantaneous crowding.

Because they move together, the headline comparison cannot say which mechanism
produces which outcome. This script runs the recommender with each mechanism in
isolation and with all three on, so every metric can be attributed to its cause.

To isolate the *routing* effect cleanly, all four arms are run under an identical
tourist-behaviour model (none of them trigger the sustainability-specific trust
discounting that the deployed `sustainable` recommender is subject to), so the
"all mechanisms" arm here is slightly more effective than the headline
`sustainable` number -- the comparison of interest is *between* the arms.

Run: `python ablation.py --tourists 4000 --runs 5 --output outputs`.
A higher tourist count is the default because the decongestion mechanism only
matters once POIs approach their capacity.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from poi_recommender.model import TourismModel


ARMS = ["sust_all", "sust_value", "sust_spread", "sust_decongest"]
ARM_LABELS = {
    "sust_all": "All mechanisms",
    "sust_value": "Value only",
    "sust_spread": "Spread only",
    "sust_decongest": "Decongest only",
}
ARM_COLORS = {
    "sust_all": "#0f9d58",
    "sust_value": "#1565c0",
    "sust_spread": "#ef6c00",
    "sust_decongest": "#6a1b9a",
}

PANELS = [
    ("district_gini", "District Gini (lower = fairer)"),
    ("wealth_gini", "Wealth Gini (lower = fairer)"),
    ("temporal_overcap_share", "Temporal over-capacity share"),
    ("local_spend_share", "Local spend share"),
    ("avg_sustainability", "Avg sustainability"),
    ("avg_satisfaction", "Avg satisfaction"),
]


def run_ablation(tourists: int, runs: int, visits_per_tourist: int, seed_base: int) -> pd.DataFrame:
    rows = []
    for arm in ARMS:
        for run in range(runs):
            model = TourismModel(
                n_tourists=tourists,
                recommender_name=arm,
                seed=seed_base + run,
                visits_per_tourist=visits_per_tourist,
            )
            model.step()
            metrics = model.summary_metrics()
            metrics["arm"] = arm
            metrics["run"] = run
            rows.append(metrics)
        sub = pd.DataFrame([r for r in rows if r["arm"] == arm])
        print(f"  {arm:15s} dgini={sub['district_gini'].mean():.3f}  "
              f"sust={sub['avg_sustainability'].mean():.3f}  "
              f"local={sub['local_spend_share'].mean():.3f}  "
              f"tempovr={sub['temporal_overcap_share'].mean():.3f}  "
              f"sat={sub['avg_satisfaction'].mean():.3f}")
    return pd.DataFrame(rows)


def plot_ablation(df: pd.DataFrame, output_dir: Path) -> None:
    agg = df.groupby("arm")[[m for m, _ in PANELS]].mean()
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    labels = [ARM_LABELS[a] for a in ARMS]
    colors = [ARM_COLORS[a] for a in ARMS]
    for ax, (metric, title) in zip(axes.ravel(), PANELS):
        values = [agg.loc[a, metric] for a in ARMS]
        ax.bar(range(len(ARMS)), values, color=colors)
        ax.set_xticks(range(len(ARMS)))
        ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.grid(True, axis="y", alpha=0.3)
        for i, v in enumerate(values):
            ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle("Mechanism ablation of the sustainable recommender", fontsize=13)
    fig.tight_layout()
    fig.savefig(output_dir / "ablation.png", dpi=170)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablate the sustainable recommender's mechanisms.")
    parser.add_argument("--tourists", type=int, default=4000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--visits-per-tourist", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)

    print(f"Running mechanism ablation ({args.runs} runs each at {args.tourists} tourists)...")
    df = run_ablation(args.tourists, args.runs, args.visits_per_tourist, args.seed_base)

    df.to_csv(args.output / "ablation.csv", index=False)
    summary = df.groupby("arm")[[m for m, _ in PANELS]].mean().round(4)
    summary = summary.reindex(ARMS)
    summary.to_csv(args.output / "ablation_summary.csv")
    plot_ablation(df, args.output)

    print("\nMechanism contribution (means):")
    print(summary.to_string())
    print(f"\nSaved ablation.csv, ablation_summary.csv and ablation.png to {args.output.resolve()}")


if __name__ == "__main__":
    main()
