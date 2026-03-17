"""Kuzu-backed local graph sync and retrieval for the lottery workspace."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
from threading import Lock

import kuzu

from ...config import Config
from .constants import GRAPH_RECENT_DRAW_LIMIT
from .kuzu_graph_state import KuzuGraphState, KuzuGraphStateStore
from .models import DrawRecord, GraphSnapshot
from .paths import LOTTERY_ROOT
from .vocabulary import extract_domain_terms


STATE_FILE = LOTTERY_ROOT / ".kuzu_graph_state.json"
GRAPH_ID = "kuzu_local"
WORKSPACE_QUERY = "紫微斗数 快乐8 命盘 历史开奖 四化 宫位 干支 选号"
NUMBER_PATTERN = re.compile(r"\b(?:[1-9]|[1-7]\d|80)\b")
NODE_QUERY = "MATCH (n:Entity) RETURN n.id AS id, n.node_kind AS node_kind, n.name AS name, n.source_path AS source_path, n.content AS content, n.period AS period"
EDGE_QUERY = "MATCH (a:Entity)-[r:Relation]->(b:Entity) RETURN a.id AS source_id, a.name AS source_name, a.period AS source_period, b.id AS target_id, b.name AS target_name, b.period AS target_period, r.relation AS relation, r.weight AS weight"


class KuzuGraphService:
    """Persist the lottery graph in a local Kuzu database."""

    def __init__(self, state_file: Path | None = None, db_root: str | None = None):
        self.state_store = KuzuGraphStateStore(state_file or STATE_FILE)
        self.db_root = Path(db_root or Config.KUZU_GRAPH_ROOT)
        self._database: kuzu.Database | None = None
        self._database_lock = Lock()

    def workspace_digest(self, documents, charts, completed, pending) -> str:
        parts = [*(f"doc:{i.relative_path}:{i.char_count}" for i in documents), *(f"chart:{i.relative_path}:{i.char_count}" for i in charts), *(self._draw_digest(i) for i in completed[-GRAPH_RECENT_DRAW_LIMIT:]), *(self._draw_digest(i) for i in pending)]
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()

    def status(self, workspace_digest: str | None = None) -> dict[str, object]:
        state = self.state_store.load()
        available = bool(state and Path(state.db_path).exists())
        return {"configured": True, "available": available, "graph_id": state.graph_id if state else GRAPH_ID, "db_path": state.db_path if state else str(self.db_root), "synced_at": state.synced_at if state else None, "node_count": state.node_count if state else 0, "edge_count": state.edge_count if state else 0, "document_count": state.document_count if state else 0, "chart_count": state.chart_count if state else 0, "draw_count": state.draw_count if state else 0, "is_stale": bool(state and workspace_digest and state.workspace_digest != workspace_digest), "workspace_digest": workspace_digest, "stored_digest": state.workspace_digest if state else None}

    def sync_workspace(self, documents, charts, completed, pending, force: bool = False) -> dict[str, object]:
        digest = self.workspace_digest(documents, charts, completed, pending)
        current = self.state_store.load()
        if current and current.workspace_digest == digest and self.db_root.exists() and not force:
            payload = self.status(digest)
            payload["reused"] = True
            return payload
        self._reset_db()
        conn = self._connection()
        self._create_schema(conn)
        self._bulk_load(conn, documents, charts, completed, pending)
        self.state_store.save(self._state_snapshot(conn, digest, documents, charts, completed, pending))
        payload = self.status(digest)
        payload["reused"] = False
        return payload

    def build_workspace_graph(self, documents, charts, completed, pending_draw, graph_id: str | None = None) -> GraphSnapshot:
        return self._search_snapshot(self._require_state(graph_id), WORKSPACE_QUERY, len(charts), None)

    def build_prediction_graph(self, history_draws, target_draw, documents, charts, graph_id: str | None = None) -> GraphSnapshot:
        visible_periods = {draw.period for draw in history_draws}
        visible_periods.add(target_draw.period)
        return self._search_snapshot(self._require_state(graph_id), self._prediction_query(history_draws, target_draw), len(charts), visible_periods)

    def _state_snapshot(self, conn, digest: str, documents, charts, completed, pending) -> KuzuGraphState:
        node_count = sum(self._count(conn, f"MATCH (n:{t}) RETURN count(n) AS count") for t in ["EvidenceDoc", "Concept", "Issue"])
        edge_count = sum(self._count(conn, f"MATCH ()-[r:{t}]->() RETURN count(r) AS count") for t in ["MENTIONS", "HAS_TERM", "HAS_ENERGY"])
        return KuzuGraphState(graph_id=GRAPH_ID, db_path=str(self.db_root), synced_at=datetime.now(UTC).isoformat(), workspace_digest=digest, document_count=len(documents), chart_count=len(charts), draw_count=len(completed) + len(pending), node_count=node_count, edge_count=edge_count)

    def _search_snapshot(self, state: KuzuGraphState, query: str, chart_count: int, visible_periods: set[str] | None) -> GraphSnapshot:
        conn = self._connection()
        node_queries = [
            "MATCH (n:EvidenceDoc) RETURN n.id AS id, 'document' AS node_kind, n.name AS name, n.content AS content, '' AS period",
            "MATCH (n:Issue) RETURN n.id AS id, 'draw' AS node_kind, n.period AS name, n.text AS content, n.period AS period",
            "MATCH (n:Concept) RETURN n.id AS id, 'concept' AS node_kind, n.name AS name, '' AS content, '' AS period"
        ]
        edge_queries = [
            "MATCH (a:EvidenceDoc)-[r:MENTIONS]->(b:Concept) RETURN a.id AS source_id, a.name AS source_name, '' AS source_period, b.id AS target_id, b.name AS target_name, '' AS target_period, 'MENTIONS' AS relation, r.weight AS weight",
            "MATCH (a:EvidenceDoc)-[r:HAS_TERM]->(b:Concept) RETURN a.id AS source_id, a.name AS source_name, '' AS source_period, b.id AS target_id, b.name AS target_name, '' AS target_period, 'HAS_TERM' AS relation, r.weight AS weight",
            "MATCH (a:Issue)-[r:HAS_ENERGY]->(b:Concept) RETURN a.id AS source_id, a.period AS source_name, a.period AS source_period, b.id AS target_id, b.name AS target_name, '' AS target_period, 'HAS_ENERGY' AS relation, r.weight AS weight"
        ]
        
        nodes = []
        for q in node_queries:
            nodes.extend(row for row in list(conn.execute(q).rows_as_dict()) if self._node_visible(row, visible_periods))
            
        edges = []
        for q in edge_queries:
            edges.extend(row for row in list(conn.execute(q).rows_as_dict()) if self._edge_visible(row, visible_periods))
        query_terms = self._query_terms(query)
        scores = self._score_nodes(nodes, query_terms)
        previews, related_ids = self._score_edges(edges, query_terms, scores)
        digest = hashlib.md5(f"{state.graph_id}|{query}".encode("utf-8")).hexdigest()[:10]
        return GraphSnapshot(snapshot_id=f"kuzu_{digest}", node_count=state.node_count, edge_count=state.edge_count, highlights=self._highlights(scores, query_terms), concept_scores=dict(scores), source_documents=self._source_documents(nodes, related_ids), chart_count=chart_count, preview_relations=tuple(previews[:6]), provider="kuzu", backend_graph_id=state.graph_id, query=query)

    def _score_nodes(self, nodes: list[dict[str, object]], query_terms: tuple[str, ...]) -> Counter:
        scores = Counter()
        for node in nodes:
            text = " ".join(str(node[key] or "") for key in ("name", "content", "period"))
            matched = sum(1 for term in query_terms if term in text)
            if matched:
                for term in self._query_terms(text):
                    scores[term] += float(matched)
        return scores

    def _score_edges(self, edges: list[dict[str, object]], query_terms: tuple[str, ...], scores: Counter) -> tuple[list[str], set[str]]:
        previews, related_ids = [], set()
        for edge in edges:
            summary = f"{edge['source_name']} {edge['relation']} {edge['target_name']}"
            if any(term in summary for term in query_terms) or edge["relation"] in {"MENTIONS", "HAS_TERM", "HAS_ENERGY"}:
                related_ids.update((edge["source_id"], edge["target_id"]))
                previews.append(f"{edge['source_name']} --{edge['relation']}--> {edge['target_name']}")
                for term in self._query_terms(summary):
                    scores[term] += float(edge["weight"] or 1.0)
        return previews, related_ids

    def _source_documents(self, nodes: list[dict[str, object]], related_ids: set[str]) -> tuple[str, ...]:
        names = [str(node["name"]) for node in nodes if node["id"] in related_ids and node["node_kind"] in {"document", "chart"}]
        return tuple(names[:6])

    def _highlights(self, scores: Counter, query_terms: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(term for term, _ in scores.most_common(12)) if scores else tuple(query_terms[:12])

    def _create_schema(self, conn: kuzu.Connection) -> None:
        tables = ["Relation", "POSTED_SIGNAL", "FOR_ISSUE", "SCORES_NUMBER", "MENTIONS", "HAS_ENERGY", "TRUSTS", "FOLLOWS", "Entity", "Agent", "Issue", "Signal", "NumberNode", "BetPlan", "EvidenceDoc", "Concept"]
        for t in tables:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
            
        # Node Tables
        conn.execute("CREATE NODE TABLE EvidenceDoc(id STRING, name STRING, path STRING, content STRING, PRIMARY KEY(id))")
        conn.execute("CREATE NODE TABLE Concept(id STRING, name STRING, PRIMARY KEY(id))")
        conn.execute("CREATE NODE TABLE Issue(id STRING, period STRING, text STRING, PRIMARY KEY(id))")
        
        # Rel Tables
        conn.execute("CREATE REL TABLE MENTIONS(FROM EvidenceDoc TO Concept, weight DOUBLE)")
        conn.execute("CREATE REL TABLE HAS_TERM(FROM EvidenceDoc TO Concept, weight DOUBLE)")
        conn.execute("CREATE REL TABLE HAS_ENERGY(FROM Issue TO Concept, weight DOUBLE)")


    def _bulk_load(self, conn, documents, charts, completed, pending) -> None:
        doc_rows, concept_rows, issue_rows, rel_rows = self._workspace_rows(documents, charts, completed, pending)
        
        mentions = [(r[0], r[1], r[3]) for r in rel_rows if r[2] == "MENTIONS"]
        has_term = [(r[0], r[1], r[3]) for r in rel_rows if r[2] == "HAS_TERM"]
        has_energy = [(r[0], r[1], r[3]) for r in rel_rows if r[2] == "HAS_ENERGY"]
        
        with tempfile.TemporaryDirectory(dir=str(self.db_root.parent)) as temp_dir:
            doc_csv = self._write_csv(Path(temp_dir) / "docs.csv", ("id", "name", "path", "content"), doc_rows)
            concept_csv = self._write_csv(Path(temp_dir) / "concepts.csv", ("id", "name"), concept_rows)
            issue_csv = self._write_csv(Path(temp_dir) / "issues.csv", ("id", "period", "text"), issue_rows)
            
            mentions_csv = self._write_csv(Path(temp_dir) / "mentions.csv", ("from", "to", "weight"), mentions)
            has_term_csv = self._write_csv(Path(temp_dir) / "has_term.csv", ("from", "to", "weight"), has_term)
            has_energy_csv = self._write_csv(Path(temp_dir) / "has_energy.csv", ("from", "to", "weight"), has_energy)
            
            conn.execute(f'COPY EvidenceDoc FROM "{doc_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Concept FROM "{concept_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Issue FROM "{issue_csv}" (PARALLEL=FALSE)')
            
            if mentions: conn.execute(f'COPY MENTIONS FROM "{mentions_csv}" (PARALLEL=FALSE)')
            if has_term: conn.execute(f'COPY HAS_TERM FROM "{has_term_csv}" (PARALLEL=FALSE)')
            if has_energy: conn.execute(f'COPY HAS_ENERGY FROM "{has_energy_csv}" (PARALLEL=FALSE)')

    def _workspace_rows(self, documents, charts, completed, pending):
        doc_rows = []
        concept_map = {}
        issue_rows = []
        rel_rows = []
        
        for item in documents:
            node_id = f"doc:{item.relative_path}"
            doc_rows.append((node_id, item.name, item.relative_path, item.content))
            for term in {t for t in item.terms if t}:
                cid = f"concept:{term}"
                concept_map[cid] = (cid, term)
                rel_rows.append((node_id, cid, "MENTIONS", 2.0))
                
        for item in charts:
            node_id = f"chart:{item.relative_path}"
            doc_rows.append((node_id, item.name, item.relative_path, item.content))
            for term in {t for t in item.feature_terms if t}:
                cid = f"concept:{term}"
                concept_map[cid] = (cid, term)
                rel_rows.append((node_id, cid, "HAS_TERM", 3.0))
                
        for draw in (*completed, *pending):
            node_id = f"draw:{draw.period}"
            issue_rows.append((node_id, draw.period, self._draw_text(draw)))
            for term in {t for t in self._draw_terms(draw) if t}:
                cid = f"concept:{term}"
                concept_map[cid] = (cid, term)
                rel_rows.append((node_id, cid, "HAS_ENERGY", 1.0))
                
        return doc_rows, list(concept_map.values()), issue_rows, rel_rows

    def _write_csv(self, path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return path.as_posix()

    def _count(self, conn, query: str) -> int:
        rows = list(conn.execute(query).rows_as_dict())
        return int(rows[0]["count"]) if rows else 0

    def _prediction_query(self, history_draws: list[DrawRecord], target_draw: DrawRecord) -> str:
        recent = " ".join(draw.period for draw in history_draws[-3:])
        parts = [target_draw.period, target_draw.daily_energy.stem, target_draw.daily_energy.branch, *target_draw.daily_energy.mutagen, target_draw.hourly_energy.stem, target_draw.hourly_energy.branch, *target_draw.hourly_energy.mutagen, recent, "紫微斗数", "命盘", "选号"]
        return " ".join(part for part in parts if part)

    def _draw_terms(self, draw: DrawRecord) -> tuple[str, ...]:
        return tuple((*draw.daily_energy.mutagen, *draw.hourly_energy.mutagen, draw.daily_energy.stem, draw.daily_energy.branch, draw.hourly_energy.stem, draw.hourly_energy.branch))

    def _draw_text(self, draw: DrawRecord) -> str:
        numbers = ",".join(str(number) for number in draw.numbers) if draw.numbers else "pending"
        daily = f"{draw.daily_energy.stem}{draw.daily_energy.branch} {' '.join(draw.daily_energy.mutagen)}"
        hourly = f"{draw.hourly_energy.stem}{draw.hourly_energy.branch} {' '.join(draw.hourly_energy.mutagen)}"
        return f"period={draw.period}\ndate={draw.date}\nnumbers={numbers}\ndaily={daily}\nhourly={hourly}"

    def _query_terms(self, text: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*extract_domain_terms(text), *NUMBER_PATTERN.findall(text))))

    def _draw_digest(self, draw: DrawRecord) -> str:
        payload = [draw.period, draw.date, *(str(number) for number in draw.numbers), *draw.daily_energy.mutagen, *draw.hourly_energy.mutagen]
        return ":".join(payload)

    def _node_visible(self, node: dict[str, object], visible_periods: set[str] | None) -> bool:
        period = str(node["period"] or "")
        return not visible_periods or not period or period in visible_periods

    def _edge_visible(self, edge: dict[str, object], visible_periods: set[str] | None) -> bool:
        if not visible_periods:
            return True
        source_period = str(edge["source_period"] or "")
        target_period = str(edge["target_period"] or "")
        return (not source_period or source_period in visible_periods) and (not target_period or target_period in visible_periods)

    def _require_state(self, graph_id: str | None) -> KuzuGraphState:
        state = self.state_store.load()
        if not state or not Path(state.db_path).exists():
            raise ValueError("Kuzu graph is not synced yet, sync it first from the lottery graph panel.")
        if graph_id and graph_id != state.graph_id:
            raise ValueError(f"Kuzu graph id does not match active graph: {graph_id}")
        return state

    def _reset_db(self) -> None:
        self._clear_database()
        if self.db_root.exists():
            if self.db_root.is_dir():
                shutil.rmtree(self.db_root)
            else:
                self.db_root.unlink()
        self.db_root.parent.mkdir(parents=True, exist_ok=True)

    def _connection(self) -> kuzu.Connection:
        return kuzu.Connection(self._database_handle())

    def _database_handle(self) -> kuzu.Database:
        with self._database_lock:
            if self._database is None:
                self._database = kuzu.Database(str(self.db_root))
            return self._database

    def _clear_database(self) -> None:
        with self._database_lock:
            self._database = None
