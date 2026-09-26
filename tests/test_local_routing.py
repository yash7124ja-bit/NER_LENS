from dataclasses import replace

import httpx

from ner_lens.config import Settings
from ner_lens.local_routing import retrieve_local_graphhopper

DATE = "2026-09-09T20:21:20Z"


def test_private_graph_uses_requested_vehicle_profile_and_persists_provenance():
    requests = []

    def reply(request):
        requests.append(request)
        if request.url.path == "/info":
            return httpx.Response(200, json={
                "data_date": DATE, "profiles": [{"name": "rigid_truck"}],
            })
        assert request.url.path == "/route"
        assert request.url.params.get("profile") == "rigid_truck"
        assert request.url.params.get_list("point") == ["26,91", "25,92"]
        return httpx.Response(200, json={"paths": [{
            "distance": 1000, "time": 120000,
            "points": {"type": "LineString", "coordinates": [[91, 26], [92, 25]]},
        }]})

    settings = Settings(
        graphhopper_local_url="http://graphhopper:8989", graphhopper_data_date=DATE
    )
    snapshot = retrieve_local_graphhopper(
        settings, points=[[91, 26], [92, 25]], profile="rigid_truck",
        transport=httpx.MockTransport(reply),
    )
    assert len(requests) == 2
    assert snapshot.status == "available" and snapshot.sha256 and snapshot.raw
    assert snapshot.url == "private://graphhopper/route"
    assert snapshot.records[0]["vehicle_profile"] == "rigid_truck"
    assert snapshot.records[0]["observed_at"] == DATE
    assert snapshot.records[0]["duration_seconds"] == 120
    assert snapshot.records[0]["snapshot_sha256"] == snapshot.sha256


def test_private_graph_rejects_mismatched_extract_and_public_egress():
    settings = Settings(
        graphhopper_local_url="http://graphhopper:8989", graphhopper_data_date=DATE
    )
    calls = []

    def wrong_graph(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"data_date": "2020-01-01T00:00:00Z"})

    result = retrieve_local_graphhopper(
        settings, points=[[91, 26], [92, 25]], profile="rigid_truck",
        transport=httpx.MockTransport(wrong_graph),
    )
    assert result.status == "failed"
    assert result.reason == "graphhopper_graph_version_mismatch"
    assert calls == ["/info"]

    public = replace(settings, graphhopper_local_url="https://graphhopper.com/api/1")
    rejected = retrieve_local_graphhopper(
        public, points=[[91, 26], [92, 25]], profile="rigid_truck",
        transport=httpx.MockTransport(lambda _: (_ for _ in ()).throw(AssertionError())),
    )
    assert rejected.status == "failed"
    assert rejected.reason == "invalid_private_graphhopper_url"
