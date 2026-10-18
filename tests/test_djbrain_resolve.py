"""Only human-reviewed code SHAs and non-executable IDs may start DJ runs."""
import json,tempfile,unittest
from pathlib import Path
from djbrain_runner.resolve import resolve_experiment,write_github_outputs
REPO="volkovitskiyartem-lab/void-vibe-router"
SHA="a"*40
def write_registry(root,changes=None):
    exp={"repository":REPO,"commit_sha":SHA,"mode":"fixed",
         "seeds":[36,37,38],"entrypoint":"djbrain_runner.execute"}
    exp.update(changes or {})
    path=Path(root)/"registry.json"
    path.write_text(json.dumps({"schema":1,"experiments":{"rc38-fixed":exp}}))
    return path
class ResolverTests(unittest.TestCase):
    def test_pinned_fixed_experiment_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            result=resolve_experiment("rc38-fixed",write_registry(d))
            self.assertEqual(result["commit_sha"],SHA)
            self.assertEqual(result["repository"],REPO)
            self.assertEqual(result["seeds"],[36,37,38])
    def test_arbitrary_ids_or_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            registry=write_registry(d)
            for value in ("../main","unlisted","rc38-fixed\ncmd=x",""):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    resolve_experiment(value,registry)
    def test_invalid_repo_and_mutable_commit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for change in ({"repository":"external/private"},
                           {"commit_sha":"main"},{"commit_sha":SHA+"bad"}):
                with self.subTest(change=change),self.assertRaises(ValueError):
                    resolve_experiment("rc38-fixed",write_registry(d,change))
    def test_script_entrypoint_and_extra_fields_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for change in ({"entrypoint":"python -c print('bad')"},
                           {"mode":"script"},{"seeds":[36,37,39]},
                           {"shell":"danger"}):
                with self.subTest(change=change),self.assertRaises(ValueError):
                    resolve_experiment("rc38-fixed",write_registry(d,change))
    def test_only_safe_fixed_outputs_written(self):
        with tempfile.TemporaryDirectory() as d:
            result=resolve_experiment("rc38-fixed",write_registry(d))
            output=Path(d)/"github-output"
            write_github_outputs(result,output)
            self.assertEqual(output.read_text().splitlines(),[
                f"private_repo={REPO}",f"private_sha={SHA}",
                "experiment_id=rc38-fixed","mode=fixed"])
if __name__=="__main__":unittest.main()
