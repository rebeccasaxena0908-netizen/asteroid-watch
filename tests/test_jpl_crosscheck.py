import json
from datetime import date, datetime
from pathlib import Path

from pipeline.jpl_crosscheck import cad_count_on_day, cad_rows, compare_approach, relative_diff, summarise

CAD = json.loads((Path(__file__).parent / "fixtures" / "cad_sample.json").read_text())

# Our stored row for 465824 (2010 FR), as loaded from NeoWs.
OURS = {"neo_id": "2465824", "name": "465824 (2010 FR)", "approach_date": date(2026, 9, 11),
        "approach_datetime": datetime(2026, 9, 11, 22, 28), "miss_distance_au": 0.0518549218,
        "relative_velocity_kps": 11.5928317092}


def test_cad_rows_zips_fields_and_data():
    rows = cad_rows(CAD)
    assert len(rows) == 1
    assert rows[0]["des"] == "465824"
    assert rows[0]["cd"] == "2026-Sep-11 22:28"


def test_matching_approach():
    result = compare_approach(OURS, cad_rows(CAD))
    assert result["status"] == "match"
    assert result["time_diff_min"] == 0
    assert result["dist_diff"] < 1e-8


def test_different_distance_is_flagged():
    result = compare_approach({**OURS, "miss_distance_au": 0.06}, cad_rows(CAD))
    assert result["status"] == "differs"
    assert result["dist_diff"] > 0.1


def test_object_not_in_jpl():
    assert compare_approach(OURS, [])["status"] == "not_in_jpl"


def test_picks_nearest_cad_row_in_time():
    far = {**cad_rows(CAD)[0], "cd": "2026-Sep-13 10:00", "dist": "0.9"}
    assert compare_approach(OURS, [far, cad_rows(CAD)[0]])["status"] == "match"


def test_relative_diff():
    assert relative_diff(1.01, 1.0) == 0.010000000000000009
    assert relative_diff(None, 1.0) is None
    assert relative_diff(1.0, 0) is None


def test_cad_count_on_day_uses_cad_date_format():
    rows = [{"cd": "2026-Jan-19 02:27"}, {"cd": "2026-Jan-19 23:59"}, {"cd": "2026-Jan-20 00:01"}]
    assert cad_count_on_day(rows, date(2026, 1, 19)) == 2


def test_summarise():
    compared = [{"status": "match"}, {"status": "match"}, {"status": "not_in_jpl"}]
    coverage = [{"day": date(2026, 1, 19), "neows": 0, "jpl": 10}, {"day": date(2026, 1, 20), "neows": 2, "jpl": 14}]
    checks = {c.check_name: c for c in summarise(compared, coverage)}

    assert not checks["jpl_objects_found"].passed and "2 of 3" in checks["jpl_objects_found"].details
    assert checks["jpl_values_match"].passed
    assert not checks["jpl_daily_coverage"].passed
    assert "NeoWs has 2 approaches vs JPL 24" in checks["jpl_daily_coverage"].details
