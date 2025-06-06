from langgraph_agent import *
import json

def eval():
    dev_set = load_swe_bench_lite('dev')

    final_results = []


    for i, datapoint in enumerate(dev_set):
        if i != 5 and i != 6:
            continue
        result = test_single_example(datapoint)

        final_results.append({
            "instance_id": datapoint["instance_id"],
            "model_name_or_path": "gpt-4o",
            "model_patch": result
        })

    output_path = "predictions2.json"
    with open(output_path, "w") as f:
        json.dump(final_results, f, indent=2)    


if __name__ == '__main__':
    eval()
    



