from langgraph_agent import *
from rag_agent import *
import json
from utils import *


"""
Runs agent and creates prediction.json for evaluation
"""
def eval():
    dev_set = load_swe_bench_lite_bm25('dev')

    final_results = []


    for i, datapoint in enumerate(dev_set):
        if i != 5 and i != 6:
            result = test_single_example_rag(datapoint)
        else:
            result = test_single_example(datapoint)

        cleaned_result = strip_code_fence(result)

        final_results.append({
            "instance_id": datapoint["instance_id"],
            "model_name_or_path": "gpt-4o",
            "model_patch": cleaned_result
        })

    output_path = "predictions.json"
    with open(output_path, "w") as f:
        json.dump(final_results, f, indent=2)    


if __name__ == '__main__':
    eval()
    



