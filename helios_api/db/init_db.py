"""Apply ``schema.sql`` to a fresh PostgreSQL database (e.g. Neon)."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

# Must match ``middleware.auth`` mock installer org.
MOCK_ORG_ID = "20000000-0000-4000-a000-000000000099"

# Strip Supabase-only RLS block (uses ``authenticated`` role and ``auth.uid()``).
RLS_BLOCK_MARKER = (
    "\n-- ═══════════════════════════════════════════════════════════════════════════════\n"
    "-- ROW LEVEL SECURITY\n"
)


def _load_neon_ddl() -> str:
    path = Path(__file__).resolve().parent / "schema.sql"
    sql = path.read_text(encoding="utf-8")
    # Fresh Neon has no ``auth`` schema — drop FK to Supabase auth.users.
    sql = sql.replace(
        "id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,",
        "id UUID PRIMARY KEY,",
    )
    if RLS_BLOCK_MARKER in sql:
        sql = sql.split(RLS_BLOCK_MARKER, 1)[0].rstrip()
    else:
        logger.warning(
            "schema.sql: RLS block marker not found; executing full file (may fail without Supabase)"
        )
    return sql


def _split_sql_statements(sql: str) -> list[str]:
    """Split on `;` respecting `--`, `/* */`, `'...'`, and dollar-quoted ``$...$`` blocks."""
    stmts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    in_squote = False
    dollar_tag: str | None = None  # None = not in dollar quote; else tag between $...$
    in_line_comment = False
    in_block_comment = False

    def flush() -> None:
        s = "".join(buf).strip()
        buf.clear()
        if s:
            stmts.append(s)

    while i < n:
        ch = sql[i]

        if in_block_comment:
            if ch == "*" and i + 1 < n and sql[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                buf.append(ch)
            i += 1
            continue

        if dollar_tag is not None:
            if ch == "$":
                delim = "$" + dollar_tag + "$"
                if sql.startswith(delim, i):
                    buf.append(delim)
                    i += len(delim)
                    dollar_tag = None
                    continue
            buf.append(ch)
            i += 1
            continue

        if in_squote:
            buf.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue

        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == "$":
            j = i + 1
            while j < n and sql[j] != "$":
                j += 1
            if j < n:
                tag = sql[i + 1 : j]
                dollar_tag = tag
                buf.append(sql[i : j + 1])
                i = j + 1
                continue

        if ch == "'":
            in_squote = True
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
            flush()
            i += 1
            continue

        buf.append(ch)
        i += 1

    flush()
    return stmts


async def init_database(pool: asyncpg.Pool) -> None:
    """Run core DDL from ``schema.sql`` (Neon-safe subset), one statement at a time.

    Each statement is isolated: failures are logged and skipped. Finally attempts
    mock-org seed in its own try/except.
    """
    ddl = _load_neon_ddl()
    statements = _split_sql_statements(ddl)
    succeeded = 0
    failed = 0
    async with pool.acquire() as conn:
        for idx, stmt in enumerate(statements):
            try:
                await conn.execute(stmt)
                succeeded += 1
            except Exception:
                failed += 1
                logger.warning(
                    "init_db statement %d/%d failed: %s",
                    idx + 1,
                    len(statements),
                    stmt[:120].replace("\n", " ") + ("…" if len(stmt) > 120 else ""),
                    exc_info=True,
                )

        try:
            await conn.execute(
                "INSERT INTO orgs (id, name) VALUES ($1::uuid, $2) ON CONFLICT (id) DO NOTHING",
                MOCK_ORG_ID,
                "Mock Org",
            )
        except Exception:
            logger.warning("init_db mock org insert failed", exc_info=True)

    logger.info(
        "Database schema init finished: %d statements attempted (%d ok, %d failed); "
        "mock org insert attempted",
        len(statements),
        succeeded,
        failed,
    )


async def seed_mock_org(pool: asyncpg.Pool) -> None:
    """Ensure bypass mock org row exists (idempotent)."""
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO orgs (id, name) VALUES ($1::uuid, $2) ON CONFLICT (id) DO NOTHING",
                MOCK_ORG_ID,
                "Mock Org",
            )
        except Exception:
            logger.warning("seed_mock_org failed", exc_info=True)
            return
    logger.info("Mock org ensured (id=%s)", MOCK_ORG_ID)


__all__ = ["MOCK_ORG_ID", "init_database", "seed_mock_org"]
