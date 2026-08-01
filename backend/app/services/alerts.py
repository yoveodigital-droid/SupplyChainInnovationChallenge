"""Alert composer — the hero output.

Turns an exposure assessment plus the top recommendation into a WhatsApp-length
message (hard cap 400 characters), in English or Swahili.

Localisation is a plain template dictionary rather than a framework: the point
is to show that the message is *composed from structured fields*, so adding a
language is a translation task, not an engineering one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..config import SUPPORTED_LANGUAGES
from .exposure import Exposure
from .recommend import Option

MAX_CHARS = 400


@dataclass
class ChatMessage:
    id: str
    sender: str  # portpulse | user
    kind: str  # alert | prompt | option | confirmation | calm | followup
    text: str
    chips: list[dict] = field(default_factory=list)
    option_id: str | None = None
    recommended: bool = False


@dataclass
class AlertBundle:
    shipment_id: str
    language: str
    risk_level: str
    alert_text: str
    alert_chars: int
    within_limit: bool
    messages: list[ChatMessage]
    quick_replies: list[str]


TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "alert": (
            "⚠️ PortPulse: {risk}% risk of {days}+ day delay at {port} for your booking "
            "ETD {etd} ({cargo}, {teu} TEU). {spoilage}"
            "Best option: {option} — est. {cost}, {risk_days} risk days, {co2} CO₂. "
            "Reply 1 to see all options."
        ),
        "calm": (
            "✅ PortPulse: your booking {ref} ({cargo}, {teu} TEU) ETD {etd} is on track. "
            "{port} is running normally — {risk}% risk of missing your {required_by} deadline. "
            "Confidence {confidence}%. We'll message you if that changes."
        ),
        "spoilage": "Spoilage risk: {band}. ",
        "prompt": "1",
        "options_intro": "Here are your options, ranked. Numbers are versus keeping the current booking.",
        "option": "{marker} {label}\n{rationale}",
        "confirm_prompt": "Reply with the number to switch, or 0 to keep the current booking.",
        "confirmed": (
            "✅ Booked. {label}. New ETD {etd}, expected arrival {arrival}. "
            "Risk is now {risk_level} ({risk}% chance of missing your deadline). "
            "Your buyer has been notified."
        ),
        "kept": "👍 No change made. We'll keep watching {port} and message you if the picture changes.",
        "feedback": "Was this alert useful?",
        "band_high": "HIGH",
        "band_medium": "MEDIUM",
        "band_low": "LOW",
    },
    "sw": {
        "alert": (
            "⚠️ PortPulse: hatari {risk}% ya kuchelewa siku {days}+ bandari ya {port} kwa mzigo wako "
            "utakaosafiri {etd} ({cargo}, TEU {teu}). {spoilage}"
            "Chaguo bora: {option} — takriban {cost}, siku {risk_days} za hatari, {co2} CO₂. "
            "Jibu 1 kuona chaguo zote."
        ),
        "calm": (
            "✅ PortPulse: mzigo wako {ref} ({cargo}, TEU {teu}) wa tarehe {etd} uko sawa. "
            "{port} inafanya kazi kawaida — hatari {risk}% ya kukosa tarehe ya {required_by}. "
            "Uhakika {confidence}%. Tutakujulisha hali ikibadilika."
        ),
        "spoilage": "Hatari ya kuharibika: {band}. ",
        "prompt": "1",
        "options_intro": "Haya ni machaguo yako kwa mpangilio. Namba ni kulinganisha na mpango wa sasa.",
        "option": "{marker} {label}\n{rationale}",
        "confirm_prompt": "Jibu namba ya chaguo, au 0 kubaki na mpango wa sasa.",
        "confirmed": (
            "✅ Imethibitishwa. {label}. Safari mpya {etd}, kuwasili {arrival}. "
            "Hatari sasa ni {risk_level} ({risk}% ya kukosa tarehe). "
            "Mnunuzi wako amejulishwa."
        ),
        "kept": "👍 Hakuna mabadiliko. Tutaendelea kufuatilia {port} na kukujulisha hali ikibadilika.",
        "feedback": "Je, taarifa hii imesaidia?",
        "band_high": "KUBWA",
        "band_medium": "WASTANI",
        "band_low": "NDOGO",
    },
}

RISK_LEVEL_WORDS = {
    "en": {"green": "low", "amber": "moderate", "red": "high"},
    "sw": {"green": "ndogo", "amber": "wastani", "red": "kubwa"},
}


def _t(lang: str, key: str) -> str:
    return TEMPLATES.get(lang, TEMPLATES["en"]).get(key, TEMPLATES["en"][key])


def _fmt_date(d: date) -> str:
    return d.strftime("%-d %b")


def _money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.0f}"


def _tonnes(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value):.2f}t"


def _spoilage_band_word(lang: str, band: str | None) -> str:
    return {
        "red": _t(lang, "band_high"),
        "amber": _t(lang, "band_medium"),
        "green": _t(lang, "band_low"),
    }.get(band or "", _t(lang, "band_low"))


def _chips(option: Option) -> list[dict]:
    return [
        {"key": "cost", "label": _money(option.delta_cost_usd), "tone": "bad" if option.delta_cost_usd > 0 else "good"},
        {
            "key": "time",
            "label": f"{option.delta_transit_days:+.0f}d arrival",
            "tone": "bad" if option.delta_transit_days > 0 else "good",
        },
        {
            "key": "risk",
            "label": f"{option.delta_risk_days:+.1f} risk days",
            "tone": "good" if option.delta_risk_days > 0 else "bad",
        },
        {"key": "co2", "label": _tonnes(option.delta_co2_tonnes), "tone": "bad" if option.delta_co2_tonnes > 0 else "good"},
    ]


def compose_alert(
    shipment,
    exposure: Exposure,
    options: list[Option],
    lang: str = "en",
) -> AlertBundle:
    lang = lang if lang in SUPPORTED_LANGUAGES else "en"
    top = next((o for o in options if o.rank == 1 and o.kind != "hold"), None)
    hold = next((o for o in options if o.kind == "hold"), None)
    port_name = _short_port(exposure)
    cargo = shipment.cargo_short or shipment.cargo

    if exposure.risk_level == "green" or top is None:
        text = _t(lang, "calm").format(
            ref=shipment.reference,
            cargo=cargo,
            teu=_teu(shipment.teu),
            etd=_fmt_date(shipment.etd),
            port=port_name,
            risk=int(round(exposure.prob_miss_deadline * 100)),
            required_by=_fmt_date(shipment.required_by),
            confidence=int(round(exposure.confidence * 100)),
        )
        messages = [ChatMessage(id="m0", sender="portpulse", kind="calm", text=_clip(text))]
        return AlertBundle(
            shipment_id=shipment.id,
            language=lang,
            risk_level=exposure.risk_level,
            alert_text=_clip(text),
            alert_chars=len(_clip(text)),
            within_limit=len(_clip(text)) <= MAX_CHARS,
            messages=messages,
            quick_replies=[],
        )

    # Round the headline down to a whole number of days the reader can picture.
    days = max(int(exposure.expected_delay_days), 1)
    risk_pct = int(round(_tail_at(exposure, days) * 100))
    spoilage_text = ""
    if exposure.spoilage_probability is not None:
        spoilage_text = _t(lang, "spoilage").format(
            band=_spoilage_band_word(lang, exposure.spoilage_band)
        )

    alert_text = _t(lang, "alert").format(
        risk=risk_pct,
        days=days,
        port=port_name,
        etd=_fmt_date(shipment.etd),
        cargo=cargo,
        teu=_teu(shipment.teu),
        spoilage=spoilage_text,
        option=_short_label(top),
        cost=_money(top.delta_cost_usd),
        risk_days=f"{-top.delta_risk_days:+.1f}",
        co2=_tonnes(top.delta_co2_tonnes),
    )
    alert_text = _clip(alert_text)

    messages: list[ChatMessage] = [
        ChatMessage(id="m0", sender="portpulse", kind="alert", text=alert_text)
    ]
    messages.append(
        ChatMessage(id="m1", sender="user", kind="prompt", text=_t(lang, "prompt"))
    )
    messages.append(
        ChatMessage(id="m2", sender="portpulse", kind="followup", text=_t(lang, "options_intro"))
    )
    for i, option in enumerate(options, start=1):
        marker = f"{i}." if option.kind != "hold" else "0."
        messages.append(
            ChatMessage(
                id=f"opt-{option.id}",
                sender="portpulse",
                kind="option",
                text=_t(lang, "option").format(
                    marker=marker, label=option.label, rationale=option.rationale
                ),
                chips=_chips(option),
                option_id=option.id,
                recommended=option.recommended,
            )
        )
    messages.append(
        ChatMessage(id="m3", sender="portpulse", kind="followup", text=_t(lang, "confirm_prompt"))
    )

    return AlertBundle(
        shipment_id=shipment.id,
        language=lang,
        risk_level=exposure.risk_level,
        alert_text=alert_text,
        alert_chars=len(alert_text),
        within_limit=len(alert_text) <= MAX_CHARS,
        messages=messages,
        quick_replies=[str(i) for i in range(1, len(options))] + ["0"],
    )


def compose_confirmation(shipment, exposure: Exposure, option: Option, lang: str = "en") -> ChatMessage:
    lang = lang if lang in SUPPORTED_LANGUAGES else "en"
    if option.kind == "hold":
        port_name = _short_port(exposure)
        return ChatMessage(
            id="confirm", sender="portpulse", kind="confirmation",
            text=_clip(_t(lang, "kept").format(port=port_name)),
        )
    return ChatMessage(
        id="confirm",
        sender="portpulse",
        kind="confirmation",
        text=_clip(
            _t(lang, "confirmed").format(
                label=option.label,
                etd=_fmt_date(option.etd),
                arrival=_fmt_date(exposure.expected_arrival),
                risk_level=RISK_LEVEL_WORDS[lang][exposure.risk_level],
                risk=int(round(exposure.prob_miss_deadline * 100)),
            )
        ),
    )


def _short_port(exposure: Exposure) -> str:
    """Short port name for the final discharge, for SMS-length messages."""
    if not exposure.calls:
        return ""
    call = exposure.calls[-1]
    return getattr(call, "port_short_name", None) or call.port_name


def _short_label(option: Option) -> str:
    """Trim a full option label down to something that fits an SMS."""
    label = option.label
    label = label.replace(" Islamic Port", "").replace(" (Doraleh)", "")
    label = label.replace("King Abdullah Port", "KAP")
    label = label.replace(", discharge at", " → discharge")
    label = label.replace(", road to", " → road to")
    label = label.replace(" days)", "d)")
    if len(label) > 96:
        label = label[:93].rstrip(" ,") + "…"
    return label


def _teu(teu: float) -> str:
    return str(int(teu)) if float(teu).is_integer() else f"{teu:g}"


def _clip(text: str) -> str:
    text = " ".join(text.split()) if "\n" not in text else text
    if len(text) <= MAX_CHARS:
        return text
    return text[: MAX_CHARS - 1].rstrip() + "…"


def _tail_at(exposure: Exposure, days: int) -> float:
    """P(delay ≥ ``days``) reusing the exposure's fitted normal."""
    from .exposure import _tail

    return _tail(exposure.expected_delay_days, max(exposure.delay_sigma, 0.3), float(days))
