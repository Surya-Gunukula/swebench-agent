import os 
import tempfile
import uuid 
import docker
import subprocess 
from pathlib import Path 
from typing import Tuple
from dataset import *


"""
Writes the test patch into the docker container so we can run it and find the error
"""
def _write_patch_to_file(patch_text: str, target_dir: Path, filename: str) -> Path:
    path = target_dir / filename
    path.write_text(patch_text, encoding="utf-8")
    return path

"""
Creates the container
"""
def _docker_exec(
    container: docker.models.containers.Container,
    cmd: str,
    workdir: str = "/workspace",
    timeout: int = 600
) -> Tuple[int, str, str]:
    
    full_cmd = f"bash -lc \"{cmd}\""

    result = container.exec_run(full_cmd, workdir=workdir, demux=True, stderr=True, stdout=True, tty=False)
    exit_code = result.exit_code
    if isinstance(result.output, tuple):
        out_bytes, err_bytes = result.output
    else:
        out_bytes, err_bytes = result.output, b""
    stdout = out_bytes.decode("utf-8", errors="ignore") if out_bytes else ""
    stderr = err_bytes.decode("utf-8", errors="ignore") if err_bytes else ""
    return exit_code, stdout, stderr


"""
Creates the docker container in the mounted at ./container. Installs all dependencies and runs test path + test suite. Records stderr output to find problem files.

Two modes: setup_only = True/False -> Whether this container persists. Was thinking of allowing iterative changes to docker container. False for now. 
"""
def run_patch_and_tests_in_docker(
    repo: str,
    commit: str,
    test_patch: str,
    setup_only: bool,
    python_base_image: str = "python:3.9-slim",
) -> dict:
    
    client = docker.from_env()

    with tempfile.TemporaryDirectory(prefix="swebench_workspace_") as host_tmp_dir:
        host_tmp = Path("/Users/suryagunukula/Developer/swebench-agent/container")
        host_tmp.mkdir(parents=True, exist_ok=True) 

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
            tty=True,  
        )

        try:
            results = {}

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
                print("Failed to install dependencies. Aborting.")
                return results


            safe_name = repo.replace("/", "_")
            clone_url = f"https://github.com/{repo}.git"
            clone_dir = f"/workspace/{safe_name}"
            cmd_clone = f"git clone {clone_url} {clone_dir} && cd {clone_dir} && git fetch && git checkout {commit}"
            print(f"    • Cloning {repo}@{commit} …")
            code, out, err = _docker_exec(container, cmd_clone)
            results["clone_exit"] = (code, out, err)
            if code != 0:
                print("Git clone/checkout failed. Aborting.")
                return results

            # 3) pip install the repository so that pytest can pick up the package 
            cmd_install_repo = f"cd {clone_dir} && pip install simplejson pytz python-dateutil && pip install ."
            print("    • pip install the repository (so pytest can import it)…")
            code, out, err = _docker_exec(container, cmd_install_repo)
            results["install_repo_exit"] = (code, out, err)
            if code != 0:
                print("pip install . failed. Aborting.")
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
            


            test_patch_file = _write_patch_to_file(test_patch, host_tmp, "tmp_test.patch")

            cmd_apply_test = f"cd {clone_dir} && git apply /workspace/tmp_test.patch"
            print("Applying test_patch …")
            code, out, err = _docker_exec(container, cmd_apply_test)
            results["apply_test_exit"] = (code, out, err)
            if code != 0:
                print("Failed to apply test_patch. Aborting.")
                return results

            cmd_pytest = f"cd {clone_dir} && pytest -q -m 'not dbt'"
            print("    • Running pytest -q …")
            code, out, err = _docker_exec(container, cmd_pytest)
            results["pytest_exit"]   = code
            results["pytest_stdout"] = out
            results["pytest_stderr"] = err

            return results

        finally:
            if not setup_only:

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

    example_repo       = dev_set[6]["repo"]
    example_commit     = dev_set[6]["base_commit"] 
    example_test_patch = dev_set[6]["test_patch"]
    example_llm_patch  = dev_set[6]["test_patch"]

    results = run_patch_and_tests_in_docker(
        repo=example_repo,
        commit=example_commit,
        test_patch=example_test_patch,
        setup_only=False,
        python_base_image="python:3.9-slim"
    )

