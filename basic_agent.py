#!/usr/bin/env/python3

import os 
import subprocess 
import argparse
from pathlib import Path
import shutil

import openai
import utils
from dataset import load_swe_bench_lite

openai.api_key = os.getenv("OPENAI_API_KEY")

def run_agent(problem_statement: str, test_patch: str, code_context: str):
    system_prompt = (
        "You are an expert software engineer. You have the code context below "
        "and a failing test. Produce a minimal unified-diff patch (git diff format) that "
        "fixes the bug. Output only the diff—no commentary."
    )

    user_prompt = (
        f"### Bug Description:\n{problem_statement}\n\n"
        f"### Failing Test (apply to see failure):\n```\n{test_patch}\n```\n\n"
        f"### Code Context (truncated to ~30k chars):\n```\n{code_context}\n```\n\n"
        "### Output (unified diff):\n"
    )

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    return response.choices[0].message.content.strip()

def test_single_example(datapoint):
    example = datapoint

    base_dir = Path("repos")
    base_dir.mkdir(exist_ok=True)

    repo = example["repo"]
    commit = example["base_commit"]
    problem_desc = example["problem_statement"]
    test_patch = example["test_patch"]
    hints_text = example.get("hints_text", None)

    result = {
        "instance_id": example["instance_id"],
        "repo": repo,
        "base_commit": commit,
        "patch_from_model": None,
        "test_exit_code": None,
        "test_stdout": [],
        "test_stderr": [],
        "failure_file": None,
        "failure_line": None,
    }

    try: 
        repo_dir = utils.clone_and_checkout(repo, commit, base_dir)
    except Exception as e:
        print(f"Error: {str(e)}")

    ok_install = utils.install_clone_into_venv(repo_dir)
    print(ok_install)

    ok_patch = utils.apply_test_patch(repo_dir, test_patch)  
    print(ok_patch)

    exit_code, stdout_lines, stderr_lines = utils.run_pytest_in_repo(repo_dir)
    result["test_exit_code"] = exit_code
    result["test_stdout"] = stdout_lines
    result["test_stderr"] = stderr_lines

    print(exit_code, stderr_lines, stdout_lines)

    fail_loc = utils.extract_failure_location(stdout_lines)

    failure_path, failure_line = fail_loc
    result["failure_file"] = failure_path
    result["failure_line"] = failure_line

    code_context = utils.load_relevant_code(repo_dir, failure_path, failure_line, context_radius=50)
    if not code_context:
        print("FAILED TO GET CONTEXT")
    if hints_text:
        code_context = hints_text + "\n\n" + code_context

    try:
        llm_patch = run_agent(problem_desc, test_patch, code_context)
    except Exception as e:
        print(f"Error: {str(e)}")

    """
    try:
        shutil.rmtree(repo_dir)
    except Exception as cleanup_err:
        print(f"Warning: could not remove {repo_dir}: {cleanup_err}")
    """

    return {
        "repo": repo,
        "commit": commit,
        "llm_patch": llm_patch,
        "error": None
    }

if __name__ == '__main__':

    dev_set = load_swe_bench_lite('dev')

    result = test_single_example(dev_set[10])

    print(result["llm_patch"])

    

