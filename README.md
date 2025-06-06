#Creates local docker containers and runs there
python -m swebench.harness.run_evaluation \
  --predictions_path ./predictions.json \
  --dataset_name swe-bench-lite \
  --split dev \
  --max_workers 2 \
  --namespace '' \
  --run_id my_run_001


python -m swebench.harness.run_evaluation \
  --predictions_path 'gold' \
  --dataset_name swe-bench-lite \
  --split dev \
  --max_workers 2 \
  --namespace '' \
  --run_id my_run_001




#Also doesn't work 
sb-cli submit swe-bench_lite dev \
    --predictions_path predictions.json \
    --run_id my_run_id

Some test cases just don't work: 

#Test cases don't work in general 
https://github.com/swe-bench/SWE-bench/issues/319 (2025)

#pvlib cases won't work on Mac
https://github.com/swe-bench/SWE-bench/issues/274 (2024)

#All SQLFluff test cases seem deprecated
https://github.com/SWE-agent/SWE-agent/issues/707 (2024)

