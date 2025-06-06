# SWE-Bench Agent 

An agent that is run and evaluated on the swe-bench_Lite dataset

## Features

- Docker-based patch testing + file-retrieval 
- Langgraph based agent system 
- Gpt-4o Patch Generation


## Installation

``` bash
git clone ...
cd swebench-agent
pip install uv 
uv init 
uv sync 
```

## Run Inference with Agents 

1. Make sure you have Docker Desktop installed and running 
2. In eval.py, you can switch between the basic_agent, langgraph_agent, and rag_agent
3. Note if you are Linux delete --namespace

``` bash

uv run eval.py
#creates predictions.json

python -m swebench.harness.run_evaluation \
  --predictions_path ./predictions.json \
  --dataset_name swe-bench-lite \
  --split dev \
  --max_workers 2 \
  --namespace '' \
  --run_id my_run_001

```

## Results 

The langgraph_agent is able to achieve a patch rate of 0-2 out of the 10/23 working test cases, which is a 0-20% effective patch rate. 
In the SWE-Bench Paper, gpt-4o was able to achieve a 2.67% effective patch rate. 

## Problems 

Many of the SWE-Bench_Lite test cases are either deprecated or only work on Linux machines. 

Doesn't work 
sb-cli submit swe-bench_lite dev \
    --predictions_path predictions.json \
    --run_id my_run_id

Some test cases just don't work: 

Test cases don't work in general 
https://github.com/swe-bench/SWE-bench/issues/319 (2025)

pvlib cases won't work on Mac
https://github.com/swe-bench/SWE-bench/issues/274 (2024)

All SQLFluff test cases seem deprecated
https://github.com/SWE-agent/SWE-agent/issues/707 (2024)

