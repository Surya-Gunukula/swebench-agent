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

class State(TypedDict):
    repo_dir: str
    problem_statement: str
    context: str 
    output: str
    error: str
    problem_statement: str


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
                content=f"""This is the problem statement:\n\n
                            {state['problem_statement']}\n
                            Below is the full context that has been received using RAG:
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
graph_builder.add_node("llm_call", llm_call)

graph_builder.add_edge(START, "llm_call")
graph_builder.add_edge("llm_call", END)

graph_worker = graph_builder.compile()


def test_single_example_rag(datapoint):

    example_repo       = datapoint["repo"]
    example_commit     = datapoint["base_commit"] 
    example_test_patch = datapoint["test_patch"]
    problem_statement = datapoint["problem_statement"]
    context  = datapoint["text"]

    context = context[:30000]

    state = graph_worker.invoke({"repo_dir": example_repo, "context": context, "problem_statement": problem_statement})

    return state['output'][0].content

if __name__ == '__main__':
    dev_set = load_swe_bench_lite_bm25('dev')
    datapoint = dev_set[5]
    result = test_single_example_rag(datapoint)
    print(result)


    







