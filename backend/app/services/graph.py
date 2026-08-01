"""Route graph over the port network (NetworkX).

Used by the recommendation engine to enumerate genuine alternative routings:
different transshipment hubs, alternative discharge ports plus a land leg, and
the Cape swing where it exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Leg


@dataclass(frozen=True)
class LegView:
    """Immutable snapshot of a leg, safe to pass around outside a session."""

    id: str
    origin_id: str
    dest_id: str
    mode: str
    service: str
    distance_nm: float
    transit_days: float
    cost_per_teu: float
    co2_tonnes_per_teu: float
    sailings_per_week: float
    chokepoints: tuple[str, ...]


def load_legs(db: Session) -> dict[str, LegView]:
    legs = db.execute(select(Leg)).scalars().all()
    return {
        leg.id: LegView(
            id=leg.id,
            origin_id=leg.origin_id,
            dest_id=leg.dest_id,
            mode=leg.mode,
            service=leg.service,
            distance_nm=leg.distance_nm,
            transit_days=leg.transit_days,
            cost_per_teu=leg.cost_per_teu,
            co2_tonnes_per_teu=leg.co2_tonnes_per_teu,
            sailings_per_week=leg.sailings_per_week,
            chokepoints=tuple(leg.chokepoints or []),
        )
        for leg in legs
    }


def build_graph(legs: dict[str, LegView]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for leg in legs.values():
        g.add_edge(leg.origin_id, leg.dest_id, key=leg.id, leg=leg, weight=leg.transit_days)
    return g


def _best_leg(legs: dict[str, LegView], graph: nx.MultiDiGraph, a: str, b: str) -> LegView:
    """Fastest parallel edge between two nodes (sea and land can both exist)."""
    candidates = [data["leg"] for _, _, data in graph.edges(a, data=True) if _ == a and data["leg"].dest_id == b]
    if not candidates:
        candidates = [leg for leg in legs.values() if leg.origin_id == a and leg.dest_id == b]
    return min(candidates, key=lambda leg: leg.transit_days)


def candidate_routes(
    db: Session,
    origin: str,
    dest: str,
    max_legs: int = 3,
    max_routes: int = 8,
) -> list[list[LegView]]:
    """K fastest simple routes from ``origin`` to ``dest``.

    Parallel edges (e.g. sea vs land between the same pair) are expanded so a
    land bridge shows up as its own option rather than being hidden behind the
    faster sea leg.
    """
    legs = load_legs(db)
    graph = build_graph(legs)
    if origin not in graph or dest not in graph:
        return []

    simple = nx.DiGraph()
    for leg in legs.values():
        prev = simple.get_edge_data(leg.origin_id, leg.dest_id)
        if prev is None or leg.transit_days < prev["weight"]:
            simple.add_edge(leg.origin_id, leg.dest_id, weight=leg.transit_days)

    routes: list[list[LegView]] = []
    seen: set[tuple[str, ...]] = set()
    try:
        paths = islice(nx.shortest_simple_paths(simple, origin, dest, weight="weight"), max_routes * 4)
    except nx.NetworkXNoPath:
        return []

    for path in paths:
        if len(path) - 1 > max_legs:
            continue
        variants: list[list[LegView]] = [[]]
        for a, b in zip(path, path[1:]):
            parallel = sorted(
                (leg for leg in legs.values() if leg.origin_id == a and leg.dest_id == b),
                key=lambda leg: leg.transit_days,
            )
            variants = [v + [leg] for v in variants for leg in parallel]
            if len(variants) > 12:
                variants = variants[:12]
        for variant in variants:
            key = tuple(leg.id for leg in variant)
            if key in seen:
                continue
            seen.add(key)
            routes.append(variant)
        if len(routes) >= max_routes:
            break

    return routes[:max_routes]


def route_nodes(route: list[LegView]) -> list[str]:
    if not route:
        return []
    return [route[0].origin_id] + [leg.dest_id for leg in route]


def route_totals(route: list[LegView]) -> dict[str, float]:
    return {
        "transit_days": round(sum(leg.transit_days for leg in route), 2),
        "cost_per_teu": round(sum(leg.cost_per_teu for leg in route), 2),
        "co2_tonnes_per_teu": round(sum(leg.co2_tonnes_per_teu for leg in route), 4),
        "distance_nm": round(sum(leg.distance_nm for leg in route), 1),
    }
