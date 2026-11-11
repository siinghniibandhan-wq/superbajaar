import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "deploy_backend.sh"


class DeployBackendConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_defaults_to_installed_production_service(self):
        self.assertIn('SERVICE="${SB_DEPLOY_SERVICE:-superbajaar-backend.service}"', self.source)

    def test_detects_production_backend_venv(self):
        self.assertIn('"$working_dir/venv"', self.source)
        self.assertIn('"$working_dir/.venv"', self.source)

    def test_validates_existing_gunicorn_runtime_without_replacing_it(self):
        self.assertIn('[[ "$working_dir" == "$REPO_DIR/backend" ]]', self.source)
        self.assertIn('[[ "$exec_start" == *"$venv/bin/"* ]]', self.source)

    def test_compilation_uses_writable_external_bytecode_cache(self):
        self.assertIn('PYTHONPYCACHEPREFIX=', self.source)
        self.assertIn('python" -m compileall -q backend/app', self.source)

    def test_preserves_deployment_safety_guards(self):
        for guard in (
            'systemctl is-active --quiet "$SERVICE"',
            'git status --porcelain',
            'git merge --ff-only "$TARGET_SHA"',
            'rollback_needed=1',
            'sudo systemctl restart "$SERVICE"',
            'curl --fail --silent --show-error --max-time 15 "$HEALTH_URL"',
        ):
            self.assertIn(guard, self.source)


if __name__ == "__main__":
    unittest.main()
