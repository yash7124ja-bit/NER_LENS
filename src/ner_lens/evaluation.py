"""Offline, fail-closed evaluation. Never promotes a model or changes road status."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

LABELS = {"disrupted": 1, "not_disrupted_observed": 0}
TIMES = (
    "issued_at",
    "occurred_at",
    "published_at",
    "retrieved_at",
    "verified_at",
    "feature_observed_at",
    "feature_published_at",
    "feature_retrieved_at",
)
REQUIRED = {
    "event_id",
    "segment_id",
    "label",
    "verification_status",
    "evidence_ref",
    "reviewer",
    "season",
    "road_band",
    "event_type",
    "rainfall_mm",
    "synthetic",
    *TIMES,
}


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return result


def read_dataset(path: Path, cutoff: datetime, *, allow_synthetic: bool = False):
    rows, excluded, seen = [], Counter(), set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED <= set(reader.fieldnames or []):
            raise ValueError(f"missing columns: {sorted(REQUIRED - set(reader.fieldnames or []))}")
        for number, raw in enumerate(reader, 2):
            try:
                if raw["synthetic"] not in {"true", "false"}:
                    raise ValueError("synthetic must be true or false")
                if raw["synthetic"] == "true" and not allow_synthetic:
                    raise ValueError("synthetic data forbidden without --allow-synthetic")
                if raw["label"] not in {*LABELS, "unknown", "ambiguous", ""}:
                    raise ValueError("unrecognized label")
                if raw["label"] not in LABELS:
                    excluded[raw["label"] or "missing_label"] += 1
                    continue
                if raw["verification_status"] != "verified":
                    excluded["unverified"] += 1
                    continue
                if any(
                    not raw[key].strip()
                    for key in (
                        "event_id",
                        "segment_id",
                        "evidence_ref",
                        "reviewer",
                        "road_band",
                        "event_type",
                    )
                ):
                    raise ValueError("verified labels require identity and evidence provenance")
                row = dict(raw)
                row.update({key: timestamp(raw[key]) for key in TIMES})
                if (
                    not row["issued_at"]
                    < row["occurred_at"]
                    <= (row["issued_at"] + timedelta(hours=6))
                ):
                    raise ValueError("outcome must occur within six hours after issue time")
                if not row["occurred_at"] <= row["published_at"] <= row["retrieved_at"]:
                    raise ValueError("outcome publication/retrieval chronology is invalid")
                if not row["retrieved_at"] <= row["verified_at"] <= cutoff:
                    raise ValueError("verification must follow retrieval and precede cutoff")
                if not (
                    row["feature_observed_at"]
                    <= row["feature_published_at"]
                    <= row["feature_retrieved_at"]
                    <= row["issued_at"]
                ):
                    raise ValueError("feature temporal leakage or invalid chronology")
                row["season"] = int(raw["season"])
                if row["season"] != row["issued_at"].year:
                    raise ValueError("season must equal issue year (annual monsoon cohort)")
                row["rainfall_mm"] = float(raw["rainfall_mm"]) if raw["rainfall_mm"] else None
                if row["rainfall_mm"] is not None and (
                    not math.isfinite(row["rainfall_mm"]) or row["rainfall_mm"] < 0
                ):
                    raise ValueError("rainfall must be finite and nonnegative or missing")
                row["y"] = LABELS[raw["label"]]
                row["age_hours"] = (
                    row["issued_at"] - row["feature_observed_at"]
                ).total_seconds() / 3600
                row["freshness"] = "fresh" if row["age_hours"] <= 24 else "stale"
                identity = (row["segment_id"], row["issued_at"])
                if identity in seen:
                    raise ValueError("duplicate segment issue-time observation")
                seen.add(identity)
                rows.append(row)
            except (ValueError, TypeError) as error:
                raise ValueError(f"row {number}: {error}") from error
    if not rows:
        raise ValueError("no verified outcome rows; evaluation blocked")
    return rows, dict(excluded)


def split_dataset(rows):
    seasons = sorted({row["season"] for row in rows})
    if len(seasons) < 3:
        raise ValueError("need at least three annual monsoon cohorts")
    splits = {"train": [], "calibration": [], "test": []}
    event_folds = {}
    for row in rows:
        fold = (
            "test"
            if row["season"] == seasons[-1]
            else "calibration"
            if row["season"] == seasons[-2]
            else "train"
        )
        if event_folds.setdefault(row["event_id"], fold) != fold:
            raise ValueError("event group crosses temporal folds")
        splits[fold].append(row)
    for early, late in (("train", "calibration"), ("calibration", "test")):
        boundary = min(row["issued_at"] for row in splits[late])
        if max(row["verified_at"] for row in splits[early]) >= boundary:
            raise ValueError("earlier fold labels were unavailable before next fold")
        if max(row["issued_at"] + timedelta(hours=6) for row in splits[early]) >= boundary:
            raise ValueError("outcome horizons cross fold boundary")
    return splits


def metrics(labels, probabilities):
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("nonempty paired predictions required")
    if any(y not in (0, 1) for y in labels) or any(
        not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities
    ):
        raise ValueError("invalid label or probability")
    n, positives = len(labels), sum(labels)
    groups = defaultdict(list)
    for y, p in zip(labels, probabilities, strict=True):
        groups[p].append(y)
    tp = count = 0
    ap = 0.0
    for p in sorted(groups, reverse=True):
        gained = sum(groups[p])
        tp += gained
        count += len(groups[p])
        if positives:
            ap += (gained / positives) * tp / count
    bins = []
    for index in range(5):
        members = [
            (y, p)
            for y, p in zip(labels, probabilities, strict=True)
            if min(int(p * 5), 4) == index
        ]
        bins.append(
            {
                "count": len(members),
                "mean_probability": sum(p for _, p in members) / len(members) if members else None,
                "observed_rate": sum(y for y, _ in members) / len(members) if members else None,
            }
        )
    return {
        "n": n,
        "prevalence": positives / n,
        "pr_auc_average_precision": ap if positives else None,
        "brier": sum((y - p) ** 2 for y, p in zip(labels, probabilities, strict=True)) / n,
        "calibration_bins": bins,
    }


def evaluate_predictions(rows, probabilities, bootstrap=200, seed=42):
    valid = [(row, p) for row, p in zip(rows, probabilities, strict=True) if p is not None]
    if not valid:
        return {"coverage": 0, "abstained": len(rows), "metrics": None}
    result = metrics([r["y"] for r, _ in valid], [p for _, p in valid])
    groups = defaultdict(list)
    for pair in valid:
        groups[pair[0]["event_id"]].append(pair)
    rng = random.Random(seed)
    samples = []
    for _ in range(bootstrap):
        sampled = [
            pair for group in rng.choices(list(groups), k=len(groups)) for pair in groups[group]
        ]
        samples.append(metrics([r["y"] for r, _ in sampled], [p for _, p in sampled]))

    def interval(values):
        values = sorted(v for v in values if v is not None)
        if len(groups) < 2 or not values:
            return None
        return [values[int((len(values) - 1) * q)] for q in (0.025, 0.975)]

    intervals = {
        key: interval([sample[key] for sample in samples])
        for key in ("brier", "pr_auc_average_precision", "prevalence")
    }
    intervals["calibration_observed_rate"] = [
        interval([sample["calibration_bins"][i]["observed_rate"] for sample in samples])
        for i in range(5)
    ]
    slices = {}
    for field in ("season", "event_type", "road_band", "freshness"):
        slices[field] = {}
        for value in sorted({str(row[field]) for row, _ in valid}):
            members = [(r, p) for r, p in valid if str(r[field]) == value]
            slices[field][value] = metrics([r["y"] for r, _ in members], [p for _, p in members])
    return {
        "coverage": len(valid) / len(rows),
        "abstained": len(rows) - len(valid),
        "metrics": result,
        "event_bootstrap_95_ci": intervals,
        "slices": slices,
    }


def evaluate(path: Path, cutoff: datetime, *, allow_synthetic=False, bootstrap=200):
    if bootstrap < 20:
        raise ValueError("at least 20 bootstrap repetitions required")
    rows, excluded = read_dataset(path, cutoff, allow_synthetic=allow_synthetic)
    splits = split_dataset(rows)
    train, calibration, test = (splits[key] for key in ("train", "calibration", "test"))
    prevalence = sum(r["y"] for r in train) / len(train)
    by_band = defaultdict(list)
    for row in train:
        by_band[row["road_band"]].append(row["y"])
    bands = {key: sum(values) / len(values) for key, values in by_band.items()}
    # Prespecified threshold, never selected against test outcomes.
    rain_threshold = 100.0
    models = {
        "prevalence_by_band": [bands.get(r["road_band"], prevalence) for r in test],
        "rainfall_rule": [
            None
            if r["rainfall_mm"] is None or r["age_hours"] > 24 or r["road_band"] not in bands
            else float(r["rainfall_mm"] >= rain_threshold)
            for r in test
        ],
    }
    logistic = {"status": "unavailable: install scikit-learn optional dependency"}
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        pass
    else:
        if len({r["y"] for r in train}) < 2 or len({r["y"] for r in calibration}) < 2:
            logistic = {"status": "blocked: both classes required in training and calibration"}
        else:

            def features(records):
                return [
                    [
                        r["rainfall_mm"] if r["rainfall_mm"] is not None else 0,
                        float(r["rainfall_mm"] is None),
                        r["age_hours"],
                    ]
                    for r in records
                ]

            model = make_pipeline(StandardScaler(), LogisticRegression(C=1, random_state=42))
            model.fit(features(train), [r["y"] for r in train])
            calibrator = LogisticRegression(C=1, random_state=42)
            calibrator.fit(
                model.decision_function(features(calibration)).reshape(-1, 1),
                [r["y"] for r in calibration],
            )
            predictions = calibrator.predict_proba(
                model.decision_function(features(test)).reshape(-1, 1)
            )[:, 1]
            models["logistic"] = [
                float(p)
                if r["rainfall_mm"] is not None and r["age_hours"] <= 24 and r["road_band"] in bands
                else None
                for r, p in zip(test, predictions, strict=True)
            ]
            logistic = {
                "status": "experimental",
                "features": ["rainfall_mm", "missing", "age_hours"],
                "standardized_coefficients": model[-1].coef_[0].tolist(),
                "intercept": model[-1].intercept_.tolist(),
                "calibration": "sigmoid fit on calibration cohort only",
            }
    synthetic = allow_synthetic or any(r["synthetic"] == "true" for r in rows)
    return {
        "status": "TEST_ONLY_SYNTHETIC" if synthetic else "UNAPPROVED_RETROSPECTIVE_EVALUATION",
        "approved_for_operations": False,
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "cutoff": cutoff.isoformat(),
        "training_cutoff": max(r["verified_at"] for r in train).isoformat(),
        "test_season": max(r["season"] for r in test),
        "excluded": excluded,
        "folds": {
            key: {"rows": len(value), "events": len({r["event_id"] for r in value})}
            for key, value in splits.items()
        },
        "verified_positive_event_groups": len({r["event_id"] for r in rows if r["y"]}),
        "configuration": {
            "seed": 42,
            "bootstrap_repetitions": bootstrap,
            "rainfall_threshold_mm": rain_threshold,
            "freshness_hours": 24,
        },
        "logistic": logistic,
        "results": {name: evaluate_predictions(test, ps, bootstrap) for name, ps in models.items()},
        "limitations": [
            "CSV verification assertions require independent evidence audit.",
            "Annual cohorts require curator confirmation of complete monsoon coverage.",
            "Rainfall-only rule lacks susceptibility; not the full operational Baseline B.",
            "No geographic holdout or operational owner threshold validation.",
            "Fewer than 30 independent positive events is demonstration-only.",
            "Repeated test runs must not be used for model selection.",
        ],
        "abstention_rule": "Missing rain, stale source (>24h), or unseen band: abstain. "
        "Prevalence is a statistical reference only; all outputs remain unapproved.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--cutoff", required=True, type=timestamp)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--bootstrap", type=int, default=200)
    args = parser.parse_args(argv)
    try:
        report = evaluate(
            args.dataset,
            args.cutoff,
            allow_synthetic=args.allow_synthetic,
            bootstrap=args.bootstrap,
        )
    except (ValueError, OSError) as error:
        parser.exit(2, f"Evaluation blocked: {error}\n")
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

