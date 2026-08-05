.. _imi-postprocessing-and-pruning:

IMI Postprocessing and Pruning Simulation Output
=================================================

This section describes how to compute satellite overpass diagnostics and the
inversion for a stretched-grid IMI target face, and how to then delete the
GEOS-Chem output those steps are finished with.

The procedure is identical on a local server and on a pcluster. Only two
things differ: where the paths point, and whether you have to remove objects
from S3 yourself.

Background and Design Philosophy
--------------------------------

A one-year global ensemble at C36S10 produces roughly 220 target faces, each
holding hundreds of Jacobian run directories. Nearly all of the storage is
``jacobian_runs/*/OutputDir``: hourly 3D GEOS-Chem fields, written so that two
postprocessing steps can consume them.

- **Satellite overpass diagnostics** sample those fields at local overpass
  time, producing ``OverpassDiagnostics/``
- **The inversion** applies the TROPOMI operator, producing
  ``inversion/data_converted/``

Both products are a small fraction of the input. Once they exist and are
verified, the input is no longer referenced by anything, and 168 TB of
``OutputDir`` can become a fraction of that.

The design problem is not *how* to delete. It is knowing, without inspecting
220 faces by hand, that deleting is safe. The answer is two **completion
markers** per face, written by the pipeline itself, which a pruning tool
verifies before removing anything.

.. warning::

   ``OutputDir`` cannot be regenerated without re-running the GEOS-Chem
   simulations. Treat every deletion as permanent and confirm the products
   are durably stored first.

Directory Layout
----------------

Per target face, under ``OutputPath``::

  Global_1yr_2025_C36S10_T001/
  ├── StateVector.nc
  ├── CS_grids/                        gridspec and tile files
  ├── jacobian_runs/
  │   └── Global_1yr_2025_C36S10_T001_0001 … _NNNN/
  │       ├── OutputDir/               <- the bulk of the storage
  │       ├── OverpassDiagnostics/     <- product
  │       └── Restarts/                gcchem_internal_checkpoint.*.nc4
  ├── inversion/
  │   ├── data_converted/              <- product
  │   └── data_converted_manifest.json
  ├── .overpass_complete.<start>_<S>   <- marker
  └── .inversion_complete.<start>_<S>  <- marker

The Shared End Date
-------------------

``S``, the *shared end date*, is the minimum across all Jacobian runs of each
run's latest checkpoint. It is the date up to which **every** run has
progressed, and it is what all the date arithmetic keys off.

Overpass output for local date ``L`` reads ``OutputDir`` for both ``L`` and
``L+1``. So while runs are still advancing:

- ``OutputDir`` holds UTC dates through ``S-1``
- overpass output can therefore only reach local date ``S-2``
- the earliest work a later round can do is local date ``S-1``, which needs
  ``OutputDir`` from ``S-1`` onward

**Files dated ``S-2`` or earlier are referenced by nothing.** That is the
cutoff. Once ``S`` reaches ``EndDate`` there is no further day to wait for and
the cutoff becomes ``EndDate-1``.

Requirements
------------

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Requirement
     - Needed for
     - Notes
   * - conda environment
     - everything
     - named in ``CondaEnv``
   * - GEOS-Chem environment file
     - ``run_imi.sh``
     - path in ``GEOSChemEnv``
   * - Slurm
     - the inversion step
     - see the caveat below
   * - nco (``ncmax``)
     - ``nElements`` during setup
     - only when ``RunSetup: true``
   * - ``GCHP/`` at v14.7.0
     - ``setup_imi``
     - cloned automatically if absent
   * - ``aws`` CLI
     - S3 upload and pruning
     - local server only

.. note::

   ``run_imi.sh`` submits the inversion through ``sbatch`` unconditionally.
   ``run_inversion()`` in ``inversion.sh`` has no non-Slurm branch, unlike the
   overpass step, which does. On a machine without Slurm the overpass stage
   runs with ``UseSlurm: false`` but the inversion stage fails.

One-Time Configuration
----------------------

Every per-face config in ``configs_C36S10/`` is generated from
``config-1yr-c36s10.yml``, so edit that template once:

.. code-block:: yaml

   OutputPath:        /path/to/output
   DataPath:          /path/to/ExtData
   DataPathTROPOMI:   /path/to/blended-tropomi
   BCpath:            /path/to/blended-boundary-conditions
   RestartFilePrefix: /path/to/.../GEOSChem.BoundaryConditions.

   SchedulerPartition: <partition>
   RequestedCPUs:      <n>
   RequestedMemory:    <n>G
   RequestedTime:      <D-HH:MM>
   InversionCPUs:      <n>
   InversionMemory:    <n>G
   InversionTime:      <D-HH:MM>

   CondaEnv:     <env name>
   GEOSChemEnv:  ${HOME}/gchp.env

``run_face_local.sh`` refuses to start while any path still points at
``/fsx_input`` or ``/fsx_output``, or does not exist, so a forgotten edit fails
immediately rather than half-running.

Processing One Face
-------------------

Step 1: Verify Data That Has Round-Tripped Through Storage
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Only needed for overpass data whose integrity you have reason to doubt: files
downloaded from S3, or produced before the missing-input guard existed.
**Skip this for data the current pipeline produced.**

.. code-block:: bash

   cd scripts/local
   ./check_overpass_complete.py ../../configs_C36S10/config_T001.yml > bad_T001.txt

Each expected file is checked: exists, opens, carries its expected variables,
contains no NaN. Failures go to stdout, which is the deletion list; everything
else goes to stderr.

.. note::

   There is no exemption for the ``StartDate-1`` file (``20241231``). It is
   mostly NaN by construction, so it is reported, deleted, and regenerated with
   everything else. This makes "produced by the current scripts" mean the same
   thing for every date.

   Run this **once, before reprocessing**. Running it again afterwards will
   flag ``20241231`` again, forever.

Step 2: Delete What Failed
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   ./delete_files_from_list.sh bad_T001.txt              # dry run
   ./delete_files_from_list.sh bad_T001.txt --execute

The script rejects any path that is not an overpass diagnostic, so a truncated
redirect cannot turn it into a general-purpose remover.

Step 3: Process
^^^^^^^^^^^^^^^

.. code-block:: bash

   ./run_face_local.sh T001 --dry-run    # generate config, check paths only
   ./run_face_local.sh T001

The config is built in a temporary file and installed only after preflight
passes, so a failed run leaves ``configs_C36S10/`` untouched.

On success the face gains two empty markers and a manifest::

  .overpass_complete.20250101_20250815
  .inversion_complete.20250101_20250815
  inversion/data_converted_manifest.json

Exactly one marker exists per stage: writing a new one removes the superseded
one, so a face holds two markers total, not two per round.

Step 4: Prune
^^^^^^^^^^^^^

.. code-block:: bash

   ./prune_outputdir.py ../../configs_C36S10/config_T001.yml            # dry run
   ./prune_outputdir.py ../../configs_C36S10/config_T001.yml --execute

This deletes files on the filesystem. Nothing more. Every precondition it
checks is a path check, so it behaves identically wherever it runs.

Processing Many Faces
---------------------

Only the prune loops; the rest is one face at a time.

.. code-block:: bash

   ./prune_outputdir.py ../../configs_C36S10/config_T*.yml \
       --execute --max-faces 10 --retain-days 7 \
       --stop-file /fsx_output/imi-gchp/STOP_PRUNE

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Effect
   * - ``--max-faces N``
     - stop after N faces; start small, confirm, then raise
   * - ``--retain-days N``
     - hold ``OutputDir`` N days further back as a recovery margin
   * - ``--stop-file PATH``
     - halt cleanly between faces once that file exists
   * - ``--record-deleted FILE``
     - append every deleted path, for the S3 step below
   * - ``--skip-converted-check``
     - only for a face whose inversion predates manifests

A blocked face is left completely untouched and reported; the loop continues.
The exit code is 2 if any face was blocked.

What the Prune Checks First
---------------------------

#. Exactly one marker per stage, both carrying the same start date and ``S``.
#. The cutoff comes from the marker's ``S``, never from the checkpoints as they
   stand now. ``S`` grows as runs advance, and recomputing it at prune time
   would delete past what the markers actually cover. This is the easiest
   thing to get wrong.
#. Every Jacobian run holds an overpass file for every date in the window,
   compared as an explicit set rather than a count. A count still matches when
   one date is missing and another is duplicated.
#. ``inversion/data_converted`` agrees with its manifest.

Any failure blocks that face and leaves it untouched. A per-face
``.outputdir_pruned.json`` records what was removed and when, which also makes
a re-run a no-op.

The data_converted Manifest
^^^^^^^^^^^^^^^^^^^^^^^^^^^

``jacobian.py`` records every TROPOMI granule the window selected and its
outcome:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Status
     - Meaning
   * - ``written``
     - the operator returned data and a pickle was saved
   * - ``cached``
     - a pickle from an earlier round was already in place
   * - ``no_valid_obs``
     - the granule held no usable observation, so nothing was written

That last row is why the manifest exists. A granule that legitimately produces
no pickle is otherwise indistinguishable from one that was never processed, so
completeness could only be inferred from which dates happen to have output, and
any such rule either accepts real gaps or rejects healthy faces.

On a pcluster: Autoexport Handles S3
-------------------------------------

With a :ref:`DRA <dra>` carrying a ``NEW,CHANGED,DELETED`` autoexport policy,
deleting a file on FSx propagates the delete to S3. Nothing further is needed:
run ``prune_outputdir.py`` and the bucket follows.

.. warning::

   A propagated delete is irreversible unless the bucket has versioning enabled.
   Turn on S3 versioning with a noncurrent-version expiry, 30 days is cheap
   insurance, **before** the first prune. That is the only real undo.

.. note::

   Autoexport through a DRA is a different mechanism from the legacy
   ``lfs hsm_archive`` path. Confirm the two coexist as expected on one file
   system before relying on autoexport across every face.

On a Local Server: S3 Is a Separate Step
-----------------------------------------

When working from data downloaded out of S3, nothing syncs on your behalf, so
uploading products and removing retired objects is an explicit extra step.

.. code-block:: bash

   # 1. delete locally, recording what went
   ./prune_outputdir.py ../../configs_C36S10/config_T001.yml \
       --execute --record-deleted pruned_T001.txt

   # 2. upload products, then delete those objects from S3
   ./s3_upload_and_prune.sh ../../configs_C36S10/config_T001.yml BUCKET \
       --deleted-list pruned_T001.txt              # dry run
   ./s3_upload_and_prune.sh ../../configs_C36S10/config_T001.yml BUCKET \
       --deleted-list pruned_T001.txt --execute

The order is deliberate: products are uploaded before any object is removed.
The script rejects any recorded path that is not under this face's
``OutputDir``, and deletes in batches of 1000 keys.

Verifying Uploads
^^^^^^^^^^^^^^^^^

An object's ``ETag`` equals its MD5 only for single-part uploads. ``aws s3 cp``
goes multipart above 8 MB, after which the ``ETag`` is an MD5 of part MD5s with
a ``-N`` suffix and will never match a local ``md5sum``. Compare **sizes**
instead, which is authoritative for truncation and needs no download.

The upload is already integrity-checked: the CLI sends a per-part checksum and
S3 rejects any part that does not match, so a successful ``sync`` proves the
bytes landed intact. For a true end-to-end hash with no download, upload with
``--checksum-algorithm CRC32C`` and read it back with
``head-object --checksum-mode ENABLED``.

Why the Overpass Archive Is Worth Keeping
------------------------------------------

``SatDiagOperator`` selects what the inversion reads:

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * -
     - ``false``
     - ``true``
   * - operator reads
     - ``OutputDir``
     - ``OverpassDiagnostics``
   * - granules selected
     - up to ``S-1``
     - up to the last overpass local date
   * - ``data_converted`` recomputable after a prune
     - no
     - yes

With ``SatDiagOperator: false`` the inversion reads ``OutputDir`` directly, so
a date whose ``OutputDir`` has been deleted can never have its inversion
re-run. The overpass archive is what restores that option: under
``SatDiagOperator: true`` it is the input from which ``data_converted`` can be
recomputed, long after ``OutputDir`` is gone.

To recompute from the archive you need, besides ``OverpassDiagnostics``: the
TROPOMI granules, ``StateVector.nc``, and ``CS_grids/``. The prune only ever
removes ``OutputDir``, so these survive it, but they must also survive whatever
else is done to shrink storage.

Why Freshly Written Data Need Not Be Re-Verified
-------------------------------------------------

Step 1 is deliberately not repeated at scale on a pcluster, where every read
would trigger an HSM restore. Data produced by the current pipeline is written
by code that:

- **cannot leave a partial file** — every diagnostic is written to a temporary
  file and moved into place atomically
- **cannot write a silent all-NaN file** — a missing ``OutputDir`` input for a
  date inside the simulation window is a hard error, not an empty result
- **never rewrites a finished file** — completed output is skipped

That last guard is what makes pruning safe at all. Without it, a later run over
a pruned date would regenerate the overpass file as silent all-NaN rather than
failing, and the corruption would be indistinguishable from real output.

Corruption therefore does not originate in the writer. It originates in the
storage round trip, which is exactly what Step 1 is for, and exactly why it is
needed once and then not again.
