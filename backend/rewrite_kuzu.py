import re

filepath = r"e:\MoFish\MiroFish\backend\app\services\lottery\kuzu_graph.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace _create_schema
schema_target = """    def _create_schema(self, conn: kuzu.Connection) -> None:
        conn.execute("DROP TABLE IF EXISTS Relation")
        conn.execute("DROP TABLE IF EXISTS Entity")
        conn.execute("CREATE NODE TABLE Entity(id STRING, node_kind STRING, name STRING, source_path STRING, content STRING, period STRING, PRIMARY KEY(id))")
        conn.execute("CREATE REL TABLE Relation(FROM Entity TO Entity, relation STRING, weight DOUBLE)")"""

schema_repl = """    def _create_schema(self, conn: kuzu.Connection) -> None:
        tables = ["Relation", "POSTED_SIGNAL", "FOR_ISSUE", "SCORES_NUMBER", "MENTIONS", "HAS_ENERGY", "TRUSTS", "FOLLOWS", "Entity", "Agent", "Issue", "Signal", "NumberNode", "BetPlan", "EvidenceDoc", "Concept"]
        for t in tables:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
            
        # Node Tables
        conn.execute("CREATE NODE TABLE EvidenceDoc(id STRING, name STRING, path STRING, content STRING, PRIMARY KEY(id))")
        conn.execute("CREATE NODE TABLE Concept(id STRING, name STRING, PRIMARY KEY(id))")
        conn.execute("CREATE NODE TABLE Issue(id STRING, period STRING, text STRING, PRIMARY KEY(id))")
        
        # Rel Tables
        conn.execute("CREATE REL TABLE Relation(FROM EvidenceDoc TO Concept, FROM Issue TO Concept, relation STRING, weight DOUBLE)")
"""
content = content.replace(schema_target, schema_repl)


search_target = """    def _search_snapshot(self, state: KuzuGraphState, query: str, chart_count: int, visible_periods: set[str] | None) -> GraphSnapshot:
        conn = self._connection()
        nodes = [row for row in list(conn.execute(NODE_QUERY).rows_as_dict()) if self._node_visible(row, visible_periods)]
        edges = [row for row in list(conn.execute(EDGE_QUERY).rows_as_dict()) if self._edge_visible(row, visible_periods)]"""

search_repl = """    def _search_snapshot(self, state: KuzuGraphState, query: str, chart_count: int, visible_periods: set[str] | None) -> GraphSnapshot:
        conn = self._connection()
        node_queries = [
            "MATCH (n:EvidenceDoc) RETURN n.id AS id, 'document' AS node_kind, n.name AS name, n.content AS content, '' AS period",
            "MATCH (n:Issue) RETURN n.id AS id, 'draw' AS node_kind, n.period AS name, n.text AS content, n.period AS period",
            "MATCH (n:Concept) RETURN n.id AS id, 'concept' AS node_kind, n.name AS name, '' AS content, '' AS period"
        ]
        edge_queries = [
            "MATCH (a:EvidenceDoc)-[r:Relation]->(b:Concept) RETURN a.id AS source_id, a.name AS source_name, '' AS source_period, b.id AS target_id, b.name AS target_name, '' AS target_period, r.relation AS relation, r.weight AS weight",
            "MATCH (a:Issue)-[r:Relation]->(b:Concept) RETURN a.id AS source_id, a.period AS source_name, a.period AS source_period, b.id AS target_id, b.name AS target_name, '' AS target_period, r.relation AS relation, r.weight AS weight"
        ]
        
        nodes = []
        for q in node_queries:
            nodes.extend(row for row in list(conn.execute(q).rows_as_dict()) if self._node_visible(row, visible_periods))
            
        edges = []
        for q in edge_queries:
            edges.extend(row for row in list(conn.execute(q).rows_as_dict()) if self._edge_visible(row, visible_periods))"""

content = content.replace(search_target, search_repl)


bulk_load_target = """    def _bulk_load(self, conn, documents, charts, completed, pending) -> None:
        node_rows, edge_rows = self._workspace_rows(documents, charts, completed, pending)
        with tempfile.TemporaryDirectory(dir=str(self.db_root.parent)) as temp_dir:
            node_csv = self._write_csv(Path(temp_dir) / "nodes.csv", ("id", "node_kind", "name", "source_path", "content", "period"), node_rows)
            edge_csv = self._write_csv(Path(temp_dir) / "edges.csv", ("from", "to", "relation", "weight"), edge_rows)
            conn.execute(f'COPY Entity FROM "{node_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Relation FROM "{edge_csv}" (PARALLEL=FALSE)')"""

bulk_load_repl = """    def _bulk_load(self, conn, documents, charts, completed, pending) -> None:
        doc_rows, concept_rows, issue_rows, rel_rows = self._workspace_rows(documents, charts, completed, pending)
        with tempfile.TemporaryDirectory(dir=str(self.db_root.parent)) as temp_dir:
            doc_csv = self._write_csv(Path(temp_dir) / "docs.csv", ("id", "name", "path", "content"), doc_rows)
            concept_csv = self._write_csv(Path(temp_dir) / "concepts.csv", ("id", "name"), concept_rows)
            issue_csv = self._write_csv(Path(temp_dir) / "issues.csv", ("id", "period", "text"), issue_rows)
            rel_csv = self._write_csv(Path(temp_dir) / "rels.csv", ("from", "to", "relation", "weight"), rel_rows)
            
            conn.execute(f'COPY EvidenceDoc FROM "{doc_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Concept FROM "{concept_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Issue FROM "{issue_csv}" (PARALLEL=FALSE)')
            conn.execute(f'COPY Relation FROM "{rel_csv}" (PARALLEL=FALSE)')"""

content = content.replace(bulk_load_target, bulk_load_repl)


workspace_rows_target = """    def _workspace_rows(self, documents, charts, completed, pending) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
        node_map: dict[str, tuple[object, ...]] = {}
        edge_rows: list[tuple[object, ...]] = []
        for item in documents:
            node_id = f"doc:{item.relative_path}"
            node_map[node_id] = (node_id, "document", item.name, item.relative_path, item.content, "")
            self._attach_terms(node_map, edge_rows, node_id, item.terms, "MENTIONS", 2.0)
        for item in charts:
            node_id = f"chart:{item.relative_path}"
            period = str(item.metadata.get("period", "")).strip()
            node_map[node_id] = (node_id, "chart", item.name, item.relative_path, item.content, period)
            self._attach_terms(node_map, edge_rows, node_id, item.feature_terms, "HAS_TERM", 3.0)
        for draw in (*completed, *pending):
            node_id = f"draw:{draw.period}"
            node_map[node_id] = (node_id, "draw", draw.period, draw.period, self._draw_text(draw), draw.period)
            self._attach_terms(node_map, edge_rows, node_id, self._draw_terms(draw), "HAS_ENERGY", 1.0)
        return list(node_map.values()), edge_rows

    def _attach_terms(self, node_map: dict[str, tuple[object, ...]], edge_rows: list[tuple[object, ...]], source_id: str, terms: tuple[str, ...], relation: str, weight: float) -> None:
        for term in {term for term in terms if term}:
            concept_id = f"concept:{term}"
            node_map[concept_id] = (concept_id, "concept", term, term, term, "")
            edge_rows.append((source_id, concept_id, relation, weight))"""

workspace_rows_repl = """    def _workspace_rows(self, documents, charts, completed, pending):
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
                
        return doc_rows, list(concept_map.values()), issue_rows, rel_rows"""

content = content.replace(workspace_rows_target, workspace_rows_repl)


with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Kuzu Graph Updated to Typed Schema!")
