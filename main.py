from pipelines.extract import run_extract
from pipelines.transform import run_transform
from pipelines.load import run_load

def run_pipeline():
    print("Starting VN Market Data Pipeline..")
    print()

    run_extract()
    print()

    run_transform()
    print()

    run_load()
    print()

    print("Pipeline complete")

if __name__ == "__main__":
    run_pipeline()