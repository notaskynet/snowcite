"""Files snowcite writes for Claude Code: CLAUDE.md, subagents, settings.json.

Rendered from `snowcite/templates/`. These move to skills/plugin packaging in a
later step; until then they live here so `ProjectService` stays about the project.
"""

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_AGENT_TEMPLATES = ("academic_reviewer", "humanizer")

# Baseline allowlist for Claude Code's settings.json.
SETTINGS_ALLOWLIST = [
    "mcp__snowcite__*",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "WebSearch",
]


def _neutralize(value: Any) -> Any:
    """Make user-supplied metadata safe to interpolate into a Jinja template.

    CLAUDE.md / agent templates render with autoescape off (they are Markdown).
    Without this, a metadata value containing `{{ config }}` or `{% include ... %}`
    would re-evaluate as Jinja. We neutralise the three Jinja openers in every string.
    """
    if isinstance(value, str):
        return value.replace("{{", "{\u200b{").replace("}}", "}\u200b}").replace("{%", "{\u200b%")
    if isinstance(value, dict):
        return {k: _neutralize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_neutralize(v) for v in value]
    return value


class ClaudeFiles:
    def __init__(self, templates_dir: Path = _TEMPLATES_DIR) -> None:
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(enabled_extensions=(), disabled_extensions=("j2",)),
            trim_blocks=False,
            lstrip_blocks=False,
        )

    def _render(self, path: str, metadata: dict[str, Any]) -> str:
        defaults = {
            "language": "en",
            "standard": "plain",
            "review_strictness": "standard",
        }
        ctx = {k: _neutralize(v) for k, v in {**defaults, **metadata}.items()}
        return self._env.get_template(path).render(**ctx)

    def write_claude_md(self, root: Path, metadata: dict[str, Any]) -> Path:
        target = root / "CLAUDE.md"
        target.write_text(self._render("claude_md.j2", metadata), encoding="utf-8")
        return target

    def write_agents(self, root: Path, metadata: dict[str, Any], overwrite: bool) -> list[str]:
        """Write `.claude/agents/*.md`; existing files are kept unless `overwrite`."""
        agents_dir = root / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for name in _AGENT_TEMPLATES:
            target = agents_dir / f"{name.replace('_', '-')}.md"
            if target.exists() and not overwrite:
                continue
            target.write_text(self._render(f"agents/{name}.md.j2", metadata), encoding="utf-8")
            written.append(target.name)
        return written

    def settings_diff(self, root: Path) -> dict[str, Any]:
        """What `init_project` would add to `.claude/settings.json`.

        Claude uses this to ask the user whether to merge, overwrite (with .bak) or skip.
        """
        path = root / ".claude" / "settings.json"
        if not path.exists():
            return {
                "exists": False,
                "path": str(path),
                "missing_entries": SETTINGS_ALLOWLIST,
                "existing_entries": [],
                "action_required": "create",
            }
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                "exists": True,
                "path": str(path),
                "error": "existing settings.json is unreadable/invalid; user must resolve manually",
                "action_required": "user_decision",
            }
        existing = current.get("permissions", {}).get("allow", [])
        missing = [e for e in SETTINGS_ALLOWLIST if e not in existing]
        return {
            "exists": True,
            "path": str(path),
            "existing_entries": existing,
            "missing_entries": missing,
            "action_required": "ask_user" if missing else "nothing",
        }

    def _create_settings(self, root: Path) -> Path:
        path = root / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"permissions": {"allow": SETTINGS_ALLOWLIST}}, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def apply_settings(self, root: Path, action: str) -> dict[str, Any]:
        """Apply the user's decision: create | merge | overwrite | skip."""
        path = root / ".claude" / "settings.json"
        if action == "skip":
            return {"applied": False, "action": "skip"}

        if action in ("create", "overwrite"):
            if action == "overwrite" and path.exists():
                path.rename(path.with_suffix(".json.bak"))
            self._create_settings(root)
            return {"applied": True, "action": action, "path": str(path)}

        if action == "merge":
            if not path.exists():
                self._create_settings(root)
                return {"applied": True, "action": "created (file was missing)", "path": str(path)}
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                return {
                    "applied": False,
                    "error": f"existing settings.json is unreadable: {e}. "
                    "Use overwrite or fix manually.",
                }
            allow = current.setdefault("permissions", {}).setdefault("allow", [])
            added = [e for e in SETTINGS_ALLOWLIST if e not in allow]
            allow.extend(added)
            path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            return {"applied": True, "action": "merge", "added": added, "path": str(path)}

        return {"applied": False, "error": f"unknown action {action!r}"}
