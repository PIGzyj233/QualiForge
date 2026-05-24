from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.platform.database import Base


MemberRole = Literal["WorkspaceOwner", "WorkspaceMember"]


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="WorkspaceMember.created_at",
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="Project.created_at",
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_workspace_member_email"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="WorkspaceMember", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="members")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_project_key_per_workspace"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="projects")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_email: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    owner_display_name: str = Field(min_length=1, max_length=120)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    created_at: datetime
    updated_at: datetime


class MemberCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    role: MemberRole = "WorkspaceMember"


class MemberResponse(BaseModel):
    id: str
    workspace_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,47}$")
    description: str = Field(default="", max_length=500)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    status: Literal["active", "archived"] | None = None


class ProjectResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    key: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class AuditLogResponse(BaseModel):
    id: str
    workspace_id: str
    actor_email: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    before: dict | None
    after: dict | None
    created_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]
ActorEmail = Annotated[str, Query(min_length=3, max_length=254)]

router = APIRouter(prefix="/api", tags=["workspaces"])


def serialize_workspace(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        owner_email=workspace.owner_email,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def serialize_member(member: WorkspaceMember) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        workspace_id=member.workspace_id,
        email=member.email,
        display_name=member.display_name,
        role=member.role,
        created_at=member.created_at,
    )


def serialize_project(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        key=project.key,
        description=project.description,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def serialize_audit_log(audit_log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=audit_log.id,
        workspace_id=audit_log.workspace_id,
        actor_email=audit_log.actor_email,
        action=audit_log.action,
        entity_type=audit_log.entity_type,
        entity_id=audit_log.entity_id,
        summary=audit_log.summary,
        before=audit_log.before,
        after=audit_log.after,
        created_at=audit_log.created_at,
    )


def get_workspace_or_404(db: Session, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


def get_project_or_404(db: Session, workspace_id: str, project_id: str) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_member(db: Session, workspace_id: str, actor_email: str) -> WorkspaceMember | None:
    return db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.email == actor_email,
        )
    )


def require_workspace_owner(db: Session, workspace_id: str, actor_email: str) -> WorkspaceMember:
    member = get_member(db, workspace_id, actor_email)
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor is not a workspace member")
    if member.role != "WorkspaceOwner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkspaceOwner role required")
    return member


def audit(
    db: Session,
    *,
    workspace_id: str,
    actor_email: str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_email=actor_email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            before=before,
            after=after,
        )
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, db: DbSession) -> WorkspaceResponse:
    workspace = Workspace(name=payload.name, owner_email=payload.owner_email)
    db.add(workspace)
    db.flush()

    owner = WorkspaceMember(
        workspace_id=workspace.id,
        email=payload.owner_email,
        display_name=payload.owner_display_name,
        role="WorkspaceOwner",
    )
    db.add(owner)
    db.flush()
    audit(
        db,
        workspace_id=workspace.id,
        actor_email=payload.owner_email,
        action="workspace.created",
        entity_type="Workspace",
        entity_id=workspace.id,
        summary=f"Created workspace {workspace.name}",
        after={"name": workspace.name, "owner_email": workspace.owner_email},
    )
    audit(
        db,
        workspace_id=workspace.id,
        actor_email=payload.owner_email,
        action="member.added",
        entity_type="WorkspaceMember",
        entity_id=owner.id,
        summary=f"Added owner {owner.email}",
        after={"email": owner.email, "display_name": owner.display_name, "role": owner.role},
    )
    db.commit()
    db.refresh(workspace)
    return serialize_workspace(workspace)


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def list_workspaces(db: DbSession, actor_email: str | None = Query(default=None, max_length=254)) -> list[WorkspaceResponse]:
    statement = select(Workspace).order_by(Workspace.created_at)
    if actor_email:
        statement = statement.join(WorkspaceMember).where(WorkspaceMember.email == actor_email)
    return [serialize_workspace(workspace) for workspace in db.scalars(statement).all()]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: str, db: DbSession) -> WorkspaceResponse:
    return serialize_workspace(get_workspace_or_404(db, workspace_id))


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberResponse])
def list_members(workspace_id: str, db: DbSession) -> list[MemberResponse]:
    get_workspace_or_404(db, workspace_id)
    members = db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at, WorkspaceMember.email)
    ).all()
    return [serialize_member(member) for member in members]


@router.post("/workspaces/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(workspace_id: str, payload: MemberCreate, db: DbSession, actor_email: ActorEmail) -> MemberResponse:
    get_workspace_or_404(db, workspace_id)
    member = WorkspaceMember(
        workspace_id=workspace_id,
        email=payload.email,
        display_name=payload.display_name,
        role=payload.role,
    )
    db.add(member)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="member.added",
        entity_type="WorkspaceMember",
        entity_id=member.id,
        summary=f"Added member {member.email}",
        after={"email": member.email, "display_name": member.display_name, "role": member.role},
    )
    db.commit()
    db.refresh(member)
    return serialize_member(member)


@router.delete("/workspaces/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(workspace_id: str, member_id: str, db: DbSession, actor_email: ActorEmail) -> Response:
    get_workspace_or_404(db, workspace_id)
    member = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id)
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == "WorkspaceOwner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace owner cannot be removed")

    before = {"email": member.email, "display_name": member.display_name, "role": member.role}
    db.delete(member)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="member.removed",
        entity_type="WorkspaceMember",
        entity_id=member_id,
        summary=f"Removed member {before['email']}",
        before=before,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectResponse])
def list_projects(workspace_id: str, db: DbSession) -> list[ProjectResponse]:
    get_workspace_or_404(db, workspace_id)
    projects = db.scalars(select(Project).where(Project.workspace_id == workspace_id).order_by(Project.created_at)).all()
    return [serialize_project(project) for project in projects]


@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(workspace_id: str, payload: ProjectCreate, db: DbSession, actor_email: ActorEmail) -> ProjectResponse:
    get_workspace_or_404(db, workspace_id)
    project = Project(
        workspace_id=workspace_id,
        name=payload.name,
        key=payload.key,
        description=payload.description,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project key already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="project.created",
        entity_type="Project",
        entity_id=project.id,
        summary=f"Created project {project.key}",
        after={"name": project.name, "key": project.key, "description": project.description, "status": project.status},
    )
    db.commit()
    db.refresh(project)
    return serialize_project(project)


@router.patch("/workspaces/{workspace_id}/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    workspace_id: str,
    project_id: str,
    payload: ProjectUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> ProjectResponse:
    project = get_project_or_404(db, workspace_id, project_id)
    before = {
        "name": project.name,
        "key": project.key,
        "description": project.description,
        "status": project.status,
    }
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    project.updated_at = now_utc()
    db.flush()
    after = {
        "name": project.name,
        "key": project.key,
        "description": project.description,
        "status": project.status,
    }
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="project.updated",
        entity_type="Project",
        entity_id=project.id,
        summary=f"Updated project {project.key}",
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(project)
    return serialize_project(project)


@router.get("/workspaces/{workspace_id}/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(workspace_id: str, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> list[AuditLogResponse]:
    get_workspace_or_404(db, workspace_id)
    logs = db.scalars(
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [serialize_audit_log(log) for log in logs]
