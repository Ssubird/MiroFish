"""Lottery research APIs."""

from flask import jsonify, request

from . import lottery_bp
from ..services.lottery import LotteryResearchService
from ..services.lottery.constants import (
    DEFAULT_AGENT_DIALOGUE_ENABLED,
    DEFAULT_AGENT_DIALOGUE_ROUNDS,
    DEFAULT_EVALUATION_SIZE,
    DEFAULT_ISSUE_PARALLELISM,
    DEFAULT_LLM_PARALLELISM,
    DEFAULT_LLM_RETRY_BACKOFF_MS,
    DEFAULT_LLM_RETRY_COUNT,
    DEFAULT_PICK_SIZE,
    KUZU_GRAPH_MODE,
    LOCAL_GRAPH_MODE,
    ZEP_GRAPH_MODE,
)
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger


logger = get_logger("mirofish.lottery")
service = LotteryResearchService()


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
    mode = str(payload.get("mode", ZEP_GRAPH_MODE)).strip() or ZEP_GRAPH_MODE
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
            "Start lottery backtest: evaluation_size=%s, pick_size=%s, llm_request_delay_ms=%s, llm_model_name=%s, llm_retry_count=%s, llm_retry_backoff_ms=%s, llm_parallelism=%s, issue_parallelism=%s, agent_dialogue_enabled=%s, agent_dialogue_rounds=%s, graph_mode=%s, zep_graph_id=%s, strategy_ids=%s",
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
            strategy_ids,
        )
        data = service.run_backtest(strategy_ids=strategy_ids, **params)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to run lottery backtest")
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
    }


def _sync_graph(mode: str, force: bool) -> dict[str, object]:
    if mode == ZEP_GRAPH_MODE:
        return service.sync_zep_graph(force=force)
    if mode == KUZU_GRAPH_MODE:
        return service.sync_kuzu_graph(force=force)
    if mode == LOCAL_GRAPH_MODE:
        raise ValueError("local mode does not need sync")
    raise ValueError(f"unknown graph sync mode: {mode}")
