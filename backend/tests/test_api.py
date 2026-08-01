"""API contract and the end-to-end demo script from §7 of the brief."""

from __future__ import annotations

from collections import Counter

import pytest

AMINA = "SHP-AMN-001"


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["name"] == "PortPulse"
    assert "synthetic data" in meta["disclaimer"]
    assert meta["languages"] == ["en", "sw"]
    assert meta["model"]["congestion_mae"] < meta["model"]["congestion_mae_naive"]


def test_reference_endpoints(client):
    ports = client.get("/api/ports").json()
    assert len(ports) == 28
    assert all(p["risk_level"] in ("green", "amber", "red") for p in ports)
    assert {"SGSIN", "SAJED", "KEMBA", "OMSLL", "ZADUR"} <= {p["id"] for p in ports}

    legs = client.get("/api/legs").json()
    assert any(leg["mode"] == "land" for leg in legs)
    assert any("bab_el_mandeb" in leg["chokepoints"] for leg in legs)

    personas = client.get("/api/personas").json()
    assert [p["id"] for p in personas] == ["amina", "rafael", "jeddah_pa"]
    assert [p["shipment_count"] for p in personas] == [1, 8, 0]

    assert len(client.get("/api/chokepoints").json()) == 5
    assert client.get("/api/events").json()


def test_unknown_ids_are_404(client):
    assert client.get("/api/ports/NOPE").status_code == 404
    assert client.get("/api/shipments/NOPE").status_code == 404
    assert client.get("/api/shipments/NOPE/exposure").status_code == 404
    assert client.get("/api/shipments?persona=nobody").status_code == 404
    assert client.get(f"/api/shipments/{AMINA}/alert?lang=fr").status_code == 400


def test_forecast_endpoint(client):
    body = client.get("/api/ports/SAJED/forecast?horizon=14").json()
    assert body["port_id"] == "SAJED"
    assert len(body["points"]) == 14
    assert body["explanation"]
    assert "gradient-boosted" in body["model_note"].lower()


def test_pressure_endpoint_serves_the_port_view(client):
    body = client.get("/api/ports/SAJED/pressure").json()
    assert body["port"]["id"] == "SAJED"
    assert len(body["history"]) == 60
    assert len(body["forecast"]) == 14
    assert body["summary"]
    assert body["peak_day"]
    assert body["inbound_shipments"] >= 3


def test_shipment_list_is_sorted_by_risk(client):
    client.post("/api/demo/trigger")
    client.post("/api/demo/advance")
    rows = client.get("/api/shipments").json()
    scores = [r["risk_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_exposure_endpoint_shape(client):
    body = client.get(f"/api/shipments/{AMINA}/exposure").json()
    assert body["shipment_id"] == AMINA
    assert body["calls"] and body["legs"] and body["delay_distribution"]
    assert body["delay_p10"] <= body["expected_delay_days"] <= body["delay_p90"]


def test_recommendations_endpoint_documents_its_objective(client):
    body = client.get(f"/api/shipments/{AMINA}/recommendations").json()
    assert "landed cost" in body["objective"]
    assert body["assumptions"]["carbon_price_usd_per_tonne"] == 95.0
    assert any(o["kind"] == "hold" for o in body["options"])


def test_feedback_round_trip(client):
    posted = client.post(
        "/api/feedback", json={"shipment_id": AMINA, "helpful": True, "note": "clear"}
    ).json()
    assert posted["helpful"] is True
    assert any(f["id"] == posted["id"] for f in client.get("/api/feedback").json())


def test_demo_clock(client):
    start = client.get("/api/demo/state").json()
    advanced = client.post("/api/demo/advance").json()
    assert advanced["days_advanced"] == start["days_advanced"] + 1
    assert advanced["data_version"] > start["data_version"]
    reset = client.post("/api/demo/reset").json()
    assert reset["days_advanced"] == 0
    assert reset["scenario_active"] is False


def test_revert_restores_the_original_booking(client):
    client.post("/api/demo/trigger")
    client.post("/api/demo/advance")
    before = client.get(f"/api/shipments/{AMINA}").json()
    options = client.get(f"/api/shipments/{AMINA}/recommendations").json()["options"]
    top = next(o for o in options if o["rank"] == 1)
    client.post(f"/api/shipments/{AMINA}/accept", json={"option_id": top["id"]})
    reverted = client.post(f"/api/shipments/{AMINA}/revert").json()
    assert reverted["leg_ids"] == before["leg_ids"]
    assert reverted["etd"] == before["etd"]
    assert reverted["applied_option"] is None


# --------------------------------------------------------------------------- #
# The scripted demo, start to finish
# --------------------------------------------------------------------------- #


def test_scripted_demo_runs_end_to_end(client):
    """§7 of the brief, as an executable checklist."""
    # 1. Seed state: everything calm, Amina's mangoes green.
    amina = client.get(f"/api/shipments/{AMINA}").json()
    assert amina["risk_level"] == "green"
    assert all(s["risk_level"] == "green" for s in client.get("/api/shipments").json())
    assert client.get(f"/api/shipments/{AMINA}/alert").json()["risk_level"] == "green"

    # 2. Presenter triggers the scenario, then advances one day.
    client.post("/api/demo/trigger")
    client.post("/api/demo/advance")
    state = client.get("/api/demo/state").json()
    assert state["scenario_active"] and state["scenario_day"] == 1

    # 3. Amina flips red with HIGH spoilage.
    amina = client.get(f"/api/shipments/{AMINA}").json()
    assert amina["risk_level"] == "red"
    assert amina["spoilage_probability"] > 0.5

    # 4. Her phone receives an alert that fits a text message.
    alert = client.get(f"/api/shipments/{AMINA}/alert").json()
    assert alert["within_limit"] and alert["risk_level"] == "red"
    assert "Salalah" in alert["alert_text"]

    # 5. The top recommendation is a Salalah reroute, and "hold" is quantified.
    options = client.get(f"/api/shipments/{AMINA}/recommendations").json()["options"]
    top = next(o for o in options if o["rank"] == 1)
    assert "Salalah" in top["label"]
    assert top["kind"] != "hold"
    assert top["delta_risk_days"] > 2
    hold = next(o for o in options if o["kind"] == "hold")
    assert hold["risk_level"] == "red"

    # 6. Rafael sees three of eight bookings amber or red.
    rafael = client.get("/api/shipments?persona=rafael").json()
    assert len(rafael) == 8
    counts = Counter(s["risk_level"] for s in rafael)
    assert counts["amber"] + counts["red"] == 3

    # 7. Jeddah sees the inbound wave.
    pressure = client.get("/api/ports/SAJED/pressure").json()
    assert pressure["peak_congestion"] > pressure["port"]["congestion_threshold"]
    assert "pressure" in pressure["summary"].lower()
    assert any(e["scenario"] for e in pressure["upstream_events"])

    # 8. Amina accepts. Route changes, risk drops, confirmation is sent.
    accepted = client.post(f"/api/shipments/{AMINA}/accept", json={"option_id": top["id"]}).json()
    assert accepted["shipment"]["rerouted"]
    assert accepted["shipment"]["leg_ids"] == top["leg_ids"]
    assert accepted["shipment"]["risk_level"] in ("green", "amber")
    assert accepted["shipment"]["risk_score"] < amina["risk_score"]
    assert accepted["message"]["kind"] == "confirmation"

    # 9. Reset puts everything back for the next run.
    client.post("/api/demo/reset")
    assert client.get(f"/api/shipments/{AMINA}").json()["risk_level"] == "green"


@pytest.mark.parametrize("lang", ["en", "sw"])
def test_alert_is_available_in_both_languages_during_the_demo(client, lang):
    client.post("/api/demo/trigger")
    client.post("/api/demo/advance")
    alert = client.get(f"/api/shipments/{AMINA}/alert?lang={lang}").json()
    assert alert["language"] == lang
    assert alert["within_limit"]
    assert len(alert["messages"]) > 3
