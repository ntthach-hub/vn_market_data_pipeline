import os

from pipelines.extract import run_extract
from pipelines.transform import run_transform
from pipelines.load import run_load
from pipelines.validate import run_validate


def run_pipeline():
    print("Starting VN Market Data Pipeline..")
    print(f"Target database: {os.getenv('DB_NAME', '(not configured)')}")
    print()

    run_extract()
    print()

    run_transform()
    print()

    run_load()
    print()
    run_validate()
    print()

    print("Pipeline complete")

if __name__ == "__main__":
    run_pipeline()
