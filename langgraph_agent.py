from typing_extensions import Literal, TypedDict
from typing import Annotated, List
import operator
from pydantic import BaseModel, Field
import os 
import shutil
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import Send
from pathlib import Path
import time

from create_docker_container import *

api_key = os.environ.get("OPENAI_API_KEY")

llm = ChatOpenAI(model="gpt-4o", api_key=api_key, temperature=0.8)

"""
High-level notes (for personal use)
1. Load datapoint
2. Run patch and get stdout
3. Use stdout and file structure -> LLM -> what file to read on 
4. Read entire file + stdout to get diff
5. Optional: Add a like evaluator agent
"""    

class FindFile(BaseModel):
    file_name: str = Field(
        description = "Name of the source file, not the TEST file, that is causing the error"
    )
    file_line: str = Field(
        description = "The line of code, written, you believe is causing the error in the file"
    )
    error: str = Field(
        description = "An explanation of the error"
    )

class State(TypedDict):
    repo_dir: str
    problem_statement: str
    context: str 
    output: str
    error: str
    error_file: FindFile


file_model = llm.with_structured_output(FindFile)

def find_file(state: State):
    file = file_model.invoke(
        [
            SystemMessage(
                content="You are an expert software engineer reviewing a test failure."
                        " Your task is to locate the actual **source code file** (not a test file) "
                        "that is responsible for the failure. The error message may come from a test file, "
                        "but your goal is to trace the root cause to the source code being tested. "
                        "Output the name of the source file (e.g., something in `src/`), the exact line you suspect "
                        "is causing the issue, and a clear human-readable explanation of the error."
                        " Do not choose files named like `test_*.py` or located in `tests/`."
            ),
            HumanMessage(
                content=f"Here is the error: {state['error']}"
            )
        ]
    )

    return {"error_file": file}

def load_file(state:State):
    file_to_load = Path(state['error_file'].file_name).name
    full_repo_name = state['repo_dir']
    repo_name = full_repo_name.split("/")[1]

    safe_name = full_repo_name.replace("/", "_")

    file_path = Path(f"./container/{safe_name}/src/{repo_name}/{file_to_load}")
    print(safe_name , "+", file_to_load)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {"context": content}

def llm_call(state: State):
    diff_report = llm.invoke(
        [
            SystemMessage(content="You are an expert Python developer fixing a bug in a project. "
                                    "You are given a source file and an error that occurred during test execution. "
                                    "Your task is to write a minimal and correct **unified diff (git diff format)** "
                                    "that fixes the root cause of the issue—not the test file itself. "
                                    "Do not silence or bypass the error unless it leads to a correct fix."
                                    " You must keep all other behavior unchanged. "
                                    "Focus on modifying only what’s needed to resolve the specific bug." \
                                    "You must fix the root cause of the exception. Do not patch unrelated code. The traceback says the failure occurred at:"
                         ),
            HumanMessage(
                content=f"""The following error occurred when running the test suite:
                            \n\n{state['error_file']}\n
                            This file appears to be the source of the issue. Below is its full content:
                            \n\n{state['context']}\n
                            Please write a **minimal** and **correct** unified diff (git diff format) that resolves the error.
                            The fix must change only the logic that is **directly responsible** for the failure.
                            Do not comment out failing code or alter test files. Output only the diff.
                            """
            )
        ]
    )
    return {"output": [diff_report]}

def llm_call(state: State):
    messages = [
            SystemMessage(content="You are an expert Python developer fixing a bug in a project. "
                                    "You are given a source file and an error that occurred during test execution. "
                                    "Your task is to write a minimal and correct **unified diff (git diff format)** "
                                    "that fixes the root cause of the issue—not the test file itself. "
                                    "Do not silence or bypass the error unless it leads to a correct fix."
                                    " You must keep all other behavior unchanged. "
                                    "Focus on modifying only what’s needed to resolve the specific bug." \
                                    "You must fix the root cause of the exception. Do not patch unrelated code. The traceback says the failure occurred at:"
                         ),
            HumanMessage(
                content=f"""The following error occurred when running the test suite:
                            \n\n{state['error_file']}\n
                            This file appears to be the source of the issue. Below is its full content:
                            \n\n{state['context']}\n
                            Please write a **minimal** and **correct** unified diff (git diff format) that resolves the error.
                            The fix must change only the logic that is **directly responsible** for the failure.
                            Do not comment out failing code or alter test files. Output only the diff.
                            """
            )
    ]
    output1 = llm.invoke(messages).content
    time.sleep(10)
    output2 = llm.invoke(messages).content
    time.sleep(10)
    output3 = llm.invoke(messages).content
    time.sleep(10)

    return {
        "output": [
            output1, 
            output2, 
            output3
        ]
    }

class ChosenDiff(BaseModel):
    best_diff: str = Field(
        description="The best unified diff (git diff format) among the given options that most directly and correctly resolves the issue"
    )

evaluate_model = llm.with_structured_output(ChosenDiff)

def ensemble_select_best_diff(state: State):
    diffs = state["output"]  

    evaluation = evaluate_model.invoke([
        SystemMessage(
            content="You are a senior software engineer. Your job is to evaluate 3 different proposed patches "
                    "(in unified git diff format) and select the best one. "
                    "The best patch is the one that: (1) directly fixes the root cause of the error, "
                    "(2) avoids silencing the error, and (3) changes as little code as necessary."
        ),
        HumanMessage(
            content=f"""The original error was:
                    {state['error_file']}

                    The context file is:
                    {state['context']}

                    Here are three proposed diffs:

                    [DIFF 1]
                    {diffs[0]}

                    [DIFF 2]
                    {diffs[1]}

                    [DIFF 3]
                    {diffs[2]}

                    Which one is the best and why? Return only the best diff.
                    """
        )
    ])

    return {"output": evaluation.best_diff}
    









graph_builder = StateGraph(State)
graph_builder.add_node("find_file", find_file)
graph_builder.add_node("load_file", load_file)
graph_builder.add_node("llm_call", llm_call)
graph_builder.add_node("ensemble_select_best_diff", ensemble_select_best_diff)

graph_builder.add_edge(START, "find_file")
graph_builder.add_edge("find_file", "load_file")
graph_builder.add_edge("load_file", "llm_call")
graph_builder.add_edge("llm_call", "ensemble_select_best_diff")
graph_builder.add_edge("ensemble_select_best_diff", END)

graph_worker = graph_builder.compile()


def test_single_example(datapoint):

    example_repo       = datapoint["repo"]
    example_commit     = datapoint["base_commit"] 
    example_test_patch = datapoint["test_patch"]
    example_llm_patch  = datapoint["test_patch"]

    results = run_patch_and_tests_in_docker(
        repo=example_repo,
        commit=example_commit,
        test_patch=example_test_patch,
        setup_only=False,
        python_base_image="python:3.9-slim"
    )

    print(results["pytest_stdout"])

    state = graph_worker.invoke({"repo_dir": example_repo, "error": results["pytest_stdout"]})

    print(state['error_file'])

    container_path = "./container"
    if os.path.exists(container_path):
        for filename in os.listdir(container_path):
            file_path = os.path.join(container_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)  # remove file or link
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)  # remove directory
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')

    return state['output']

if __name__ == '__main__':
    dev_set = load_swe_bench_lite('dev')
    datapoint = dev_set[5]
    result = test_single_example(datapoint)
    print(result)


    







