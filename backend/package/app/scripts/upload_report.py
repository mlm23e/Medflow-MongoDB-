import asyncio

import boto3

from app.database import client, database, initialize_database, next_id

BUCKET_NAME = "medflow-reports-mm1234"
LOCAL_FILE_PATH = "app/scripts/sample_report.txt"
S3_KEY = "reports/FJ1-3420.txt"


def upload_to_s3() -> str:
    s3_client = boto3.client("s3")
    s3_client.upload_file(LOCAL_FILE_PATH, BUCKET_NAME, S3_KEY)
    return f"s3://{BUCKET_NAME}/{S3_KEY}"


async def record_report(file_url: str) -> None:
    report = {
        "id": await next_id(database, "reports"),
        "work_order_id": 1,
        "file_url": file_url,
        "notes": "Uploaded via upload_report.py",
    }
    await database.reports.insert_one(report)
    print(f"Created report with id={report['id']}, file_url={report['file_url']}")


async def main() -> None:
    await initialize_database()
    file_url = upload_to_s3()
    print(f"Uploaded to {file_url}")
    await record_report(file_url)


async def run() -> None:
    try:
        await main()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())