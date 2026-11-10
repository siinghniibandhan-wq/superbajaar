import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "sync_main.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


class MainSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.bare = self.root / "origin.git"
        self.work = self.root / "checkout"
        subprocess.run(["git", "init", "--bare", str(self.bare)], check=True, capture_output=True)
        subprocess.run(["git", "--git-dir", str(self.bare), "symbolic-ref", "HEAD", "refs/heads/main"], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "main", str(self.work)], check=True, capture_output=True)
        git(self.work, "config", "user.email", "sync-test@example.invalid")
        git(self.work, "config", "user.name", "Sync Test")
        (self.work / "tracked.txt").write_text("initial\n")
        git(self.work, "add", "tracked.txt")
        git(self.work, "commit", "-m", "initial")
        git(self.work, "remote", "add", "origin", str(self.bare))
        git(self.work, "push", "-u", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self):
        env = os.environ.copy()
        env.update({
            "SB_SYNC_REPO_DIR": str(self.work),
            "SB_SYNC_LOG_FILE": str(self.root / "sync.log"),
            "SB_SYNC_LOCK_FILE": str(self.root / "sync.lock"),
        })
        return subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True)

    def push_remote_change(self, text):
        other = self.root / "writer"
        subprocess.run(["git", "clone", str(self.bare), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "writer@example.invalid")
        git(other, "config", "user.name", "Writer")
        (other / "tracked.txt").write_text(text)
        git(other, "add", "tracked.txt")
        git(other, "commit", "-m", "remote update")
        git(other, "push", "origin", "main")

    def test_fast_forwards_when_main_has_new_commit(self):
        self.push_remote_change("updated remotely\n")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.work / "tracked.txt").read_text(), "updated remotely\n")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.work, "rev-parse", "origin/main"))

    def test_does_nothing_when_already_current(self):
        before = git(self.work, "rev-parse", "HEAD")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)

    def test_refuses_to_overwrite_local_changes(self):
        (self.work / "tracked.txt").write_text("local change\n")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.work / "tracked.txt").read_text(), "local change\n")

    def test_refuses_to_switch_from_non_main_branch(self):
        git(self.work, "checkout", "-b", "feature/test")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git(self.work, "branch", "--show-current"), "feature/test")


if __name__ == "__main__":
    unittest.main()
