import subprocess
import unittest
from pathlib import Path


class MarkdownRendererSmokeTests(unittest.TestCase):
    def test_markdown_renderer_smoke(self):
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "tests" / "markdown_renderer_smoke.js"
        completed = subprocess.run(
            ["node", str(script_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(
                "markdown renderer smoke failed:\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )


if __name__ == "__main__":
    unittest.main()
