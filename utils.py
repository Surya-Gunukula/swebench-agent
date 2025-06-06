from pathlib import Path
import subprocess
import re
import json
import shlex
import os

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

def load_relevant_code(repo_dir: Path, failure_path: str, line_no: int, context_radius: int = 50)->str:

    try:
        abs_path = Path(failure_path)
        # If pytest printed an absolute path outside of repo_dir, attempt to relativize:
        try:
            rel = abs_path.relative_to(repo_dir)
            target_file = repo_dir / rel
        except Exception:
            target_file = abs_path

        all_lines = target_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        start = max(0, line_no - 1 - context_radius)
        end = min(len(all_lines), line_no - 1 + context_radius)
        snippet = "\n".join(all_lines[start:end])
        return snippet
    except Exception:
        return ""

def apply_patch(repo_dir: Path, patch_text: str):
    patch_file = repo_dir / "candidate.patch"
    patch_file.write_text(patch_text, encoding="utf-8")

    check_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", "--check", str(patch_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if check_proc.returncode != 0:
        patch_file.unlink(missing_ok=True)
        return False

    apply_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "apply", str(patch_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    patch_file.unlink(missing_ok=True)
    return apply_proc.returncode == 0


def apply_test_patch(repo_dir: Path, test_patch: str) -> bool:
    patch_filename = "tmp_test_to_apply.patch"
    test_file = repo_dir / patch_filename
    try:
        print(f"DEBUG: Writing normalized patch to: {test_file.resolve()}")
        test_file.write_text(test_patch, encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Could not write patch file at {test_file!s}: {e}")
        return False

    if not test_file.exists():
        print(f"ERROR: After write_text, patch file is missing at: {test_file.resolve()}")
        return False
    else:
        print(f"DEBUG: Patch file confirmed at: {test_file.resolve()}")

    check_cmd = ["git", "-C", str(repo_dir.resolve()), "apply", "--check", patch_filename]
    print("DEBUG: Running:", " ".join(check_cmd))
    check_proc = subprocess.run(
        check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if check_proc.returncode != 0:
        print("git apply --check failed:\n")
        print(check_proc.stderr.strip(), "\n")
        test_file.unlink(missing_ok=True)
        return False

    apply_cmd = ["git", "-C", str(repo_dir.resolve()), "apply", patch_filename]
    print("DEBUG: Now running:", " ".join(apply_cmd))
    apply_proc = subprocess.run(
        apply_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if apply_proc.returncode != 0:
        print("git apply failed:\n")
        print(apply_proc.stderr.strip(), "\n")
        test_file.unlink(missing_ok=True)
        return False

    test_file.unlink(missing_ok=True)
    return True


def run_test_command(repo_dir: Path, test_command: str):
    print(repo_dir, test_command)
    try:
        parts = test_command.strip().split()
        proc = subprocess.run(
            parts, cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print(proc.stdout)
        return proc.stderr.splitlines()
    except Exception as e:
        print(f"Error: {str(e)}")
        return []

def run_pytest_in_repo(repo_dir: Path):
    cmd = f"pytest -q"
    parts = shlex.split(cmd)

    env = os.environ.copy()
    local_src = str(repo_dir / "src")
    env["PYTHONPATH"] = local_src + (":" + env.get("PYTHONPATH", ""))

    proc = subprocess.run(
        parts, 
        cwd = repo_dir,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        text = True, 
        env=env
    )
    stdout_lines = proc.stdout.splitlines()
    stderr_lines = proc.stdout.splitlines()
    return proc.returncode, stdout_lines, stderr_lines

def extract_failure_location(stdout_lines: list[str]):
    pattern = re.compile(r'file\s+"(.+?\.py)",\s*line\s*(\d+)', re.IGNORECASE)

    for line in stdout_lines:
        match = pattern.search(line)
        if match:
            full_path = match.group(1)
            line_no = int(match.group(2))
            return full_path, line_no
    return None

def install_clone_into_venv(repo_dir: Path) -> bool:
    """
    Inside the cloned repo, run:
      1) pip install -e .
      2) pip install -r requirements.txt
      3) pip install -r requirements_dev.txt

    Returns True if all three install commands succeed, False otherwise.
    """
    try:
        subprocess.run(
            ["python", "-m", "pip", "install", "--upgrade", "pip"],
            cwd=repo_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["python", "-m", "pip", "install", "-e", "."],
            cwd=repo_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        req1 = repo_dir / "requirements.txt"
        if req1.exists():
            subprocess.run(
                ["python", "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=repo_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        req_dev = repo_dir / "requirements_dev.txt"
        if req_dev.exists():
            subprocess.run(
                ["python", "-m", "pip", "install", "-r", "requirements_dev.txt"],
                cwd=repo_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return True
    except subprocess.CalledProcessError as e:
        print(f"↳ Failed to install dependencies in {repo_dir}:\n{e.stderr or e}")
        return False
    

def strip_code_fence(text: str) -> str:
    if text.startswith("```diff"):
        text = text[len("```diff"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
    if text.endswith("```"):
        text = text[:-len("```")].strip()
    return text
    

    
