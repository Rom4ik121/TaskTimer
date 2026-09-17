"""Roadmap nodes and edges."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RoadmapEdge, RoadmapNode
from app.schemas import RoadmapEdgeCreate, RoadmapNodeCreate, RoadmapNodeUpdate

_STATUS_CYCLE = ["pending", "active", "done"]


def list_nodes(session: Session) -> list[RoadmapNode]:
    return list(session.scalars(select(RoadmapNode).order_by(RoadmapNode.id)).all())


def list_edges(session: Session) -> list[RoadmapEdge]:
    return list(session.scalars(select(RoadmapEdge).order_by(RoadmapEdge.id)).all())


def get_node(session: Session, node_id: int) -> Optional[RoadmapNode]:
    return session.get(RoadmapNode, node_id)


def create_node(session: Session, data: RoadmapNodeCreate) -> RoadmapNode:
    node = RoadmapNode(**data.model_dump())
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def update_node(
    session: Session, node_id: int, data: RoadmapNodeUpdate
) -> Optional[RoadmapNode]:
    node = session.get(RoadmapNode, node_id)
    if not node:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    session.commit()
    session.refresh(node)
    return node


def cycle_node_status(session: Session, node_id: int) -> Optional[RoadmapNode]:
    node = session.get(RoadmapNode, node_id)
    if not node:
        return None
    idx = _STATUS_CYCLE.index(node.status) if node.status in _STATUS_CYCLE else 0
    node.status = _STATUS_CYCLE[(idx + 1) % len(_STATUS_CYCLE)]
    session.commit()
    session.refresh(node)
    return node


def delete_node(session: Session, node_id: int) -> bool:
    node = session.get(RoadmapNode, node_id)
    if not node:
        return False
    # Remove connected edges first
    edges = session.scalars(
        select(RoadmapEdge).where(
            (RoadmapEdge.from_node_id == node_id) | (RoadmapEdge.to_node_id == node_id)
        )
    ).all()
    for e in edges:
        session.delete(e)
    session.delete(node)
    session.commit()
    return True


def create_edge(session: Session, data: RoadmapEdgeCreate) -> Optional[RoadmapEdge]:
    if data.from_node_id == data.to_node_id:
        return None
    if not session.get(RoadmapNode, data.from_node_id):
        return None
    if not session.get(RoadmapNode, data.to_node_id):
        return None
    edge = RoadmapEdge(**data.model_dump())
    session.add(edge)
    session.commit()
    session.refresh(edge)
    return edge


def delete_edge(session: Session, edge_id: int) -> bool:
    edge = session.get(RoadmapEdge, edge_id)
    if not edge:
        return False
    session.delete(edge)
    session.commit()
    return True


def auto_layout_nodes(
    session: Session,
    *,
    x0: float = 40.0,
    y0: float = 40.0,
    dx: float = 120.0,
    dy: float = 90.0,
) -> list[RoadmapNode]:
    """Recompute node x/y in a layered grid from edge BFS levels and save."""
    from collections import defaultdict, deque

    nodes = list_nodes(session)
    edges = list_edges(session)
    if not nodes:
        return []

    node_ids = [n.id for n in nodes]
    children: dict[int, list[int]] = {nid: [] for nid in node_ids}
    indeg: dict[int, int] = {nid: 0 for nid in node_ids}
    for e in edges:
        if e.from_node_id in children and e.to_node_id in indeg:
            children[e.from_node_id].append(e.to_node_id)
            indeg[e.to_node_id] += 1

    roots = [nid for nid in node_ids if indeg[nid] == 0]
    if not roots:
        roots = [min(node_ids)]

    level: dict[int, int] = {}
    q: deque[int] = deque()
    for r in roots:
        level[r] = 0
        q.append(r)
    while q:
        u = q.popleft()
        for v in children[u]:
            if v not in level:
                level[v] = level[u] + 1
                q.append(v)

    for nid in node_ids:
        if nid not in level:
            level[nid] = 0

    by_level: dict[int, list[int]] = defaultdict(list)
    for nid in sorted(node_ids):
        by_level[level[nid]].append(nid)

    by_id = {n.id: n for n in nodes}
    for lvl, ids in sorted(by_level.items()):
        for col, nid in enumerate(ids):
            node = by_id[nid]
            node.x = float(x0 + col * dx)
            node.y = float(y0 + lvl * dy)

    session.commit()
    for n in nodes:
        session.refresh(n)
    return nodes
