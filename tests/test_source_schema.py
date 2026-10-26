"""Fast static tests. No Databricks workspace or data files needed."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTest(unittest.TestCase):
    def test_notebook_sources_are_valid_python(self):
        for name in ("00_verify_access", "01_ingest_bronze", "02_transform_silver", "03_build_gold", "04_validate_quality"):
            path = ROOT / "notebooks" / f"{name}.py"
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("# Databricks notebook source"))
            ast.parse(content, filename=str(path))

    def test_no_sensitive_files_are_committed(self):
        self.assertIn(".env", (ROOT / ".gitignore").read_text())


if __name__ == "__main__":
    unittest.main()
