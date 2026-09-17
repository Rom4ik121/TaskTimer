"""Infinite canvas nodes/edges — section MD cards + free notes + roadmap mirrors."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CanvasEdge, CanvasNode
from app.schemas import CanvasEdgeCreate, CanvasNodeCreate, CanvasNodeUpdate
from app.services import notes_service


# Nice default layout for section nodes (virtual space ~2000×1400)
_SECTION_LAYOUT: list[tuple[str, str, float, float, str]] = [
    # key, title, x, y, color — compact cluster for phone first paint
    ("home", "Дом", 40.0, 100.0, "#FF8A00"),
    ("tasks", "Задачи", 220.0, 80.0, "#4C8DFF"),
    ("goals", "Цели", 40.0, 220.0, "#3DDC97"),
    ("focus", "Фокус", 220.0, 220.0, "#A78BFA"),
    ("analytics", "Аналитика", 40.0, 340.0, "#F43F5E"),
    ("roadmap", "Роадмап", 220.0, 340.0, "#FF8A00"),
]


def list_nodes(session: Session, *, kind: str | None = None) -> list[CanvasNode]:
    q = select(CanvasNode).order_by(CanvasNode.id)
    if kind:
        q = q.where(CanvasNode.kind == kind)
    return list(session.scalars(q).all())


def get_node(session: Session, node_id: int) -> CanvasNode | None:
    return session.get(CanvasNode, node_id)


def _safe_ref(kind: str, ref: str) -> str:
    """Basename-sanitize MD refs for section/note; leave roadmap refs alone."""
    raw = (ref or "").strip()
    if not raw:
        return ""
    if kind in ("section", "note"):
        try:
            return notes_service.sanitize_filename(raw)
        except ValueError:
            # Collapse path-like input to basename then sanitize
            base = raw.replace("\\", "/").split("/")[-1]
            return notes_service.sanitize_filename(base)
    return raw[:255]


def create_node(session: Session, data: CanvasNodeCreate) -> CanvasNode:
    node = CanvasNode(
        title=data.title.strip(),
        x=float(data.x),
        y=float(data.y),
        kind=data.kind,
        ref=_safe_ref(data.kind, data.ref or ""),
        color=data.color,
        w=float(data.w),
        h=float(data.h),
    )
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def update_node(
    session: Session, node_id: int, data: CanvasNodeUpdate
) -> CanvasNode | None:
    node = session.get(CanvasNode, node_id)
    if not node:
        return None
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        if k == "title" and isinstance(v, str):
            v = v.strip()
        if k == "ref":
            kind = payload.get("kind", node.kind)
            v = _safe_ref(kind or "note", v or "")
        setattr(node, k, v)
    session.commit()
    session.refresh(node)
    return node


def delete_node(session: Session, node_id: int) -> bool:
    node = session.get(CanvasNode, node_id)
    if not node:
        return False
    # Cascade edges
    edges = session.scalars(
        select(CanvasEdge).where(
            (CanvasEdge.from_node_id == node_id) | (CanvasEdge.to_node_id == node_id)
        )
    ).all()
    for e in edges:
        session.delete(e)
    session.delete(node)
    session.commit()
    return True


def list_edges(session: Session) -> list[CanvasEdge]:
    return list(session.scalars(select(CanvasEdge).order_by(CanvasEdge.id)).all())


def create_edge(session: Session, data: CanvasEdgeCreate) -> CanvasEdge | None:
    if data.from_node_id == data.to_node_id:
        return None
    a = session.get(CanvasNode, data.from_node_id)
    b = session.get(CanvasNode, data.to_node_id)
    if not a or not b:
        return None
    existing = session.scalars(
        select(CanvasEdge).where(
            CanvasEdge.from_node_id == data.from_node_id,
            CanvasEdge.to_node_id == data.to_node_id,
        )
    ).first()
    if existing:
        return existing
    edge = CanvasEdge(from_node_id=data.from_node_id, to_node_id=data.to_node_id)
    session.add(edge)
    session.commit()
    session.refresh(edge)
    return edge


def delete_edge(session: Session, edge_id: int) -> bool:
    edge = session.get(CanvasEdge, edge_id)
    if not edge:
        return False
    session.delete(edge)
    session.commit()
    return True


def seed_section_nodes(session: Session, *, commit: bool = True) -> list[CanvasNode]:
    """Insert default section nodes if none exist. Ensures vault files."""
    notes_service.ensure_vault()
    existing = list_nodes(session, kind="section")
    if existing:
        return existing
    created: list[CanvasNode] = []
    for key, title, x, y, color in _SECTION_LAYOUT:
        fname = notes_service.SECTION_FILES[key]
        node = CanvasNode(
            title=title,
            x=x,
            y=y,
            kind="section",
            ref=fname,
            color=color,
            w=168.0,
            h=88.0,
        )
        session.add(node)
        created.append(node)
    # Soft links between related sections
    session.flush()
    by_ref = {n.ref: n for n in created}
    pair_refs = [
        ("home.md", "tasks.md"),
        ("home.md", "goals.md"),
        ("tasks.md", "focus.md"),
        ("goals.md", "analytics.md"),
        ("focus.md", "analytics.md"),
        ("analytics.md", "roadmap.md"),
    ]
    for a_ref, b_ref in pair_refs:
        a, b = by_ref.get(a_ref), by_ref.get(b_ref)
        if a and b:
            session.add(CanvasEdge(from_node_id=a.id, to_node_id=b.id))
    if commit:
        session.commit()
        for n in created:
            session.refresh(n)
    else:
        session.flush()
    return created


def ensure_canvas_seeded(session: Session) -> None:
    """Idempotent: vault + section nodes for fresh or upgraded DBs."""
    notes_service.ensure_vault()
    seed_section_nodes(session)
