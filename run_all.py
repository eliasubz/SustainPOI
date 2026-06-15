from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _run(stage, cmd):
    print("\n" + "=" * 70)
    print(f">>> {stage}")
    print("    " + " ".join(cmd))
    print("=" * 70, flush=True)
    t0 = time.time()
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"Stage '{stage}' failed with exit code {result.returncode}.")
    print(f"--- {stage} done in {time.time() - t0:.0f}s ---", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run the full recommender study end to end.")
    parser.add_argument("--output", default="outputs", help="Shared output directory for all stages.")
    # Main experiment
    parser.add_argument("--main-tourists", type=int, default=4000)
    parser.add_argument("--main-runs", type=int, default=10)
    # Sensitivity (parameter sweeps)
    parser.add_argument("--sweep-tourists", type=int, default=3000)
    parser.add_argument("--sweep-runs", type=int, default=5)
    # Ablation (mechanism decomposition)
    parser.add_argument("--ablation-tourists", type=int, default=4000)
    parser.add_argument("--ablation-runs", type=int, default=5)
    # Load (volume) sweep
    parser.add_argument("--load-min", type=int, default=4000)
    parser.add_argument("--load-max", type=int, default=10000)
    parser.add_argument("--load-step", type=int, default=1000)
    parser.add_argument("--load-runs", type=int, default=5)
    # Stage toggles
    parser.add_argument("--skip-main", action="store_true")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    py = sys.executable
    overall = time.time()

    if not args.skip_main:
        _run("1/4  Main comparison + statistical analysis", [
            py, str(here / "run_experiment.py"),
            "--tourists", str(args.main_tourists),
            "--runs", str(args.main_runs),
            "--output", args.output,
        ])

    if not args.skip_ablation:
        _run("2/4  Mechanism ablation (sustainable recommender)", [
            py, str(here / "ablation.py"),
            "--tourists", str(args.ablation_tourists),
            "--runs", str(args.ablation_runs),
            "--output", args.output,
        ])

    if not args.skip_sensitivity:
        _run("3/4  Parameter sensitivity (strength + compliance/trust)", [
            py, str(here / "sensitivity.py"),
            "--tourists", str(args.sweep_tourists),
            "--runs", str(args.sweep_runs),
            "--output", args.output,
        ])

    if not args.skip_load:
        _run("4/4  Tourist-volume (saturation) sweep", [
            py, str(here / "load_sweep.py"),
            "--min", str(args.load_min),
            "--max", str(args.load_max),
            "--step", str(args.load_step),
            "--runs", str(args.load_runs),
            "--output", args.output,
        ])

    print(f"\nAll requested stages complete in {time.time() - overall:.0f}s. "
          f"Outputs in {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
