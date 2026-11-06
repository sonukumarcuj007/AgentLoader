from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape

from flask import Flask, jsonify, render_template, request

from skills import discover_skills, list_resources

app = Flask(__name__)
app.config["PROJECT_ROOT"] = Path(
    os.environ.get("AGENT_SKILLS_PROJECT_ROOT", Path.cwd())
).resolve()
app.config["USER_ROOT"] = Path(
    os.environ.get("AGENT_SKILLS_USER_ROOT", Path.home())
).resolve()


def _trust_project() -> bool:
    return request.args.get("trust_project", "").lower() in {"1", "true", "yes"}


def _current_skills():
    return discover_skills(
        app.config["PROJECT_ROOT"],
        app.config["USER_ROOT"],
        trust_project=_trust_project(),
    )


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/skills")
def skills_catalog():
    skills, diagnostics = _current_skills()
    catalog = [
        {
            "name": skill.name,
            "description": skill.description,
            "location": skill.location,
            "scope": skill.scope,
        }
        for skill in skills.values()
    ]
    return jsonify(skills=catalog, diagnostics=diagnostics)


@app.get("/api/system-prompt")
def system_prompt():
    skills, _ = _current_skills()
    if not skills:
        return jsonify(system_prompt="")
    entries = "\n".join(
        "  <skill>\n"
        f"    <name>{escape(skill.name)}</name>\n"
        f"    <description>{escape(skill.description)}</description>\n"
        f"    <location>{escape(skill.location)}</location>\n"
        "  </skill>"
        for skill in skills.values()
    )
    return jsonify(
        system_prompt=(
            "The following skills provide specialized instructions. When a skill "
            "matches the task, request GET /api/skills/{name}/activate to load its "
            "instructions before proceeding. Resolve paths in those instructions "
            "relative to the skill directory.\n"
            "<available_skills>\n"
            f"{entries}\n"
            "</available_skills>"
        )
    )


@app.get("/api/skills/<name>/activate")
def activate_skill(name: str):
    skills, _ = _current_skills()
    skill = skills.get(name)
    if skill is None:
        return jsonify(error="Skill not found. Refresh the catalog and try again."), 404

    resources, truncated = list_resources(skill)
    resource_list = "\n".join(f"  <file>{escape(path)}</file>" for path in resources)
    truncation_note = (
        "\n  <note>Resource listing truncated at the configured limit.</note>"
        if truncated
        else ""
    )
    content = (
        f'<skill_content name="{escape(skill.name)}">\n'
        f"{skill.body}\n\n"
        f"Skill directory: {skill.directory}\n"
        "Resolve relative paths in these instructions against the skill directory.\n"
        f"<skill_resources>\n{resource_list}{truncation_note}\n</skill_resources>\n"
        "</skill_content>"
    )
    return jsonify(
        name=skill.name,
        scope=skill.scope,
        location=skill.location,
        directory=str(skill.directory),
        content=content,
        resources=resources,
        resources_truncated=truncated,
    )


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=False,
    )
