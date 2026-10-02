"""Guard against autogenerate dropping tables it cannot see.

alembic/env.py runs with include_schemas=True and target_metadata=Base.metadata.
Any mapped table whose module env.py does not import is absent from that
metadata but present in the database, so the next --autogenerate emits a
drop_table for it.
"""

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ENV_PY = BACKEND / "migrations" / "env.py"

EXPECTED_AUTH_TABLES = {
    "vantage_auth.users",
    "vantage_auth.refresh_tokens",
    "vantage_auth.email_tokens",
    "vantage_auth.auth_attempts",
}


def _model_imports_declared_by_env() -> list[str]:
    """The app.* import statements env.py actually performs."""
    source = ENV_PY.read_text(encoding="utf-8")
    return [
        line.strip()
        for line in source.splitlines()
        if re.match(r"^\s*(import app\.|from app\.)", line)
    ]


def test_env_imports_register_every_auth_table() -> None:
    program = "\n".join(
        [
            "from app.db.base import Base",
            *_model_imports_declared_by_env(),
            "print(' '.join(sorted(Base.metadata.tables)))",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(BACKEND),
    )
    assert result.returncode == 0, result.stderr

    registered = set(result.stdout.split())
    missing = EXPECTED_AUTH_TABLES - registered
    assert not missing, (
        f"migrations/env.py does not import the modules defining {sorted(missing)}; "
        "the next --autogenerate would emit drop_table for them"
    )
