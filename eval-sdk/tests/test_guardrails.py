"""
test_guardrails.py — Unit tests for accurate dependency parsers and bad dependency store with TTL.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

# Ensure parent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import DependencyType, BadDependencyEntry
from guardrails import (
    scan_pom_for_dependency,
    scan_package_json_for_dependency,
    scan_requirements_txt_for_dependency,
    BadDepsStore
)


class TestGuardrails(unittest.TestCase):

    def test_pom_xml_parsing(self):
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <dependencies>
        <dependency>
            <groupId>org.apache.poi</groupId>
            <artifactId>poi-ooxml-schemas</artifactId>
            <version>4.1.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(pom_content)
            temp_path = f.name

        try:
            self.assertTrue(scan_pom_for_dependency(temp_path, "org.apache.poi", "poi-ooxml-schemas"))
            self.assertTrue(scan_pom_for_dependency(temp_path, "org.springframework.boot", "spring-boot-starter-web"))
            self.assertFalse(scan_pom_for_dependency(temp_path, "org.apache.poi", "non-existent"))
            self.assertFalse(scan_pom_for_dependency(temp_path, "fake.group", "poi-ooxml-schemas"))
        finally:
            os.remove(temp_path)

    def test_package_json_parsing(self):
        pkg_content = """{
            "name": "my-app",
            "dependencies": {
                "react": "^18.2.0",
                "lodash": "4.17.21"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }"""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(pkg_content)
            temp_path = f.name

        try:
            self.assertTrue(scan_package_json_for_dependency(temp_path, "react"))
            self.assertTrue(scan_package_json_for_dependency(temp_path, "typescript"))
            self.assertFalse(scan_package_json_for_dependency(temp_path, "vue"))
        finally:
            os.remove(temp_path)

    def test_requirements_txt_parsing(self):
        req_content = """
# Comment line
requests>=2.28.0
fastapi==0.95.0; python_version >= '3.8'
numpy~=1.24.0
pytest
"""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(req_content)
            temp_path = f.name

        try:
            self.assertTrue(scan_requirements_txt_for_dependency(temp_path, "requests"))
            self.assertTrue(scan_requirements_txt_for_dependency(temp_path, "fastapi"))
            self.assertTrue(scan_requirements_txt_for_dependency(temp_path, "numpy"))
            self.assertTrue(scan_requirements_txt_for_dependency(temp_path, "pytest"))
            self.assertFalse(scan_requirements_txt_for_dependency(temp_path, "requests-toolbelt"))
            self.assertFalse(scan_requirements_txt_for_dependency(temp_path, "django"))
        finally:
            os.remove(temp_path)

    def test_bad_deps_store_and_ttl(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            store_path = f.name

        try:
            store = BadDepsStore(store_path, default_ttl_days=30)
            
            # Add a bad dependency without online verification for test
            ok, msg = store.add_bad_dep(
                dep_type=DependencyType.PIP,
                dep_name="fake-ghost-pkg-12345",
                reason="Package removed from PyPI",
                verify_online=False,
                ttl_days=30
            )
            self.assertTrue(ok)

            entries = store.get_all(prune_expired=True)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].dep_name, "fake-ghost-pkg-12345")
            self.assertFalse(entries[0].is_expired())

            # Test expiration
            now_dt = datetime.now(timezone.utc)
            expired_entry = BadDependencyEntry(
                id="npm:old-deprecated-pkg",
                dep_type=DependencyType.NPM,
                dep_name="old-deprecated-pkg",
                reason="Expired",
                created_at=now_dt - timedelta(days=40),
                expires_at=now_dt - timedelta(days=10)
            )
            store._save_raw([entries[0].model_dump(mode="json"), expired_entry.model_dump(mode="json")])
            
            # get_all with prune should automatically remove the expired one
            pruned_entries = store.get_all(prune_expired=True)
            self.assertEqual(len(pruned_entries), 1)
            self.assertEqual(pruned_entries[0].id, "pip:fake-ghost-pkg-12345")
        finally:
            if os.path.exists(store_path):
                os.remove(store_path)


if __name__ == "__main__":
    unittest.main()
