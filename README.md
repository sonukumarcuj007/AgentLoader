# Agent Skills Flask Client

A local Flask app that implements the Agent Skills discovery and activation flow:

- Scans project and user skill directories for subfolders containing `SKILL.md`.
- Shows only skill names and descriptions in the catalog.
- Loads full instructions and lists bundled resources only when a skill is activated.
- Exposes a system-prompt endpoint for integrating the catalog with another model client.
- Gives trusted project skills precedence over user skills when names collide.

Project skills are hidden until **Trust project skills** is enabled in the UI. The equivalent API option is `?trust_project=true`. User skills are always discovered.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. By default, the app scans the current working directory and the user's home directory:

- `<project>/.agents/skills/`
- `<project>/.flask-agent/skills/`
- `<home>/.agents/skills/`
- `<home>/.flask-agent/skills/`

Override the roots with `AGENT_SKILLS_PROJECT_ROOT` and `AGENT_SKILLS_USER_ROOT`. The server binds to `127.0.0.1` by default; set `FLASK_HOST` and `FLASK_PORT` to override.

## API

- `GET /api/skills` — compact skill catalog and discovery diagnostics.
- `GET /api/skills?trust_project=true` — also include project-level skills.
- `GET /api/skills/<name>/activate` — return structured instructions and resource paths.
- `GET /api/system-prompt` — create a short model instruction block and XML catalog; supports the same trust option.

The app does not execute skill scripts or automatically send skill content to an external model. A model client can fetch `/api/system-prompt` at session start and activate a listed skill when needed.

## Tests

```powershell
python -m unittest discover -s tests
```
