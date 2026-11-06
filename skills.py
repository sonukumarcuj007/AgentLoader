from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
SKIPPED_DIRECTORIES = {".git", "node_modules", "__pycache__"}
MAX_SKILL_DIRECTORIES = 2000
MAX_SKILL_ROOT_ENTRIES = 10000
MAX_RESOURCE_FILES = 100
MAX_RESOURCE_DIRECTORIES = 2000


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    location: str
    scope: str
    directory: Path
    body: str

def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")

    closing = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if closing is None:
        raise ValueError("SKILL.md is missing the closing frontmatter delimiter")

    raw_frontmatter = "\n".join(lines[1:closing])
    try:
        metadata = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        metadata = {}
        for line in raw_frontmatter.splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() in {"name", "description"}:
                metadata[key.strip()] = value.strip().strip("\"'")
        if not metadata:
            raise ValueError("SKILL.md frontmatter is not valid YAML")
        logger.warning("Loaded skill frontmatter using plain-text fallback")

    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    return metadata, "\n".join(lines[closing + 1 :]).strip()


def _read_skill(skill_file: Path, scope: str) -> tuple[Skill | None, str | None]:
    if skill_file.is_symlink():
        return None, f"{skill_file}: SKILL.md must not be a symbolic link"
    try:
        text = skill_file.read_text(encoding="utf-8-sig")
        metadata, body = _parse_frontmatter(text)
    except (OSError, UnicodeError, ValueError) as error:
        return None, f"{skill_file}: {error}"

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        return None, f"{skill_file}: missing or invalid required name"
    if not isinstance(description, str) or not description.strip():
        return None, f"{skill_file}: missing or empty required description"

    name = name.strip()
    if name != skill_file.parent.name:
        logger.warning(
            "Skill name %r does not match directory %r",
            name,
            skill_file.parent.name,
        )
    if len(name) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        logger.warning("Skill name %r does not meet the specification", name)

    return (
        Skill(
            name=name,
            description=description.strip(),
            location=str(skill_file.resolve()),
            scope=scope,
            directory=skill_file.parent.resolve(),
            body=body,
        ),
        None,
    )


def _skills_in_root(root: Path, scope: str) -> tuple[list[Skill], list[str]]:
    skills: list[Skill] = []
    diagnostics: list[str] = []
    if not root.is_dir():
        return skills, diagnostics

    try:
        entries = list(islice(root.iterdir(), MAX_SKILL_ROOT_ENTRIES + 1))
    except OSError as error:
        return skills, [f"{root}: unable to scan skills directory: {error}"]
    if len(entries) > MAX_SKILL_ROOT_ENTRIES:
        diagnostics.append(
            f"{root}: stopped scanning after {MAX_SKILL_ROOT_ENTRIES} entries"
        )
        entries = entries[:MAX_SKILL_ROOT_ENTRIES]
    directories = sorted(
        (
            path
            for path in entries
            if path.is_dir()
            and not path.is_symlink()
            and path.name not in SKIPPED_DIRECTORIES
        ),
        key=lambda path: path.name.casefold(),
    )[:MAX_SKILL_DIRECTORIES]

    for directory in directories:
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            continue
        skill, diagnostic = _read_skill(skill_file, scope)
        if skill:
            skills.append(skill)
        if diagnostic:
            diagnostics.append(diagnostic)
            logger.warning(diagnostic)
    return skills, diagnostics


def discover_skills(
    project_root: Path,
    user_root: Path,
    trust_project: bool = False,
) -> tuple[dict[str, Skill], list[str]]:
    """Discover skills with trusted project skills taking precedence over user skills."""
    roots: list[tuple[Path, str]] = []
    if trust_project:
        roots.extend(
            [
                (project_root / ".agents" / "skills", "project"),
                (project_root / ".flask-agent" / "skills", "project"),
            ]
        )
    roots.extend(
        [
            (user_root / ".agents" / "skills", "user"),
            (user_root / ".flask-agent" / "skills", "user"),
        ]
    )

    skills: dict[str, Skill] = {}
    diagnostics: list[str] = []
    for root, scope in roots:
        found, root_diagnostics = _skills_in_root(root, scope)
        diagnostics.extend(root_diagnostics)
        for skill in found:
            if skill.name in skills:
                message = (
                    f"Skill name collision for {skill.name!r}: "
                    f"{skills[skill.name].location} takes precedence over {skill.location}"
                )
                diagnostics.append(message)
                logger.warning(message)
                continue
            skills[skill.name] = skill
    return skills, diagnostics


def list_resources(skill: Skill) -> tuple[list[str], bool]:
    """List resource paths without reading their contents."""
    resources: list[str] = []
    truncated = False
    visited_directories = 0
    for current, directories, filenames in os.walk(skill.directory, topdown=True):
        visited_directories += 1
        if visited_directories > MAX_RESOURCE_DIRECTORIES:
            truncated = True
            break
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name not in SKIPPED_DIRECTORIES
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            if filename == "SKILL.md" or path.is_symlink():
                continue
            if len(resources) == MAX_RESOURCE_FILES:
                truncated = True
                break
            resources.append(path.relative_to(skill.directory).as_posix())
        if truncated:
            break
    return resources, truncated
