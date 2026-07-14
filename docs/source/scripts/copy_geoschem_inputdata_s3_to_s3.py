#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mirror GEOS-Chem ExtData referenced by a dry-run log from a source S3
bucket (default: public s3://gcgrid) into a destination S3 bucket/prefix.

Performance features
--------------------
1. Copies multiple objects concurrently.
2. In --mode auto, tries S3 server-side copy first.
3. If server-side copy is not permitted, automatically falls back to
   unsigned GET + signed streaming upload.
4. Skips existing destination objects unless --overwrite is specified.
5. Uses connection pooling, retries, and managed multipart transfers.

Examples
--------
Dry run:
    python copy_geoschem_inputdata_s3_to_s3.py gchp.dryrun.log \
        --dest-bucket my-bucket \
        --dest-prefix ExtData/ \
        --workers 16 \
        --dryrun

Actual transfer:
    python copy_geoschem_inputdata_s3_to_s3.py gchp.dryrun.log \
        --dest-bucket my-bucket \
        --dest-prefix ExtData/ \
        --workers 16

Only files reported missing by GEOS-Chem:
    python copy_geoschem_inputdata_s3_to_s3.py gchp.dryrun.log \
        --dest-bucket my-bucket \
        --only-missing \
        --workers 16

If the destination is empty and overwriting is acceptable, --overwrite
avoids one destination HEAD request per object:
    python copy_geoschem_inputdata_s3_to_s3.py gchp.dryrun.log \
        --dest-bucket my-bucket \
        --workers 16 \
        --overwrite
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import boto3
from boto3.s3.transfer import TransferConfig
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


DEFAULT_SOURCE_BUCKET = "gcgrid"
DEFAULT_DEST_PREFIX = "ExtData/"
DEFAULT_WORKERS = 16

# Preserve the substitution behavior from the original script:
# read the corrected filename from gcgrid, but save it at the destination
# using the filename expected by GEOS-Chem.
FILENAME_SUBSTITUTIONS = {
    "IPMN": "PMN",
    "NPMN": "PMN",
    "RIPA": "RIP",
    "RIPB": "RIP",
    "RIPD": "RIP",
}

PRINT_LOCK = threading.Lock()
SERVER_COPY_DISABLED = threading.Event()
SERVER_COPY_NOTICE_PRINTED = threading.Event()


@dataclass(frozen=True)
class TransferJob:
    source_key: str
    destination_key: str


@dataclass
class TransferResult:
    status: str
    job: TransferJob
    method: str = ""
    error: str = ""


def log(message: str) -> None:
    """Print one complete line without mixing output from worker threads."""
    with PRINT_LOCK:
        print(message, flush=True)


def normalize_log_path(value: str) -> str:
    """Remove common quoting/punctuation around a path extracted from a log."""
    return value.strip().strip("'\";,()[]{}")


def extract_paths_from_log(dryrun_log: str) -> tuple[list[str], list[str]]:
    """Return sorted (found_paths, missing_paths) parsed from a dry-run log."""
    found: set[str] = set()
    missing: set[str] = set()

    with open(dryrun_log, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.replace("CHEM_INPUTS//", "CHEM_INPUTS/")
            upper = line.upper()
            fields = line.split()

            if not fields:
                continue

            path = normalize_log_path(fields[-1])

            if ": OPENING" in upper or ": READING" in upper:
                found.add(path)
            elif "REQUIRED FILE NOT FOUND" in upper or "FILE NOT FOUND" in upper:
                missing.add(path)

    return sorted(found), sorted(missing)


def extdata_rel_key_from_path(path: str) -> str | None:
    """
    Extract the object key relative to ExtData/.

    Example
    -------
    /some/path/ExtData/HEMCO/CH4/file.nc
        -> HEMCO/CH4/file.nc
    """
    match = re.search(r"(?:^|/)ExtData/(.+)", path)
    if not match:
        return None

    key = match.group(1).lstrip("/")
    return key or None


def make_destination_key(destination_prefix: str, extdata_relative_key: str) -> str:
    prefix = destination_prefix.strip("/")
    return f"{prefix}/{extdata_relative_key}" if prefix else extdata_relative_key


def corrected_source_key(expected_key: str) -> str:
    """Apply at most one filename substitution, matching the original behavior."""
    directory, separator, filename = expected_key.rpartition("/")

    for wrong, correct in FILENAME_SUBSTITUTIONS.items():
        if wrong in filename:
            corrected_filename = filename.replace(wrong, correct)
            return f"{directory}{separator}{corrected_filename}"

    return expected_key


def build_jobs(
    dryrun_log: str,
    destination_prefix: str,
    include_found: bool,
) -> tuple[list[TransferJob], int, int]:
    found_paths, missing_paths = extract_paths_from_log(dryrun_log)

    candidate_paths: Iterable[str]
    if include_found:
        candidate_paths = (*found_paths, *missing_paths)
    else:
        candidate_paths = missing_paths

    expected_keys: set[str] = set()
    ignored = 0

    for path in candidate_paths:
        relative_key = extdata_rel_key_from_path(path)
        if relative_key is None:
            ignored += 1
            continue
        expected_keys.add(relative_key)

    jobs = [
        TransferJob(
            source_key=corrected_source_key(key),
            destination_key=make_destination_key(destination_prefix, key),
        )
        for key in sorted(expected_keys)
    ]

    return jobs, len(found_paths), len(missing_paths)


def destination_exists(s3_client, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False

        # A role may have PutObject permission but not HeadObject/GetObject.
        # In that situation, attempt the write rather than stopping here.
        if code in {"403", "AccessDenied"} or status == 403:
            return False

        raise


def server_copy_is_unavailable(exc: BaseException) -> bool:
    """Identify failures for which unsigned streaming is worth trying."""
    codes = {
        "403",
        "405",
        "AccessDenied",
        "InvalidRequest",
        "MethodNotAllowed",
        "NotImplemented",
    }

    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in codes or status in {403, 405, 501}:
            return True

    text = str(exc)
    return any(token in text for token in codes)


def copy_server_side(
    source_client,
    destination_client,
    source_bucket: str,
    source_key: str,
    destination_bucket: str,
    destination_key: str,
    transfer_config: TransferConfig,
) -> None:
    """Ask S3 to copy the object directly without routing bytes through Python."""
    destination_client.copy(
        CopySource={"Bucket": source_bucket, "Key": source_key},
        Bucket=destination_bucket,
        Key=destination_key,
        SourceClient=source_client,
        Config=transfer_config,
    )


def copy_streaming(
    source_client,
    destination_client,
    source_bucket: str,
    source_key: str,
    destination_bucket: str,
    destination_key: str,
    transfer_config: TransferConfig,
) -> None:
    """Unsigned GET from source followed by signed upload to destination."""
    body = None

    try:
        response = source_client.get_object(Bucket=source_bucket, Key=source_key)
        body = response["Body"]

        upload_args = {
            "Fileobj": body,
            "Bucket": destination_bucket,
            "Key": destination_key,
            "Config": transfer_config,
        }

        content_type = response.get("ContentType")
        if content_type:
            upload_args["ExtraArgs"] = {"ContentType": content_type}

        destination_client.upload_fileobj(**upload_args)
    finally:
        if body is not None:
            body.close()


def transfer_one(
    job: TransferJob,
    *,
    source_client,
    destination_client,
    source_bucket: str,
    destination_bucket: str,
    mode: str,
    overwrite: bool,
    dryrun: bool,
    server_copy_config: TransferConfig,
    streaming_config: TransferConfig,
) -> TransferResult:
    source_uri = f"s3://{source_bucket}/{job.source_key}"
    destination_uri = f"s3://{destination_bucket}/{job.destination_key}"

    if dryrun:
        log(f"[DRYRUN:{mode}] {source_uri} -> {destination_uri}")
        return TransferResult("dryrun", job, method=mode)

    try:
        if not overwrite and destination_exists(
            destination_client, destination_bucket, job.destination_key
        ):
            log(f"[SKIP]        exists {destination_uri}")
            return TransferResult("skipped", job)

        if mode == "stream":
            copy_streaming(
                source_client,
                destination_client,
                source_bucket,
                job.source_key,
                destination_bucket,
                job.destination_key,
                streaming_config,
            )
            log(f"[OK:stream]   {source_uri} -> {destination_uri}")
            return TransferResult("copied", job, method="stream")

        if mode == "server":
            copy_server_side(
                source_client,
                destination_client,
                source_bucket,
                job.source_key,
                destination_bucket,
                job.destination_key,
                server_copy_config,
            )
            log(f"[OK:server]   {source_uri} -> {destination_uri}")
            return TransferResult("copied", job, method="server")

        # mode == "auto"
        if not SERVER_COPY_DISABLED.is_set():
            try:
                copy_server_side(
                    source_client,
                    destination_client,
                    source_bucket,
                    job.source_key,
                    destination_bucket,
                    job.destination_key,
                    server_copy_config,
                )
                log(f"[OK:server]   {source_uri} -> {destination_uri}")
                return TransferResult("copied", job, method="server")
            except Exception as exc:
                if not server_copy_is_unavailable(exc):
                    raise

                SERVER_COPY_DISABLED.set()
                if not SERVER_COPY_NOTICE_PRINTED.is_set():
                    with PRINT_LOCK:
                        if not SERVER_COPY_NOTICE_PRINTED.is_set():
                            print(
                                "[INFO] Server-side copy was not permitted; "
                                "using unsigned GET + streaming upload instead.",
                                flush=True,
                            )
                            SERVER_COPY_NOTICE_PRINTED.set()

        copy_streaming(
            source_client,
            destination_client,
            source_bucket,
            job.source_key,
            destination_bucket,
            job.destination_key,
            streaming_config,
        )
        log(f"[OK:stream]   {source_uri} -> {destination_uri}")
        return TransferResult("copied", job, method="stream")

    except (ClientError, BotoCoreError, OSError, Exception) as exc:
        # The broad catch is intentional: one failed object should not terminate
        # all other concurrent transfers.
        message = str(exc).replace("\n", " ")
        log(f"[FAIL]        {source_uri} -> {destination_uri}: {message}")
        return TransferResult("failed", job, error=message)


def make_clients(
    *,
    profile: str | None,
    region: str | None,
    workers: int,
):
    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region

    session = boto3.session.Session(**session_kwargs)
    pool_size = max(32, workers * 4)

    common_config = {
        "max_pool_connections": pool_size,
        "connect_timeout": 20,
        "read_timeout": 120,
        "retries": {"mode": "standard", "max_attempts": 10},
    }

    source_client = session.client(
        "s3",
        config=Config(signature_version=UNSIGNED, **common_config),
    )
    destination_client = session.client("s3", config=Config(**common_config))

    return source_client, destination_client


def write_failed_file(path: str, failures: list[TransferResult]) -> None:
    if not failures:
        return

    output = Path(path)
    with output.open("w", encoding="utf-8") as handle:
        handle.write("source_key\tdestination_key\terror\n")
        for result in failures:
            error = result.error.replace("\t", " ").replace("\n", " ")
            handle.write(
                f"{result.job.source_key}\t"
                f"{result.job.destination_key}\t"
                f"{error}\n"
            )

    log(f"Failed-object report: {output.resolve()}")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mirror GEOS-Chem ExtData paths from a dry-run log into an S3 bucket."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("dryrun_log", help="GEOS-Chem dry-run log file")
    parser.add_argument(
        "--source-bucket",
        default=DEFAULT_SOURCE_BUCKET,
        help="public source S3 bucket",
    )
    parser.add_argument("--dest-bucket", required=True, help="destination S3 bucket")
    parser.add_argument(
        "--dest-prefix",
        default=DEFAULT_DEST_PREFIX,
        help="destination key prefix; pass an empty string for bucket root",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=DEFAULT_WORKERS,
        help="number of objects transferred concurrently",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "server", "stream"),
        default="auto",
        help=(
            "auto tries server-side copy and falls back to streaming; "
            "server never falls back; stream always routes data through this host"
        ),
    )

    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--only-missing",
        action="store_true",
        help="copy only paths reported as missing",
    )
    selection.add_argument(
        "--include-found",
        action="store_true",
        help="copy both found and missing paths (the default)",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite destination objects and skip destination HEAD checks",
    )
    parser.add_argument(
        "--dryrun",
        action="store_true",
        help="print planned transfers without contacting S3",
    )
    parser.add_argument(
        "--profile",
        help="AWS profile used for destination access",
    )
    parser.add_argument(
        "--region",
        help="AWS region for the clients; otherwise use normal AWS configuration",
    )
    parser.add_argument(
        "--failed-file",
        default="mirror_extdata_failed.tsv",
        help="write failed source/destination keys here",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.dryrun_log):
        parser.error(f"dry-run log does not exist: {args.dryrun_log}")

    return args


def main() -> int:
    args = parse_args()
    include_found = not args.only_missing

    jobs, found_count, missing_count = build_jobs(
        args.dryrun_log,
        args.dest_prefix,
        include_found,
    )

    destination_root = (
        f"s3://{args.dest_bucket}/{args.dest_prefix.strip('/')}/"
        if args.dest_prefix.strip("/")
        else f"s3://{args.dest_bucket}/"
    )

    print("================ GEOS-Chem ExtData mirror ================")
    print(f"Log:               {args.dryrun_log}")
    print(f"Source:            s3://{args.source_bucket}/")
    print(f"Destination:       {destination_root}")
    print(f"Log found paths:   {found_count}")
    print(f"Log missing paths: {missing_count}")
    print(f"Unique objects:    {len(jobs)}")
    print(f"Selection:         {'found + missing' if include_found else 'missing only'}")
    print(f"Mode:              {args.mode}")
    print(f"Workers:           {args.workers}")
    print(f"Dry run:           {args.dryrun}")
    print(f"Overwrite:         {args.overwrite}")
    print("===========================================================")

    if not jobs:
        print("No ExtData object keys were found in the selected log lines.")
        return 0

    # A dry run does not need credentials or network access.
    if args.dryrun:
        source_client = None
        destination_client = None
    else:
        source_client, destination_client = make_clients(
            profile=args.profile,
            region=args.region,
            workers=args.workers,
        )

    # One outer worker handles one object. The server-side transfer manager may
    # use a few additional threads only when a single object needs multipart copy.
    server_copy_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=4,
        use_threads=True,
    )

    # Streaming transfers are already parallelized across objects, so avoid a
    # second large per-object thread pool.
    streaming_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=16 * 1024 * 1024,
        max_concurrency=1,
        use_threads=False,
    )

    counts: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    failures: list[TransferResult] = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_job: dict[Future[TransferResult], TransferJob] = {
            executor.submit(
                transfer_one,
                job,
                source_client=source_client,
                destination_client=destination_client,
                source_bucket=args.source_bucket,
                destination_bucket=args.dest_bucket,
                mode=args.mode,
                overwrite=args.overwrite,
                dryrun=args.dryrun,
                server_copy_config=server_copy_config,
                streaming_config=streaming_config,
            ): job
            for job in jobs
        }

        try:
            for future in as_completed(future_to_job):
                result = future.result()
                counts[result.status] += 1
                if result.method:
                    methods[result.method] += 1
                if result.status == "failed":
                    failures.append(result)
        except KeyboardInterrupt:
            log("\n[INTERRUPTED] Cancelling transfers that have not started...")
            for future in future_to_job:
                future.cancel()
            return 130

    if failures:
        write_failed_file(args.failed_file, failures)

    print("===========================================================")
    print(
        "Done: "
        f"copied={counts['copied']} "
        f"skipped={counts['skipped']} "
        f"failed={counts['failed']} "
        f"dryrun={counts['dryrun']}"
    )
    if counts["copied"]:
        print(
            "Copy methods: "
            f"server={methods['server']} "
            f"stream={methods['stream']}"
        )
    print("===========================================================")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())