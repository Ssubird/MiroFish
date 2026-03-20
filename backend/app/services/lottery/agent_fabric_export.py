"""CLI export for the declarative world_v2 agent fabric."""

from __future__ import annotations

import json

from .research_service import LotteryResearchService


def main() -> None:
    service = LotteryResearchService()
    payload = service.get_agent_fabric_registry()
    print(json.dumps(payload["snapshot_artifacts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
