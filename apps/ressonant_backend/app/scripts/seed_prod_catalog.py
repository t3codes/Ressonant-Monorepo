"""Seed idempotente do catálogo de planos (ADR 0003, opção A).

Uso: python -m app.scripts.seed_prod_catalog

Insere `trial_default` e mantém/insere `inicial`, `equipe` e `empresa`.
`ON CONFLICT (code) DO NOTHING`: plano existente nunca é sobrescrito — preço,
`active`, limites e configuração permanecem como estão.
"""

import sys
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.engine import get_session_factory
from app.modules.billing.domain.models import Plan


def _plan(
    *,
    code: str,
    name: str,
    price_cents: int,
    seat_limit: int | None,
    trial_days: int,
) -> dict[str, Any]:
    included_seats = seat_limit if seat_limit is not None else 0
    return {
        "id": str(uuid.uuid4()),
        "code": code,
        "name": name,
        "billing_cycle": "monthly",
        "base_price_cents": price_cents,
        "price_per_seat_cents": 0,
        "included_seats": included_seats,
        "limits": {"seats": included_seats},
        "is_public": True,
        "is_active": True,
        # Colunas legadas lidas pelos serviços de billing atuais.
        "price_cents": price_cents,
        "currency": "BRL",
        "seat_limit": seat_limit,
        "overage_cents_per_seat": 0,
        "trial_days": trial_days,
        "active": True,
    }


def catalog_rows() -> list[dict[str, Any]]:
    """Valores legados alinhados ao catálogo já usado pelos testes.

    IDs são gerados por execução; nada aqui é aplicado a planos existentes.
    """
    return [
        _plan(code="trial_default", name="Teste", price_cents=0, seat_limit=1, trial_days=14),
        _plan(code="inicial", name="Inicial", price_cents=0, seat_limit=3, trial_days=7),
        _plan(code="equipe", name="Equipe", price_cents=4900, seat_limit=15, trial_days=14),
        _plan(code="empresa", name="Empresa", price_cents=7900, seat_limit=None, trial_days=14),
    ]


def main() -> int:
    with get_session_factory()() as db:
        dialect = db.get_bind().dialect.name
        rows = catalog_rows()
        if dialect == "sqlite":
            stmt = sqlite_insert(Plan).values(rows).on_conflict_do_nothing(index_elements=["code"])
        elif dialect == "postgresql":
            stmt = pg_insert(Plan).values(rows).on_conflict_do_nothing(index_elements=["code"])
        else:
            print(f"Dialeto não suportado pelo seed: {dialect}", file=sys.stderr)
            return 1
        try:
            db.execute(stmt)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print("Catálogo de planos verificado (seed idempotente).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
