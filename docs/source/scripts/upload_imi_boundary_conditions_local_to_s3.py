#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Upload IMI boundary condition files from a LOCAL directory into a destination
S3 bucket, preserving the directory structure relative to a local root.

Destination key rule:
  dst_key = <dest_prefix> + <path of file relative to local_root>

Typical local layout:
  <local_root>/<version>/GEOSChem.BoundaryConditions.YYYYMMDD_0000z.nc4

Typical destination layout:
  s3://<dst_bucket>/<dest_prefix>/<version>/GEOSChem.BoundaryConditions.YYYYMMDD_0000z.nc4

Usage:
  python upload_imi_boundary_conditions_local_to_s3.py \
      <start_yyyymmdd> <end_yyyymmdd> \
      <dst_bucket> <vYYYY-MM> \
      [--local-root DIR] \
      [--src-subdir SUBDIR] \
      [--dest-prefix PREFIX] \
      [--nproc N] \
      [--dryrun] \
      [--overwrite]

Notes:
  - Date range is [start, end) (end exclusive)
  - Files are found by walking <local_root>/<src-subdir>. If --src-subdir is
    omitted it defaults to <vYYYY-MM>, matching the S3 source layout.
  - The S3 key preserves each file's path relative to --local-root, so the
    <version> folder is kept in the key just like the S3 -> S3 script.
  - Destination uploads use your AWS credentials (env vars, ~/.aws, or an
    instance/role profile).
"""

import os
import sys
import mimetypes
import multiprocessing as mp
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError


FILE_PREFIX = "GEOSChem.BoundaryConditions."
FILE_SUFFIX = "_0000z.nc4"

# mimetypes doesn't know NetCDF; add a couple of sensible defaults.
_CONTENT_TYPES = {
    ".nc4": "application/x-netcdf",
    ".nc": "application/x-netcdf",
}


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


def _guess_content_type(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in _CONTENT_TYPES:
        return _CONTENT_TYPES[ext]
    ctype, _ = mimetypes.guess_type(path)
    return ctype


def _dest_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound", "403", "AccessDenied"):
            return False
        raise


def _upload_one(local_path: str,
                dst_bucket: str, dst_key: str,
                dryrun: bool, overwrite: bool) -> str:
    """
    Local -> private S3 upload.
    Returns: copied | skipped | failed | dryrun
    """
    dst_s3 = boto3.client("s3")

    if dryrun:
        print(f"[DRYRUN] {local_path} -> s3://{dst_bucket}/{dst_key}")
        return "dryrun"

    if not overwrite and _dest_exists(dst_s3, dst_bucket, dst_key):
        print(f"[SKIP]   exists s3://{dst_bucket}/{dst_key}")
        return "skipped"

    try:
        extra = {}
        ctype = _guess_content_type(local_path)
        if ctype:
            extra["ContentType"] = ctype

        # upload_file handles multipart/large files automatically
        dst_s3.upload_file(
            Filename=local_path,
            Bucket=dst_bucket,
            Key=dst_key,
            ExtraArgs=extra if extra else None,
        )

        print(f"[OK]     {local_path} -> s3://{dst_bucket}/{dst_key}")
        return "copied"

    except Exception as e:
        print(f"[FAIL]   {local_path} -> s3://{dst_bucket}/{dst_key}: {e}")
        return "failed"


def _iter_matching_files(local_root: str, search_dir: str, expected_names: set):
    """
    Walk search_dir and yield (abs_path, rel_key) for files whose basename
    matches expected_names. rel_key is the path relative to local_root, using
    forward slashes so it is a valid S3 key.
    """
    for root, _dirs, files in os.walk(search_dir):
        for name in files:
            if name in expected_names:
                abs_path = os.path.join(root, name)
                rel = os.path.relpath(abs_path, local_root)
                rel_key = rel.replace(os.sep, "/")
                yield abs_path, rel_key


# ------------------------
# main logic
# ------------------------

def upload_bc_to_s3(start_dt: datetime,
                    end_dt: datetime,
                    dst_bucket: str,
                    version: str,
                    local_root: str = ".",
                    src_subdir: str | None = None,
                    dest_prefix: str = "",
                    nproc: int | None = None,
                    dryrun: bool = False,
                    overwrite: bool = False):
    """
    Upload BC files for [start_dt, end_dt) from a local directory into the
    destination bucket/prefix.
    """

    local_root = os.path.abspath(local_root)

    if src_subdir is None:
        src_subdir = version

    search_dir = os.path.join(local_root, src_subdir) if src_subdir else local_root
    dest_prefix = _normalize_prefix(dest_prefix)

    expected = _expected_filenames(start_dt, end_dt)

    print("=============Upload IMI Boundary Conditions (local → S3)=============")
    print(f"Range:      [{start_dt.strftime('%Y%m%d')}, {end_dt.strftime('%Y%m%d')})")
    print(f"Local root: {local_root}")
    print(f"Search dir: {search_dir}")
    print(f"Dest:       s3://{dst_bucket}/{dest_prefix}")
    print(f"Key rule:   dst_key = <dest_prefix> + <path relative to local_root>")
    print(f"Dryrun:     {dryrun} | Overwrite: {overwrite}")
    print("====================================================================")

    if not os.path.isdir(search_dir):
        print(f"[ERROR] Local directory not found: {search_dir}")
        sys.exit(1)

    matches = sorted(set(_iter_matching_files(local_root, search_dir, expected)))
    print(f"Files matched: {len(matches)}")

    # Report any expected dates that were not found locally
    found_names = {os.path.basename(p) for p, _ in matches}
    missing = sorted(expected - found_names)
    if missing:
        print(f"[WARN] {len(missing)} expected file(s) not found locally, e.g.:")
        for name in missing[:5]:
            print(f"       - {name}")
        if len(missing) > 5:
            print(f"       ... and {len(missing) - 5} more")

    if not matches:
        print("[INFO] Nothing to upload.")
        return

    if nproc is None:
        nproc = min(32, os.cpu_count() or 1)

    tasks = [
        (abs_path, dst_bucket, f"{dest_prefix}{rel_key}", dryrun, overwrite)
        for abs_path, rel_key in matches
    ]

    with mp.Pool(processes=nproc) as pool:
        results = pool.starmap(_upload_one, tasks)

    counts = {k: results.count(k) for k in ("copied", "skipped", "failed", "dryrun")}

    print("====================================================================")
    print(
        f"Done. copied={counts['copied']} "
        f"skipped={counts['skipped']} "
        f"failed={counts['failed']}"
        + (f" dryrun={counts['dryrun']}" if dryrun else "")
    )
    print("====================================================================")


# ------------------------
# CLI
# ------------------------

def _usage_and_exit():
    print(
        "Usage:\n"
        "  python upload_imi_boundary_conditions_local_to_s3.py "
        "<start_yyyymmdd> <end_yyyymmdd> <dst_bucket> <vYYYY-MM>\n"
        "      [--local-root DIR] [--src-subdir SUBDIR] [--dest-prefix PREFIX]\n"
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

    local_root = "."
    src_subdir = None
    dest_prefix = ""
    nproc = None
    dryrun = False
    overwrite = False

    argv = sys.argv[5:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--local-root":
            local_root = argv[i + 1]; i += 2
        elif a == "--src-subdir":
            src_subdir = argv[i + 1]; i += 2
        elif a == "--dest-prefix":
            dest_prefix = argv[i + 1]; i += 2
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

    upload_bc_to_s3(
        start_dt=start_dt,
        end_dt=end_dt,
        dst_bucket=dst_bucket,
        version=version,
        local_root=local_root,
        src_subdir=src_subdir,
        dest_prefix=dest_prefix,
        nproc=nproc,
        dryrun=dryrun,
        overwrite=overwrite,
    )


if __name__ == "__main__":
    main()
