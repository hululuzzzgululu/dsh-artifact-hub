from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "package_uncommitted.sh"


def init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def commit_file(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "add", relative_path],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"add {relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_script(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def run_script_with_args(
    repo: Path, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=cwd or repo,
        check=False,
        capture_output=True,
        text=True,
    )


def find_generated_zip(repo: Path) -> Path:
    archives = sorted(repo.glob("uncommitted-*.zip"))
    assert len(archives) == 1
    return archives[0]


def test_packages_uncommitted_files_and_deleted_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")
    commit_file(repo, "deleted.txt", "to be removed\n")

    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
    (repo / "new.txt").write_text("new file\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()

    result = run_script(repo)

    assert result.returncode == 0, result.stderr
    archive_path = find_generated_zip(repo)

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "tracked.txt" in names
        assert "new.txt" in names
        assert "deleted.txt" not in names
        assert "deleted_files.txt" in names
        deleted_manifest = archive.read("deleted_files.txt").decode("utf-8")

    assert deleted_manifest.splitlines() == ["deleted.txt"]


def test_fails_when_worktree_is_clean(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    result = run_script(repo)

    assert result.returncode == 1
    assert "No uncommitted files found" in result.stderr
    assert not list(repo.glob("uncommitted-*.zip"))


def test_writes_empty_deleted_manifest_when_no_deleted_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")

    result = run_script(repo)

    assert result.returncode == 0, result.stderr
    archive_path = find_generated_zip(repo)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.read("deleted_files.txt").decode("utf-8") == ""


def test_supports_custom_output_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
    caller_dir = repo / "nested"
    caller_dir.mkdir()
    output_dir = caller_dir / "artifacts"
    output_dir.mkdir()

    result = run_script_with_args(repo, "artifacts/custom.zip", cwd=caller_dir)

    assert result.returncode == 0, result.stderr
    archive_path = output_dir / "custom.zip"
    assert archive_path.exists()

    with zipfile.ZipFile(archive_path) as archive:
        assert "tracked.txt" in archive.namelist()
        assert archive.read("deleted_files.txt").decode("utf-8") == ""


def test_packages_untracked_directories_recursively(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    nested_dir = repo / "evals" / "cases"
    nested_dir.mkdir(parents=True)
    (nested_dir / "case1.yaml").write_text("name: case1\n", encoding="utf-8")

    result = run_script(repo)

    assert result.returncode == 0, result.stderr
    archive_path = find_generated_zip(repo)

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "evals/cases/case1.yaml" in names


def test_excludes_gitignored_files_inside_untracked_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, ".gitignore", "__pycache__/\n")
    commit_file(repo, "tracked.txt", "v1\n")

    nested_dir = repo / "evals"
    (nested_dir / "cases").mkdir(parents=True)
    (nested_dir / "cases" / "case1.yaml").write_text("name: case1\n", encoding="utf-8")
    (nested_dir / "__pycache__").mkdir()
    (nested_dir / "__pycache__" / "cached.pyc").write_text(
        "compiled\n", encoding="utf-8"
    )

    result = run_script(repo)

    assert result.returncode == 0, result.stderr
    archive_path = find_generated_zip(repo)

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "evals/cases/case1.yaml" in names
        assert "evals/__pycache__/cached.pyc" not in names


def test_packages_paths_that_start_with_dash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    (repo / "-h.zip").write_text("leading dash file\n", encoding="utf-8")

    result = run_script(repo)

    assert result.returncode == 0, result.stderr
    archive_path = find_generated_zip(repo)

    with zipfile.ZipFile(archive_path) as archive:
        assert "-h.zip" in archive.namelist()


def test_packages_head_commit_against_its_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")
    commit_file(repo, "deleted.txt", "to be removed\n")

    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
    (repo / "new.txt").write_text("new file\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()
    commit_all(repo, "feature change")

    result = run_script_with_args(repo, "--commit", "HEAD")

    assert result.returncode == 0, result.stderr
    archive_path = next(repo.glob("commit-*.zip"))

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "tracked.txt" in names
        assert "new.txt" in names
        assert "deleted.txt" not in names
        assert archive.read("tracked.txt").decode("utf-8") == "v2\n"
        assert archive.read("deleted_files.txt").decode("utf-8").splitlines() == [
            "deleted.txt"
        ]


def test_packages_specific_commit_without_later_or_worktree_changes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "base.txt", "base\n")

    (repo / "base.txt").write_text("feature\n", encoding="utf-8")
    (repo / "feature.txt").write_text("feature file\n", encoding="utf-8")
    feature_commit = commit_all(repo, "feature change")

    (repo / "later.txt").write_text("later file\n", encoding="utf-8")
    commit_all(repo, "later change")
    (repo / "worktree.txt").write_text("uncommitted file\n", encoding="utf-8")

    result = run_script_with_args(repo, "--commit", feature_commit)

    assert result.returncode == 0, result.stderr
    archive_path = next(repo.glob("commit-*.zip"))

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "base.txt" in names
        assert "feature.txt" in names
        assert "later.txt" not in names
        assert "worktree.txt" not in names
        assert archive.read("base.txt").decode("utf-8") == "feature\n"
        assert archive.read("deleted_files.txt").decode("utf-8") == ""


def test_packages_root_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "first.txt", "first commit\n")

    result = run_script_with_args(repo, "--commit", "HEAD")

    assert result.returncode == 0, result.stderr
    archive_path = next(repo.glob("commit-*.zip"))
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.read("first.txt").decode("utf-8") == "first commit\n"
        assert archive.read("deleted_files.txt").decode("utf-8") == ""


def test_packages_last_commits_into_one_cumulative_archive(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "unchanged.txt").write_text("outside range\n", encoding="utf-8")
    (repo / "changed.txt").write_text("before\n", encoding="utf-8")
    (repo / "removed.txt").write_text("remove me\n", encoding="utf-8")
    (repo / "old-name.txt").write_text("renamed content\n", encoding="utf-8")
    commit_all(repo, "base commit")

    (repo / "changed.txt").write_text("first change\n", encoding="utf-8")
    (repo / "temporary.txt").write_text("temporary\n", encoding="utf-8")
    subprocess.run(
        ["git", "mv", "old-name.txt", "new-name.txt"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    commit_all(repo, "first selected commit")
    (repo / "temporary.txt").unlink()
    (repo / "removed.txt").unlink()
    (repo / "second.txt").write_text("second change\n", encoding="utf-8")
    commit_all(repo, "second selected commit")
    (repo / "changed.txt").write_text("final content\n", encoding="utf-8")
    (repo / "third.txt").write_text("third change\n", encoding="utf-8")
    commit_all(repo, "third selected commit")
    (repo / "worktree.txt").write_text("uncommitted\n", encoding="utf-8")

    result = run_script_with_args(repo, "--last", "3", "recent.zip")

    assert result.returncode == 0, result.stderr
    archive_path = repo / "recent.zip"
    assert result.stdout.strip() == str(archive_path)
    assert list(repo.glob("*.zip")) == [archive_path]

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "changed.txt" in names
        assert "new-name.txt" in names
        assert "second.txt" in names
        assert "third.txt" in names
        assert "old-name.txt" not in names
        assert "removed.txt" not in names
        assert "temporary.txt" not in names
        assert "unchanged.txt" not in names
        assert "worktree.txt" not in names
        assert archive.read("changed.txt").decode("utf-8") == "final content\n"
        assert set(
            archive.read("deleted_files.txt").decode("utf-8").splitlines()
        ) == {"old-name.txt", "removed.txt"}


def test_packages_last_commits_when_range_includes_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "first.txt", "first commit\n")

    result = run_script_with_args(repo, "--last", "7", "all.zip")

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(repo / "all.zip") as archive:
        assert archive.read("first.txt").decode("utf-8") == "first commit\n"
        assert archive.read("deleted_files.txt").decode("utf-8") == ""


def test_rejects_invalid_last_commit_count(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    commit_file(repo, "tracked.txt", "v1\n")

    result = run_script_with_args(repo, "--last", "0")

    assert result.returncode == 1
    assert "Commit count must be a positive integer" in result.stderr
