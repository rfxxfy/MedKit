import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("pilot", Path(__file__).resolve().parents[2] / "scripts" / "evaluate_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_unfinished_attempt_counts_all_five_missed_problems():
    pairs = [[str(i), "SHORTAGE"] for i in range(5)]
    attempts = [{"completed": True, "seconds": 240, "expected": pairs, "reported": pairs + pairs} for _ in range(9)]
    attempts.append({"completed": False, "seconds": 12, "expected": pairs, "reported": pairs})
    result = pilot.evaluate(attempts)
    assert result["tp"] == 45
    assert result["fn"] == 5
    assert result["precision"] == 1
    assert result["recall"] == 0.9
    assert result["completed"] == 9
    assert result["passed"] is True


def test_no_report_is_not_a_pass():
    pairs = [[str(i), "SHORTAGE"] for i in range(5)]
    result = pilot.evaluate([{"completed": False, "seconds": 600, "expected": pairs, "reported": []} for _ in range(10)])
    assert result["precision"] == result["recall"] == 0
    assert result["median_seconds"] == 600
    assert result["passed"] is False
