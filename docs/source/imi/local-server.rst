.. _imi-pruning-local:

Running on a Local Server
==========================

Processing faces one at a time on a machine with limited disk, working from
data held in S3. Each face is downloaded, processed, pruned, pushed back, and
then removed locally before the next one starts, so only one face is ever on
disk.

Nearly all of a face's storage is ``OutputDir``, and it grows as the runs
advance, so size the disk against a face at its current progress rather than a
fixed figure.

See :ref:`imi-pruning-overview` for why the procedure is safe.

Prerequisites
-------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Requirement
     - Notes
   * - conda environment
     - named in ``CondaEnv``; must have xarray, since ``ncmax`` in
       ``common.sh`` wraps ``python -c "... xarray ..."``
   * - GEOS-Chem environment file
     - path in ``GEOSChemEnv``
   * - Slurm
     - required; see the caveat below
   * - ``GCHP/`` at v14.7.0 in the repo root
     - ``setup_imi`` clones it if absent
   * - ``aws`` CLI, configured
     - for download, upload, and object deletion
   * - free disk ≥ one face
     - nearly all of it ``OutputDir``; grows as the runs advance

.. note::

   ``run_imi.sh`` submits the inversion through ``sbatch`` unconditionally.
   ``run_inversion()`` in ``inversion.sh`` has no non-Slurm branch, unlike the
   overpass step. Without Slurm the overpass stage runs under
   ``UseSlurm: false`` but the inversion stage fails.

One-Time Configuration
----------------------

Edit ``scripts/postprocess/local_env.sh``, **not** the template.
``config-1yr-c36s10.yml`` keeps its pcluster values so it stays usable there;
``run_face_local.sh`` overlays the ``CFG_*`` values onto each per-face config
as it generates it.

.. code-block:: bash

   LOCAL_ROOT="/path/to/work/root"

   CFG_OutputPath="${LOCAL_ROOT}/output"
   CFG_DataPath="/path/to/ExtData"
   CFG_DataPathTROPOMI="/path/to/blended"
   CFG_BCpath="/path/to/blended-boundary-conditions"
   CFG_BCversion="v2025-12"

   CFG_CondaEnv="imi-gchp"
   CFG_GEOSChemEnv='${HOME}/envs/.../gchp.env'

   CFG_SchedulerPartition="part1,part2,part3"
   CFG_InvSchedulerPartition="${CFG_SchedulerPartition}"
   CFG_RequestedCPUs="48"
   CFG_RequestedMemory="180G"
   CFG_RequestedTime="0-3:30"

A comma-separated partition list lets Slurm place the job wherever frees up
first. ``InvSchedulerPartition`` is read by ``inversion.sh`` but absent from the
template, so the overlay appends it.

Anything that should not appear in a public repository — the bucket name, site
paths — goes in ``local_env.local.sh``, which ``local_env.sh`` sources at the
end and ``.gitignore`` excludes:

.. code-block:: bash

   S3_BUCKET="my-bucket"

``run_face_local.sh`` refuses to start while any path still points at
``/fsx_input`` or ``/fsx_output``, or does not exist.

Fetching From S3
----------------

``fetch_from_s3.sh`` lives inside the tree it fetches, so the first copy on a
new machine has to come down by hand:

.. code-block:: bash

   aws s3 sync s3://BUCKET/imi-gchp/ /path/to/process-imi-aws/imi-gchp/ \
       --exclude "*__pycache__/*" --exclude "*.pyc" --exclude "*.DS_Store"

   cd /path/to/process-imi-aws/imi-gchp/scripts/postprocess
   ./restore_git_modes.sh ../.. --restore

Confirm ``.git`` survived, since the repair reads from it::

   git -C ../.. fsck --no-progress
   git -C ../.. log --oneline | wc -l      # expect 1279

If it did not, ``git clone`` the repository there instead. After that the
scripts drive everything:

.. code-block:: bash

   cd scripts/postprocess
   ./fetch_from_s3.sh code                  # the imi-gchp tree, incl. GCHP/
   ./fetch_from_s3.sh code --no-gchp        # skip GCHP if the server has one
   ./fetch_from_s3.sh face T005 --dry-run   # size and free space, no transfer
   ./fetch_from_s3.sh face T005

Each face reports its remote size against local free space before transferring,
so a full filesystem surfaces before a multi-hundred-gigabyte copy rather than
during one.

Nothing needs pushing back to run a face — the flow into this machine is
one-directional. ``push_code_to_s3.sh`` exists for the reverse case: you edited
a script here and want other machines to pick it up.

.. code-block:: bash

   ./push_code_to_s3.sh --dry-run
   ./push_code_to_s3.sh

.. warning::

   S3 stores neither symlinks nor POSIX modes. A fetched source tree arrives
   with executable bits cleared and every symlink rewritten as a regular file
   holding its own target path — around 700 files across GCHP and its
   submodules, including ``GCHP/run``, which ``setup_template`` does ``cd``
   into.

   ``fetch_from_s3.sh code`` runs ``restore_git_modes.sh`` afterwards to put
   both back. Run it by hand on any tree you copied across another way:

   .. code-block:: bash

      ./restore_git_modes.sh <repo-root>             # survey
      ./restore_git_modes.sh <repo-root> --restore

   It restores a path only when the working file is byte-identical to the
   index, so local edits are never discarded.

Automated: One Command Per Face
--------------------------------

``process_face_cycle.sh`` runs the whole loop. Start with a dry run, which
downloads and verifies but stops before anything is deleted:

.. code-block:: bash

   cd scripts/postprocess
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
to the next face. Step 5 is **not** retried: a failure there needs looking at,
so the face is left as the run stopped it and can be resumed by hand once the
cause is understood. Use ``--keep-local`` to skip step 8 entirely.

Every invocation writes ``logs_C36S10/process_face_cycle_<timestamp>.log``,
alongside the per-face ``imi_output_C36S10_T###.log`` that ``run_imi.sh``
keeps.

Running It in the Background
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The script writes its own log, so backgrounding it needs nothing more than
detaching. Discard the terminal copy; the ``tee`` inside still writes the file.

.. code-block:: bash

   nohup ./process_face_cycle.sh T005 --execute \
         --stop-file /path/to/process-imi-aws/STOP_CYCLE \
         > /dev/null 2>&1 &

   tail -f ../../logs_C36S10/process_face_cycle_*.log

Two files track a run, both under ``logs_C36S10/``:

.. list-table::
   :header-rows: 1
   :widths: 42 58

   * - File
     - Contents
   * - ``process_face_cycle_<timestamp>.log``
     - one per invocation, so runs never overwrite each other
   * - ``process_face_cycle.pid``
     - fixed name: pid, start time, log path, host, command

The PID file is removed however the run ends. A second cycle refuses to start
while the recorded pid is alive, since two cycles on one face would race on the
same directory; a stale file from a crashed run is detected and cleared.

.. code-block:: bash

   cat ../../logs_C36S10/process_face_cycle.pid
   ps -o pid,etime,stat,args -p "$(awk -F= '/^pid=/ {print $2}' \
       ../../logs_C36S10/process_face_cycle.pid)"

Pass ``--stop-file`` from the start. Without it there is no graceful exit, and
killing mid-face leaves the work half-done.

.. warning::

   ``run_imi.sh`` sources ``CondaFile`` and then runs ``conda activate``. Many
   ``.bashrc`` files open with ``[[ $- != *i* ]] && return``, which makes them a
   no-op under ``nohup``: conda never initialises and the run dies at
   activation. Check before backgrounding anything:

   .. code-block:: bash

      bash -c 'source ~/.bashrc; conda activate imi-gchp && echo OK'

   If that fails, point ``CFG_CondaFile`` at
   ``$HOME/miniconda3/etc/profile.d/conda.sh`` instead — the same file
   ``CONDA_SH`` uses, and it carries no interactivity guard.

On a login node this process mostly sleeps, waiting on ``sbatch -W``, so it is
undemanding; ``tmux`` or ``screen`` is the more conventional choice if you would
rather keep it attachable.

Holding Work Back
^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Control
     - Effect
   * - ``--stop-file PATH``
     - halts the whole loop between faces
   * - ``STOP_PROCESSING`` in a face's run directory
     - holds back that one face

The per-face file sits beside ``inversion/``. It is checked after the download
and again immediately before the prune, so it can be dropped in while a face is
still processing and will still stop it before anything is deleted. It is not
in the upload list, so it stays local and never reaches the bucket.

What Gets Uploaded
^^^^^^^^^^^^^^^^^^

Step 7 uploads an explicit list, not "everything except ``OutputDir``":

.. code-block:: text

  jacobian_runs/*/OverpassDiagnostics/*
  inversion/data_converted/*
  inversion/data_visualization/*
  inversion/data_converted_manifest.json
  CS_grids/overpass_sample_utc_hour.nc
  .overpass_complete.*  .inversion_complete.*
  config_*.yml  imi_output.log  .outputdir_pruned.json

A downloaded file carries a local mtime newer than its S3 object, so a
whole-face sync would push ``Restarts/``, the rest of ``CS_grids/`` and
``StateVector.nc`` back into the bucket they came from. Those are already
archived and are left alone.

``CS_grids/overpass_sample_utc_hour.nc`` is the exception worth naming: it is
built on the first overpass run from an ``OutputDir`` file the prune later
deletes, so once a face is fully pruned it cannot be regenerated.

Manual: Step by Step
--------------------

The same sequence, run by hand, for a single face:

.. code-block:: bash

   cd scripts/postprocess
   FACE=T005
   CFG=../../configs_C36S10/config_${FACE}.yml

   # 1. download
   ./fetch_from_s3.sh face ${FACE}

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
   rm -rf "${CFG_OutputPath}/Global_1yr_2025_C36S10_${FACE}"

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
