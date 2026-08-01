"""Static description of the synthetic PortPulse world.

This module holds *structure* (which ports exist, which legs connect them, who
the personas are). ``app/seed.py`` holds *process* (how 18 months of daily
observations are generated). Keeping them apart makes the swap seam obvious: a
production team replaces this file with a port master-data feed and seed.py
with real AIS/terminal telemetry.
"""

from __future__ import annotations

import math
from datetime import date
from typing import NamedTuple

# --------------------------------------------------------------------------- #
# Ports
# --------------------------------------------------------------------------- #


class PortSpec(NamedTuple):
    id: str
    name: str
    country: str
    region: str
    lat: float
    lon: float
    capacity_teu_per_day: int
    base_congestion: float
    demurrage_usd_per_teu_day: float
    free_days: int
    is_hub: bool
    congestion_threshold: float
    weather_peak_doy: int  # day-of-year of worst weather
    weather_amp: float
    congestion_peak_doy: int
    blurb: str
    short_name: str = ""


PORTS: list[PortSpec] = [
    # --- East Asian origins ---
    PortSpec("CNSHA", "Shanghai", "China", "East Asia", 31.34, 121.65, 12800, 46, 165, 5, True, 72, 255, 3.4, 40, "World's busiest box port; typhoon-exposed Aug–Oct.", "Shanghai"),
    PortSpec("CNNGB", "Ningbo-Zhoushan", "China", "East Asia", 29.87, 121.85, 10200, 42, 155, 5, True, 70, 255, 3.2, 40, "Deep-water alternative to Shanghai.", "Ningbo"),
    PortSpec("CNSZX", "Shenzhen (Shekou)", "China", "East Asia", 22.47, 113.90, 8400, 40, 150, 5, True, 70, 240, 3.0, 45, "South China gateway.", "Shenzhen"),
    PortSpec("VNSGN", "Ho Chi Minh (Cat Lai)", "Vietnam", "Southeast Asia", 10.76, 106.79, 3600, 48, 110, 4, False, 70, 270, 2.6, 60, "River terminal; draft-limited, feeder-dependent.", "Ho Chi Minh"),
    PortSpec("VNHPH", "Haiphong", "Vietnam", "Southeast Asia", 20.86, 106.72, 2400, 44, 105, 4, False, 70, 250, 3.0, 60, "Northern Vietnam gateway.", "Haiphong"),
    PortSpec("THLCH", "Laem Chabang", "Thailand", "Southeast Asia", 13.08, 100.88, 3100, 41, 115, 4, False, 70, 265, 2.4, 55, "Thailand's main box port.", "Laem Chabang"),
    PortSpec("PHMNL", "Manila", "Philippines", "Southeast Asia", 14.60, 120.96, 1900, 49, 120, 3, False, 68, 240, 3.8, 50, "Chronic yard density; typhoon alley.", "Manila"),
    PortSpec("IDJKT", "Tanjung Priok", "Indonesia", "Southeast Asia", -6.10, 106.88, 2600, 47, 100, 4, False, 70, 30, 2.2, 45, "Jakarta gateway.", "Jakarta"),
    # --- Hubs ---
    PortSpec("SGSIN", "Singapore", "Singapore", "Southeast Asia", 1.264, 103.84, 15400, 38, 145, 5, True, 68, 350, 1.8, 150, "Transshipment anchor of the corridor.", "Singapore"),
    PortSpec("MYPKG", "Port Klang", "Malaysia", "Southeast Asia", 3.00, 101.39, 4200, 40, 95, 5, True, 70, 330, 1.9, 150, "Overflow hub when Singapore tightens.", "Port Klang"),
    PortSpec("MYTPP", "Tanjung Pelepas", "Malaysia", "Southeast Asia", 1.363, 103.55, 3800, 39, 95, 5, True, 70, 330, 1.9, 150, "Alliance transshipment hub next to Singapore.", "Tanjung Pelepas"),
    PortSpec("LKCMB", "Colombo", "Sri Lanka", "South Asia", 6.95, 79.84, 3400, 43, 120, 4, True, 68, 185, 4.2, 180, "Indian Ocean relay; monsoon-sensitive.", "Colombo"),
    PortSpec("INNSA", "Mumbai (Nhava Sheva)", "India", "South Asia", 18.95, 72.95, 4100, 44, 130, 3, True, 70, 195, 4.6, 190, "India's largest container gateway.", "Nhava Sheva"),
    PortSpec("INMUN", "Mundra", "India", "South Asia", 22.75, 69.70, 3900, 40, 125, 3, False, 70, 195, 3.8, 190, "Private port, high productivity.", "Mundra"),
    PortSpec("MUPLU", "Port Louis", "Mauritius", "Indian Ocean", -20.15, 57.50, 700, 36, 90, 5, False, 66, 30, 3.4, 40, "Small relay on the Cape swing.", "Port Louis"),
    # --- Gulf / Red Sea ---
    PortSpec("OMSLL", "Salalah", "Oman", "Gulf", 16.94, 54.01, 3000, 37, 135, 5, True, 68, 200, 2.4, 200, "Outside Hormuz and Bab el-Mandeb; the corridor's shock absorber.", "Salalah"),
    PortSpec("AEJEA", "Jebel Ali", "UAE", "Gulf", 25.01, 55.06, 6800, 41, 190, 5, True, 70, 190, 2.0, 190, "Largest Gulf hub; landbridge origin to Saudi Arabia.", "Jebel Ali"),
    PortSpec("AEKHL", "Khalifa Port", "UAE", "Gulf", 24.81, 54.65, 2600, 35, 180, 5, False, 70, 190, 2.0, 190, "Abu Dhabi hub, spare capacity.", "Khalifa Port"),
    PortSpec("SADMM", "Dammam", "Saudi Arabia", "Gulf", 26.50, 50.20, 2200, 42, 210, 4, False, 68, 185, 2.2, 185, "Saudi east-coast gateway.", "Dammam"),
    PortSpec("SAJED", "Jeddah Islamic Port", "Saudi Arabia", "Red Sea", 21.48, 39.16, 4600, 43, 240, 4, True, 66, 175, 2.0, 300, "Red Sea gateway to western Saudi Arabia; the demo's pressure point.", "Jeddah"),
    PortSpec("SAKAP", "King Abdullah Port", "Saudi Arabia", "Red Sea", 22.48, 39.10, 3200, 33, 225, 5, True, 70, 175, 2.0, 300, "Modern relief port 80 nm north of Jeddah.", "King Abdullah Port"),
    PortSpec("DJJIB", "Djibouti (Doraleh)", "Djibouti", "Red Sea", 11.60, 43.14, 1500, 43, 175, 3, True, 66, 200, 2.6, 210, "Bab el-Mandeb doorstep; Horn of Africa relay.", "Djibouti"),
    PortSpec("EGSOK", "Ain Sokhna", "Egypt", "Red Sea", 29.66, 32.35, 1800, 38, 165, 4, False, 70, 190, 1.8, 190, "Suez southern approach; landbridge to the Med.", "Ain Sokhna"),
    PortSpec("EGPSD", "Port Said East", "Egypt", "Mediterranean", 31.26, 32.30, 4400, 40, 170, 4, True, 70, 20, 2.2, 20, "Suez northern mouth; Asia–Europe relay.", "Port Said"),
    # --- East & Southern Africa ---
    PortSpec("KEMBA", "Mombasa", "Kenya", "East Africa", -4.05, 39.66, 1400, 45, 130, 3, False, 66, 150, 3.6, 160, "Kenya's ocean gateway; Amina's loading port.", "Mombasa"),
    PortSpec("TZDAR", "Dar es Salaam", "Tanzania", "East Africa", -6.82, 39.29, 1100, 47, 125, 3, False, 66, 150, 3.4, 160, "Congested regional gateway.", "Dar es Salaam"),
    PortSpec("ZADUR", "Durban", "South Africa", "Southern Africa", -29.87, 31.03, 2900, 47, 145, 4, True, 68, 200, 4.4, 200, "Cape-route call; wind-driven berth downtime.", "Durban"),
    PortSpec("ZACPT", "Cape Town", "South Africa", "Southern Africa", -33.91, 18.43, 1200, 45, 140, 4, False, 68, 200, 5.0, 200, "Cape of Good Hope bunkering and reefer call.", "Cape Town"),
]

PORT_IDS = [p.id for p in PORTS]
PORTS_BY_ID = {p.id: p for p in PORTS}


# --------------------------------------------------------------------------- #
# Chokepoints
# --------------------------------------------------------------------------- #


class ChokepointSpec(NamedTuple):
    id: str
    name: str
    lat: float
    lon: float
    base_risk: float
    delay_days_at_max_risk: float
    note: str


CHOKEPOINTS: list[ChokepointSpec] = [
    ChokepointSpec("bab_el_mandeb", "Bab el-Mandeb / southern Red Sea", 12.58, 43.33, 0.08, 1.0,
                   "Southern Red Sea approach. Security incidents here push carriers to the Cape."),
    ChokepointSpec("suez", "Suez Canal", 30.53, 32.35, 0.05, 3.0,
                   "Transit slots and draft restrictions."),
    ChokepointSpec("hormuz", "Strait of Hormuz", 26.57, 56.25, 0.06, 2.5,
                   "Gulf entry; insurance-sensitive."),
    ChokepointSpec("malacca", "Strait of Malacca", 2.50, 101.30, 0.04, 1.5,
                   "Dense traffic, occasional haze closures."),
    ChokepointSpec("cape", "Cape of Good Hope", -34.36, 18.47, 0.07, 2.0,
                   "Weather-driven; the long way round."),
]


# --------------------------------------------------------------------------- #
# Legs
# --------------------------------------------------------------------------- #


class LegSpec(NamedTuple):
    origin: str
    dest: str
    service: str  # mainline | feeder | truck
    chokepoints: tuple[str, ...] = ()
    detour: float = 1.06
    distance_nm: float | None = None  # explicit override for non-great-circle routings
    sailings_per_week: float = 2.0
    mode: str = "sea"


_MALACCA_WEST = ("malacca",)

LEG_SPECS: list[LegSpec] = [
    # East Asia -> Singapore hub
    LegSpec("CNSHA", "SGSIN", "mainline", (), 1.08, None, 5),
    LegSpec("CNNGB", "SGSIN", "mainline", (), 1.08, None, 4),
    LegSpec("CNSZX", "SGSIN", "mainline", (), 1.07, None, 6),
    LegSpec("VNSGN", "SGSIN", "feeder", (), 1.10, None, 7),
    LegSpec("VNHPH", "SGSIN", "feeder", (), 1.12, None, 4),
    LegSpec("THLCH", "SGSIN", "feeder", (), 1.10, None, 6),
    LegSpec("PHMNL", "SGSIN", "feeder", (), 1.08, None, 5),
    LegSpec("IDJKT", "SGSIN", "feeder", (), 1.10, None, 6),
    LegSpec("MYPKG", "SGSIN", "feeder", (), 1.15, None, 7),
    LegSpec("MYTPP", "SGSIN", "feeder", (), 1.40, None, 7),
    # East Asia -> Port Klang / TPP (alternate hubs)
    LegSpec("CNSHA", "MYPKG", "mainline", _MALACCA_WEST, 1.09, None, 3),
    LegSpec("CNSZX", "MYTPP", "mainline", (), 1.08, None, 3),
    LegSpec("THLCH", "MYPKG", "feeder", (), 1.12, None, 4),
    # Singapore westbound mainlines
    LegSpec("SGSIN", "MYPKG", "feeder", (), 1.15, None, 7),
    LegSpec("SGSIN", "MYTPP", "feeder", (), 1.40, None, 7),
    LegSpec("SGSIN", "LKCMB", "mainline", _MALACCA_WEST, 1.06, None, 5),
    LegSpec("SGSIN", "INNSA", "mainline", _MALACCA_WEST, 1.06, None, 4),
    LegSpec("SGSIN", "OMSLL", "mainline", _MALACCA_WEST, 1.05, 3300, 4),
    LegSpec("SGSIN", "AEJEA", "mainline", ("malacca", "hormuz"), 1.05, 3400, 4),
    LegSpec("SGSIN", "SAJED", "mainline", ("malacca", "bab_el_mandeb"), 1.05, 4900, 3),
    LegSpec("SGSIN", "EGPSD", "mainline", ("malacca", "bab_el_mandeb", "suez"), 1.05, 6300, 5),
    LegSpec("SGSIN", "MUPLU", "mainline", (), 1.08, None, 1),
    LegSpec("MYPKG", "LKCMB", "mainline", _MALACCA_WEST, 1.06, 1420, 4),
    LegSpec("MYPKG", "OMSLL", "mainline", _MALACCA_WEST, 1.05, 3380, 2),
    LegSpec("MYTPP", "LKCMB", "mainline", _MALACCA_WEST, 1.06, 1560, 3),
    # Indian Ocean relays
    LegSpec("LKCMB", "INNSA", "feeder", (), 1.08, None, 5),
    LegSpec("LKCMB", "OMSLL", "mainline", (), 1.05, 2000, 4),
    LegSpec("LKCMB", "AEJEA", "mainline", ("hormuz",), 1.05, None, 4),
    LegSpec("LKCMB", "SAJED", "mainline", ("bab_el_mandeb",), 1.05, 3350, 3),
    LegSpec("LKCMB", "DJJIB", "mainline", ("bab_el_mandeb",), 1.05, 2300, 2),
    LegSpec("LKCMB", "KEMBA", "feeder", (), 1.06, 2650, 2),
    LegSpec("LKCMB", "MUPLU", "feeder", (), 1.07, None, 1),
    LegSpec("INNSA", "OMSLL", "mainline", (), 1.06, 1350, 4),
    LegSpec("INNSA", "AEJEA", "mainline", ("hormuz",), 1.06, None, 5),
    LegSpec("INNSA", "SAJED", "mainline", ("bab_el_mandeb",), 1.05, 2750, 2),
    LegSpec("INNSA", "KEMBA", "feeder", (), 1.06, 2600, 2),
    LegSpec("INMUN", "AEJEA", "feeder", ("hormuz",), 1.07, None, 4),
    LegSpec("INMUN", "OMSLL", "feeder", (), 1.06, 1080, 2),
    # Gulf
    LegSpec("OMSLL", "AEJEA", "mainline", ("hormuz",), 1.10, None, 6),
    LegSpec("OMSLL", "SAJED", "mainline", ("bab_el_mandeb",), 1.06, 1750, 5),
    LegSpec("OMSLL", "SAKAP", "mainline", ("bab_el_mandeb",), 1.06, 1830, 3),
    LegSpec("OMSLL", "DJJIB", "mainline", ("bab_el_mandeb",), 1.06, 900, 4),
    LegSpec("OMSLL", "EGSOK", "mainline", ("bab_el_mandeb",), 1.06, 2650, 3),
    LegSpec("OMSLL", "KEMBA", "feeder", (), 1.07, 2000, 2),
    LegSpec("AEJEA", "AEKHL", "feeder", (), 1.20, 95, 6),
    LegSpec("AEJEA", "SADMM", "feeder", ("hormuz",), 1.15, 570, 5),
    LegSpec("AEJEA", "SAJED", "mainline", ("hormuz", "bab_el_mandeb"), 1.06, 3450, 2),
    LegSpec("AEJEA", "KEMBA", "mainline", ("hormuz",), 1.06, 2600, 2),
    LegSpec("AEKHL", "SADMM", "feeder", ("hormuz",), 1.15, 480, 3),
    # Red Sea
    LegSpec("DJJIB", "SAJED", "feeder", ("bab_el_mandeb",), 1.06, 1120, 4),
    LegSpec("DJJIB", "SAKAP", "feeder", ("bab_el_mandeb",), 1.06, 1200, 2),
    LegSpec("DJJIB", "EGSOK", "mainline", ("bab_el_mandeb",), 1.05, 1330, 3),
    LegSpec("SAJED", "SAKAP", "feeder", (), 1.10, 85, 7),
    LegSpec("SAKAP", "SAJED", "feeder", (), 1.10, 85, 7),
    LegSpec("SAJED", "EGSOK", "mainline", (), 1.06, 650, 4),
    LegSpec("SAKAP", "EGSOK", "mainline", (), 1.06, 580, 3),
    LegSpec("EGSOK", "EGPSD", "mainline", ("suez",), 1.05, 120, 6),
    # East Africa
    LegSpec("KEMBA", "SAJED", "feeder", ("bab_el_mandeb",), 1.06, 2100, 2),
    LegSpec("KEMBA", "DJJIB", "feeder", (), 1.06, None, 3),
    LegSpec("KEMBA", "OMSLL", "mainline", (), 1.06, 2050, 2),
    LegSpec("KEMBA", "TZDAR", "feeder", (), 1.10, None, 4),
    LegSpec("KEMBA", "MUPLU", "feeder", (), 1.07, None, 1),
    LegSpec("TZDAR", "ZADUR", "feeder", (), 1.08, None, 2),
    LegSpec("KEMBA", "ZADUR", "mainline", (), 1.07, None, 1),
    # Cape swing (the genuine long way round to the Mediterranean)
    LegSpec("MUPLU", "ZADUR", "feeder", (), 1.08, None, 2),
    LegSpec("ZADUR", "ZACPT", "mainline", ("cape",), 1.12, None, 4),
    LegSpec("ZACPT", "EGPSD", "mainline", (), 1.00, 7950, 2),
    LegSpec("SGSIN", "ZADUR", "mainline", (), 1.06, None, 1),
    # Landbridges (Gulf -> Red Sea coast by road; what shippers actually did in 2024)
    LegSpec("AEJEA", "SAJED", "truck", (), 1.0, 1300, 7, "land"),
    LegSpec("AEJEA", "SADMM", "truck", (), 1.0, 230, 7, "land"),
    LegSpec("SADMM", "SAJED", "truck", (), 1.0, 750, 7, "land"),
    LegSpec("SAKAP", "SAJED", "truck", (), 1.0, 50, 7, "land"),
    LegSpec("EGSOK", "EGPSD", "truck", (), 1.0, 70, 7, "land"),
]


# --------------------------------------------------------------------------- #
# Leg economics — one place to tune the cost / time / carbon model
# --------------------------------------------------------------------------- #

SPEED_NM_PER_DAY = {"mainline": 480.0, "feeder": 320.0, "truck": 430.0}
PORT_TIME_DAYS = {"mainline": 1.0, "feeder": 0.8, "truck": 0.4}
COST_PER_NM = {"mainline": 0.22, "feeder": 0.34, "truck": 2.10}
COST_BASE = {"mainline": 250.0, "feeder": 180.0, "truck": 150.0}
CO2_T_PER_TEU_NM = {"mainline": 0.000090, "feeder": 0.000153, "truck": 0.000830}
EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def leg_metrics(spec: LegSpec) -> dict:
    """Derive distance / transit / cost / CO2 for a leg spec."""
    if spec.distance_nm is not None:
        distance = float(spec.distance_nm)
    else:
        a, b = PORTS_BY_ID[spec.origin], PORTS_BY_ID[spec.dest]
        distance = haversine_nm(a.lat, a.lon, b.lat, b.lon) * spec.detour
    distance = max(distance, 30.0)
    svc = spec.service
    transit = distance / SPEED_NM_PER_DAY[svc] + PORT_TIME_DAYS[svc]
    transit = round(transit * 2) / 2  # half-day granularity reads as a real schedule
    cost = COST_BASE[svc] + COST_PER_NM[svc] * distance
    co2 = CO2_T_PER_TEU_NM[svc] * distance
    return {
        "distance_nm": round(distance, 1),
        "transit_days": max(transit, 0.5),
        "cost_per_teu": round(cost, 2),
        "co2_tonnes_per_teu": round(co2, 4),
    }


def leg_id(spec: LegSpec) -> str:
    suffix = "-LAND" if spec.mode == "land" else ""
    return f"{spec.origin}-{spec.dest}{suffix}"


# --------------------------------------------------------------------------- #
# Personas
# --------------------------------------------------------------------------- #


class PersonaSpec(NamedTuple):
    id: str
    name: str
    role: str
    org: str
    location: str
    view: str
    home_port_id: str | None
    language: str
    avatar: str
    blurb: str


PERSONAS: list[PersonaSpec] = [
    PersonaSpec(
        "amina", "Amina Wanjiku", "SME mango exporter", "Wanjiku Fresh Produce Ltd",
        "Mombasa, Kenya", "phone", "KEMBA", "sw", "🥭",
        "Ships two containers of mangoes a month to Gulf buyers. Runs the business from a phone on patchy 3G.",
    ),
    PersonaSpec(
        "rafael", "Rafael Santos", "Freight forwarder", "Bayanihan Logistics",
        "Manila, Philippines", "dashboard", "PHMNL", "en", "📦",
        "Manages eight live bookings across the Southeast Asia–Gulf corridor for a dozen SME clients.",
    ),
    PersonaSpec(
        "jeddah_pa", "Port of Jeddah", "Port authority planner", "Jeddah Islamic Port",
        "Jeddah, Saudi Arabia", "port", "SAJED", "en", "🏗️",
        "Plans berth and yard capacity 14 days out against inbound pressure from the corridor.",
    ),
]


# --------------------------------------------------------------------------- #
# Shipments
# --------------------------------------------------------------------------- #


class ShipmentSpec(NamedTuple):
    id: str
    persona: str
    reference: str
    legs: tuple[str, ...]
    etd_offset_days: int  # relative to SEED_TODAY
    cargo: str
    teu: float
    perishable: bool
    shelf_life_days: int | None
    value_usd: float
    buyer: str
    # Contractual slack: days after the scheduled arrival that the buyer will
    # still accept the cargo. Late delivery past this costs the exporter money.
    buffer_days: int = 7
    # Short cargo name for SMS-length alerts.
    cargo_short: str = ""


SHIPMENTS: list[ShipmentSpec] = [
    # --- Amina: the hero shipment ---
    ShipmentSpec("SHP-AMN-001", "amina", "WFP-2418", ("KEMBA-SAJED",), 6,
                 "Fresh mangoes (Apple variety)", 2, True, 14, 28400,
                 "Al-Rayan Fresh Markets, Jeddah", 9, "mangoes"),
    # --- Rafael: eight mixed bookings ---
    ShipmentSpec("SHP-RAF-101", "rafael", "BYN-9014", ("CNSHA-SGSIN", "SGSIN-SAJED"), 2,
                 "Consumer electronics", 4, False, None, 186000, "Tamimi Trading, Jeddah", 4, "electronics"),
    ShipmentSpec("SHP-RAF-102", "rafael", "BYN-9021", ("VNSGN-SGSIN", "SGSIN-AEJEA"), 4,
                 "Flat-pack furniture", 6, False, None, 74000, "Gulf Home Co, Dubai", 9, "furniture"),
    ShipmentSpec("SHP-RAF-103", "rafael", "BYN-9033", ("THLCH-SGSIN", "SGSIN-LKCMB", "LKCMB-SAJED"), 3,
                 "Jasmine rice", 8, False, None, 96000, "Najd Foods, Riyadh", 4, "rice"),
    ShipmentSpec("SHP-RAF-104", "rafael", "BYN-9040", ("PHMNL-SGSIN", "SGSIN-EGPSD"), 8,
                 "Refined coconut oil", 5, False, None, 108000, "Delta Oils, Alexandria", 8, "coconut oil"),
    ShipmentSpec("SHP-RAF-105", "rafael", "BYN-9052", ("IDJKT-SGSIN", "SGSIN-AEJEA", "AEJEA-SADMM"), 6,
                 "Natural rubber", 6, False, None, 82000, "Eastern Rubber, Dammam", 9, "rubber"),
    ShipmentSpec("SHP-RAF-106", "rafael", "BYN-9061", ("CNNGB-SGSIN", "SGSIN-AEJEA", "AEJEA-SADMM"), 10,
                 "Industrial machinery", 3, False, None, 240000, "Saudi Metalworks, Jubail", 12, "machinery"),
    ShipmentSpec("SHP-RAF-107", "rafael", "BYN-9068", ("VNHPH-SGSIN", "SGSIN-INNSA"), 5,
                 "Cotton textiles", 5, False, None, 63000, "Deccan Apparel, Pune", 8, "textiles"),
    ShipmentSpec("SHP-RAF-108", "rafael", "BYN-9075", ("THLCH-SGSIN", "SGSIN-SAJED"), 7,
                 "Fresh longan (reefer)", 2, True, 21, 41000, "Hejaz Fruit Co, Jeddah", 3, "longan"),
]


# --------------------------------------------------------------------------- #
# Historical disruption episodes (these teach the forecaster what shocks look like)
# --------------------------------------------------------------------------- #


class Episode(NamedTuple):
    id: str
    start: date
    end: date
    type: str
    severity: int
    headline: str
    detail: str
    # port_id -> peak congestion uplift (index points)
    impact: dict
    chokepoint: str | None = None
    weather_uplift: float = 0.0


HISTORY_EPISODES: list[Episode] = [
    Episode(
        "EVH-001", date(2024, 5, 15), date(2024, 6, 30), "congestion", 3,
        "Berth congestion cascades through Singapore and Port Klang",
        "Bunching of delayed Asia–Europe services pushes Singapore yard density above 90%; feeders wait for windows.",
        {"SGSIN": 18, "MYPKG": 12, "MYTPP": 10, "VNSGN": 5},
    ),
    Episode(
        "EVH-002", date(2024, 6, 5), date(2024, 7, 20), "weather", 3,
        "Southwest monsoon slows Colombo berth productivity",
        "Swell and crane downtime at Colombo lengthen relay dwell; Nhava Sheva feels the knock-on.",
        {"LKCMB": 18, "INNSA": 8, "KEMBA": 5},
        weather_uplift=3.0,
    ),
    Episode(
        "EVH-003", date(2024, 9, 14), date(2024, 9, 21), "weather", 4,
        "Typhoon closes Shanghai and Ningbo terminals",
        "Port closure for 62 hours, followed by an arrival backlog into the first week of October.",
        {"CNSHA": 20, "CNNGB": 16, "CNSZX": 6},
        weather_uplift=5.5,
    ),
    Episode(
        "EVH-004", date(2024, 12, 10), date(2025, 2, 20), "security", 5,
        "Red Sea security episode diverts services around the Cape",
        "Carriers suspend Bab el-Mandeb transits. Jeddah and Djibouti volumes swing; Salalah and Durban absorb relays.",
        {"SAJED": 22, "DJJIB": 17, "SAKAP": 14, "EGSOK": 12, "EGPSD": 11, "OMSLL": 9, "ZADUR": 10, "ZACPT": 7},
        chokepoint="bab_el_mandeb",
    ),
    Episode(
        "EVH-005", date(2025, 3, 1), date(2025, 3, 24), "labor", 3,
        "Labour slowdown at Dammam cuts gang availability",
        "Crane gang shortfall reduces moves per hour by a third; vessels wait at anchorage.",
        {"SADMM": 21, "AEJEA": 6, "AEKHL": 4},
    ),
    Episode(
        "EVH-006", date(2025, 6, 10), date(2025, 7, 15), "weather", 3,
        "Monsoon returns: Colombo and Mumbai waiting times climb",
        "Second monsoon season in the training window; the same shape as 2024, slightly milder.",
        {"LKCMB": 13, "INNSA": 9, "KEMBA": 4},
        weather_uplift=2.5,
    ),
]


# Quiet, ordinary background news so the feed does not look empty pre-scenario.
CALM_FEED: list[tuple[int, str, int, str, str, str | None]] = [
    # (days_before_seed_today, type, severity, headline, detail, port_id)
    (1, "congestion", 1, "Jeddah yard density steady at 68%",
     "Berth productivity within normal range; no waiting time reported for the last three arrivals.", "SAJED"),
    (2, "weather", 2, "Moderate swell forecast for the Gulf of Aden",
     "Regional met services expect 2.5 m swell mid-week, easing by the weekend.", "DJJIB"),
    (3, "policy", 1, "Salalah adds a second weekly Red Sea relay call",
     "Additional feeder capacity from Salalah to Jeddah and King Abdullah Port from this month.", "OMSLL"),
    (4, "congestion", 2, "Colombo dwell edges up after monsoon season",
     "Post-monsoon recovery continues; average waiting time down to 1.1 days from a 2.4-day peak.", "LKCMB"),
    (6, "weather", 1, "Clear conditions along the East Africa coast",
     "Mombasa reports no weather-related berth downtime for eleven consecutive days.", "KEMBA"),
    (8, "congestion", 1, "Singapore transshipment connectivity normal",
     "Relay times back to the five-year average after the northern-summer peak.", "SGSIN"),
]


# --------------------------------------------------------------------------- #
# The scripted demo scenario (§7) — injected live, never seeded
# --------------------------------------------------------------------------- #

SCENARIO_ID = "red_sea_jeddah_2025_08"

SCENARIO_EVENTS = [
    # (day_offset_from_trigger, type, severity, headline, detail, port_id, chokepoint_id)
    (0, "security", 5,
     "Security incidents halt Bab el-Mandeb transits",
     "Two vessels report attacks in the southern Red Sea overnight. Three carriers suspend transits and war-risk premiums jump.",
     None, "bab_el_mandeb"),
    (0, "congestion", 4,
     "Jeddah berth queue forms as services bunch",
     "Nine vessels at anchorage off Jeddah after schedule recovery attempts; yard density crosses 84%.",
     "SAJED", None),
    (1, "congestion", 3,
     "Djibouti absorbs diverted Red Sea calls",
     "Doraleh reports a 40% jump in inbound bookings as carriers reshuffle Red Sea strings.",
     "DJJIB", None),
    (1, "policy", 3,
     "Salalah opens priority Red Sea relay with guaranteed berth windows",
     "Oman's hub adds express relay strings to Jeddah and King Abdullah Port with contracted berth windows for transshipped cargo, and waives connection waiting.",
     "OMSLL", None),
    (2, "policy", 3,
     "King Abdullah Port opens overflow reefer plugs",
     "KAP releases 400 additional reefer plugs to handle perishable cargo diverted from Jeddah.",
     "SAKAP", None),
]
