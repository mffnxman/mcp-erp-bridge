"""Entry point so `python -m mcp_erp_bridge` boots the server."""
from __future__ import annotations

import asyncio

from .server import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
