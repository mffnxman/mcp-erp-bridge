"""MCP server registration.

Exposes three production-ready tools backed by the deterministic
``ErpClient``: ``get_work_order``, ``list_pending_work``, ``add_closeout_note``.

Two additional tool surfaces, ``find_field_schedule`` and
``detect_overtime``, are designed and have schemas + helper logic ready
in ``schemas.py`` and ``overtime.py``, but their HTTP/export integration is
intentionally not registered here until the ERP-specific schedule-export
parser is contributed by the deploying team. This keeps the published
surface honest: every registered tool actually works.
"""

from __future__ import annotations

import logging
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .erp_client import ErpClient
from .schemas import (
    AddCloseoutNoteInput,
    GetWorkOrderInput,
    ListPendingInput,
    NoteResult,
    WorkOrder,
)

log = logging.getLogger("mcp_erp_bridge.server")

server: Server = Server("mcp-erp-bridge")


# -- Tool list -------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_work_order",
            description=(
                "Look up a single work order by its number. "
                "Returns full structured record: status, technician, schedule, "
                "NTE, customer, location, parent WO, and the close-out fields."
            ),
            inputSchema=GetWorkOrderInput.model_json_schema(),
        ),
        Tool(
            name="list_pending_work",
            description=(
                "List all pending-dispatch and in-progress work orders, "
                "optionally filtered to a single manager."
            ),
            inputSchema=ListPendingInput.model_json_schema(),
        ),
        Tool(
            name="add_closeout_note",
            description=(
                "Submit a close-out note with all required fields. "
                "Validates every field; raises rather than submitting incomplete."
            ),
            inputSchema=AddCloseoutNoteInput.model_json_schema(),
        ),
    ]


# -- Tool dispatcher -------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log.info("tool call: %s", name)

    async with ErpClient() as client:
        if name == "get_work_order":
            args = GetWorkOrderInput(**arguments)
            raw = await client.get_work_order(args.wo_number)
            wo = WorkOrder(**raw)
            return [TextContent(type="text", text=wo.model_dump_json(indent=2))]

        if name == "list_pending_work":
            args = ListPendingInput(**arguments)
            raw_list = await client.list_pending(manager=args.manager)
            return [
                TextContent(
                    type="text",
                    text=f"{len(raw_list)} pending/in-progress work orders\n\n"
                    + "\n".join(f"- {r['number']}: {r['status']}" for r in raw_list),
                )
            ]

        if name == "add_closeout_note":
            args = AddCloseoutNoteInput(**arguments)
            raw = await client.add_closeout_note(
                args.wo_number, args.fields.model_dump()
            )
            result = NoteResult(
                wo_number=args.wo_number,
                note_id=raw["note_id"],
                submitted_at=datetime.utcnow(),
                success=raw["success"],
            )
            return [TextContent(type="text", text=result.model_dump_json(indent=2))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# -- Entry point -----------------------------------------------------------


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("mcp-erp-bridge starting; tools registered")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
