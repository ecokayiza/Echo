import tempfile
import unittest

from eco_rag.config import Config
from eco_rag.settings import AppSettings, save_app_settings
from eco_rag.skills import manager as skills_manager
from eco_rag.workflow.prompts import default_system_prompt


class SkillsManagerTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_settings_path = Config.SETTINGS_PATH
        Config.SETTINGS_PATH = type(Config.SETTINGS_PATH)(self._temp_dir.name) / "settings.json"

    def tearDown(self):
        Config.SETTINGS_PATH = self._previous_settings_path
        self._temp_dir.cleanup()

    def test_default_skills_include_search_and_workspace_files(self):
        self.assertEqual(skills_manager.DEFAULT_SKILLS, ("search", "workspace-files"))

    def test_default_skills_are_listed_first(self):
        skills = skills_manager.list_available_skills()

        self.assertGreaterEqual(len(skills), len(skills_manager.DEFAULT_SKILLS))
        self.assertEqual(skills[: len(skills_manager.DEFAULT_SKILLS)], list(skills_manager.DEFAULT_SKILLS))

    def test_loads_standard_folder_skill_without_frontmatter(self):
        skill_name, content = skills_manager.load_skill_document("search")

        self.assertEqual(skill_name, "search")
        self.assertIn("# Search", content)
        self.assertIn("database_search", content)
        self.assertIn("web_search", content)
        self.assertIn("web_fetch", content)
        self.assertNotIn("---", content)

    def test_old_flat_skill_names_are_not_supported(self):
        with self.assertRaises(ValueError):
            skills_manager.load_skill_document("database_search")
        with self.assertRaises(ValueError):
            skills_manager.load_skill_document("web_search")

    def test_loads_workspace_files_skill(self):
        skill_name, content = skills_manager.load_skill_document("workspace-files")

        self.assertEqual(skill_name, "workspace-files")
        self.assertIn("# Workspace Files", content)
        self.assertIn("workspace_read_file", content)
        self.assertIn("workspace_edit_file", content)

    def test_extract_requested_skill_normalizes_command(self):
        skill_name, query = skills_manager.extract_requested_skill("/skill Search   latest langgraph release notes  ")

        self.assertEqual(skill_name, "search")
        self.assertEqual(query, "latest langgraph release notes")

    def test_disabled_skill_is_omitted_and_rejected(self):
        save_app_settings(AppSettings(enabled_skills=["search"], default_skills=["search"]))

        self.assertEqual(skills_manager.list_available_skills(), ["search"])
        self.assertEqual(skills_manager.list_default_skills(), ["search"])
        with self.assertRaises(ValueError):
            skills_manager.load_skill_document("workspace-files")

    def test_default_skill_prompt_injection_follows_settings(self):
        save_app_settings(AppSettings(enabled_skills=["search", "workspace-files"], default_skills=["search"]))

        prompt = default_system_prompt(available_skills=skills_manager.list_available_skills())

        self.assertIn("# Search", prompt)
        self.assertNotIn("# Workspace Files", prompt)
        self.assertIn("workspace-files", prompt)
        self.assertNotIn("- `search`:", prompt)
        self.assertIn("Default skills are already loaded", prompt)

    def test_skill_settings_crud_and_protected_delete(self):
        previous_skills_dir = skills_manager.SKILLS_DIR
        skills_dir = type(previous_skills_dir)(self._temp_dir.name) / "skills"
        _write_skill(skills_dir, "search", "Search skill.", "# Search\n\nUse search.")
        _write_skill(skills_dir, "workspace-files", "Workspace skill.", "# Workspace Files\n\nUse files.")
        skills_manager.SKILLS_DIR = skills_dir
        try:
            document = skills_manager.load_skill_settings_document()
            self.assertEqual([skill.name for skill in document.skills], ["search", "workspace-files"])
            self.assertTrue(document.skills[0].protected)

            updated = skills_manager.save_skill_settings_document(
                {
                    "skills": [
                        {
                            "name": "search",
                            "description": "Updated search skill.",
                            "content": "# Search\n\nUpdated.",
                            "enabled": True,
                            "default": True,
                            "protected": True,
                        },
                        {
                            "name": "workspace-files",
                            "description": "Workspace skill.",
                            "content": "# Workspace Files\n\nUse files.",
                            "enabled": False,
                            "default": False,
                            "protected": True,
                        },
                        {
                            "name": "custom-notes",
                            "description": "Custom notes skill.",
                            "content": "# Custom Notes\n\nUse notes.",
                            "enabled": True,
                            "default": False,
                            "protected": False,
                        },
                    ]
                }
            )
            self.assertEqual([skill.name for skill in updated.skills], ["search", "workspace-files", "custom-notes"])
            self.assertTrue((skills_dir / "custom-notes" / "SKILL.md").exists())
            self.assertEqual(skills_manager.list_available_skills(), ["search", "custom-notes"])

            with self.assertRaises(ValueError):
                skills_manager.save_skill_settings_document(
                    {
                        "skills": [
                            {
                                "name": "workspace-files",
                                "description": "Workspace skill.",
                                "content": "# Workspace Files\n\nUse files.",
                                "enabled": True,
                                "default": True,
                                "protected": True,
                            }
                        ]
                    }
                )
        finally:
            skills_manager.SKILLS_DIR = previous_skills_dir


def _write_skill(skills_dir, name: str, description: str, content: str):
    path = skills_dir / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{content}\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
