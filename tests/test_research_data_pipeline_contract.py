from __future__ import annotations

import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class ResearchDataPipelineContractTests(unittest.TestCase):
    def read(self,name: str) -> str:
        return (ROOT/".github"/"workflows"/name).read_text(encoding="utf-8")

    def test_child_workflows_are_reusable_and_serialized(self):
        for name in (
            "live-free-evidence-connectors.yml",
            "abf-source-health.yml",
            "free-evidence-history.yml",
        ):
            text=self.read(name)
            self.assertIn("workflow_call:",text)
            self.assertIn("group: evidence-data-writer",text)
            self.assertIn("cancel-in-progress: false",text)
            self.assertNotIn("schedule:\n",text)

    def test_only_orchestrator_owns_daily_schedule(self):
        text=self.read("research-data-pipeline.yml")
        self.assertIn('cron: "10 1 * * *"',text)
        self.assertIn("workflow_dispatch:",text)
        self.assertIn("uses: ./.github/workflows/live-free-evidence-connectors.yml",text)
        self.assertIn("uses: ./.github/workflows/abf-source-health.yml",text)
        self.assertIn("uses: ./.github/workflows/free-evidence-history.yml",text)

    def test_history_never_force_pushes_or_switches_data_branch(self):
        text=self.read("free-evidence-history.yml")
        self.assertNotIn("--force",text)
        self.assertNotIn("git switch -C evidence-data",text)
        self.assertIn("Checkout persistent evidence branch",text)

    def test_run_manifests_are_persisted(self):
        for name,folder in (
            ("live-free-evidence-connectors.yml","run_manifests/live"),
            ("abf-source-health.yml","run_manifests/abf"),
            ("free-evidence-history.yml","run_manifests/history"),
        ):
            text=self.read(name)
            self.assertIn(folder,text)
            self.assertIn("pipeline_run_manifest.json",text)
            self.assertIn("pipeline_validation.json",text)


if __name__=="__main__":
    unittest.main()
