import sys
import logging
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.constants import WORLD_V2_MARKET_RUNTIME_MODE

logging.basicConfig(level=logging.INFO)

def main():
    service = LotteryResearchService()
    print("Forcing Kuzu graph sync...")
    service.sync_kuzu_graph(force=True)
    print("Starting World V2 Market simulation...")
    try:
        result = service.advance_world_session(
            evaluation_size=1, 
            pick_size=5, 
            runtime_mode=WORLD_V2_MARKET_RUNTIME_MODE,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            llm_parallelism=2,
            issue_parallelism=1
        )
        print("Simulation completed successfully!")
        print("Latest Prediction:", result.get("latest_prediction", {}))
    except Exception as e:
        print(f"Simulation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
