"""Compute USER-01 metrics from real observations; never invent interview results.
Input JSON: [{"completed":true,"seconds":240,"expected":[["1","SHORTAGE"]],
              "reported":[["1","SHORTAGE"]]}] (exactly 10 attempts).
"""
import argparse
import json
import statistics
from pathlib import Path


def evaluate(attempts: list[dict]) -> dict:
    if len(attempts) != 10:
        raise ValueError("USER-01 requires exactly 10 attempts")
    tp = fp = fn = completed = 0
    seconds = []
    for attempt in attempts:
        expected = set(map(tuple, attempt["expected"]))
        if len(expected) != 5:
            raise ValueError("Each attempt requires 5 unique expected item/problem pairs")
        done = attempt["completed"] is True and 0 <= attempt["seconds"] <= 600
        reported = set(map(tuple, attempt["reported"])) if done else set()
        tp += len(expected & reported)
        fp += len(reported - expected)
        fn += len(expected - reported)
        completed += done
        seconds.append(attempt["seconds"] if done else 600)
    recall = tp / (tp + fn) if tp + fn else 0
    precision = tp / (tp + fp) if tp + fp else 0
    median = statistics.median(seconds)
    return {"tp": tp, "fp": fp, "fn": fn, "recall": recall, "precision": precision, "median_seconds": median, "completed": completed, "passed": recall >= .9 and precision >= .9 and completed >= 9 and median <= 300}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(json.loads(args.observations.read_text())), indent=2))
