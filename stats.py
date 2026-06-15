from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps


# Metrics analysed for significance. Kept to the headline city-management and
# recommendation-quality outcomes so the corrected p-values stay interpretable.
KEY_METRICS = [
    "avg_satisfaction",
    "avg_sustainability",
    "poi_coverage",
    "district_gini",
    "district_entropy",
    "exposure_gini",
    "peak_occupancy_ratio",
    "temporal_overcap_share",
    "wealth_gini",
    "local_spend_share",
    "precision_at_5",
    "diversity_at_5",
    "novelty_at_5",
]

RECOMMENDERS = ["random", "popularity", "personalized", "crowd_aware", "sustainable"]

#Return (mean, ci_low, ci_high, std) using a t-interval across runs. CI means Confidence Interval
def _ci95(values):
    n = len(values)
    mean = float(np.mean(values))
    if n < 2:
        return mean, mean, mean, 0.0
    sd = float(np.std(values, ddof=1))
    se = sd / np.sqrt(n)
    margin = float(sps.t.ppf(0.975, df=n - 1)) * se
    return mean, mean - margin, mean + margin, sd


def confidence_intervals(summary):
    rows = []
    metrics = [m for m in KEY_METRICS if m in summary.columns]
    for recommender in RECOMMENDERS:
        sub = summary[summary["recommender"] == recommender]
        if sub.empty:
            continue
        for metric in metrics:
            values = sub[metric].to_numpy(dtype=float)
            mean, lo, hi, sd = _ci95(values)
            rows.append({
                "recommender": recommender,
                "metric": metric,
                "n_runs": len(values),
                "mean": round(mean, 4),
                "ci95_low": round(lo, 4),
                "ci95_high": round(hi, 4),
                "std": round(sd, 4),
            })
    return pd.DataFrame(rows)


def _paired_cohens_d(diff):
    sd = np.std(diff, ddof=1)
    if sd == 0:
        return 0.0
    return float(np.mean(diff) / sd)

# Apply Holm-Bonferroni across a family of comparisons (in place).
def _holm_correction(pairs):
    order = sorted(range(len(pairs)), key=lambda i: pairs[i]["p_value"])
    m = len(pairs)
    prev = 0.0
    for rank, idx in enumerate(order):
        adjusted = (m - rank) * pairs[idx]["p_value"]
        adjusted = min(1.0, max(adjusted, prev))  # enforce monotonicity
        prev = adjusted
        pairs[idx]["p_holm"] = round(adjusted, 5)
        pairs[idx]["significant_5pct"] = bool(adjusted < 0.05)


def pairwise_tests(summary):
    rows = []
    metrics = [m for m in KEY_METRICS if m in summary.columns]
    pivot = {
        rec: summary[summary["recommender"] == rec].sort_values("run")
        for rec in RECOMMENDERS
    }
    for metric in metrics:
        metric_pairs = []
        for a, b in combinations(RECOMMENDERS, 2):
            va = pivot[a][metric].to_numpy(dtype=float)
            vb = pivot[b][metric].to_numpy(dtype=float)
            n = min(len(va), len(vb))
            if n < 2:
                continue
            va, vb = va[:n], vb[:n]
            diff = va - vb
            # Paired t-test; guard the degenerate zero-variance case.
            if np.allclose(diff, diff[0]):
                t_stat = np.inf if diff[0] != 0 else 0.0
                p_value = 0.0 if diff[0] != 0 else 1.0
            else:
                t_stat, p_value = sps.ttest_rel(va, vb)
            metric_pairs.append({
                "metric": metric,
                "comparison": f"{a}_vs_{b}",
                "mean_a": round(float(np.mean(va)), 4),
                "mean_b": round(float(np.mean(vb)), 4),
                "mean_diff": round(float(np.mean(diff)), 4),
                "t_stat": round(float(t_stat), 3),
                "p_value": round(float(p_value), 5),
                "cohens_d": round(_paired_cohens_d(diff), 3),
                "n_runs": n,
            })
        _holm_correction(metric_pairs)
        rows.extend(metric_pairs)
    return pd.DataFrame(rows)


def _print_console_summary(ci, tests):
    print("\n95% confidence intervals (mean across runs):")
    for metric in ci["metric"].unique():
        sub = ci[ci["metric"] == metric]
        cells = "  ".join(
            f"{r.recommender[:4]}={r['mean']:.3f}[{r['ci95_low']:.3f},{r['ci95_high']:.3f}]"
            for _, r in sub.iterrows()
        )
        print(f"  {metric:24s} {cells}")

    print("\nPaired t-tests (Holm-corrected within each metric, * = p<0.05):")
    for metric in tests["metric"].unique():
        sub = tests[tests["metric"] == metric]
        print(f"  {metric}:")
        for _, r in sub.iterrows():
            star = "*" if r["significant_5pct"] else " "
            print(
                f"    {star} {r['comparison']:30s} "
                f"diff={r['mean_diff']:+.3f}  d={r['cohens_d']:+.2f}  "
                f"p_holm={r['p_holm']:.4f}"
            )


def analyse(summary, output_dir):
    output_dir.mkdir(exist_ok=True)
    ci = confidence_intervals(summary)
    tests = pairwise_tests(summary)
    ci.to_csv(output_dir / "confidence_intervals.csv", index=False)
    tests.to_csv(output_dir / "statistical_tests.csv", index=False)
    _print_console_summary(ci, tests)
    print(f"\nSaved confidence_intervals.csv and statistical_tests.csv to {output_dir.resolve()}")
    return ci, tests


def main():
    parser = argparse.ArgumentParser(description="Statistical analysis of recommender comparison.")
    parser.add_argument("--input", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    summary_path = args.input / "summary_metrics.csv"
    if not summary_path.exists():
        raise SystemExit(f"Could not find {summary_path}. Run run_experiment.py first.")
    summary = pd.read_csv(summary_path)
    if "run" not in summary.columns:
        raise SystemExit("summary_metrics.csv has no 'run' column; cannot pair across runs.")
    analyse(summary, args.input)


if __name__ == "__main__":
    main()
