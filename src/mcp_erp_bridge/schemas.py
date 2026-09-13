"""Pydantic schemas for every tool input/output.

Strict typing is the deployment artifact. Claude sees these schemas and
generates well-shaped calls; we validate before any HTTP traffic leaves.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# -- Inputs ----------------------------------------------------------------


class GetWorkOrderInput(BaseModel):
    """Look up a single work order by its number."""

    wo_number: str = Field(
        ...,
        description="The numeric work order id, e.g. '12345678'.",
        pattern=r"^\d{6,10}$",
    )


class ListPendingInput(BaseModel):
    """List pending or in-progress work, optionally scoped to one manager."""

    manager: str | None = Field(
        None,
        description="Manager name in 'Last, First' format. Omit for org-wide view.",
    )
    include_in_progress: bool = Field(
        True,
        description="If True, include both pending-dispatch and in-progress work.",
    )


class CloseoutFields(BaseModel):
    """Fields required for a complete close-out note.

    A close-out note is the structured record a field-service system wants
    before a work order can be billed or archived. The exact field set is
    ERP-specific; this is a representative one. Adapt the model and the
    ``note_field_prefix`` selector together.
    """

    visit_summary: str = Field(..., description="Narrative of the site visit(s).")
    follow_up_summary: str | None = Field(
        None, description="Narrative of any follow-up visit."
    )
    job_code: str = Field(..., description="Job category code, e.g. 'PLUMB-LEAK'.")
    repair_location: str = Field(..., description="Where on-site the repair occurred.")
    repair_details: str = Field(
        ...,
        description="Brief abbreviation of repair (full narrative goes in visit_summary).",
    )
    materials: str = Field(..., description="Materials consumed.")
    equipment: str = Field(..., description="Equipment or assets serviced.")
    assets_added: Literal["Y", "N"] = Field(
        ..., description="Whether new assets were added."
    )
    completion: Literal["Y", "N"] = Field(
        ..., description="Whether the work order is fully complete."
    )
    ot_explanation: str = Field("", description="Explanation if overtime was required.")
    warranty_call: Literal["Y", "N"] = Field(
        ..., description="Whether this was a warranty call."
    )
    sub_cost: Decimal | None = Field(
        None, description="Subcontractor cost, if applicable."
    )


class AddCloseoutNoteInput(BaseModel):
    """Add a close-out note with all required fields validated upfront."""

    wo_number: str = Field(..., pattern=r"^\d{6,10}$")
    fields: CloseoutFields


class FindScheduleInput(BaseModel):
    """Look up a field worker's schedule for a given week from the schedule export."""

    name: str = Field(..., description="Worker name in 'Last, First' format.")
    week_of: date = Field(..., description="Sunday of the target week.")


class DetectOvertimeInput(BaseModel):
    """Scan the roster for overtime exceedances in a given week."""

    week_of: date = Field(..., description="Sunday of the target week.")
    threshold: float = Field(40.0, description="Hours threshold above which to flag.")


# -- Outputs ---------------------------------------------------------------


class WorkOrder(BaseModel):
    number: str
    status: str
    technician: str | None = None
    scheduled: datetime | None = None
    nte: Decimal | None = None
    customer: str = ""
    location: str = ""
    description: str = ""
    parent_wo: str | None = None
    closeout_fields: dict[str, str] = Field(default_factory=dict)


class NoteResult(BaseModel):
    wo_number: str
    note_id: str
    submitted_at: datetime
    success: bool


class ShiftEntry(BaseModel):
    day: Literal["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    hours: float


class Schedule(BaseModel):
    technician: str
    week_of: date
    shifts: list[ShiftEntry]
    total_hours: float
    overtime_hours: float


class OTAlert(BaseModel):
    technician: str
    total_hours: float
    overtime_hours: float
    primary_overage_day: str | None
    severity: Literal["low", "medium", "high"]
