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
     - not needed
   * - scale
     - one face per cycle
     - all 220 faces in one loop

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

   Verify the products **before** turning this on, not after. Once a face is
   pruned, its ``OutputDir`` cannot be rebuilt without re-simulating, so a
   corrupt overpass file or ``data_converted`` pickle discovered afterwards is
   not repairable. Run both checkers across every target face first:

   .. code-block:: bash

      for cfg in configs_C36S10/config_T*.yml; do
          ./src/utilities/check_overpass_complete.py "$cfg"
          ./src/utilities/check_data_converted.py    "$cfg"
      done

   Products written since are safe without re-checking: both the overpass
   diagnostics and the pickles are now written to a temporary file and renamed,
   so a file bearing its final name is complete.

Pruning by Hand
---------------

The alternative, if you would rather keep a person in the loop. Faces are
processed by the usual submission workflow
(``scripts/submit/batch_submit.sh``), which is unchanged. Once faces carry both
markers, prune them.

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
markers forward and the cutoff with them, so the prune is worth re-running
periodically. ``outputdir_pruned.json`` makes an already-pruned face a no-op,
so re-running across every face is cheap.

No Verification Step
--------------------

Content verification is deliberately not repeated at pcluster scale. Every read
would trigger an HSM restore, and the data was written by code that cannot
leave a partial file, cannot write a silent all-NaN file, and never rewrites a
finished one. See :ref:`imi-pruning-overview` for the reasoning.
