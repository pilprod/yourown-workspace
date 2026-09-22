"""Offline integration tests; fixtures remain under the ignored workspace .local/."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-workspace.sh"


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        local = ROOT / ".local"
        local.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-workspace-", dir=local)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace with spaces"
        self.env = os.environ.copy()
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "5",
            "GIT_CONFIG_KEY_0": "protocol.file.allow",
            "GIT_CONFIG_VALUE_0": "always",
            "GIT_CONFIG_KEY_1": "user.name",
            "GIT_CONFIG_VALUE_1": "Workspace Test",
            "GIT_CONFIG_KEY_2": "user.email",
            "GIT_CONFIG_VALUE_2": "workspace-test@example.invalid",
            "GIT_CONFIG_KEY_3": "commit.gpgsign",
            "GIT_CONFIG_VALUE_3": "false",
            "GIT_CONFIG_KEY_4": "core.hooksPath",
            "GIT_CONFIG_VALUE_4": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.workspace.mkdir()
        self.git(self.workspace, "init", "-q")
        (self.workspace / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.workspace / "scripts/prepare-workspace.sh")
        (self.workspace / ".gitignore").write_text(".agents/\n.claude/\n")
        self.pins = {}
        for module in ("yourown-platform", "yourown-rag"):
            source = self.base / (module + "-source")
            source.mkdir()
            self.git(source, "init", "-q")
            if module == "yourown-rag":
                files = {
                    "rules/core.md": "Shared rules\n",
                    "rules/terraform.md": "Terraform rules\n",
                    "knowledge/platform.md": "Platform knowledge\n",
                    "skills/yourown-terraform/SKILL.md": "---\nname: yourown-terraform\ndescription: Terraform task\n---\n",
                }
            else:
                files = {"README.md": "Platform fixture\n"}
            for relative, content in files.items():
                file = source / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            self.git(source, "add", ".")
            self.git(source, "commit", "-qm", "Fixture")
            pin = self.git(source, "rev-parse", "HEAD").stdout.strip()
            self.pins[module] = pin
            self.git(self.workspace, "config", "-f", ".gitmodules", "submodule." + module + ".path", module)
            self.git(self.workspace, "config", "-f", ".gitmodules", "submodule." + module + ".url", str(source))
            self.git(self.workspace, "update-index", "--add", "--cacheinfo", "160000," + pin + "," + module)
            self.git(self.workspace, "clone", "-q", "--no-hardlinks", str(source), module)
        self.git(self.workspace, "add", "scripts", ".gitmodules", ".gitignore")
        self.git(self.workspace, "commit", "-qm", "Workspace fixture")

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], env=self.env,
                              text=True, capture_output=True, check=True)

    def prepare(self, *args, success=True):
        result = subprocess.run(["bash", str(self.workspace / "scripts/prepare-workspace.sh"), *args],
                                cwd=self.base, env=self.env, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_prepare_is_repeatable_and_check_is_read_only(self):
        self.prepare()
        link = self.workspace / ".agents/skills/yourown-terraform"
        self.assertEqual(os.readlink(link), "../../yourown-rag/skills/yourown-terraform")
        self.assertTrue((link / "SKILL.md").is_file())
        before = link.lstat().st_mtime_ns
        self.prepare()
        self.prepare("--check", "--strict")
        self.assertEqual(link.lstat().st_mtime_ns, before)
        self.assertTrue((self.workspace / ".claude/skills/yourown-terraform").is_symlink())

    def test_check_does_not_create_links(self):
        self.prepare("--check", success=False)
        self.assertFalse((self.workspace / ".agents").exists())
        self.assertFalse((self.workspace / ".claude").exists())

    def test_generic_needs_no_client_links(self):
        self.prepare("--agent", "generic", "--check", "--strict")
        self.assertFalse((self.workspace / ".agents").exists())

    def test_selected_client_only(self):
        self.prepare("--agent", "claude")
        self.assertTrue((self.workspace / ".claude/skills/yourown-terraform").is_symlink())
        self.assertFalse((self.workspace / ".agents").exists())

    def test_missing_submodule_check_preserves_git_state_and_prepare_initializes_pin(self):
        shutil.rmtree(self.workspace / "yourown-rag")
        gitdir = self.workspace / ".git"
        before = {name: (gitdir / name).read_bytes() for name in ("config", "index")}
        self.prepare("--check", success=False)
        self.assertFalse((self.workspace / "yourown-rag").exists())
        for name, content in before.items():
            self.assertEqual((gitdir / name).read_bytes(), content)
        self.prepare("--strict")
        self.assertEqual(self.git(self.workspace / "yourown-rag", "rev-parse", "HEAD").stdout.strip(),
                         self.pins["yourown-rag"])

    def test_dirty_work_survives_and_strict_rejects_it(self):
        platform = self.workspace / "yourown-platform"
        edited = platform / "README.md"
        edited.write_text("Uncommitted work\n")
        (platform / "new.txt").write_text("Untracked work\n")
        self.git(platform, "add", "README.md")
        before = self.git(platform, "status", "--porcelain=v1").stdout
        result = self.prepare()
        self.assertIn("local changes", result.stderr)
        self.assertEqual(edited.read_text(), "Uncommitted work\n")
        self.assertEqual(self.git(platform, "status", "--porcelain=v1").stdout, before)
        self.prepare("--strict", success=False)
        self.assertEqual(self.git(platform, "status", "--porcelain=v1").stdout, before)

    def test_pin_mismatch_is_preserved_and_strict_rejects_it(self):
        platform = self.workspace / "yourown-platform"
        (platform / "README.md").write_text("Another commit\n")
        self.git(platform, "commit", "-qam", "Local development")
        head = self.git(platform, "rev-parse", "HEAD").stdout
        result = self.prepare()
        self.assertIn("differs from the workspace pin", result.stderr)
        self.prepare("--strict", success=False)
        self.assertEqual(self.git(platform, "rev-parse", "HEAD").stdout, head)

    def test_conflicting_file_is_preserved_before_any_links_are_created(self):
        conflict = self.workspace / ".claude/skills/yourown-terraform"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("Existing instructions\n")
        self.prepare(success=False)
        self.assertEqual(conflict.read_text(), "Existing instructions\n")
        self.assertFalse((self.workspace / ".agents").exists())

    def test_conflicting_link_is_preserved(self):
        link = self.workspace / ".agents/skills/yourown-terraform"
        link.parent.mkdir(parents=True)
        link.symlink_to("somewhere-else")
        self.prepare(success=False)
        self.assertEqual(os.readlink(link), "somewhere-else")

    def test_nonempty_nonrepository_is_preserved(self):
        platform = self.workspace / "yourown-platform"
        shutil.rmtree(platform / ".git")
        before = (platform / "README.md").read_text()
        result = self.prepare(success=False)
        self.assertIn("not its own Git checkout", result.stderr)
        self.assertEqual((platform / "README.md").read_text(), before)

    def test_strict_preflight_does_not_initialize_other_submodule(self):
        shutil.rmtree(self.workspace / "yourown-platform")
        (self.workspace / "yourown-rag/rules/core.md").write_text("Local edit\n")
        self.prepare("--strict", success=False)
        self.assertFalse((self.workspace / "yourown-platform").exists())

    def test_missing_required_context_fails(self):
        (self.workspace / "yourown-rag/rules/core.md").unlink()
        self.prepare(success=False)
        self.assertFalse((self.workspace / ".agents").exists())

    def test_script_in_nested_nonroot_folder_is_rejected(self):
        nested = self.workspace / "nested/scripts"
        nested.mkdir(parents=True)
        shutil.copy2(SCRIPT, nested / "prepare-workspace.sh")
        result = subprocess.run(["bash", str(nested / "prepare-workspace.sh")],
                                env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workspace Git root", result.stderr)


if __name__ == "__main__":
    unittest.main()
