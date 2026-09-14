import csv
import json

import pytest

from ner_lens.evaluation import REQUIRED, evaluate, main, metrics, timestamp


def dataset(tmp_path, mutate=None):
    rows = []
    for year in (2022, 2023, 2024):
        for index in range(4):
            issue = f"{year}-07-0{index + 1}T00:00:00Z"
            row = dict.fromkeys(REQUIRED, "")
            row.update(
                event_id=f"event-{year}-{index}",
                segment_id=f"segment-{index}",
                label="disrupted" if index % 2 else "not_disrupted_observed",
                verification_status="verified",
                evidence_ref="synthetic://fixture",
                reviewer="test-only",
                season=str(year),
                road_band="hill",
                event_type="landslide",
                rainfall_mm=str(index * 60),
                synthetic="true",
                issued_at=issue,
                occurred_at=issue.replace("00:00", "03:00"),
                published_at=issue.replace("00:00", "04:00"),
                retrieved_at=issue.replace("00:00", "05:00"),
                verified_at=issue.replace("00:00", "06:00"),
                feature_observed_at=issue,
                feature_published_at=issue,
                feature_retrieved_at=issue,
            )
            rows.append(row)
    if mutate:
        mutate(rows)
    path = tmp_path / "TEST_ONLY.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(REQUIRED))
        writer.writeheader()
        writer.writerows(rows)
    return path


CUTOFF = timestamp("2025-01-01T00:00:00Z")


def test_metrics_and_tied_ranking():
    result = metrics([0, 1], [0.2, 0.8])
    assert result["brier"] == pytest.approx(0.04)
    assert result["pr_auc_average_precision"] == 1
    assert metrics([0, 1], [0.5, 0.5])["pr_auc_average_precision"] == 0.5
    assert metrics([0, 0], [0.1, 0.9])["pr_auc_average_precision"] is None


def test_reproducible_evaluation_and_optional_logistic(tmp_path):
    path = dataset(tmp_path)
    report = evaluate(path, CUTOFF, allow_synthetic=True, bootstrap=20)
    assert report == evaluate(path, CUTOFF, allow_synthetic=True, bootstrap=20)
    assert report["status"] == "TEST_ONLY_SYNTHETIC"
    assert report["approved_for_operations"] is False
    assert report["test_season"] == 2024
    assert report["results"]["prevalence_by_band"]["metrics"]["brier"] == 0.25
    pytest.importorskip("sklearn")
    assert report["logistic"]["status"] == "experimental"
    assert report["results"]["logistic"]["metrics"]["n"] == 4


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda rs: rs[0].update(feature_retrieved_at="2022-07-01T01:00:00Z"), "leakage"),
        (lambda rs: rs[4].update(event_id=rs[0]["event_id"]), "crosses temporal"),
        (lambda rs: rs[0].update(verified_at="2023-07-01T00:00:00Z"), "unavailable"),
        (lambda rs: rs[0].update(rainfall_mm="NaN"), "finite"),
    ],
)
def test_rejects_leakage_and_bad_values(tmp_path, mutation, match):
    with pytest.raises(ValueError, match=match):
        evaluate(dataset(tmp_path, mutation), CUTOFF, allow_synthetic=True)


def test_missing_and_unknown_are_not_negative(tmp_path):
    def mutate(rows):
        rows[0]["label"] = "unknown"
        rows[-1]["rainfall_mm"] = ""

    report = evaluate(dataset(tmp_path, mutate), CUTOFF, allow_synthetic=True, bootstrap=20)
    assert report["excluded"] == {"unknown": 1}
    assert report["results"]["rainfall_rule"]["abstained"] == 1


def test_cli_fails_closed_and_writes_only_explicit_test_run(tmp_path):
    path = dataset(tmp_path)
    output = tmp_path / "model-card.json"
    args = [str(path), "--cutoff", CUTOFF.isoformat(), "--output", str(output)]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert not output.exists()
    assert main([*args, "--allow-synthetic", "--bootstrap", "20"]) == 0
    assert json.loads(output.read_text())["approved_for_operations"] is False


def test_no_verified_data_blocks(tmp_path):
    def mutate(rows):
        for row in rows:
            row["synthetic"] = "false"
            row["verification_status"] = "pending"

    with pytest.raises(ValueError, match="no verified"):
        evaluate(dataset(tmp_path, mutate), CUTOFF)
