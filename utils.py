from pathlib import Path
import subprocess

def clone_and_checkout(repo: str, commit: str, base_dir: Path):

    safe_name = repo.replace("/", "_")
    repo_dir = base_dir / safe_name

    if not repo_dir.exists(): 
        repo_url = f"https://github.com/{repo}.git"

        print(f"Cloning {repo_url} into {repo_dir}")
        subprocess.run(["git", "clone", repo_url, str(repo_dir)], check=True)

    subprocess.run(["git", "-C", str(repo_dir), "fetch"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", commit], check=True)

    return repo_dir

def load_relevant_code(repo_dir: Path, relevant_files: list[str])->str:

    MAX_CHARS = 30000
    parts = []

    def try_append(file_path:Path):
        try:
            text = file_path.read_text(encoding='utf-8', errors='ignore')
            parts.append(f"==== FILE: {file_path.relative_to(repo_dir)} =====\n")
            parts.append(text + "\n\n")
        except Exception:
            pass
    
    if relevant_files:
        for rel in relevant_files:
            fpath = repo_dir / rel
            if fpath.exists() and fpath.is_file():
                try_append(fpath)
        if parts:
            return "".join(parts)[:MAX_CHARS]
        
    for py_file in repo_dir.rglob("*.py"):
        if len("".join(parts)) > MAX_CHARS:
            break
        try_append(py_file)
    
    return "".join(parts)[:MAX_CHARS]

def apply_patch(repo_dir: Path, patch_text: str):
    patch_file = repo_dir / "candidate.patch"
    patch_file.write_text(patch_text, encoding="utf-8")

    check_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", "--check", str(patch_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check_proc.returncode != 0:
        patch_file.unlink(missing_ok=True)
        return False

    apply_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", str(patch_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    patch_file.unlink(missing_ok=True)
    return apply_proc.returncode == 0


def apply_test_patch(repo_dir: Path, test_patch: str):
    test_file = repo_dir / "test_to_apply.patch"
    test_file.write_text(test_patch, encoding="utf-8")

    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", "--check", str(test_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        test_file.unlink(missing_ok=True)
        return False

    apply_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", str(test_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    test_file.unlink(missing_ok=True)
    return apply_proc.returncode == 0


def run_test_command(repo_dir: Path, test_command: str):
    try:
        parts = test_command.strip().split()
        proc = subprocess.run(
            parts, cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return proc.returncode == 0
    except Exception:
        return False
    
