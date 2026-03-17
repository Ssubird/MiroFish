import re

filepath = r"e:\MoFish\MiroFish\backend\app\services\lottery\research_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 替换 imports
import_target = "from .constants import ("
import_repl = "from .constants import (\n    WORLD_V2_MARKET_RUNTIME_MODE,"
content = content.replace(import_target, import_repl)

runtime_import_target = "from .world_runtime import LotteryWorldRuntime"
runtime_import_repl = "from .world_runtime import LotteryWorldRuntime\nfrom .world_v2_runtime import LotteryWorldV2Runtime"
content = content.replace(runtime_import_target, runtime_import_repl)

# 2. 修改 __init__
init_target = """        self.kuzu_graph_service = runtime.kuzu_graph_service"""
init_repl = """        self.world_v2_runtime = LotteryWorldV2Runtime(
            runtime.graph_service,
            store=self.world_runtime.store,
            kuzu_graph_service=runtime.kuzu_graph_service,
        )
        self.kuzu_graph_service = runtime.kuzu_graph_service"""
content = content.replace(init_target, init_repl)

# 3. 添加 helper methods (放在 __init__ 之后)
helper_target = """    def build_overview(self) -> dict[str, object]:"""
helper_repl = """    def _runtime_for_mode(self, runtime_mode: str):
        if runtime_mode == WORLD_V2_MARKET_RUNTIME_MODE:
            return self.world_v2_runtime
        return self.world_runtime

    def _runtime_for_session(self, session_id: str):
        session = self.world_runtime.store.load_session(session_id)
        if session.get("runtime_mode") == WORLD_V2_MARKET_RUNTIME_MODE:
            return self.world_v2_runtime
        return self.world_runtime

    def build_overview(self) -> dict[str, object]:"""
content = content.replace(helper_target, helper_repl)

# 4. 替换 run_backtest 里的 world_runtime
run_backtest_target = """        else:
            payload = self.world_runtime.run_backtest(assets, selected, evaluation_size, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        if runtime_mode == WORLD_V1_RUNTIME_MODE:
            self.world_runtime.store.save_result(payload["world_session"]["session_id"], payload)
            self.world_runtime.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload"""
run_backtest_repl = """        else:
            rt = self._runtime_for_mode(runtime_mode)
            payload = rt.run_backtest(assets, selected, evaluation_size, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        if runtime_mode in (WORLD_V1_RUNTIME_MODE, WORLD_V2_MARKET_RUNTIME_MODE):
            rt = self._runtime_for_mode(runtime_mode)
            rt.store.save_result(payload["world_session"]["session_id"], payload)
            rt.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload"""
content = content.replace(run_backtest_target, run_backtest_repl)

# 5. advance_world_session
adv_target = """        selected = select_strategies(assets.strategies, strategy_ids)
        payload = self.world_runtime.advance(assets, selected, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        self.world_runtime.store.save_result(payload["world_session"]["session_id"], payload)
        self.world_runtime.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload"""
adv_repl = """        selected = select_strategies(assets.strategies, strategy_ids)
        rt = self._runtime_for_mode(runtime_mode)
        payload = rt.advance(assets, selected, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        rt.store.save_result(payload["world_session"]["session_id"], payload)
        rt.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload"""
content = content.replace(adv_target, adv_repl)

# 6. prepare_world_session
prep_target = """        selected = select_strategies(assets.strategies, strategy_ids)
        return self.world_runtime.prepare_session(assets, selected, pick_size, llm_model_name, session_id)"""
prep_repl = """        selected = select_strategies(assets.strategies, strategy_ids)
        rt = self._runtime_for_mode(runtime_mode)
        return rt.prepare_session(assets, selected, pick_size, llm_model_name, session_id)"""
content = content.replace(prep_target, prep_repl)

# 7. current session and query methods
methods_to_replace = [
    ("current_world_session", "self.world_runtime.get_current_session()", "self._runtime_for_mode(WORLD_V2_MARKET_RUNTIME_MODE).get_current_session()"), # hack: get current session might need real check, but store is shared
    ("get_world_session", "self.world_runtime.get_session(session_id)", "self._runtime_for_session(session_id).get_session(session_id)"),
    ("get_world_timeline", "self.world_runtime.get_timeline(session_id, offset, limit)", "self._runtime_for_session(session_id).get_timeline(session_id, offset, limit)"),
    ("get_world_result", "self.world_runtime.get_result(session_id)", "self._runtime_for_session(session_id).get_result(session_id)"),
    ("get_world_graph", "self.world_runtime.get_graph(session_id)", "self._runtime_for_session(session_id).get_graph(session_id)"),
    ("get_world_recent_draw_stats", "self.world_runtime.get_recent_draw_stats(assets, session_id)", "self._runtime_for_session(session_id).get_recent_draw_stats(assets, session_id)" if 'session_id' in content else "self.world_runtime.get_recent_draw_stats(assets, session_id)"),
    ("interview_world_agent", "self.world_runtime.interview_agent(session_id, agent_id, prompt, assets)", "self._runtime_for_session(session_id).interview_agent(session_id, agent_id, prompt, assets)"),
]

# Specifically handle current_world_session to use store directly
cur_target = """    def current_world_session(self) -> dict[str, object]:
        return self.world_runtime.get_current_session()"""
cur_repl = """    def current_world_session(self) -> dict[str, object]:
        session_id = self.world_runtime.store.current_session_id()
        if not session_id: return {}
        return self._runtime_for_session(session_id).get_session(session_id)"""
content = content.replace(cur_target, cur_repl)

cur_get_recent_target = """    def get_world_recent_draw_stats(self, session_id: str | None = None) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        return self.world_runtime.get_recent_draw_stats(assets, session_id)"""
cur_get_recent_repl = """    def get_world_recent_draw_stats(self, session_id: str | None = None) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        rt = self._runtime_for_session(session_id) if session_id else self.world_runtime
        return rt.get_recent_draw_stats(assets, session_id)"""
content = content.replace(cur_get_recent_target, cur_get_recent_repl)

for name, target, repl in methods_to_replace:
    if "current_world_session" in name or "get_world_recent_draw_stats" in name:
        continue
    content = content.replace(target, repl)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Research service replace done!")
