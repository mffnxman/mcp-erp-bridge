"""Input/output schema validation. No I/O."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_erp_bridge.schemas import (
    AddCloseoutNoteInput,
    CloseoutFields,
    GetWorkOrderInput,
    WorkOrder,
)

VALID_FIELDS = {
    "visit_summary": "Fixed leak under sink.",
    "job_code": "PLUMB-LEAK",
    "repair_location": "Break room",
    "repair_details": "Replaced coupling",
    "materials": "1 coupling, silicone",
    "equipment": "Sink",
    "assets_added": "N",
    "completion": "Y",
    "warranty_call": "N",
}


def test_wo_number_must_be_numeric():
    with pytest.raises(ValidationError):
        GetWorkOrderInput(wo_number="abc123")
    assert GetWorkOrderInput(wo_number="12345678").wo_number == "12345678"


def test_closeout_fields_reject_missing_required():
    incomplete = {k: v for k, v in VALID_FIELDS.items() if k != "job_code"}
    with pytest.raises(ValidationError) as exc:
        CloseoutFields(**incomplete)
    assert "job_code" in str(exc.value)


def test_closeout_fields_reject_bad_literal():
    with pytest.raises(ValidationError):
        CloseoutFields(**{**VALID_FIELDS, "completion": "maybe"})


def test_add_closeout_note_input_roundtrip():
    inp = AddCloseoutNoteInput(wo_number="12345678", fields=VALID_FIELDS)
    dumped = inp.fields.model_dump()
    assert dumped["ot_explanation"] == ""  # default applied
    assert dumped["sub_cost"] is None
    assert set(VALID_FIELDS) <= set(dumped)


def test_work_order_accepts_client_dict():
    raw = {
        "number": "12345678",
        "status": "In Progress",
        "technician": "Doe, Jane",
        "scheduled": None,
        "nte": "850.00",
        "customer": "Acme Retail Co",
        "location": "Anytown-Main",
        "description": "Leak",
        "parent_wo": None,
        "closeout_fields": {},
    }
    wo = WorkOrder(**raw)
    assert wo.number == "12345678"
    assert str(wo.nte) == "850.00"
    assert wo.closeout_fields == {}
