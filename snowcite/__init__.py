"""snowcite — MCP server + library for systematic literature review.

Re-exports the stable, library-usable surface. The MCP tool surface is
registered via `server.py` / `snowcite.app`; consumers integrating as a
library work against the container (repositories) and source layers.
"""

from snowcite.container import Container, container
from snowcite.domain.models import ApprovedPaper, Paper, PersistResult
from snowcite.domain.types import (
    Backend,
    Confidence,
    Direction,
    Phase,
    ReviewedBy,
    Severity,
    Source,
    Status,
)
from snowcite.storage.projects import (
    NoProjectError,
    create_project_dir,
    find_project_root,
    get_db_path,
    require_project_root,
)


__version__ = "0.1.0"

__all__ = [
    "ApprovedPaper",
    "Backend",
    "Confidence",
    "Container",
    "Direction",
    "NoProjectError",
    "Paper",
    "PersistResult",
    "Phase",
    "ReviewedBy",
    "Severity",
    "Source",
    "Status",
    "__version__",
    "container",
    "create_project_dir",
    "find_project_root",
    "get_db_path",
    "require_project_root",
]
