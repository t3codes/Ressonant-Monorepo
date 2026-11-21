"""Seed idempotente do cenário RBAC de testes.

Uso (a partir de apps/ressonant_backend, com o mesmo .env/DATABASE_URL do app):
    uv run python -m scripts.seed_rbac
ou:
    python -m scripts.seed_rbac

Não apaga dados existentes. Pode ser executado várias vezes (get-or-create).
Senha padrão de todos os usuários de teste: Teste@1234
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Permite rodar como "python scripts/seed_rbac.py" além de "-m scripts.seed_rbac"
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.common.security import hash_password  # noqa: E402
from app.database.engine import get_session_factory  # noqa: E402
from app.modules.chat.domain.models import Channel  # noqa: E402
from app.modules.kanban_boards.domain.models import Board, BoardColumn  # noqa: E402
from app.modules.teams.domain.models import Team, TeamMember  # noqa: E402
from app.modules.user.domain.models import User  # noqa: E402
from app.modules.workspace.domain.models import Workspace, WorkspaceMember  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

DEFAULT_PASSWORD = "Teste@1234"


def _valid_cpf(base9: list[int]) -> str:
    def dv(nums: list[int]) -> int:
        s = sum((len(nums) + 1 - i) * n for i, n in enumerate(nums))
        r = (s * 10) % 11
        return r if r < 10 else 0

    d1 = dv(base9)
    d2 = dv(base9 + [d1])
    return "".join(str(x) for x in base9 + [d1, d2])


# pool de CPFs válidos determinísticos para fallback em caso de colisão no banco
CPF_POOL = [
    _valid_cpf([1, 0, 4, 3, 3, 2, 1, 8, 1]),
    _valid_cpf([9, 6, 0, 0, 1, 3, 3, 8, 9]),
    _valid_cpf([0, 8, 3, 8, 6, 3, 7, 9, 4]),
    _valid_cpf([0, 2, 6, 5, 4, 2, 3, 5, 1]),
    _valid_cpf([1, 6, 1, 5, 5, 9, 4, 0, 7]),
    _valid_cpf([8, 1, 6, 1, 8, 4, 9, 5, 9]),
    _valid_cpf([3, 1, 0, 3, 4, 1, 3, 1, 6]),
    _valid_cpf([4, 7, 5, 2, 5, 5, 3, 4, 1]),
    _valid_cpf([9, 2, 8, 3, 2, 7, 6, 4, 8]),
    _valid_cpf([3, 5, 0, 3, 0, 5, 6, 4, 1]),
    _valid_cpf([3, 9, 5, 3, 7, 6, 7, 2, 4]),
    _valid_cpf([2, 3, 8, 8, 4, 9, 6, 9, 6]),
    _valid_cpf([7, 1, 4, 2, 8, 5, 3, 6, 9]),
    _valid_cpf([5, 0, 9, 1, 7, 4, 8, 2, 3]),
]


@dataclass
class SeedUser:
    email: str
    cpf: str
    telefone: str
    interno_adm: bool


USERS = [
    SeedUser("owner@ressonant.com", CPF_POOL[0], "11990000001", True),
    SeedUser("gestor.equipes@ressonant.com", CPF_POOL[1], "11990000002", False),
    SeedUser("lider.tech@ressonant.com", CPF_POOL[2], "11990000003", False),
    SeedUser("dev.member@ressonant.com", CPF_POOL[3], "11990000004", False),
    SeedUser("auditor.viewer@ressonant.com", CPF_POOL[4], "11990000005", False),
    SeedUser("sem.equipe@ressonant.com", CPF_POOL[5], "11990000006", False),
    SeedUser("externo@empresab.com", CPF_POOL[6], "11990000007", False),
]


def _pick_free_cpf(db: Session, preferred: str) -> str:
    taken = db.scalar(select(User.id).where(User.cpf == preferred))
    if not taken:
        return preferred
    for cpf in CPF_POOL[7:]:
        if not db.scalar(select(User.id).where(User.cpf == cpf)):
            return cpf
    # fallback determinístico incremental
    base = 100000000
    for i in range(500):
        cpf = _valid_cpf([(base + i) // (10 ** (8 - j)) % 10 for j in range(9)])
        if not db.scalar(select(User.id).where(User.cpf == cpf)):
            return cpf
    raise RuntimeError("Não foi possível gerar CPF livre para seed")


def get_or_create_user(db: Session, spec: SeedUser) -> User:
    user = db.scalar(select(User).where(User.email == spec.email))
    if user:
        return user
    cpf = _pick_free_cpf(db, spec.cpf)
    user = User(
        email=spec.email,
        senha_hash=hash_password(DEFAULT_PASSWORD),
        cpf=cpf,
        idade=30,
        termos_contrato=True,
        telefone=spec.telefone,
        status_ativo=True,
        interno_adm=spec.interno_adm,
    )
    db.add(user)
    db.flush()
    return user


def get_or_create_workspace(db: Session, *, name: str, slug: str, owner_id: str, description: str) -> Workspace:
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if ws:
        return ws
    ws = Workspace(name=name, slug=slug, owner_id=owner_id, description=description, status_ativo=True)
    db.add(ws)
    db.flush()
    return ws


def ensure_workspace_member(db: Session, workspace_id: str, user_id: str, role: str) -> WorkspaceMember:
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
        )
    )
    if member:
        return member
    member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(member)
    db.flush()
    return member


def get_or_create_team(db: Session, *, name: str, slug: str, workspace_id: str, owner_id: str) -> Team:
    team = db.scalar(select(Team).where(Team.slug == slug))
    if team:
        return team
    team = Team(name=name, slug=slug, workspace_id=workspace_id, owner_id=owner_id, status_ativo=True)
    db.add(team)
    db.flush()
    return team


def ensure_team_member(db: Session, team_id: str, user_id: str, role: str) -> TeamMember:
    member = db.scalar(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    if member:
        return member
    member = TeamMember(team_id=team_id, user_id=user_id, role=role)
    db.add(member)
    db.flush()
    return member


def get_or_create_board(db: Session, *, name: str, slug: str, workspace_id: str, team_id: str) -> Board:
    board = db.scalar(select(Board).where(Board.slug == slug))
    if board:
        return board
    board = Board(name=name, slug=slug, workspace_id=workspace_id, team_id=team_id, status_ativo=True)
    db.add(board)
    db.flush()
    for col_name, col_slug, pos in [("Backlog", "backlog", 0), ("Em Andamento", "em-andamento", 1), ("Feito", "feito", 2)]:
        db.add(BoardColumn(board_id=board.id, name=col_name, slug=col_slug, position=pos))
    db.flush()
    return board


def get_or_create_channel(db: Session, *, name: str, slug: str, workspace_id: str, created_by: str) -> Channel:
    # slug de canal tem constraint única global; usa slug namespaced por workspace
    channel = db.scalar(select(Channel).where(Channel.workspace_id == workspace_id, Channel.name == name))
    if channel:
        return channel
    desired_slug = f"{slug}-{workspace_id[:8]}"
    existing = db.scalar(select(Channel).where(Channel.slug == desired_slug))
    if existing:
        return existing
    channel = Channel(
        workspace_id=workspace_id,
        name=name,
        slug=desired_slug,
        topic="Canal geral",
        visibility="public",
        member_ids=f'["{created_by}"]',
        created_by=created_by,
        status_ativo=True,
    )
    db.add(channel)
    db.flush()
    return channel


def main() -> int:
    session_factory = get_session_factory()
    with session_factory() as db:
        try:
            users = {u.email: get_or_create_user(db, u) for u in USERS}

            # Workspace Principal: Ressonant Corp
            ws_main = get_or_create_workspace(
                db,
                name="Ressonant Corp",
                slug="ressonant-corp-seed",
                owner_id=users["owner@ressonant.com"].id,
                description="Workspace principal de testes RBAC",
            )
            ensure_workspace_member(db, ws_main.id, users["owner@ressonant.com"].id, "admin")
            ensure_workspace_member(db, ws_main.id, users["gestor.equipes@ressonant.com"].id, "admin")
            ensure_workspace_member(db, ws_main.id, users["lider.tech@ressonant.com"].id, "member")
            ensure_workspace_member(db, ws_main.id, users["dev.member@ressonant.com"].id, "member")
            ensure_workspace_member(db, ws_main.id, users["auditor.viewer@ressonant.com"].id, "member")
            ensure_workspace_member(db, ws_main.id, users["sem.equipe@ressonant.com"].id, "member")

            eng = get_or_create_team(
                db, name="Engenharia", slug="engenharia-seed", workspace_id=ws_main.id, owner_id=users["owner@ressonant.com"].id
            )
            plataforma = get_or_create_team(
                db, name="Plataforma", slug="plataforma-seed", workspace_id=ws_main.id, owner_id=users["owner@ressonant.com"].id
            )
            # owner: admin de todas as equipes
            for team in (eng, plataforma):
                ensure_team_member(db, team.id, users["owner@ressonant.com"].id, "admin")
            # gestor.equipes: admin do workspace (pode criar/atribuir equipes), sem membership forçada nas equipes
            # lider.tech: member do workspace, admin apenas da Engenharia
            ensure_team_member(db, eng.id, users["lider.tech@ressonant.com"].id, "admin")
            # dev.member: member da Engenharia
            ensure_team_member(db, eng.id, users["dev.member@ressonant.com"].id, "member")
            # auditor.viewer: viewer da Engenharia
            ensure_team_member(db, eng.id, users["auditor.viewer@ressonant.com"].id, "viewer")
            # sem.equipe: membro do workspace, sem nenhuma equipe

            get_or_create_board(db, name="Board Engenharia", slug="board-engenharia-seed", workspace_id=ws_main.id, team_id=eng.id)
            get_or_create_board(db, name="Board Plataforma", slug="board-plataforma-seed", workspace_id=ws_main.id, team_id=plataforma.id)
            get_or_create_channel(db, name="geral", slug="geral", workspace_id=ws_main.id, created_by=users["owner@ressonant.com"].id)

            # Workspace Isolado: Empresa B
            ws_b = get_or_create_workspace(
                db,
                name="Empresa B - Teste IDOR",
                slug="empresa-b-seed",
                owner_id=users["externo@empresab.com"].id,
                description="Workspace isolado para validação de acesso cruzado",
            )
            ensure_workspace_member(db, ws_b.id, users["externo@empresab.com"].id, "admin")
            team_b = get_or_create_team(
                db, name="Equipe B", slug="equipe-b-seed", workspace_id=ws_b.id, owner_id=users["externo@empresab.com"].id
            )
            ensure_team_member(db, team_b.id, users["externo@empresab.com"].id, "admin")
            get_or_create_board(db, name="Board B", slug="board-b-seed", workspace_id=ws_b.id, team_id=team_b.id)

            db.commit()

            # Resumo (buscar nomes reais caso já existissem)
            eng = db.scalar(select(Team).where(Team.slug == "engenharia-seed"))
            plataforma = db.scalar(select(Team).where(Team.slug == "plataforma-seed"))
            ws_main = db.scalar(select(Workspace).where(Workspace.slug == "ressonant-corp-seed"))
            ws_b = db.scalar(select(Workspace).where(Workspace.slug == "empresa-b-seed"))

            rows = [
                ("owner@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: owner (admin membro)", "Engenharia: admin; Plataforma: admin"),
                ("gestor.equipes@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: admin (workspace)", "(sem equipe atribuída)"),
                ("lider.tech@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: member", "Engenharia: admin"),
                ("dev.member@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: member", "Engenharia: member"),
                ("auditor.viewer@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: member", "Engenharia: viewer"),
                ("sem.equipe@ressonant.com", DEFAULT_PASSWORD, "Ressonant Corp: member", "(nenhuma equipe)"),
                ("externo@empresab.com", DEFAULT_PASSWORD, "Empresa B - Teste IDOR: owner (admin membro)", "Equipe B: admin"),
            ]
            headers = ("E-mail", "Senha", "Papel Workspace", "Equipe & Role")
            widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
            sep = "-+-".join("-" * w for w in widths)
            print("\nSeed RBAC concluído (idempotente, dados existentes preservados).")
            print(f"Workspace principal: {ws_main.name} ({ws_main.id})")
            print(f"Workspace isolado : {ws_b.name} ({ws_b.id})")
            print(f"Equipe Engenharia : {eng.name} ({eng.id})")
            print(f"Equipe Plataforma : {plataforma.name} ({plataforma.id})\n")
            print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
            print(sep)
            for r in rows:
                print(" | ".join(r[i].ljust(widths[i]) for i in range(len(headers))))
            print()
        except Exception:
            db.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
