"""Exporta o OpenAPI do app sem precisar de banco ou servidor."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_SECRET", "x" * 32)

from app.main import app  # noqa: E402

target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
print(f"OpenAPI escrito em {target}")
