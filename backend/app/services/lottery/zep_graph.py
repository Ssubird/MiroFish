"""Zep-backed graph sync and retrieval for the lottery workspace."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import re
import time
import uuid
from pathlib import Path
from typing import Callable

from zep_cloud import EpisodeData
from zep_cloud.client import Zep

from ...config import Config
from ...utils.logger import get_logger
from ...utils.zep_paging import fetch_all_edges, fetch_all_nodes
from ..text_processor import TextProcessor
from .constants import GRAPH_RECENT_DRAW_LIMIT
from .models import ChartProfile, DrawRecord, GraphSnapshot, KnowledgeDocument
from .paths import LOTTERY_ROOT
from .vocabulary import extract_domain_terms
from .zep_graph_state import ZepGraphState, ZepGraphStateStore


logger = get_logger("mirofish.lottery.zep_graph")

STATE_FILE = LOTTERY_ROOT / ".zep_graph_state.json"
GRAPH_NAME_PREFIX = "MiroFish Ziwei Lottery"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
BATCH_SIZE = 12
SEARCH_LIMIT = 12
SYNC_WAIT_TIMEOUT_SECONDS = 900
SYNC_WAIT_INTERVAL_SECONDS = 3
NUMBER_PATTERN = re.compile(r"\b(?:[1-9]|[1-7]\d|80)\b")
WORKSPACE_QUERY = "紫微斗数 快乐8 命盘 历史开奖 四化 宫位 干支 选号"


class ZepGraphService:
    """Sync workspace assets into Zep and build remote graph snapshots."""

    def __init__(
        self,
        state_file: Path | None = None,
        client_factory: Callable[[str], Zep] | None = None,
    ):
        self.state_store = ZepGraphStateStore(state_file or STATE_FILE)
        self.client_factory = client_factory or (lambda api_key: Zep(api_key=api_key))

    def workspace_digest(
        self,
        knowledge_documents: tuple[KnowledgeDocument, ...],
        chart_profiles: tuple[ChartProfile, ...],
        completed_draws: tuple[DrawRecord, ...],
        pending_draws: tuple[DrawRecord, ...],
    ) -> str:
        parts = [
            *(f"doc:{item.relative_path}:{item.char_count}" for item in knowledge_documents),
            *(f"chart:{item.relative_path}:{item.char_count}" for item in chart_profiles if item.kind != "draw_chart"),
            *(self._draw_digest(draw) for draw in completed_draws[-GRAPH_RECENT_DRAW_LIMIT:]),
            *(self._draw_digest(draw) for draw in pending_draws),
        ]
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()

    def status(self, workspace_digest: str | None = None) -> dict[str, object]:
        state = self._load_state()
        return {"configured": bool(Config.ZEP_API_KEY), "available": bool(state), "graph_id": state.graph_id if state else None, "synced_at": state.synced_at if state else None, "node_count": state.node_count if state else 0, "edge_count": state.edge_count if state else 0, "document_count": state.document_count if state else 0, "chart_count": state.chart_count if state else 0, "draw_count": state.draw_count if state else 0, "is_stale": bool(state and workspace_digest and state.workspace_digest != workspace_digest), "workspace_digest": workspace_digest, "stored_digest": state.workspace_digest if state else None}

    def sync_workspace(
        self,
        knowledge_documents: tuple[KnowledgeDocument, ...],
        chart_profiles: tuple[ChartProfile, ...],
        completed_draws: tuple[DrawRecord, ...],
        pending_draws: tuple[DrawRecord, ...],
        force: bool = False,
    ) -> dict[str, object]:
        digest = self.workspace_digest(knowledge_documents, chart_profiles, completed_draws, pending_draws)
        current = self._load_state()
        if current and current.workspace_digest == digest and not force:
            payload = self.status(digest)
            payload["reused"] = True
            return payload
        client = self._client()
        graph_id = self._create_graph(client)
        episode_ids = self._upload_chunks(client, graph_id, self._build_chunks(knowledge_documents, chart_profiles, completed_draws, pending_draws))
        self._wait_for_episodes(client, episode_ids)
        state = ZepGraphState(graph_id=graph_id, synced_at=datetime.now(UTC).isoformat(), workspace_digest=digest, document_count=len(knowledge_documents), chart_count=len(chart_profiles), draw_count=len(completed_draws) + len(pending_draws), node_count=len(fetch_all_nodes(client, graph_id)), edge_count=len(fetch_all_edges(client, graph_id)))
        self._save_state(state)
        payload = self.status(digest)
        payload["reused"] = False
        return payload

    def build_workspace_graph(
        self,
        knowledge_documents: list[KnowledgeDocument],
        chart_profiles: list[ChartProfile],
        completed_draws: list[DrawRecord],
        pending_draw: DrawRecord | None,
        graph_id: str | None = None,
    ) -> GraphSnapshot:
        state = self._require_state(graph_id)
        return self._search_snapshot(state.graph_id, WORKSPACE_QUERY, len(chart_profiles), state.node_count, state.edge_count)

    def build_prediction_graph(
        self,
        history_draws: list[DrawRecord],
        target_draw: DrawRecord,
        knowledge_documents: list[KnowledgeDocument],
        chart_profiles: list[ChartProfile],
        graph_id: str | None = None,
    ) -> GraphSnapshot:
        state = self._require_state(graph_id)
        return self._search_snapshot(state.graph_id, self._prediction_query(history_draws, target_draw), len(chart_profiles), state.node_count, state.edge_count)

    def _client(self) -> Zep:
        if not Config.ZEP_API_KEY:
            raise ValueError("ZEP_API_KEY 未配置，无法使用 Zep 图谱模式。")
        return self.client_factory(Config.ZEP_API_KEY)

    def _create_graph(self, client: Zep) -> str:
        graph_id = f"ziwei_{uuid.uuid4().hex[:16]}"
        client.graph.create(graph_id=graph_id, name=f"{GRAPH_NAME_PREFIX} {LOTTERY_ROOT.name}", description="Ziwei lottery workspace graph synced from local research assets.")
        logger.info("已创建 Zep 图谱: %s", graph_id)
        return graph_id

    def _build_chunks(
        self,
        knowledge_documents: tuple[KnowledgeDocument, ...],
        chart_profiles: tuple[ChartProfile, ...],
        completed_draws: tuple[DrawRecord, ...],
        pending_draws: tuple[DrawRecord, ...],
    ) -> list[str]:
        chunks: list[str] = []
        for item in knowledge_documents:
            chunks.extend(self._split_episode(self._document_text(item)))
        for item in chart_profiles:
            if item.kind != "draw_chart":
                chunks.extend(self._split_episode(self._chart_text(item)))
        for draw in (*completed_draws, *pending_draws):
            chunks.append(self._draw_text(draw))
        return chunks

    def _document_text(self, item: KnowledgeDocument) -> str:
        return "\n".join([f"source=document path={item.relative_path} kind={item.kind}", f"name={item.name}", f"terms={', '.join(item.terms)}", item.content])

    def _chart_text(self, item: ChartProfile) -> str:
        period = str(item.metadata.get("period", "")).strip()
        return "\n".join([f"source=chart path={item.relative_path} kind={item.kind}", f"name={item.name}", f"period={period or 'n/a'}", f"terms={', '.join(item.feature_terms)}", item.content])

    def _draw_text(self, draw: DrawRecord) -> str:
        numbers = ",".join(str(number) for number in draw.numbers) if draw.numbers else "pending"
        return "\n".join([f"source=draw period={draw.period} date={draw.date}", f"numbers={numbers}", f"daily={draw.daily_energy.stem}{draw.daily_energy.branch} {' '.join(draw.daily_energy.mutagen)}", f"hourly={draw.hourly_energy.stem}{draw.hourly_energy.branch} {' '.join(draw.hourly_energy.mutagen)}"])

    def _split_episode(self, text: str) -> list[str]:
        return TextProcessor.split_text(TextProcessor.preprocess_text(text), CHUNK_SIZE, CHUNK_OVERLAP)

    def _upload_chunks(self, client: Zep, graph_id: str, chunks: list[str]) -> list[str]:
        episode_ids: list[str] = []
        for index in range(0, len(chunks), BATCH_SIZE):
            batch = [EpisodeData(data=item, type="text") for item in chunks[index:index + BATCH_SIZE]]
            result = client.graph.add_batch(graph_id=graph_id, episodes=batch)
            for item in result or []:
                episode_id = getattr(item, "uuid_", None) or getattr(item, "uuid", None)
                if episode_id:
                    episode_ids.append(episode_id)
            time.sleep(1)
        return episode_ids

    def _wait_for_episodes(self, client: Zep, episode_ids: list[str]) -> None:
        if not episode_ids:
            return
        deadline = time.time() + SYNC_WAIT_TIMEOUT_SECONDS
        pending = set(episode_ids)
        while pending:
            if time.time() > deadline:
                raise TimeoutError(f"等待 Zep 处理图谱超时，仍有 {len(pending)} 个 episode 未完成。")
            for episode_id in list(pending):
                episode = client.graph.episode.get(uuid_=episode_id)
                if bool(getattr(episode, "processed", False)):
                    pending.remove(episode_id)
            if pending:
                time.sleep(SYNC_WAIT_INTERVAL_SECONDS)

    def _prediction_query(self, history_draws: list[DrawRecord], target_draw: DrawRecord) -> str:
        recent_periods = " ".join(draw.period for draw in history_draws[-3:])
        target_terms = [target_draw.period, target_draw.daily_energy.stem, target_draw.daily_energy.branch, *target_draw.daily_energy.mutagen, target_draw.hourly_energy.stem, target_draw.hourly_energy.branch, *target_draw.hourly_energy.mutagen, recent_periods, "紫微斗数", "命盘", "选号"]
        return " ".join(item for item in target_terms if item)

    def _search_snapshot(self, graph_id: str, query: str, chart_count: int, node_count: int, edge_count: int) -> GraphSnapshot:
        result = self._client().graph.search(graph_id=graph_id, query=query, limit=SEARCH_LIMIT, scope="edges", reranker="cross_encoder")
        facts = [getattr(item, "fact", "").strip() for item in getattr(result, "edges", []) if getattr(item, "fact", "")]
        facts.extend(f"[{getattr(item, 'name', 'node')}]: {getattr(item, 'summary', '').strip()}" for item in getattr(result, "nodes", []) if getattr(item, "summary", ""))
        highlights, concept_scores = self._fact_scores(query, facts)
        source_names = tuple(getattr(item, "name", "") for item in getattr(result, "nodes", [])[:6] if getattr(item, "name", ""))
        digest = hashlib.md5(f"{graph_id}|{query}".encode("utf-8")).hexdigest()[:10]
        return GraphSnapshot(snapshot_id=f"zep_{digest}", node_count=node_count, edge_count=edge_count, highlights=highlights, concept_scores=concept_scores, source_documents=source_names, chart_count=chart_count, preview_relations=tuple(facts[:6]), provider="zep", backend_graph_id=graph_id, query=query)

    def _fact_scores(self, query: str, facts: list[str]) -> tuple[tuple[str, ...], dict[str, float]]:
        score_map = Counter()
        text = "\n".join(facts)
        for term in extract_domain_terms(f"{query}\n{text}"):
            score_map[term] += 2.0
        for number in NUMBER_PATTERN.findall(text):
            score_map[number] += 1.0
        if not score_map:
            for term in query.split()[:8]:
                score_map[term] += 1.0
        return tuple(term for term, _ in score_map.most_common(12)), dict(score_map)

    def _draw_digest(self, draw: DrawRecord) -> str:
        payload = [draw.period, draw.date, *(str(number) for number in draw.numbers), *draw.daily_energy.mutagen, *draw.hourly_energy.mutagen]
        return ":".join(payload)

    def _require_state(self, graph_id: str | None) -> ZepGraphState:
        state = self._load_state()
        if graph_id:
            if not state or state.graph_id != graph_id:
                raise ValueError(f"指定的 Zep 图谱不存在或未同步: {graph_id}")
            return state
        if not state:
            raise ValueError("尚未同步 Zep 图谱，请先在页面里执行“同步到 Zep”。")
        return state

    def _load_state(self) -> ZepGraphState | None:
        return self.state_store.load()

    def _save_state(self, state: ZepGraphState) -> None:
        self.state_store.save(state)
