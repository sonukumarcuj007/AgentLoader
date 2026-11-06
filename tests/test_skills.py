import tempfile
import unittest
from pathlib import Path

from app import app
from skills import discover_skills


def write_skill(root: Path, directory: str, name: str, description: str, body: str = "Instructions"):
    skill_dir = root / directory / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillDiscoveryTests(unittest.TestCase):
    def test_project_skills_are_hidden_until_trusted_and_override_user(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            user = root / "user"
            write_skill(project, ".agents", "shared", "Project version")
            write_skill(user, ".agents", "shared", "User version")
            write_skill(user, ".agents", "user-only", "User skill")

            skills, _ = discover_skills(project, user)
            self.assertEqual(set(skills), {"shared", "user-only"})
            self.assertEqual(skills["shared"].scope, "user")

            skills, _ = discover_skills(project, user, trust_project=True)
            self.assertEqual(skills["shared"].scope, "project")

    def test_malformed_skill_is_reported_without_hiding_valid_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = write_skill(root, ".agents", "valid", "A valid skill")
            malformed = valid.parent / "broken"
            malformed.mkdir()
            (malformed / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

            skills, diagnostics = discover_skills(root, root)
            self.assertEqual(set(skills), {"valid"})
            self.assertEqual(len(diagnostics), 1)


class SkillsApiTests(unittest.TestCase):
    def test_catalog_prompt_activation_and_unknown_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            user = root / "user"
            skill_dir = write_skill(project, ".agents", "demo", "Demo skill", "Do the task.")
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "guide.md").write_text("reference", encoding="utf-8")
            previous_config = {
                key: app.config[key]
                for key in ("TESTING", "PROJECT_ROOT", "USER_ROOT")
            }
            self.addCleanup(app.config.update, previous_config)
            app.config.update(TESTING=True, PROJECT_ROOT=project, USER_ROOT=user)
            client = app.test_client()

            catalog = client.get("/api/skills?trust_project=true").get_json()
            self.assertEqual(catalog["skills"][0]["name"], "demo")
            prompt = client.get("/api/system-prompt?trust_project=true").get_json()
            self.assertIn("<available_skills>", prompt["system_prompt"])
            activated = client.get("/api/skills/demo/activate?trust_project=true")
            self.assertEqual(activated.status_code, 200)
            self.assertIn("Do the task.", activated.get_json()["content"])
            self.assertEqual(activated.get_json()["resources"], ["references/guide.md"])
            self.assertEqual(client.get("/api/skills/missing/activate").status_code, 404)


if __name__ == "__main__":
    unittest.main()
