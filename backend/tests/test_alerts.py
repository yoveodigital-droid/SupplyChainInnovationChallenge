"""Alert composer: length discipline and localisation."""

from __future__ import annotations

import pytest

from app.config import SUPPORTED_LANGUAGES
from app.models import Shipment
from app.services.alerts import MAX_CHARS, compose_alert, compose_confirmation
from app.services.exposure import Plan

AMINA = "SHP-AMN-001"


def _bundle(stack, shipment_id=AMINA, lang="en"):
    shipment = stack.db.get(Shipment, shipment_id)
    plan = Plan(
        legs=[stack.recommender.legs[i] for i in shipment.leg_ids],
        etd=max(shipment.etd, stack.sim_date),
        teu=shipment.teu,
        perishable=shipment.perishable,
        shelf_life_days=shipment.shelf_life_days,
        value_usd=shipment.value_usd,
        required_by=shipment.required_by,
    )
    exposure = stack.exposure.evaluate(plan)
    options = stack.recommender.recommend(shipment)
    return shipment, exposure, options, compose_alert(shipment, exposure, options, lang)


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_alert_fits_a_text_message(stack, lang):
    stack.trigger()
    stack.advance()
    *_, bundle = _bundle(stack, lang=lang)
    assert bundle.alert_chars <= MAX_CHARS
    assert bundle.within_limit
    assert bundle.language == lang


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_calm_alert_also_fits(stack, lang):
    *_, bundle = _bundle(stack, lang=lang)
    assert bundle.alert_chars <= MAX_CHARS
    assert bundle.risk_level == "green"
    assert bundle.messages[0].kind == "calm"


def test_disrupted_alert_names_the_numbers_that_matter(stack):
    stack.trigger()
    stack.advance()
    _, exposure, _, bundle = _bundle(stack)
    text = bundle.alert_text
    assert text.startswith("⚠️ PortPulse:")
    assert "%" in text
    assert "Spoilage risk: HIGH" in text
    assert "mangoes" in text
    assert "Jeddah" in text
    assert "Jeddah Islamic Port" not in text, "use the short name in an SMS"
    assert "Reply 1" in text


def test_swahili_is_a_real_translation_not_a_copy(stack):
    stack.trigger()
    stack.advance()
    *_, english = _bundle(stack, lang="en")
    *_, swahili = _bundle(stack, lang="sw")
    assert swahili.alert_text != english.alert_text
    assert "hatari" in swahili.alert_text
    assert "Jibu 1" in swahili.alert_text


def test_unknown_language_falls_back_to_english(stack):
    stack.trigger()
    *_, bundle = _bundle(stack, lang="xx")
    assert bundle.language == "en"


def test_conversation_walks_through_the_options(stack):
    stack.trigger()
    stack.advance()
    _, _, options, bundle = _bundle(stack)
    kinds = [m.kind for m in bundle.messages]
    assert kinds[0] == "alert"
    assert "prompt" in kinds
    option_messages = [m for m in bundle.messages if m.kind == "option"]
    assert len(option_messages) == len(options)
    assert sum(1 for m in option_messages if m.recommended) == 1
    for message in option_messages:
        assert {c["key"] for c in message.chips} == {"cost", "time", "risk", "co2"}
        assert message.option_id


def test_confirmation_reflects_the_accepted_option(stack):
    stack.trigger()
    stack.advance()
    shipment, exposure, options, _ = _bundle(stack)
    top = next(o for o in options if o.rank == 1)
    message = compose_confirmation(shipment, exposure, top, "en")
    assert message.kind == "confirmation"
    assert len(message.text) <= MAX_CHARS
    assert "Booked" in message.text or "No change" in message.text


def test_holding_is_confirmed_without_pretending_something_changed(stack):
    stack.trigger()
    shipment, exposure, options, _ = _bundle(stack)
    hold = next(o for o in options if o.kind == "hold")
    message = compose_confirmation(shipment, exposure, hold, "en")
    assert "No change made" in message.text
