#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import multiprocessing as mp
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError


# ====== Customize defaults for the blended dataset layout ======
DEFAULT_SUBDIR = "data/"
DEFAULT_FILE_PREFIX = "S5P_BLND_L2__CH4____"


def get_file_prefixes(start_date: datetime, end_date: datetime,
                      subdir: str = DEFAULT_SUBDIR,
                      file_prefix: str = DEFAULT_FILE_PREFIX):
    """
    Build month prefixes and acceptable file path prefixes for [start_date, end_date).
    """
    months_set = set()
    days_set = set()

    current = start_date
    while current < end_date:
        month_dir = current.strftime("%Y-%m") + "/"
        months_set.add(subdir + month_dir)
        days_set.add(subdir + month_dir + file_prefix + current.strftime("%Y%m%d"))
        current += timedelta(days=1)

    return sorted(months_set), sorted(days_set)


def iter_matching_keys(s3_client, bucket: str, month_prefix: str, day_prefixes: list[str]):
    """
    Yield object keys in `bucket` under `month_prefix` whose key startswith any `day_prefixes`.
    Uses paginator to avoid 1000-key truncation.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=month_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if any(key.startswith(dp) for dp in day_prefixes):
                yield key


def _copy_one(args):
    """
    Worker: copy one S3 object (server-side) if it doesn't exist at destination (optional).
    args = (src_bucket, src_key, dst_bucket, dst_key, dry_run)
    """
    src_bucket, src_key, dst_bucket, dst_key, dry_run = args
    s3 = boto3.client("s3")

    if dry_run:
        print(f"[DRYRUN] copy s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return True

    try:
        # Optional existence check to avoid overwriting:
        # Comment this block out if you want overwrite behavior.
        try:
            s3.head_object(Bucket=dst_bucket, Key=dst_key)
            print(f"[SKIP] exists s3://{dst_bucket}/{dst_key}")
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise

        s3.copy_object(
            Bucket=dst_bucket,
            Key=dst_key,
            CopySource={"Bucket": src_bucket, "Key": src_key},
        )
        print(f"[OK]   s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return True

    except Exception as e:
        print(f"[FAIL] s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key} :: {e}")
        return False


def copy_blended_date_range(start_date: datetime,
                            end_date: datetime,
                            src_bucket: str,
                            dst_bucket: str,
                            dst_prefix: str = "",
                            nproc: int | None = None,
                            dry_run: bool = False):
    """
    Copy blended TROPOMI+GOSAT methane files from src_bucket to dst_bucket for [start_date, end_date).
    Keys are preserved unless dst_prefix is provided.

    Example:
      src_key: data/2019-01/S5P_BLND_L2__CH4____20190101...
      dst_key: <dst_prefix>data/2019-01/S5P_BLND_L2__CH4____20190101...
    """
    s3 = boto3.client("s3")

    month_prefixes, day_prefixes = get_file_prefixes(start_date, end_date)
    all_tasks = []

    for mprefix in month_prefixes:
        # Collect matching keys
        keys = list(iter_matching_keys(s3, src_bucket, mprefix, day_prefixes))
        if not keys:
            # Don't hard-fail; just report.
            print(f"[WARN] No keys found under s3://{src_bucket}/{mprefix} in selected range.")
            continue

        for src_key in keys:
            dst_key = f"{dst_prefix}{src_key}" if dst_prefix else src_key
            all_tasks.append((src_bucket, src_key, dst_bucket, dst_key, dry_run))

    print("=============Copying S3 -> S3 (date-filtered)=============")
    print(f"Range: [{start_date.strftime('%Y%m%d')}, {end_date.strftime('%Y%m%d')})")
    print(f"Source: s3://{src_bucket}/")
    print(f"Dest:   s3://{dst_bucket}/{dst_prefix}")
    print(f"Files matched: {len(all_tasks)}")

    if nproc is None:
        nproc = min(32, (os.cpu_count() or 1))  # sane default

    if len(all_tasks) == 0:
        print("[INFO] Nothing to copy.")
        return

    with mp.Pool(processes=nproc) as pool:
        results = pool.map(_copy_one, all_tasks)

    ok = sum(1 for r in results if r)
    fail = len(results) - ok
    print("==========================================================")
    print(f"Done. Success: {ok}, Failed: {fail}")


if __name__ == "__main__":
    """
    Usage:
      python copy_blended_TROPOMI_s3_to_s3.py 20190101 20190214 <dest-bucket> [--dest-prefix PREFIX] [--src-bucket NAME] [--nproc N] [--dryrun]

    Notes:
      - end date is exclusive: [start, end)
      - default src bucket is blended-tropomi-gosat-methane
    """
    if len(sys.argv) < 4:
        print("Usage: python script.py <start_yyyymmdd> <end_yyyymmdd> <dest-bucket> [--dest-prefix P] [--src-bucket B] [--nproc N] [--dryrun]")
        sys.exit(2)

    start = sys.argv[1]
    end = sys.argv[2]
    dst_bucket = sys.argv[3]

    src_bucket = "blended-tropomi-gosat-methane"
    dst_prefix = ""
    nproc = None
    dry_run = False

    # Simple flag parsing (kept dependency-free)
    i = 4
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--dest-prefix":
            dst_prefix = sys.argv[i + 1]
            i += 2
        elif arg == "--src-bucket":
            src_bucket = sys.argv[i + 1]
            i += 2
        elif arg == "--nproc":
            nproc = int(sys.argv[i + 1])
            i += 2
        elif arg == "--dryrun":
            dry_run = True
            i += 1
        else:
            raise ValueError(f"Unknown argument: {arg}")

    start_date = datetime.strptime(start, "%Y%m%d")
    end_date = datetime.strptime(end, "%Y%m%d")

    copy_blended_date_range(
        start_date=start_date,
        end_date=end_date,
        src_bucket=src_bucket,
        dst_bucket=dst_bucket,
        dst_prefix=dst_prefix,
        nproc=nproc,
        dry_run=dry_run,
    )
