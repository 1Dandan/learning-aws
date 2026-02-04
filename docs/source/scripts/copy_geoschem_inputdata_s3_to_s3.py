#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mirror GEOS-Chem ExtData referenced in a dry-run log from s3://gcgrid into
a destination S3 bucket/prefix.

Default behavior:
- Copy BOTH "found" (Opening/Reading) and "missing" (REQUIRED FILE NOT FOUND)
- Skip objects that already exist at destination (sync-like)

Source bucket access: unsigned (public).
Destination uploads: signed (your AWS credentials/role).

Usage:
  python mirror_extdata_from_log.py <dryrun_log> \
    --dest-bucket <bucket> \
    [--dest-prefix ExtData/] \
    [--only-missing | --include-found] \
    [--dryrun] [--overwrite]
"""

import os
import sys
import re
import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError


SRC_BUCKET = "gcgrid"
DEFAULT_DEST_PREFIX = "ExtData/"  # recommended


def extract_paths_from_log(dryrun_log: str):
    """
    Parse dry-run log and return (found_paths, missing_paths).
    We normalize CHEM_INPUTS// to CHEM_INPUTS/.
    """
    found = set()
    missing = set()

    with open(dryrun_log, "r", encoding="utf-8") as f:
        for line in f:
            line = line.replace("CHEM_INPUTS//", "CHEM_INPUTS/")
            up = line.upper()

            if ": OPENING" in up or ": READING" in up:
                # last token is the path
                found.add(line.split()[-1])

            elif "REQUIRED FILE NOT FOUND" in up or "FILE NOT FOUND" in up:
                missing.add(line.split()[-1])

    return sorted(found), sorted(missing)


def extdata_rel_key_from_path(path: str) -> str | None:
    """
    Extract key relative to ExtData/ from an absolute path.

    Example:
      /.../ExtData/HEMCO/CH4/v2024-01/foo.nc
    returns:
      HEMCO/CH4/v2024-01/foo.nc
    """
    m = re.search(r"ExtData/(.+)", path)
    return m.group(1) if m else None


def dest_key(dest_prefix: str, ext_rel_key: str) -> str:
    dp = dest_prefix.strip("/")
    return f"{dp}/{ext_rel_key}" if dp else ext_rel_key


def dest_exists(dst_s3, bucket: str, key: str) -> bool:
    try:
        dst_s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        if code in ("403", "AccessDenied"):
            # can't head; treat as missing so we attempt upload
            return False
        raise


def copy_streaming(src_s3_unsigned, dst_s3_signed,
                   src_bucket: str, src_key: str,
                   dst_bucket: str, dst_key: str,
                   dryrun: bool, overwrite: bool):
    """
    Robust S3->S3 copy:
    - unsigned get_object() from public src
    - upload_fileobj() to dest
    """
    if dryrun:
        print(f"[DRYRUN] s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return "dryrun"

    if not overwrite and dest_exists(dst_s3_signed, dst_bucket, dst_key):
        print(f"[SKIP]   exists s3://{dst_bucket}/{dst_key}")
        return "skipped"

    try:
        obj = src_s3_unsigned.get_object(Bucket=src_bucket, Key=src_key)
        body = obj["Body"]

        extra = {}
        if obj.get("ContentType"):
            extra["ContentType"] = obj["ContentType"]

        dst_s3_signed.upload_fileobj(
            Fileobj=body,
            Bucket=dst_bucket,
            Key=dst_key,
            ExtraArgs=extra if extra else None,
        )
        print(f"[OK]     s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}")
        return "copied"

    except ClientError as e:
        print(f"[FAIL]   s3://{src_bucket}/{src_key} -> s3://{dst_bucket}/{dst_key}: {e}")
        return "failed"


def mirror_from_log(dryrun_log: str,
                    dest_bucket: str,
                    dest_prefix: str,
                    include_found: bool,
                    dryrun: bool,
                    overwrite: bool):
    found_paths, missing_paths = extract_paths_from_log(dryrun_log)

    # Choose which sets to mirror
    if include_found:
        candidate_paths = found_paths + missing_paths
    else:
        candidate_paths = missing_paths

    # Extract ExtData keys only
    ext_keys = []
    for p in candidate_paths:
        k = extdata_rel_key_from_path(p)
        if k:
            ext_keys.append(k)

    # Deduplicate keys
    ext_keys = sorted(set(ext_keys))

    print("=============Mirror ExtData referenced by dry-run log=============")
    print(f"Log:        {dryrun_log}")
    print(f"Source:     s3://{SRC_BUCKET}/")
    print(f"Dest:       s3://{dest_bucket}/{dest_prefix.strip('/')}/" if dest_prefix else f"Dest: s3://{dest_bucket}/")
    print(f"Mode:       {'found+missing' if include_found else 'missing-only'}")
    print(f"Objects:    {len(ext_keys)}")
    print(f"Dryrun:     {dryrun} | Overwrite: {overwrite}")
    print("===================================================================")

    src_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    dst_s3 = boto3.client("s3")

    substitutions = {
        "IPMN": "PMN",
        "NPMN": "PMN",
        "RIPA": "RIP",
        "RIPB": "RIP",
        "RIPD": "RIP",
    }

    counts = {"copied": 0, "skipped": 0, "failed": 0, "dryrun": 0}

    for ext_rel in ext_keys:
        src_key = ext_rel
        dst_key = dest_key(dest_prefix, ext_rel)

        filename = os.path.basename(src_key)

        # Preserve your special substitution behavior:
        # Fetch corrected source name, but store using original expected name.
        did_sub = False
        for wrong, correct in substitutions.items():
            if wrong in filename:
                corrected_src_key = src_key.replace(wrong, correct)
                status = copy_streaming(
                    src_s3, dst_s3,
                    SRC_BUCKET, corrected_src_key,
                    dest_bucket, dst_key,
                    dryrun=dryrun,
                    overwrite=overwrite,
                )
                counts[status] += 1
                did_sub = True
                break

        if did_sub:
            continue

        status = copy_streaming(
            src_s3, dst_s3,
            SRC_BUCKET, src_key,
            dest_bucket, dst_key,
            dryrun=dryrun,
            overwrite=overwrite,
        )
        counts[status] += 1

    print("===================================================================")
    print(f"Done. copied={counts['copied']} skipped={counts['skipped']} failed={counts['failed']}" +
          (f" dryrun={counts['dryrun']}" if dryrun else ""))
    print("===================================================================")


def parse_args():
    if len(sys.argv) < 2:
        raise ValueError("Usage: python mirror_extdata_from_log.py <dryrun_log> --dest-bucket <bucket> [--dest-prefix P] [--only-missing] [--dryrun] [--overwrite]")

    dryrun_log = None
    dest_bucket = None
    dest_prefix = DEFAULT_DEST_PREFIX
    include_found = True
    dryrun = False
    overwrite = False

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]

        if dryrun_log is None and not a.startswith("-"):
            dryrun_log = a
            i += 1
            continue

        if a == "--dest-bucket":
            dest_bucket = argv[i + 1]
            i += 2
        elif a == "--dest-prefix":
            dest_prefix = argv[i + 1]
            i += 2
        elif a == "--only-missing":
            include_found = False
            i += 1
        elif a == "--include-found":
            include_found = True
            i += 1
        elif a == "--dryrun":
            dryrun = True
            i += 1
        elif a == "--overwrite":
            overwrite = True
            i += 1
        else:
            raise ValueError(f"Unknown argument: {a}")

    if dryrun_log is None:
        raise ValueError("You must provide a dryrun log file as the first argument.")
    if dest_bucket is None:
        raise ValueError("Missing required argument: --dest-bucket")

    return dryrun_log, dest_bucket, dest_prefix, include_found, dryrun, overwrite


def main():
    dryrun_log, dest_bucket, dest_prefix, include_found, dryrun, overwrite = parse_args()
    mirror_from_log(
        dryrun_log=dryrun_log,
        dest_bucket=dest_bucket,
        dest_prefix=dest_prefix,
        include_found=include_found,
        dryrun=dryrun,
        overwrite=overwrite,
    )


if __name__ == "__main__":
    main()
