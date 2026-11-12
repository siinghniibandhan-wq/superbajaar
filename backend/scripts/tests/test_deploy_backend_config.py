import json
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "deploy_backend.sh"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class DeployBackendConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    def test_defaults_to_installed_production_service(self):
        self.assertIn('SERVICE="${SB_DEPLOY_SERVICE:-superbajaar-backend.service}"', self.source)

    def test_detects_production_backend_venv(self):
        self.assertIn('"$working_dir/venv"', self.source)
        self.assertIn('"$working_dir/.venv"', self.source)

    def test_validates_existing_gunicorn_runtime_without_replacing_it(self):
        self.assertIn('[[ "$working_dir" == "$REPO_DIR/backend" ]]', self.source)
        self.assertIn('[[ "$exec_start" == *"$venv/bin/"* ]]', self.source)

    def test_compilation_uses_writable_external_bytecode_cache(self):
        self.assertIn("PYTHONPYCACHEPREFIX=", self.source)
        self.assertIn('python" -m compileall -q backend/app', self.source)

    def test_amplify_workflow_can_discover_app_by_repository_when_variable_missing(self):
        self.assertIn("aws amplify list-apps", self.workflow)
        self.assertIn("https://github.com/siinghniibandhan-wq/superbajaar", self.workflow)
        self.assertIn("Unable to resolve the configured Super Bajaar Amplify app", self.workflow)

    def test_amplify_health_check_uses_canonical_branch_domain_from_app_metadata(self):
        self.assertIn('echo "site_url=https://${BRANCH_NAME}.${DEFAULT_DOMAIN}" >> "$GITHUB_OUTPUT"', self.workflow)
        self.assertIn("SITE_URL: ${{ steps.amplify.outputs.site_url }}", self.workflow)
        self.assertNotIn("vars.AMPLIFY_SITE_URL || secrets.AMPLIFY_SITE_URL", self.workflow)

    def test_discovered_amplify_app_id_is_exported_for_later_steps(self):
        self.assertIn('echo "app_id=$APP_ID" >> "$GITHUB_OUTPUT"', self.workflow)

    def test_rollback_uses_the_resolved_amplify_app_id(self):
        self.assertIn("APP_ID: ${{ steps.amplify.outputs.app_id }}", self.workflow)

    def test_amplify_policy_allows_app_discovery_without_broadening_job_access(self):
        policy_path = REPO_ROOT / "docs" / "operations" / "amplify-rollback-iam-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        discovery = [s for s in policy["Statement"] if s.get("Sid") == "DiscoverSuperBajaarAmplifyApp"]
        self.assertEqual(len(discovery), 1)
        self.assertEqual(discovery[0]["Action"], "amplify:ListApps")
        self.assertEqual(discovery[0]["Resource"], "*")
        job_permissions = [s for s in policy["Statement"] if s.get("Sid") in {
            "ListProductionAmplifyJobs", "ReadAndRetryProductionAmplifyJobs"
        }]
        self.assertEqual(len(job_permissions), 2)
        self.assertTrue(all("<AMPLIFY_APP_ID>" in s["Resource"] for s in job_permissions))

    def test_production_database_workflow_requires_explicit_manual_apply(self):
        workflow_path = REPO_ROOT / ".github" / "workflows" / "production-database-migrations.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("push:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("backend/schema/**", workflow)
        self.assertIn("backend/schema_required.txt", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("apply_requested=false", workflow)
        self.assertIn("environment: production-database", workflow)
        self.assertIn("SB_DB=superbajaar", workflow)
        self.assertIn("SB_PSQL=/usr/local/bin/sb-psql", workflow)
        self.assertIn("APPLY SUPERBAJAAR", workflow)
        self.assertIn("--status", workflow)
        self.assertIn("apply_schema.sh", workflow)
        self.assertIn("needs: preflight", workflow)
        self.assertIn("environment: production-database", workflow)
        self.assertIn("Dry-run production migrations (no writes)", workflow)
        self.assertIn("Apply explicitly authorized production migrations", workflow)
        self.assertLess(workflow.index("Dry-run production migrations (no writes)"),
                        workflow.index("Apply explicitly authorized production migrations"))
        preflight = workflow.split("\n  apply:\n", 1)[0]
        self.assertNotIn("Approved Super Bajaar production schema apply", preflight)
        self.assertIn('EXPECTED_MAIN_SHA: ${{ github.sha }}', workflow)
        self.assertIn('EXPECTED_BASELINE_SHA: 519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938', workflow)
        self.assertIn('git rev-parse HEAD', workflow)
        self.assertIn('git status --porcelain', workflow)
        self.assertIn('sha256sum', workflow)
        self.assertIn("git show", workflow)
        self.assertIn(r"\$EXPECTED_MAIN_SHA:backend/schema/000_baseline_schema.sql", workflow)
        self.assertIn('Source SHA did not reach the triggering main commit', workflow)
        self.assertIn('Production baseline SHA-256 mismatch', workflow)

    def test_production_source_guard_avoids_runner_expansion_of_awk_field(self):
        workflow_path = REPO_ROOT / ".github" / "workflows" / "production-database-migrations.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("cut -d", workflow)
        self.assertNotIn("awk", workflow)
    def test_preserves_deployment_safety_guards(self):
        for guard in (
            'systemctl is-active --quiet "$SERVICE"',
            "git status --porcelain",
            'git merge --ff-only "$TARGET_SHA"',
            "rollback_needed=1",
            'sudo systemctl restart "$SERVICE"',
            'curl --fail --silent --show-error --max-time 15 "$HEALTH_URL"',
        ):
            self.assertIn(guard, self.source)


if __name__ == "__main__":
    unittest.main()
