from mcp_erp_bridge.overtime import compute_overtime, severity_from_overtime


def test_no_overtime_under_threshold():
    ot = compute_overtime({"Mon": 8, "Tue": 8, "Wed": 8, "Thu": 8, "Fri": 8})
    assert ot.total == 40 and ot.overtime == 0 and ot.primary_day is None


def test_walk_back_finds_primary_overage_day():
    # 10h Mon-Thu = 40, Fri 6h pushes to 46; walking back from Fri: 6 >= 6 -> Fri
    ot = compute_overtime({"Mon": 10, "Tue": 10, "Wed": 10, "Thu": 10, "Fri": 6})
    assert ot.overtime == 6 and ot.primary_day == "Fri"
    # 12h every day = 60, OT 20; Fri 12 < 20, Fri+Thu 24 >= 20 -> Thu
    ot = compute_overtime({"Mon": 12, "Tue": 12, "Wed": 12, "Thu": 12, "Fri": 12})
    assert ot.overtime == 20 and ot.primary_day == "Thu"


def test_severity_bands():
    assert severity_from_overtime(2) == "low"
    assert severity_from_overtime(8) == "medium"
    assert severity_from_overtime(16) == "high"
