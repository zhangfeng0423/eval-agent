"""
guardrails.py — Precise static AST/dependency scanners, official registry verifiers, and self-learning rule bank with TTL.
"""

import os
import json
import logging
import requests
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from .models import BadDependencyEntry, DependencyType
except (ImportError, ValueError):
    from models import BadDependencyEntry, DependencyType

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Precise AST & Package Manifest Parsers
# ==============================================================================

def scan_pom_for_dependency(pom_path: str, group_id: str, artifact_id: str) -> bool:
    """Parses pom.xml using ElementTree, respecting XML namespaces and exact coordinate match."""
    if not os.path.exists(pom_path):
        return False
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag[:root.tag.index("}") + 1]

        for dep in root.iter(f"{ns}dependency"):
            g_el = dep.find(f"{ns}groupId")
            a_el = dep.find(f"{ns}artifactId")
            if g_el is not None and a_el is not None:
                if (g_el.text or "").strip() == group_id and (a_el.text or "").strip() == artifact_id:
                    return True
    except (ET.ParseError, Exception) as e:
        logger.warning(f"Error parsing pom.xml at {pom_path}: {e}")
    return False


def scan_package_json_for_dependency(pkg_path: str, package_name: str) -> bool:
    """Parses package.json to accurately check dependencies, devDependencies, and peerDependencies."""
    if not os.path.exists(pkg_path):
        return False
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_deps = {}
        for section in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
            all_deps.update(data.get(section, {}))
        return package_name in all_deps
    except Exception as e:
        logger.warning(f"Error parsing package.json at {pkg_path}: {e}")
    return False


def scan_requirements_txt_for_dependency(req_path: str, package_name: str) -> bool:
    """Parses requirements.txt lines accurately, checking normalized package names."""
    if not os.path.exists(req_path):
        return False
    try:
        pkg_norm = package_name.lower().replace("-", "_").replace(".", "_")
        with open(req_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Split off version constraints: ==, >=, <=, ~=, !=, >, <, ;, @
                import re
                raw_name = re.split(r"[=<>!~;@\s]", line)[0].strip()
                if raw_name:
                    target_norm = raw_name.lower().replace("-", "_").replace(".", "_")
                    if pkg_norm == target_norm:
                        return True
    except Exception as e:
        logger.warning(f"Error parsing requirements.txt at {req_path}: {e}")
    return False


# ==============================================================================
# 2. Official Registry Verifiers (Prevents LLM Hallucinations / False Positives)
# ==============================================================================

def verify_package_missing_in_registry(dep_type: DependencyType, dep_id: str) -> Tuple[bool, str]:
    """
    Checks official package registries (npm, PyPI, Maven Central) to confirm if the package really 404s.
    Returns: (is_really_missing, details)
    """
    try:
        if dep_type == DependencyType.NPM:
            url = f"https://registry.npmjs.org/{dep_id}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 404:
                return True, f"NPM registry confirmed package '{dep_id}' is 404."
            elif resp.status_code == 200:
                return False, f"NPM registry found valid package '{dep_id}'."
                
        elif dep_type == DependencyType.PIP:
            url = f"https://pypi.org/pypi/{dep_id}/json"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 404:
                return True, f"PyPI confirmed package '{dep_id}' does not exist."
            elif resp.status_code == 200:
                return False, f"PyPI found valid package '{dep_id}'."

        elif dep_type == DependencyType.MAVEN:
            # dep_id format: groupId:artifactId
            parts = dep_id.split(":")
            if len(parts) == 2:
                g, a = parts
                url = f"https://search.maven.org/solrsearch/select?q=g:%22{g}%22+AND+a:%22{a}%22&rows=1&wt=json"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    docs = resp.json().get("response", {}).get("docs", [])
                    if len(docs) == 0:
                        return True, f"Maven Central confirmed no artifacts for '{dep_id}'."
                    else:
                        return False, f"Maven Central found valid artifact '{dep_id}'."
    except Exception as e:
        logger.warning(f"Registry verification request failed for {dep_type}:{dep_id}: {e}")
        # On network error or timeout, do NOT aggressively treat as missing
        return False, f"Network check error: {e}"

    return False, "Unknown package type or check inconclusive."


# ==============================================================================
# 3. Bad Dependencies Store with Memory Bank & TTL
# ==============================================================================

class BadDepsStore:
    """Manages bad dependency rules with atomic JSON persistence, confidence scores, and TTL."""
    def __init__(self, store_path: str, default_ttl_days: int = 30):
        self.store_path = Path(store_path)
        self.default_ttl_days = default_ttl_days
        self._ensure_file()

    def _ensure_file(self):
        if not self.store_path.exists():
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_raw([])

    def _load_raw(self) -> List[Dict]:
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_raw(self, data: List[Dict]):
        temp_file = self.store_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(self.store_path)

    def get_all(self, prune_expired: bool = True) -> List[BadDependencyEntry]:
        raw_list = self._load_raw()
        entries = []
        now = datetime.now(timezone.utc)
        changed = False

        for item in raw_list:
            try:
                entry = BadDependencyEntry.model_validate(item)
                if prune_expired and entry.is_expired():
                    changed = True
                    continue
                entries.append(entry)
            except Exception:
                continue

        if changed:
            self._save_raw([e.model_dump(mode="json") for e in entries])
        return entries

    def add_bad_dep(
        self,
        dep_type: DependencyType,
        dep_name: str,
        reason: str,
        verify_online: bool = True,
        ttl_days: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Adds a new bad dependency to the rule bank.
        Performs official registry verification to avoid hallucinations.
        """
        dep_id = f"{dep_type.value}:{dep_name}"

        # Online verification
        if verify_online:
            is_missing, detail = verify_package_missing_in_registry(dep_type, dep_name)
            if not is_missing:
                logger.info(f"Refusing to blacklist {dep_id}: {detail}")
                return False, f"Registry verification rejected: {detail}"

        entries = self.get_all(prune_expired=True)
        for e in entries:
            if e.id == dep_id:
                e.hit_count += 1
                e.reason = reason
                self._save_raw([x.model_dump(mode="json") for x in entries])
                return True, f"Updated existing rule for {dep_id}"

        ttl = ttl_days or self.default_ttl_days
        now_dt = datetime.now(timezone.utc)
        new_entry = BadDependencyEntry(
            id=dep_id,
            dep_type=dep_type,
            dep_name=dep_name,
            reason=reason,
            confidence=1.0,
            hit_count=1,
            created_at=now_dt,
            expires_at=now_dt + timedelta(days=ttl)
        )
        entries.append(new_entry)
        self._save_raw([x.model_dump(mode="json") for x in entries])
        logger.info(f"Learned new bad dependency: {dep_id} (Reason: {reason})")
        return True, f"Successfully recorded {dep_id}"

    def check_project_for_bad_deps(self, project_root: str) -> Optional[BadDependencyEntry]:
        """
        Fast scan across pom.xml, package.json, and requirements.txt in the project directory.
        Returns the matching BadDependencyEntry if hit.
        """
        entries = self.get_all(prune_expired=True)
        if not entries:
            return None

        # Collect all manifest files
        pom_files = []
        pkg_files = []
        req_files = []

        for root, _, files in os.walk(project_root):
            if "node_modules" in root or ".venv" in root or "target" in root:
                continue
            for f in files:
                p = os.path.join(root, f)
                if f == "pom.xml":
                    pom_files.append(p)
                elif f == "package.json":
                    pkg_files.append(p)
                elif f.startswith("requirements") and f.endswith(".txt"):
                    req_files.append(p)

        for entry in entries:
            if entry.dep_type == DependencyType.MAVEN:
                parts = entry.dep_name.split(":")
                if len(parts) == 2:
                    g, a = parts
                    for pom in pom_files:
                        if scan_pom_for_dependency(pom, g, a):
                            entry.hit_count += 1
                            return entry
            elif entry.dep_type == DependencyType.NPM:
                for pkg in pkg_files:
                    if scan_package_json_for_dependency(pkg, entry.dep_name):
                        entry.hit_count += 1
                        return entry
            elif entry.dep_type == DependencyType.PIP:
                for req in req_files:
                    if scan_requirements_txt_for_dependency(req, entry.dep_name):
                        entry.hit_count += 1
                        return entry

        return None
