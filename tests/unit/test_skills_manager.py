import unittest

from eco_rag.skills.manager import DEFAULT_SKILLS, extract_requested_skill, list_available_skills


class SkillsManagerTests(unittest.TestCase):
    def test_default_skills_are_listed_first(self):
        skills = list_available_skills()

        self.assertGreaterEqual(len(skills), len(DEFAULT_SKILLS))
        self.assertEqual(skills[: len(DEFAULT_SKILLS)], list(DEFAULT_SKILLS))

    def test_extract_requested_skill_normalizes_command(self):
        skill_name, query = extract_requested_skill("/skill Web-Search   latest langgraph release notes  ")

        self.assertEqual(skill_name, "web-search")
        self.assertEqual(query, "latest langgraph release notes")


if __name__ == "__main__":
    unittest.main()
