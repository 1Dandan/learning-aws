.. _imi-pruning-aws:

Running on AWS ParallelCluster
===============================

Pruning ``OutputDir`` across every target face on a pcluster, where FSx holds
the data and a data repository association keeps S3 in step.

See :ref:`imi-pruning-overview` for why the procedure is safe.

How This Differs from a Local Server
-------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * -
     - Local server
     - pcluster
   * - data location
     - downloaded per face
     - already on FSx
   * - disk pressure
     - one face at a time
     - whole ensemble present
   * - S3 deletion
     - explicit extra step
     - automatic via autoexport
   * - content verification
     - once, on data from S3
     - once per face, before its first run
   * - scale
     - one face per cycle
     - one face at a time, driven by a script

Everything else is identical. ``prune_outputdir.py`` is the same tool with the
same checks; only the surrounding work changes.

Before the First Prune
----------------------

.. warning::

   With a ``NEW,CHANGED,DELETED`` autoexport policy, deleting a file on FSx
   propagates the delete to S3, and that is irreversible.

   **Consider S3 bucket versioning with a short noncurrent-version expiry.**
   Enabling it costs nothing on existing objects — noncurrent versions appear
   only when something is deleted or overwritten — so the bill follows the
   deletion *rate*, not the bucket total. At a few hundred GiB pruned per day
   against a 3-day expiry, that is tens of dollars for an entire sweep.

   It is the only measure here that protects against a mistake nobody
   anticipated; every other check catches a failure that was foreseen. Suspend
   versioning once the results are verified, and the lifecycle rule clears the
   retained versions within the window.

   .. code-block:: bash

      aws s3api put-bucket-versioning --bucket BUCKET \
          --versioning-configuration Status=Enabled

      aws s3api put-bucket-lifecycle-configuration --bucket BUCKET \
          --lifecycle-configuration '{"Rules":[{
            "ID":"expire-pruned-outputdir","Status":"Enabled",
            "Filter":{"Prefix":"output/"},
            "NoncurrentVersionExpiration":{"NoncurrentDays":3},
            "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}}]}'

   Confirm the interaction with your DRA on a single face before enabling it
   bucket-wide: that deletes still propagate, and that a noncurrent version is
   retained where you expect.

.. note::

   Autoexport through a :ref:`DRA <dra>` is a different mechanism from the
   legacy ``lfs hsm_archive`` path used by
   ``scripts/utils/archive-all-to-s3.sh``. Confirm the two coexist as expected
   on one file system before relying on autoexport across every face.

Confirm the policy is what you think it is:

.. code-block:: bash

   aws fsx describe-data-repository-associations \
       --filters Name=file-system-id,Values=fs-XXXXXXXX \
       --query 'Associations[].{Path:FileSystemPath,S3:DataRepositoryPath,Export:S3.AutoExportPolicy.Events}'

.. _prune-in-job:

Pruning Inside the IMI Job
--------------------------

The simplest arrangement on pcluster: let each IMI job prune its own face when
it finishes. Set in the config,

.. code-block:: yaml

   PruneOutputDir: true

and ``run_imi.sh`` runs ``src/utilities/prune_outputdir.py`` as its last step,
after both stages have had their chance to write markers. With autoexport the
deletes reach S3 by themselves, so nothing else is needed — no separate pass
over 220 faces, no upload step.

The flag does not weaken any check. The prune still refuses unless an overpass
and an inversion marker both exist carrying the same ``S``, which happens only
when both stages completed over a consistent window. **A submission that ran
only one stage leaves the two disagreeing, and nothing is deleted** — that is
the check working, so it does not fail the job. The key defaults to ``false``
when absent, so a config that does not mention it is unaffected.

What it deletes is recorded in ``<run_dirs>/outputdir_pruned_keys.txt``.

.. important::

   Verify a face's products **before** the prune runs, not after. Once a face
   is pruned, its ``OutputDir`` cannot be rebuilt without re-simulating, so a
   corrupt overpass file or ``data_converted`` pickle found afterwards is not
   repairable.

   :ref:`aws-face-driver` does this as its first step, ahead of the run that
   prunes. Turning ``PruneOutputDir`` on outside that driver means checking the
   face yourself first:

   .. code-block:: bash

      ./src/utilities/check_overpass_complete.py "$cfg" --flag-nan-first-date
      ./src/utilities/check_data_converted.py    "$cfg"

.. _aws-face-driver:

Driving the Faces
-----------------

``scripts/submit/submit_postprocess_faces.sh`` runs the faces one at a time.
It is the normal route; the by-hand sections below are for when something needs
looking at.

.. code-block:: bash

   cd /fsx_output/imi-gchp/scripts/submit

   nohup ./submit_postprocess_faces.sh > /dev/null 2>&1 &
   disown

   ./submit_postprocess_faces.sh --status

The face list defaults to ``/fsx_output/imi-gchp/submit_faces.txt``, one face
per line (``T001``, or ``1``, or ``T1``); pass a different path as the only
argument.

Per face it:

1. generates ``configs_C36S10/config_T042.yml`` from ``config-1yr-c36s10.yml``
   and ``supportData/target_coords_num-sv.csv``, setting ``RunName``,
   ``TARGET_LAT``, ``TARGET_LON``, ``StateVectorFile`` and the postprocessing
   flags, ``PruneOutputDir: true`` among them
2. runs both checkers **once**, deletes what they flag, and retires the
   corresponding marker so the run rebuilds it — then stamps
   ``logs_C36S10/verified/<face>.ok`` so it never checks that face again
3. runs ``run_imi.sh``, which submits the overpass and inversion jobs and
   prunes when they finish
4. reads the log to confirm the prune actually ran, and records the face
   ``failed`` if it declined
5. releases the face's local blocks, so the next face starts with the space back

Only the overpass and inversion steps become Slurm jobs. The driver, the
checkers, ``run_imi.sh`` itself and the prune all run on the head node, where
they cost nothing but wall time — which is why the driver is started under
``nohup``.

Progress is recorded in ``logs_C36S10/postprocess_state.tsv``, so the same
command resumes rather than repeats. A face recorded ``ok`` is skipped; one
recorded ``failed`` is retried.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Option
     - Effect
   * - ``--config-only``
     - generate the configs and stop; read-only, worth running first
   * - ``--verify-only``
     - run the checks without running the IMI
   * - ``--skip-verify``
     - skip the checks for a face already dealt with by hand
   * - ``--no-release``
     - keep the face resident instead of releasing its blocks
   * - ``--status``
     - counts by state, and whether the driver is running

To stop:

.. code-block:: bash

   touch STOP_POSTPROCESS

It finishes the current face and starts no more.

.. warning::

   Step 2 **deletes** what the checkers flag, and with a ``DELETED`` autoexport
   policy that reaches S3. There is no dry run through it. On the first face,
   run the checkers by hand and read the output before letting the driver take
   over — see below.

Testing a Single Face
---------------------

Before the first campaign, take one face through by hand. The checkers are
read-only and print the paths they would delete:

.. code-block:: bash

   CFG=/fsx_output/imi-gchp/configs_C36S10/config_T042.yml

   python -u src/utilities/check_overpass_complete.py "$CFG" \
       --flag-nan-first-date --workers 4 > /tmp/overpass_bad.txt

   python -u src/utilities/check_data_converted.py "$CFG" \
       --workers 4 > /tmp/converted_bad.txt

   wc -l /tmp/overpass_bad.txt /tmp/converted_bad.txt
   head /tmp/overpass_bad.txt

Expect the ``StartDate-1`` files, which are partly NaN by construction and are
flagged deliberately so the run rebuilds them, and little else. A long list
means something is wrong with that face's products, not with the check.

Then let the driver take the face. It has stamped nothing yet, so it repeats
the same checks and proceeds:

.. code-block:: bash

   echo T042 > one_face.txt
   ./submit_postprocess_faces.sh one_face.txt

Confirm afterwards that the face shrank in S3 and that the space came back:

.. code-block:: bash

   aws s3 ls --recursive --summarize \
       s3://BUCKET/output/Global_1yr_2025_C36S10_T042/ | grep "Total Size"
   lfs df -h

.. _aws-release:

Releasing Space Between Faces
-----------------------------

After pruning, what remains of a face is small, but 220 of them still
accumulate. ``lfs hsm_release`` frees the local blocks while leaving the file in
the namespace; a later read pulls it back from S3, in-region and unbilled.

Releasing is **not** deleting — the file stays in the namespace, so the
``DELETED`` policy does not fire and nothing leaves the bucket.

The driver does this after a face is recorded ``ok``, and only when every file
under the face is archived. That check is the protection: a released file whose
S3 object is missing is unrecoverable, and autoexport is asynchronous, so a
face finishing does not mean its export has.

By hand:

.. code-block:: bash

   F=/fsx_output/output/Global_1yr_2025_C36S10_T042

   find "$F" -type f -print0 | xargs -0 -n1 lfs hsm_state | grep -c archived
   find "$F" -type f | wc -l          # the two must match

   find "$F" -type f -print0 | xargs -0 -n 100 lfs hsm_release
   lfs df -h

Pruning by Hand
---------------

Not the normal route — :ref:`aws-face-driver` prunes each face as part of its
run. This is for pruning faces that were processed some other way, or for
looking at what the prune would do without running anything else.

Always start with a dry run across everything:

.. code-block:: bash

   cd scripts/postprocess
   ../../src/utilities/prune_outputdir.py ../../configs_C36S10/config_T*.yml

This reports, per face, either how much would be freed or exactly which check
blocked it. Nothing is touched.

Then begin small:

.. code-block:: bash

   ../../src/utilities/prune_outputdir.py ../../configs_C36S10/config_T*.yml \
       --execute --max-faces 5 --retain-days 7 \
       --stop-file /fsx_output/imi-gchp/STOP_PRUNE

Confirm the result, then widen:

.. code-block:: bash

   ../../src/utilities/prune_outputdir.py ../../configs_C36S10/config_T*.yml \
       --execute --max-faces 50 --retain-days 7 \
       --stop-file /fsx_output/imi-gchp/STOP_PRUNE

Options
-------

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Option
     - Effect
   * - ``--execute``
     - actually delete; without it nothing is removed
   * - ``--max-faces N``
     - stop after N faces are pruned
   * - ``--retain-days N``
     - hold ``OutputDir`` N days further back than strictly safe, as a
       recovery margin
   * - ``--stop-file PATH``
     - halt cleanly between faces once that file exists
   * - ``--keep-checkpoints N``
     - newest internal checkpoints kept per Jacobian run; default 1, ``0``
       disables checkpoint pruning
   * - ``--skip-converted-check``
     - only for a face whose inversion predates manifests
   * - ``--record-deleted FILE``
     - append every deleted path; not needed when autoexport handles S3

To stop a running prune:

.. code-block:: text

  touch /fsx_output/imi-gchp/STOP_PRUNE

It finishes the current face and exits. Remove the file before the next run.

Reading the Output
------------------

Each face reports one line:

.. code-block:: text

  [PRUNED]  Global_1yr_2025_C36S10_T007: deleted 4218 file(s), 731.4 GiB, dated <= 20250813
  [SKIPPED] Global_1yr_2025_C36S10_T008: already pruned through 20250813
  [BLOCKED] Global_1yr_2025_C36S10_T009: no inversion_complete marker

A blocked face is left completely untouched; the loop continues. The exit code
is 2 if any face was blocked, so a wrapper can notice without parsing output.

When overpass output is incomplete, every run directory is listed, so it is
clear whether a run is merely missing a date or was never processed:

.. code-block:: text

  [BLOCKED] Global_1yr_2025_C36S10_T009: 2 of 7 Jacobian run(s) have incomplete
            overpass output for window 20241231..20250813 (235 file(s) missing)
      Global_1yr_2025_C36S10_T009_0001: complete (678)
      ...
      Global_1yr_2025_C36S10_T009_0006: 9 of 226 missing, first GEOSChem.CH4col.overpass.20250104_1330.nc4
      Global_1yr_2025_C36S10_T009_0007: NONE of 226 present -- this run was never processed

Common blocks and what they mean:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Message
     - Meaning
   * - ``no inversion_complete marker``
     - the inversion has not finished for this face
   * - ``markers disagree``
     - one stage has advanced past the other; rerun the lagging one
   * - ``N of M Jacobian run(s) have incomplete overpass output``
     - see the per-run listing that follows it
   * - ``NONE of N present``
     - that run produced no overpass output at all; see the warning in
       :ref:`imi-pruning-overview` about the run-indexing fix
   * - ``data_converted disagrees with its manifest``
     - a pickle recorded as written is absent

Repeat as Runs Advance
----------------------

``S`` grows as the Jacobian runs progress. Each processing round pushes the
markers forward and the cutoff with them, so a face already pruned once can
have more to give later. Re-running is cheap either way:
``outputdir_pruned.json`` makes a face with nothing new a no-op, and the
driver skips a face recorded ``ok`` unless its state line is cleared.

Verification Runs Once Per Face
-------------------------------

Each face is checked before its first run and never again. The stamp in
``logs_C36S10/verified/<face>.ok`` records that it happened, so a retry after a
failed run goes straight to the IMI.

Once is enough because the products written since are written to a temporary
name and renamed, so a file bearing its final name is complete. What the check
is for is the data that came off the original simulations, which predates that
guarantee.

Re-checking would also be expensive here in a way it is not on a local server:
every read of a released file triggers an HSM restore from S3.

To force a re-check on a face:

.. code-block:: bash

   rm logs_C36S10/verified/T042.ok
