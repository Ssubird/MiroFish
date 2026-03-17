"""Lottery research APIs."""

from flask import jsonify, request

from . import lottery_bp
from ..config import Config
from ..services.lottery import LotteryResearchService
from ..services.lottery.world_jobs import WorldRunManager
from ..services.lottery.constants import (
    DEFAULT_AGENT_DIALOGUE_ENABLED,
    DEFAULT_AGENT_DIALOGUE_ROUNDS,
    DEFAULT_BUDGET_YUAN,
    DEFAULT_EVALUATION_SIZE,
    DEFAULT_ISSUE_PARALLELISM,
    DEFAULT_LIVE_INTERVIEW_ENABLED,
    DEFAULT_LLM_PARALLELISM,
    DEFAULT_LLM_RETRY_BACKOFF_MS,
    DEFAULT_LLM_RETRY_COUNT,
    DEFAULT_PICK_SIZE,
    KUZU_GRAPH_MODE,
    LEGACY_RUNTIME_MODE,
    LOCAL_GRAPH_MODE,
    WORLD_V1_RUNTIME_MODE,
    WORLD_V2_MARKET_RUNTIME_MODE,
    WORLD_WARMUP_ISSUES,
    ZEP_GRAPH_MODE,
)
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger


logger = get_logger("mirofish.lottery")
service = LotteryResearchService()
world_runs = WorldRunManager()


@lottery_bp.route("/overview", methods=["GET"])
def get_lottery_overview():
    try:
        return jsonify({"success": True, "data": service.build_overview()})
    except Exception as exc:
        logger.exception("Failed to load lottery overview")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/graph/status", methods=["GET"])
def get_lottery_graph_status():
    try:
        overview = service.build_overview()
        return jsonify({"success": True, "data": {"kuzu": overview.get("kuzu_graph_status", {}), "zep": overview.get("zep_graph_status", {})}})
    except Exception as exc:
        logger.exception("Failed to load Zep graph status")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/graph/sync", methods=["POST"])
def sync_lottery_graph():
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force", False))
    mode = str(payload.get("mode", KUZU_GRAPH_MODE)).strip() or KUZU_GRAPH_MODE
    try:
        data = _sync_graph(mode, force)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to sync Zep graph")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/models", methods=["GET"])
def get_lottery_models():
    try:
        client = LLMClient()
        models = client.list_models()
        return jsonify({"success": True, "data": {"models": models, "default_model": client.model}})
    except Exception as exc:
        logger.exception("Failed to list LLM models")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/models/probe", methods=["POST"])
def probe_lottery_model():
    payload = request.get_json(silent=True) or {}
    model_name = str(payload.get("model_name", "")).strip()
    if not model_name:
        return jsonify({"success": False, "error": "model_name is required"}), 400
    try:
        return jsonify({"success": True, "data": LLMClient().probe_model(model_name)})
    except Exception as exc:
        logger.exception("Failed to probe model: %s", model_name)
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/backtest", methods=["POST"])
def run_lottery_backtest():
    payload = request.get_json(silent=True) or {}
    strategy_ids = payload.get("strategy_ids")
    if strategy_ids is not None and not isinstance(strategy_ids, list):
        return jsonify({"success": False, "error": "strategy_ids must be an array"}), 400
    params = _backtest_params(payload)
    try:
        logger.info(
            "Start lottery backtest: evaluation_size=%s, pick_size=%s, llm_request_delay_ms=%s, llm_model_name=%s, llm_retry_count=%s, llm_retry_backoff_ms=%s, llm_parallelism=%s, issue_parallelism=%s, agent_dialogue_enabled=%s, agent_dialogue_rounds=%s, graph_mode=%s, zep_graph_id=%s, runtime_mode=%s, warmup_size=%s, live_interview_enabled=%s, strategy_ids=%s",
            params["evaluation_size"],
            params["pick_size"],
            params["llm_request_delay_ms"],
            params["llm_model_name"],
            params["llm_retry_count"],
            params["llm_retry_backoff_ms"],
            params["llm_parallelism"],
            params["issue_parallelism"],
            params["agent_dialogue_enabled"],
            params["agent_dialogue_rounds"],
            params["graph_mode"],
            params["zep_graph_id"],
            params["runtime_mode"],
            params["warmup_size"],
            params["live_interview_enabled"],
            strategy_ids,
        )
        data = service.run_backtest(strategy_ids=strategy_ids, **params)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to run lottery backtest")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/start", methods=["POST"])
def start_lottery_world():
    return advance_lottery_world()


@lottery_bp.route("/world/advance", methods=["POST"])
def advance_lottery_world():
    payload = request.get_json(silent=True) or {}
    strategy_ids = payload.get("strategy_ids")
    if strategy_ids is not None and not isinstance(strategy_ids, list):
        return jsonify({"success": False, "error": "strategy_ids must be an array"}), 400
    params = _backtest_params(payload)
    params["runtime_mode"] = WORLD_V1_RUNTIME_MODE
    try:
        data = world_runs.start(service, strategy_ids, params)
        return jsonify({"success": True, "data": data}), 202
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to start lottery world session")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/evolution", methods=["POST"])
def evolution_lottery_world():
    payload = request.get_json(silent=True) or {}
    strategy_ids = payload.get("strategy_ids")
    iterations = int(payload.get("iterations", 3))
    if strategy_ids is not None and not isinstance(strategy_ids, list):
        return jsonify({"success": False, "error": "strategy_ids must be an array"}), 400
    if iterations < 1:
        return jsonify({"success": False, "error": "iterations must be at least 1"}), 400
        
    params = _backtest_params(payload)
    params["runtime_mode"] = WORLD_V2_MARKET_RUNTIME_MODE
    try:
        data = world_runs.start_evolution(service, strategy_ids, params, iterations)
        return jsonify({"success": True, "data": data}), 202
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to start lottery evolutionary world session")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/current", methods=["GET"])
def get_current_lottery_world():
    try:
        return jsonify({"success": True, "data": service.get_current_world_session()})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "No current world session"}), 404
    except Exception as exc:
        logger.exception("Failed to load current lottery world session")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/reset", methods=["POST"])
def reset_lottery_world():
    try:
        return jsonify({"success": True, "data": service.reset_current_world_session()})
    except Exception as exc:
        logger.exception("Failed to reset current lottery world session")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/<session_id>", methods=["GET"])
def get_lottery_world_session(session_id: str):
    try:
        return jsonify({"success": True, "data": service.get_world_session(session_id)})
    except FileNotFoundError:
        return jsonify({"success": False, "error": f"Unknown world session: {session_id}"}), 404
    except Exception as exc:
        logger.exception("Failed to load lottery world session")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/<session_id>/timeline", methods=["GET"])
def get_lottery_world_timeline(session_id: str):
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 50, type=int)
    latest = request.args.get("latest", "0").strip().lower() in {"1", "true", "yes"}
    try:
        data = service.get_world_timeline(session_id, offset, limit, latest)
        return jsonify({"success": True, "data": data})
    except FileNotFoundError:
        return jsonify({"success": False, "error": f"Unknown world session: {session_id}"}), 404
    except Exception as exc:
        logger.exception("Failed to load lottery world timeline")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/<session_id>/graph", methods=["GET"])
def get_lottery_world_graph(session_id: str):
    try:
        return jsonify({"success": True, "data": service.get_world_graph(session_id)})
    except FileNotFoundError:
        return jsonify({"success": False, "error": f"Unknown world session: {session_id}"}), 404
    except Exception as exc:
        logger.exception("Failed to load lottery world graph")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/<session_id>/result", methods=["GET"])
def get_lottery_world_result(session_id: str):
    try:
        return jsonify({"success": True, "data": service.get_world_result(session_id)})
    except FileNotFoundError:
        return jsonify({"success": False, "error": f"World result not ready: {session_id}"}), 404
    except Exception as exc:
        logger.exception("Failed to load lottery world result")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/recent-draw-stats", methods=["GET"])
def get_lottery_recent_draw_stats():
    session_id = request.args.get("session_id", "", type=str).strip() or None
    try:
        return jsonify({"success": True, "data": service.get_recent_draw_stats(session_id)})
    except Exception as exc:
        logger.exception("Failed to load recent draw stats")
        return jsonify({"success": False, "error": str(exc)}), 500


@lottery_bp.route("/world/<session_id>/interview", methods=["POST"])
def interview_lottery_world_agent(session_id: str):
    payload = request.get_json(silent=True) or {}
    agent_id = str(payload.get("agent_id", "")).strip()
    prompt = str(payload.get("prompt", "")).strip()
    if not agent_id or not prompt:
        return jsonify({"success": False, "error": "agent_id and prompt are required"}), 400
    try:
        data = service.interview_world_agent(session_id, agent_id, prompt)
        return jsonify({"success": True, "data": data})
    except FileNotFoundError:
        return jsonify({"success": False, "error": f"Unknown world session: {session_id}"}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to interview lottery world agent")
        return jsonify({"success": False, "error": str(exc)}), 500


def _backtest_params(payload: dict[str, object]) -> dict[str, object]:
    return {
        "evaluation_size": int(payload.get("evaluation_size", DEFAULT_EVALUATION_SIZE)),
        "pick_size": int(payload.get("pick_size", DEFAULT_PICK_SIZE)),
        "llm_request_delay_ms": int(payload.get("llm_request_delay_ms", 0)),
        "llm_model_name": str(payload.get("llm_model_name", "")).strip() or None,
        "llm_retry_count": int(payload.get("llm_retry_count", DEFAULT_LLM_RETRY_COUNT)),
        "llm_retry_backoff_ms": int(payload.get("llm_retry_backoff_ms", DEFAULT_LLM_RETRY_BACKOFF_MS)),
        "llm_parallelism": int(payload.get("llm_parallelism", DEFAULT_LLM_PARALLELISM)),
        "issue_parallelism": int(payload.get("issue_parallelism", DEFAULT_ISSUE_PARALLELISM)),
        "agent_dialogue_enabled": bool(payload.get("agent_dialogue_enabled", DEFAULT_AGENT_DIALOGUE_ENABLED)),
        "agent_dialogue_rounds": int(payload.get("agent_dialogue_rounds", DEFAULT_AGENT_DIALOGUE_ROUNDS)),
        "graph_mode": str(payload.get("graph_mode", LOCAL_GRAPH_MODE)).strip() or LOCAL_GRAPH_MODE,
        "zep_graph_id": str(payload.get("zep_graph_id", "")).strip() or None,
        "runtime_mode": str(payload.get("runtime_mode", Config.LOTTERY_RUNTIME_MODE)).strip() or LEGACY_RUNTIME_MODE,
        "warmup_size": int(payload.get("warmup_size", WORLD_WARMUP_ISSUES)),
        "live_interview_enabled": bool(payload.get("live_interview_enabled", DEFAULT_LIVE_INTERVIEW_ENABLED)),
        "budget_yuan": int(payload.get("budget_yuan", DEFAULT_BUDGET_YUAN)),
        "session_id": str(payload.get("session_id", "")).strip() or None,
        "target_period": str(payload.get("target_period", "")).strip() or None,
    }


def _sync_graph(mode: str, force: bool) -> dict[str, object]:
    if mode == ZEP_GRAPH_MODE:
        return service.sync_zep_graph(force=force)
    if mode == KUZU_GRAPH_MODE:
        return service.sync_kuzu_graph(force=force)
    if mode == LOCAL_GRAPH_MODE:
        raise ValueError("local mode does not need sync")
    raise ValueError(f"unknown graph sync mode: {mode}")
