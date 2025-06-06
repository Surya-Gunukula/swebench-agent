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

from create_docker_container import *

api_key = os.environ.get("OPENAI_API_KEY")

llm = ChatOpenAI(model="gpt-4o", api_key=api_key)

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
                         ),
            HumanMessage(
                content=f"""The following error occurred when running the test suite:
                            \n\n{state['error_file']}\n
                            This file appears to be the source of the issue. Below is the full context that has been received using RAG:
                            \n\n{state['context']}\n
                            Please write a **minimal** and **correct** unified diff (git diff format) that resolves the error.
                            The fix must change only the logic that is **directly responsible** for the failure.
                            Do not comment out failing code or alter test files. Output only the diff.
                            """
            )
        ]
    )
    return {"output": [diff_report]}






graph_builder = StateGraph(State)
graph_builder.add_node("find_file", find_file)
graph_builder.add_node("llm_call", llm_call)

graph_builder.add_edge(START, "find_file")
graph_builder.add_edge("find_file", "llm_call")
graph_builder.add_edge("llm_call", END)

graph_worker = graph_builder.compile()


def test_single_example(datapoint):

    example_repo       = datapoint["repo"]
    example_commit     = datapoint["base_commit"] 
    example_test_patch = datapoint["test_patch"]
    context  = datapoint["text"]

    results = run_patch_and_tests_in_docker(
        repo=example_repo,
        commit=example_commit,
        test_patch=example_test_patch,
        setup_only=False,
        python_base_image="python:3.9-slim"
    )

    print(results["pytest_stdout"])

    state = graph_worker.invoke({"repo_dir": example_repo, "error": results["pytest_stdout"], "context": context})

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

    return state['output'][0].content

if __name__ == '__main__':
    dev_set = load_swe_bench_lite_bm25('dev')
    datapoint = dev_set[5]
    result = test_single_example(datapoint)
    print(result)


    







