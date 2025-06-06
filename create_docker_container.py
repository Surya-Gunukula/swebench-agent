import os 
import tempfile
import uuid 
import docker
import subprocess 
from pathlib import Path 
from typing import Tuple
from dataset import *


def _write_patch_to_file(patch_text: str, target_dir: Path, filename: str) -> Path:
    """
    Write the given patch_text to a file named `filename` under target_dir.
    Returns the Path to the file on disk.
    """
    path = target_dir / filename
    path.write_text(patch_text, encoding="utf-8")
    return path

def _docker_exec(
    container: docker.models.containers.Container,
    cmd: str,
    workdir: str = "/workspace",
    timeout: int = 600
) -> Tuple[int, str, str]:
    """
    Run `cmd` inside the given container (attached), returning (exit_code, stdout, stderr).
    We run in bash so that multi‐command strings work. We assume /bin/bash is available.
    """
    full_cmd = f"bash -lc \"{cmd}\""
    # demux=True to get (stdout, stderr) separately as bytes
    result = container.exec_run(full_cmd, workdir=workdir, demux=True, stderr=True, stdout=True, tty=False)
    exit_code = result.exit_code
    if isinstance(result.output, tuple):
        # docker-py older versions return (stdout_bytes, stderr_bytes)
        out_bytes, err_bytes = result.output
    else:
        # some versions return a single bytes object on stdout, stderr is empty
        out_bytes, err_bytes = result.output, b""
    stdout = out_bytes.decode("utf-8", errors="ignore") if out_bytes else ""
    stderr = err_bytes.decode("utf-8", errors="ignore") if err_bytes else ""
    return exit_code, stdout, stderr


def run_patch_and_tests_in_docker(
    repo: str,
    commit: str,
    test_patch: str,
    setup_only: bool,
    python_base_image: str = "python:3.9-slim",
) -> dict:
    """
    1. Launch a Python 3.9‐slim container.
    2. Inside the container:
         • Install git, pytest, and any build tools.
         • Clone the repo at the requested commit.
         • pip install the repository (so that running pytest will see local code).
         • Apply the `test_patch`, then apply the `llm_patch`.
         • Run `pytest -q` and capture results.
    3. Tear down (stop + remove) the container.
    4. Return a dict summarizing what happened:
         {
           "clone_exit": (code, stdout, stderr),
           "install_exit": …,
           "apply_test_exit": …,
           "apply_llm_exit": …,
           "pytest_exit": …,
           "pytest_stdout": "...",
           "pytest_stderr": "..."
         }
    """
    client = docker.from_env()

    # Create a temporary host directory to mount into the container
    with tempfile.TemporaryDirectory(prefix="swebench_workspace_") as host_tmp_dir:
        host_tmp = Path("/Users/suryagunukula/Developer/swebench-agent/container")
        host_tmp.mkdir(parents=True, exist_ok=True) 
        # We will clone into /workspace/<something> inside the container
        container_workspace = "/workspace"
        volume_name = "swebench_volume"
        client.volumes.create(name=volume_name)

        print(f"▶️  Launching container from image: {python_base_image}")
        container = client.containers.run(
            image=python_base_image,
            command="sleep infinity",
            working_dir="/workspace",
            volumes={ str(host_tmp): {"bind": "/workspace", "mode": "rw"},
                    volume_name: {"bind": "/mnt/shared", "mode": "rw"}, },
            detach=True,
            tty=True,  # allocate a tty so bash -lc works properly
        )

        try:
            results = {}

            # 1) Install system dependencies inside the container:
            #    • git (to clone), build-essential (to compile if needed), 
            #    • pytest (to run tests), maybe pip upgrade.
            cmd_install_deps = """
                apt-get update && \
                DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
                  git \
                  build-essential \
                  libssl-dev \
                  python3-dev \
                  python3-pip && \
                pip install --upgrade pip pytest
            """
            print("    • Installing git, pytest, etc. inside container...")
            code, out, err = _docker_exec(container, cmd_install_deps)
            results["install_exit"] = (code, out, err)
            if code != 0:
                print("    ❌ Failed to install dependencies. Aborting.")
                return results

            # 2) Clone the target repository at the requested commit.
            #    We'll clone into /workspace/<safe_name>
            safe_name = repo.replace("/", "_")
            clone_url = f"https://github.com/{repo}.git"
            clone_dir = f"/workspace/{safe_name}"
            cmd_clone = f"git clone {clone_url} {clone_dir} && cd {clone_dir} && git fetch && git checkout {commit}"
            print(f"    • Cloning {repo}@{commit} …")
            code, out, err = _docker_exec(container, cmd_clone)
            results["clone_exit"] = (code, out, err)
            if code != 0:
                print("    ❌ Git clone/checkout failed. Aborting.")
                return results

            # 3) pip install the repository so that pytest can pick up the package 
            cmd_install_repo = f"cd {clone_dir} && pip install 'numpy<2.0' && pip install ."
            print("    • pip install the repository (so pytest can import it)…")
            code, out, err = _docker_exec(container, cmd_install_repo)
            results["install_repo_exit"] = (code, out, err)
            if code != 0:
                print("    ❌ pip install . failed. Aborting.")
                return results
            
            cmd_install_repo = f"cd {clone_dir} && pip install -r requirements.txt && pip install hypothesis"
            print("    • pip install the requirements repository (so pytest can import it)…")
            code, out, err = _docker_exec(container, cmd_install_repo)
            results["install_repo_exit"] = (code, out, err)

            cmd_install_repo = f"cd {clone_dir} && pip install -r requirements-dev.txt"
            print("    • pip install the dev requirements repository (so pytest can import it)…")
            code, out, err = _docker_exec(container, cmd_install_repo)
            results["install_repo_exit"] = (code, out, err)

            if setup_only:
                print("Setup-only mode complete. Skipping patching and testing")
                return results
            


            # 4) Write the `test_patch` and `llm_patch` into files in the host‐mounted workspace.
            #    We write on the host (in host_tmp) so the container can see them under /workspace.
            test_patch_file = _write_patch_to_file(test_patch, host_tmp, "tmp_test.patch")

            # 5) Apply the test‐patch inside the container:
            cmd_apply_test = f"cd {clone_dir} && git apply /workspace/tmp_test.patch"
            print("    • Applying test_patch …")
            code, out, err = _docker_exec(container, cmd_apply_test)
            results["apply_test_exit"] = (code, out, err)
            if code != 0:
                print("    Failed to apply test_patch. Aborting.")
                return results

            """
            # 6) Apply the llm_patch inside the container:
            cmd_apply_llm = f"cd {clone_dir} && git apply /workspace/tmp_llm.patch"
            print("    • Applying llm_patch …")
            code, out, err = _docker_exec(container, cmd_apply_llm)
            results["apply_llm_exit"] = (code, out, err)
            if code != 0:
                print("    Failed to apply llm_patch. Aborting.")
                return results
            """

            # 7) Finally, run pytest inside the repo folder.
            #    We use “pytest -q” for brevity. You can add flags like “--maxfail=1” etc.
            cmd_pytest = f"cd {clone_dir} && pytest -q -m 'not dbt'"
            print("    • Running pytest -q …")
            code, out, err = _docker_exec(container, cmd_pytest)
            results["pytest_exit"]   = code
            results["pytest_stdout"] = out
            results["pytest_stderr"] = err

            return results

        finally:
            if not setup_only:
                # 8) Tear everything down:
                print("▶️  Stopping and removing container …")
                try:
                    container.stop(timeout=5)
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass


if __name__ == "__main__":
    dev_set = load_swe_bench_lite('dev')

    example_repo       = dev_set[10]["repo"]
    example_commit     = dev_set[10]["base_commit"] 
    example_test_patch = dev_set[10]["test_patch"]
    example_llm_patch  = dev_set[10]["test_patch"]
    # Run everything inside Docker:
    results = run_patch_and_tests_in_docker(
        repo=example_repo,
        commit=example_commit,
        test_patch=example_test_patch,
        setup_only=True,
        python_base_image="python:3.9-slim"
    )

    # Print out a summary:
    print("\n===== Docker Test Summary =====")
    for k, v in results.items():
        if isinstance(v, tuple):
            print(f"{k}: exit={v[0]}")
            if v[1].strip():
                print(f"  stdout:\n{v[1]}")
            if v[2].strip():
                print(f"  stderr:\n{v[2]}")
        else:
            print(f"{k}: {v}")
    print("================================")