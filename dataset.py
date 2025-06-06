from datasets import load_dataset

def load_swe_bench_lite(split: str):

    dataset = load_dataset("princeton-nlp/SWE-bench_Lite")
    try:
        subset = dataset[split]
        print(f"Loaded {len(subset)} examples")
    except Exception as e: 
        print(f"Failed to load dataset: {str(e)}")
        return
    
    return subset

def load_swe_bench_lite_bm25(split: str):
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite_bm25_27k")
    try:
        subset = dataset[split]
        print(f"Loaded {len(subset)} examples")
    except Exception as e:
        print(f"Failed to load dataset: {str(e)}")
        return
    

if __name__ == '__main__':
    dev_set = load_swe_bench_lite('dev')

    test_failure = load_swe_bench_lite('abc')   

    dev_set2 = load_swe_bench_lite_bm25('dev') 

