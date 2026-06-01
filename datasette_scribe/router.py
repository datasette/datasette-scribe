from pathlib import Path
from functools import wraps

from datasette import Forbidden
from datasette_plugin_router import Router

router = Router()

SCRIBE_ACCESS_NAME = "datasette_scribe_scribe"

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


def check_permission():
    """Decorator for routes requiring scribe access."""

    def decorator(func):
        @wraps(func)
        async def wrapper(datasette, request, **kwargs):
            result = await datasette.allowed(
                action=SCRIBE_ACCESS_NAME, actor=request.actor
            )
            if not result:
                raise Forbidden("Permission denied for datasette-scribe scribe access")
            return await func(datasette=datasette, request=request, **kwargs)

        return wrapper

    return decorator


async def ensure_schema(datasette, database: str):
    db = datasette.get_database(database)
    await db.execute_write_script(SCHEMA_SQL)
    # Migration: `created_by` was added after initial release. CREATE TABLE IF
    # NOT EXISTS won't add it to pre-existing tables, so feature-detect and
    # ALTER. Safe to run every page load (the column check short-circuits).
    columns = [
        row["name"]
        for row in (
            await db.execute("PRAGMA table_info(datasette_scribe_transcriptions)")
        ).rows
    ]
    if "created_by" not in columns:
        await db.execute_write(
            "ALTER TABLE datasette_scribe_transcriptions ADD COLUMN created_by text"
        )
