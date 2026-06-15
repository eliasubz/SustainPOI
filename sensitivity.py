from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from poi_recommender.model import TourismModel


STRENGTH_GRID = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
COMPLIANCE_GRID = [0.2, 0.4, 0.6, 0.8, 1.0]

# Metrics tracked across both sweeps.
TRACK = [
    "avg_satisfaction",
    "avg_sustainability",
    "poi_coverage",
    "district_gini",
    "wealth_gini",
    "local_spend_share",
    "temporal_overcap_share",
]


def _mean_metrics(records):
    df = pd.DataFrame(records)
    return {m: float(df[m].mean()) for m in TRACK if m in df.columns}


def sweep_strength(tourists, runs, seed_base):
    rows = []
    for strength in STRENGTH_GRID:
        per_run = []
        for run in range(runs):
            model = TourismModel(
                n_tourists=tourists,
                recommender_name="sustainable",
                seed=seed_base + run,
                sustainability_strength=strength,
            )
            model.step()
            per_run.append(model.summary_metrics())
        agg = _mean_metrics(per_run)
        agg["sustainability_strength"] = strength
        rows.append(agg)
        print(f"  strength={strength:.2f}  dgini={agg['district_gini']:.3f}  "
              f"sat={agg['avg_satisfaction']:.3f}  sust={agg['avg_sustainability']:.3f}")
    return pd.DataFrame(rows)


def reference_lines(tourists, runs, seed_base):
    refs = {}
    for recommender in ("personalized", "popularity"):
        per_run = []
        for run in range(runs):
            model = TourismModel(
                n_tourists=tourists, recommender_name=recommender, seed=seed_base + run,
            )
            model.step()
            per_run.append(model.summary_metrics())
        refs[recommender] = _mean_metrics(per_run)
    return refs


def sweep_compliance(tourists, runs, seed_base):
    rows = []
    for level in COMPLIANCE_GRID:
        per_run = []
        for run in range(runs):
            model = TourismModel(
                n_tourists=tourists,
                recommender_name="sustainable",
                seed=seed_base + run,
                compliance_mean=level,
                trust_mean=level,
            )
            model.step()
            per_run.append(model.summary_metrics())
        agg = _mean_metrics(per_run)
        agg["compliance_trust_mean"] = level
        rows.append(agg)
        print(f"  compliance/trust={level:.2f}  dgini={agg['district_gini']:.3f}  "
              f"sust={agg['avg_sustainability']:.3f}  sat={agg['avg_satisfaction']:.3f}")
    return rows_to_df(rows)


def rows_to_df(rows):
    return pd.DataFrame(rows)


def plot_strength(df, refs, output_dir):
    panels = [
        ("district_gini", "District Gini (lower = fairer)"),
        ("avg_satisfaction", "Avg satisfaction"),
        ("avg_sustainability", "Avg sustainability"),
        ("poi_coverage", "POI coverage"),
        ("wealth_gini", "Wealth Gini (lower = fairer)"),
        ("local_spend_share", "Local spend share"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    colors = {"personalized": "#4285f4", "popularity": "#db4437"}
    for ax, (metric, title) in zip(axes.ravel(), panels):
        ax.plot(df["sustainability_strength"], df[metric], "o-", color="#0f9d58",
                linewidth=2, label="sustainable (swept)")
        for rec, style in colors.items():
            if metric in refs.get(rec, {}):
                ax.axhline(refs[rec][metric], linestyle="--", color=style, alpha=0.8, label=rec)
        ax.axvline(1.0, color="#999", linewidth=1, alpha=0.6)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("sustainability strength (lambda)")
        ax.grid(True, alpha=0.3)
    axes.ravel()[0].legend(fontsize=8, loc="best")
    fig.suptitle("Sensitivity to sustainability strength (lambda=1 is the default)", fontsize=13)
    fig.tight_layout()
    fig.savefig(output_dir / "sensitivity_strength.png", dpi=170)
    plt.close(fig)


def plot_compliance(df, refs, output_dir):
    panels = [
        ("district_gini", "District Gini (lower = fairer)"),
        ("avg_sustainability", "Avg sustainability"),
        ("avg_satisfaction", "Avg satisfaction"),
        ("local_spend_share", "Local spend share"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (metric, title) in zip(axes.ravel(), panels):
        ax.plot(df["compliance_trust_mean"], df[metric], "s-", color="#0f9d58", linewidth=2,
                label="sustainable")
        if metric in refs.get("personalized", {}):
            ax.axhline(refs["personalized"][metric], linestyle="--", color="#4285f4",
                       alpha=0.8, label="personalized (full compliance)")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("mean compliance / trust")
        ax.grid(True, alpha=0.3)
    axes.ravel()[0].legend(fontsize=8, loc="best")
    fig.suptitle("Sensitivity to tourist compliance and trust", fontsize=13)
    fig.tight_layout()
    fig.savefig(output_dir / "sensitivity_compliance.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Sensitivity analysis for the sustainable recommender.")
    parser.add_argument("--tourists", type=int, default=3000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed-base", type=int, default=2000)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)

    print("Sweeping sustainability strength...")
    strength_df = sweep_strength(args.tourists, args.runs, args.seed_base)
    print("Computing baseline reference lines...")
    refs = reference_lines(args.tourists, args.runs, args.seed_base)
    print("Sweeping compliance / trust...")
    compliance_df = sweep_compliance(args.tourists, args.runs, args.seed_base)

    strength_df.round(4).to_csv(args.output / "sensitivity_strength.csv", index=False)
    compliance_df.round(4).to_csv(args.output / "sensitivity_compliance.csv", index=False)
    plot_strength(strength_df, refs, args.output)
    plot_compliance(compliance_df, refs, args.output)
    print(f"\nSaved sensitivity outputs to {args.output.resolve()}")


if __name__ == "__main__":
    main()
