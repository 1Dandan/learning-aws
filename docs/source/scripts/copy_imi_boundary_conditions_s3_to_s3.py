#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mirror IMI boundary condition files from a public S3 bucket into a destination
S3 bucket, inheriting the original S3 key structure.

Destination key rule:
  dst_key = <dest_prefix> + <src_key>

Typical source layout:
  s3://imi-boundary-conditions/<version>/GEOSChem.BoundaryConditions.YYYYMMDD_0000z.nc4

Typical destination layout:
  s3://<dst_bucket>/<dest_prefix>/<version>/GEOSChem.BoundaryConditions.YYYYMMDD_0000z.nc4

Usage:
  python copy_imi_boundary_conditions_s3_to_s3.py \
      <start_yyyymmdd> <end_yyyymmdd> \
      <dst_bucket> <vYYYY-MM> \
      [--dest-prefix PREFIX] \
      [--src-bucket imi-boundary-conditions] \
      [--src-prefix PREFIX] \
      [--nproc N] \
      [--dryrun] \
      [--overwrite]

Notes:
  - Date range is [start, end) (end exclusive)
  - Source bucket is accessed unsigned (public)
  - Destination uploads use your AWS credentials
"""

import os
import sys
import multiprocessing as mp
from datetime import datetime, timedelta

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError


DEFAULT_SRC_BUCKET = "imi-boundary-conditions"
FILE_PREFIX = "GEOSChem.BoundaryConditions."
FILE_SUFFIX = "_0000z.nc4"


# ------------------------
# helpers
# ------------------------

def _normalize_prefix(p: str) -> str:
    if not p:
        return ""
    return p if p.endswith("/") else p + "/"


def _iter_dates(start_dt: datetime, end_dt: datetime):
    cur = start_dt
    while cur < end_dt:
        yield cur
        cur += timedelta(days=1)


def _expected_filenames(start_dt: datetime, end_dt: datetime) -> set:
    return {
        f"{FILE_PREFIX}{d.strftime('%Y%m%d')}{FILE_SUFFIX}"
        for d in _iter_dates(start_dt, end_dt)
    }


def _dest_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound", "403", "AccessDenied"):
            return False
        raise


def _copy_streaming(src_bucket: str, src_key: str,
                    dst_bucket: str, dst_key: str,
                    dryrun: bool, overwrite: bool) -> str:
    """
    Public -> private S3 copy via streaming.
    Returns: copied | skipped | failed | dryrun
    """
    src_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    dst_s3 = boto3.client("s3")

    if dryrun:
        print(f"[DRYRUN] s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return "dryrun"

    if not overwrite and _dest_exists(dst_s3, dst_bucket, dst_key):
        print(f"[SKIP]   exists s3://{dst_bucket}/{dst_key}")
        return "skipped"

    try:
        obj = src_s3.get_object(Bucket=src_bucket, Key=src_key)
        body = obj["Body"]

        extra = {}
        if obj.get("ContentType"):
            extra["ContentType"] = obj["ContentType"]

        dst_s3.upload_fileobj(
            Fileobj=body,
            Bucket=dst_bucket,
            Key=dst_key,
            ExtraArgs=extra if extra else None,
        )

        print(f"[OK]     s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return "copied"

    except Exception as e:
        print(f"[FAIL]   s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}: {e}")
        return "failed"


def _iter_matching_keys(src_bucket: str, src_prefix: str, expected_names: set):
    """
    Yield source keys under src_prefix whose basename matches expected_names.
    """
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=src_bucket, Prefix=src_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if os.path.basename(key) in expected_names:
                yield key


# ------------------------
# main logic
# ------------------------

def mirror_bc_from_s3(start_dt: datetime,
                      end_dt: datetime,
                      dst_bucket: str,
                      version: str,
                      dest_prefix: str = "",
                      src_bucket: str = DEFAULT_SRC_BUCKET,
                      src_prefix: str | None = None,
                      nproc: int | None = None,
                      dryrun: bool = False,
                      overwrite: bool = False):
    """
    Mirror BC files for [start_dt, end_dt) into destination bucket/prefix.
    """

    if src_prefix is None:
        src_prefix = _normalize_prefix(version)
    else:
        src_prefix = _normalize_prefix(src_prefix)

    dest_prefix = _normalize_prefix(dest_prefix)

    expected = _expected_filenames(start_dt, end_dt)

    print("=============Mirror IMI Boundary Conditions (S3 → S3)=============")
    print(f"Range:      [{start_dt.strftime('%Y%m%d')}, {end_dt.strftime('%Y%m%d')})")
    print(f"Source:     s3://{src_bucket}/{src_prefix}")
    print(f"Dest:       s3://{dst_bucket}/{dest_prefix}")
    print(f"Key rule:   dst_key = <dest_prefix> + <src_key>")
    print(f"Dryrun:     {dryrun} | Overwrite: {overwrite}")
    print("===================================================================")

    keys = sorted(set(_iter_matching_keys(src_bucket, src_prefix, expected)))
    print(f"Objects matched: {len(keys)}")

    if not keys:
        print("[INFO] Nothing to copy.")
        return

    if nproc is None:
        nproc = min(32, os.cpu_count() or 1)

    tasks = [
        (src_bucket, k, dst_bucket, f"{dest_prefix}{k}", dryrun, overwrite)
        for k in keys
    ]

    with mp.Pool(processes=nproc) as pool:
        results = pool.starmap(_copy_streaming, tasks)

    counts = {k: results.count(k) for k in ("copied", "skipped", "failed", "dryrun")}

    print("===================================================================")
    print(
        f"Done. copied={counts['copied']} "
        f"skipped={counts['skipped']} "
        f"failed={counts['failed']}"
        + (f" dryrun={counts['dryrun']}" if dryrun else "")
    )
    print("===================================================================")


# ------------------------
# CLI
# ------------------------

def _usage_and_exit():
    print(
        "Usage:\n"
        "  python copy_imi_boundary_conditions_s3_to_s3.py "
        "<start_yyyymmdd> <end_yyyymmdd> <dst_bucket> <vYYYY-MM>\n"
        "      [--dest-prefix PREFIX] [--src-bucket B] [--src-prefix P]\n"
        "      [--nproc N] [--dryrun] [--overwrite]\n"
    )
    sys.exit(2)


def main():
    if len(sys.argv) < 5:
        _usage_and_exit()

    start = sys.argv[1]
    end = sys.argv[2]
    dst_bucket = sys.argv[3]
    version = sys.argv[4]

    dest_prefix = ""
    src_bucket = DEFAULT_SRC_BUCKET
    src_prefix = None
    nproc = None
    dryrun = False
    overwrite = False

    argv = sys.argv[5:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dest-prefix":
            dest_prefix = argv[i + 1]; i += 2
        elif a == "--src-bucket":
            src_bucket = argv[i + 1]; i += 2
        elif a == "--src-prefix":
            src_prefix = argv[i + 1]; i += 2
        elif a == "--nproc":
            nproc = int(argv[i + 1]); i += 2
        elif a == "--dryrun":
            dryrun = True; i += 1
        elif a == "--overwrite":
            overwrite = True; i += 1
        else:
            raise ValueError(f"Unknown argument: {a}")

    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")

    mirror_bc_from_s3(
        start_dt=start_dt,
        end_dt=end_dt,
        dst_bucket=dst_bucket,
        version=version,
        dest_prefix=dest_prefix,
        src_bucket=src_bucket,
        src_prefix=src_prefix,
        nproc=nproc,
        dryrun=dryrun,
        overwrite=overwrite,
    )


if __name__ == "__main__":
    main()
