# swebench-agent
python -m swebench.harness.run_evaluation \
  --predictions_path ./predictions.json \
  --dataset_name swe-bench-lite \
  --split dev \
  --max_workers 2 \
  --namespace '' \
  --run_id my_run_001

sb-cli submit swe-bench_lite dev \
    --predictions_path predictions.json \
    --run_id my_run_id