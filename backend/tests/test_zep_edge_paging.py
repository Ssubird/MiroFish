from types import SimpleNamespace

from app.utils import zep_paging


def _client():
    edge_api = SimpleNamespace(get_by_graph_id=lambda *args, **kwargs: [])
    return SimpleNamespace(graph=SimpleNamespace(edge=edge_api))


def test_edge_cap_stops_pagination_at_requested_limit(monkeypatch):
    pages = [
        [SimpleNamespace(uuid_="e1"), SimpleNamespace(uuid_="e2")],
        [SimpleNamespace(uuid_="e3"), SimpleNamespace(uuid_="e4")],
    ]
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]

    monkeypatch.setattr(zep_paging, "_fetch_page_with_retry", fake_fetch)

    result = zep_paging.fetch_all_edges(_client(), "graph", page_size=2, max_items=3)

    assert [edge.uuid_ for edge in result] == ["e1", "e2", "e3"]
    assert len(calls) == 2
    assert calls[1]["uuid_cursor"] == "e2"


def test_existing_positional_retry_arguments_keep_their_meaning(monkeypatch):
    observed = {}

    def fake_fetch(*args, **kwargs):
        observed.update(kwargs)
        return []

    monkeypatch.setattr(zep_paging, "_fetch_page_with_retry", fake_fetch)

    zep_paging.fetch_all_edges(_client(), "graph", 25, 7, 0.25)

    assert observed["limit"] == 25
    assert observed["max_retries"] == 7
    assert observed["retry_delay"] == 0.25
