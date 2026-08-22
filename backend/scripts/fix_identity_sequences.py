"""Move every identity sequence past the rows already in its table.

Needed after rows are loaded by COPY, which carries the values but not the
counters behind them. A sequence left at 1 hands the next insert an id that is
already taken, and the table's own primary key refuses it — so the symptom is
not a warning at load time but a 500 much later, on the first *new* row: an
account that has signed in before works perfectly while a new one cannot be
created at all.

`pg_get_serial_sequence` is what finds them. The obvious query — pg_depend with
deptype 'a' — silently returns nothing for `GENERATED AS IDENTITY` columns,
whose dependency is 'i', and a loop that finds no sequences looks exactly like
a loop that found nothing to fix.

Idempotent: run it as often as you like.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

sys.path.insert(0, ".")

from app.db.session import SessionLocal  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        columns = (
            await session.execute(
                text(
                    """
                    select c.table_name, c.column_name
                    from information_schema.columns c
                    join information_schema.tables t
                      on t.table_schema = c.table_schema and t.table_name = c.table_name
                    where c.table_schema = 'public'
                      and t.table_type = 'BASE TABLE'
                      and (c.is_identity = 'YES' or c.column_default like 'nextval%')
                    order by c.table_name
                    """
                )
            )
        ).all()

        for table, column in columns:
            sequence = (
                await session.execute(
                    text("select pg_get_serial_sequence(:t, :c)"), {"t": table, "c": column}
                )
            ).scalar()
            if not sequence:
                continue

            highest = (
                await session.execute(text(f'select max("{column}") from "{table}"'))
            ).scalar()
            if highest is None:
                print(f"{table}.{column}: empty, left alone")
                continue

            before = (await session.execute(text(f"select last_value from {sequence}"))).scalar()
            await session.execute(
                text("select setval(:s, :v)"), {"s": sequence, "v": int(highest)}
            )
            print(f"{table}.{column}: {before} -> {highest} (next id {int(highest) + 1})")

        await session.commit()


asyncio.run(main())
