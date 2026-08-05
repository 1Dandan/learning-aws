.. _imi-pruning-local:

Running on a Local Server
==========================

Processing faces one at a time on a machine with limited disk, working from
data held in S3. Each face is downloaded, processed, pruned, pushed back, and
then removed locally before the next one starts, so only one face is ever on
disk.

A face is roughly 0.75 TB, nearly all of it ``OutputDir``.

See :ref:`imi-pruning-overview` for why the procedure is safe.

Prerequisites
-------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Requirement
     - Notes
   * - conda environment
     - named in ``CondaEnv``
   * - GEOS-Chem environment file
     - path in ``GEOSChemEnv``
   * - Slurm
     - required; see the caveat below
   * - nco (``ncmax``)
     - used for ``nElements`` during setup
   * - ``GCHP/`` at v14.7.0 in the repo root
     - ``setup_imi`` clones it if absent
   * - ``aws`` CLI, configured
     - for download, upload, and object deletion
   * - free disk ≥ one face
     - roughly 0.75 TB

.. note::

   ``run_imi.sh`` submits the inversion through ``sbatch`` unconditionally.
   ``run_inversion()`` in ``inversion.sh`` has no non-Slurm branch, unlike the
   overpass step. Without Slurm the overpass stage runs under
   ``UseSlurm: false`` but the inversion stage fails.

One-Time Configuration
----------------------

Edit ``config-1yr-c36s10.yml`` once; every per-face config is generated from
it:

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

   CondaEnv:    imi-gchp
   GEOSChemEnv: ${HOME}/gchp.env

The scripts refuse to start while any path still points at ``/fsx_input`` or
``/fsx_output``, or does not exist.

Automated: One Command Per Face
--------------------------------

``process_face_cycle.sh`` runs the whole loop. Start with a dry run, which
downloads and verifies but stops before anything is deleted:

.. code-block:: bash

   cd scripts/local
   ./process_face_cycle.sh BUCKET T001

Then for real:

.. code-block:: bash

   ./process_face_cycle.sh BUCKET T001 --execute

Several faces in sequence, with a way to stop cleanly between them:

.. code-block:: bash

   ./process_face_cycle.sh BUCKET T001 T002 T003 --execute \
       --stop-file /tmp/STOP_CYCLE

   # or from a file, one face per line
   ./process_face_cycle.sh BUCKET --faces-file faces.txt --execute

Per face it performs:

.. list-table::
   :header-rows: 1
   :widths: 8 22 70

   * - Step
     - Action
     - Detail
   * - 1
     - download
     - ``aws s3 sync`` the face from the bucket
   * - 2
     - configure
     - generate the per-face config and preflight every path
   * - 3
     - verify
     - check overpass files that came from S3
   * - 4
     - repair
     - delete what failed, so step 5 regenerates it
   * - 5
     - process
     - overpass diagnostics, then the inversion
   * - 6
     - prune
     - delete ``OutputDir`` dates both stages are finished with
   * - 7
     - push
     - upload products, **verify them in S3**, delete retired objects
   * - 8
     - clean
     - remove the local face directory

.. important::

   Step 8 runs only if step 7 exited 0, and step 7 exits nonzero unless every
   product is confirmed present in S3 at a matching size. The local copy is
   never destroyed on the strength of an unchecked upload.

A face that fails at any step is left on disk and reported; the loop continues
to the next face. Use ``--keep-local`` to skip step 8 entirely.

Manual: Step by Step
--------------------

The same sequence, run by hand, for a single face:

.. code-block:: bash

   cd scripts/local
   FACE=T001
   RUN=Global_1yr_2025_C36S10_${FACE}
   CFG=../../configs_C36S10/config_${FACE}.yml

   # 1. download
   aws s3 sync s3://BUCKET/output/${RUN}/ /path/to/output/${RUN}/

   # 2. generate the config and preflight paths
   ./run_face_local.sh ${FACE} --dry-run

   # 3. verify overpass data that round-tripped through S3
   ./check_overpass_complete.py ${CFG} > bad_${FACE}.txt

   # 4. delete what failed
   ./delete_files_from_list.sh bad_${FACE}.txt --execute

   # 5. process; writes both markers and the manifest on success
   ./run_face_local.sh ${FACE}

   # 6. prune locally, recording what went
   ./prune_outputdir.py ${CFG} --execute --record-deleted pruned_${FACE}.txt

   # 7. upload products, verify, delete retired objects
   ./s3_upload_and_prune.sh ${CFG} BUCKET --deleted-list pruned_${FACE}.txt --execute

   # 8. remove the local copy
   rm -rf /path/to/output/${RUN}

.. note::

   Step 3 is a **run-once-before-reprocessing** tool. It deliberately flags the
   ``StartDate-1`` file (``20241231``), which is mostly NaN by construction, so
   that it is regenerated along with everything else. Running it again after
   processing would flag that file again, forever. Afterwards, the markers are
   the statement of completeness.

Why S3 Deletion Is Explicit Here
---------------------------------

``prune_outputdir.py`` deletes files on the filesystem and nothing else. On a
machine working from downloaded data nothing syncs on your behalf, so removing
the retired objects from the bucket is a separate, deliberate step performed by
``s3_upload_and_prune.sh`` after the products are confirmed uploaded.

On a pcluster this is unnecessary; see :ref:`imi-pruning-aws`.
