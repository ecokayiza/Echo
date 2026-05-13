import tempfile
import unittest
from pathlib import Path

from eco_rag.config import Config
from eco_rag.tools.registry import build_retrieve_tools
from eco_rag.tools.workspace_files import (
    workspace_edit_file,
    workspace_list_files,
    workspace_read_file,
    workspace_write_file,
)
from eco_rag.workflow.nodes import _parse_retrieve_call


class WorkspaceFilesTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_workspace_dir = Config.WORKSPACE_DIR
        Config.WORKSPACE_DIR = Path(self._temp_dir.name) / "workspace"

    def tearDown(self):
        Config.WORKSPACE_DIR = self._previous_workspace_dir
        self._temp_dir.cleanup()

    def test_workspace_tools_create_read_list_and_edit_text_files(self):
        write_result = workspace_write_file.invoke(
            {
                "file_path": "notes/todo.txt",
                "content": "alpha\nbeta\n",
            }
        )
        self.assertNotIn("error", write_result)

        list_result = workspace_list_files.invoke({"path": ".", "recursive": True})
        self.assertEqual([item["file_path"] for item in list_result["items"]], ["notes", "notes/todo.txt"])

        read_result = workspace_read_file.invoke({"file_path": "notes/todo.txt"})
        self.assertEqual(read_result["items"][0]["content"], "alpha\nbeta\n")

        edit_result = workspace_edit_file.invoke(
            {
                "file_path": "notes/todo.txt",
                "old_text": "beta",
                "new_text": "gamma",
                "expected_replacements": 1,
            }
        )
        self.assertNotIn("error", edit_result)
        self.assertEqual((Config.WORKSPACE_DIR / "notes" / "todo.txt").read_text(encoding="utf-8"), "alpha\ngamma\n")

    def test_workspace_tools_reject_paths_outside_workspace(self):
        result = workspace_write_file.invoke(
            {
                "file_path": "../outside.txt",
                "content": "nope",
            }
        )

        self.assertIn("workspace root", result["error"])
        self.assertFalse((Config.WORKSPACE_DIR.parent / "outside.txt").exists())

    def test_workspace_retrieve_parser_accepts_file_tools(self):
        allowed = {
            "workspace_list_files",
            "workspace_read_file",
            "workspace_write_file",
            "workspace_edit_file",
        }

        self.assertEqual(
            _parse_retrieve_call('workspace_read_file("notes/todo.txt", max_chars=100)', allowed),
            {"name": "workspace_read_file", "args": {"file_path": "notes/todo.txt", "max_chars": 100}},
        )
        self.assertEqual(
            _parse_retrieve_call('workspace_write_file("notes/todo.txt", "hello", overwrite=True)', allowed),
            {
                "name": "workspace_write_file",
                "args": {"file_path": "notes/todo.txt", "content": "hello", "overwrite": True},
            },
        )
        self.assertEqual(
            _parse_retrieve_call(
                'workspace_edit_file("notes/todo.txt", old_text="hello", new_text="hi", expected_replacements=1)',
                allowed,
            ),
            {
                "name": "workspace_edit_file",
                "args": {
                    "file_path": "notes/todo.txt",
                    "old_text": "hello",
                    "new_text": "hi",
                    "expected_replacements": 1,
                },
            },
        )

    def test_retrieve_tools_include_workspace_tools(self):
        names = {tool.name for tool in build_retrieve_tools()}

        self.assertIn("workspace_list_files", names)
        self.assertIn("workspace_read_file", names)
        self.assertIn("workspace_write_file", names)
        self.assertIn("workspace_edit_file", names)
        self.assertIn("web_fetch", names)


if __name__ == "__main__":
    unittest.main()
