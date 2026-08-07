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

.. _one-time-configuration:

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

Settings that belong to one machine rather than to the workflow — the bucket,
site paths — go in ``local_env.local.sh``, which ``local_env.sh`` sources at the
end and ``.gitignore`` excludes. Keeping them out of the tracked file means the
repository stays portable, and anything you would rather not publish stays
unpublished:

.. code-block:: bash

   S3_BUCKET="dzhang-imi-gchp-output"

``run_face_local.sh`` refuses to start while any path still points at
``/fsx_input`` or ``/fsx_output``, or does not exist.

.. _shell-variables:

Shell Variables Used Below
--------------------------

Every example on this page uses these. Set them once per session, so a bucket
or face name is never retyped into a command that deletes things:

.. code-block:: bash

   cd scripts/postprocess
   source local_env.sh                    # defines S3_BUCKET, via local_env.local.sh

   BUCKET="$S3_BUCKET"
   FACE=T005
   CFG=../../configs_C36S10/config_${FACE}.yml

Taking the bucket from ``local_env.local.sh`` keeps the one machine-specific
name in one place, rather than repeated across a page where several of the
commands delete things. Check it arrived before relying on it::

   echo "$BUCKET"
   dzhang-imi-gchp-output

An empty result means ``local_env.local.sh`` is missing or does not set
``S3_BUCKET`` — see :ref:`one-time-configuration`.

``BUCKET`` need not be given at all on a configured machine. Every script
sources ``local_env.sh`` before deciding, so ``S3_BUCKET`` supplies it:

.. code-block:: bash

   ./process_face_cycle.sh T001 --execute            # same as passing it

``process_face_cycle.sh`` also tests whether its first argument *looks like a
face* (``T001``, ``1``) before treating it as a bucket, so an empty ``${BUCKET}``
collapsing on expansion cannot shift the arguments along — which is how a
missing bucket used to surface as a complaint about an unrelated filename.

Passing one explicitly overrides ``S3_BUCKET``, which is useful for a one-off
against a different bucket but means a typo silently wins.

Optional Settings
-----------------

All in ``local_env.sh``, or ``local_env.local.sh`` to keep them off the
repository.

**Skipping verification on a marked face.** Step 3 reads every overpass file
and every pickle, which is the most expensive thing the cycle does after the
transfers. A completion marker is only written by the current code, which
writes each file to a temporary name and renames it — so a file bearing its
final name under a marker cannot be partial, and checking it again confirms
what is already established.

.. code-block:: bash

   VERIFY_IF_MARKED="false"   # default: skip a marked face
   VERIFY_IF_MARKED="true"    # check regardless

.. warning::

   A marker attests that the stage **finished**, not that every file under it
   was written atomically — neither producer rewrites a file it finds already
   present. And the marker travels with the data, so it says nothing about
   whether the transfer from S3 was clean, which is a different failure and the
   one that produced a truncated regridding weight file.

   What makes skipping safe is having verified every face **once** beforehand.
   After that, a file present is either already checked or newly written.

**Running the heavy steps on a compute node.** Steps 1, 3 and 7 move bytes;
the rest are light. On a login node the first three are what you want elsewhere.

.. code-block:: bash

   SLURM_STEPS="1 3 7"
   SLURM_STEP_CPUS="4"
   SLURM_STEP_MEM="16G"
   SLURM_STEP_TIME="0-6:00"
   SLURM_STEP_PARTITION="shared,unrestricted"

Each step is submitted with ``sbatch -W`` and waited on, so the cycle blocks
exactly as before. ``run_on_slurm.sh`` keeps stdout as stdout and stderr as
stderr, which matters because ``check_overpass_complete.py`` writes the paths
to delete on the first and its report on the second.

Only correct where compute nodes can reach S3. Check before enabling:

.. code-block:: bash

   srun -p shared -t 5 --pty bash -c \
       'source ~/.bashrc; conda activate aws; aws s3 ls s3://BUCKET/ | head -3'

**Verification tuning.**

.. code-block:: bash

   CHECK_WORKERS="4"     # parallel readers
   CHECK_TIMEOUT="600"   # seconds before one file's read is abandoned

Fetching From S3
----------------

``fetch_from_s3.sh`` lives inside the tree it fetches, so the first copy on a
new machine has to come down by hand:

.. code-block:: bash

   aws s3 sync s3://${BUCKET}/imi-gchp/ /path/to/process-imi-aws/imi-gchp/ \
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
   ./fetch_from_s3.sh code --scripts        # only src/ and scripts/postprocess/
   ./fetch_from_s3.sh face T005 --dry-run   # size and free space, no transfer
   ./fetch_from_s3.sh face T005 --quiet     # errors only, for a short log
   ./fetch_from_s3.sh face T005

``--scripts`` is the one to use for picking up a code change between runs: it
syncs only ``src/`` and ``scripts/postprocess/`` — a few megabytes rather than
several gigabytes — and restores the executable bits afterwards, which
``restore_git_modes.sh`` cannot do for untracked files. It holds back
``local_env.local.sh``, so this machine's bucket and paths survive the fetch.

Each face reports its remote size against local free space before transferring,
so a full filesystem surfaces before a multi-hundred-gigabyte copy rather than
during one.

.. warning::

   Face transfers pass ``--no-follow-symlinks`` and exclude ``satellite_data``.
   Both matter. ``satellite_data`` is a link to the whole TROPOMI archive, and
   without the first flag ``aws s3 sync`` walks the destination *through* it,
   comparing hundreds of thousands of files it will never transfer — and
   aborting with ``File does not exist`` when one moves mid-walk. The exclude
   then stops the 26-byte link object being written onto a symlink that points
   at a directory. Nothing is stored under that prefix in S3; ``run_imi.sh``
   recreates the link from ``DataPathTROPOMI``.

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
   ./process_face_cycle.sh ${BUCKET} T001

Then for real:

.. code-block:: bash

   ./process_face_cycle.sh ${BUCKET} T001 --execute

Several faces in sequence, with a way to stop cleanly between them:

.. code-block:: bash

   ./process_face_cycle.sh ${BUCKET} T001 T002 T003 --execute \
       --stop-file /tmp/STOP_CYCLE

   # or from a file, one face per line
   ./process_face_cycle.sh ${BUCKET} --faces-file faces.txt --execute

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
     - check overpass files and ``data_converted`` pickles that came from S3 —
       each skipped when its completion marker is present
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
  CS_grids/*                              (second pass, --size-only)
  overpass_complete.*  inversion_complete.*
  imi_output.log  outputdir_pruned.json

A downloaded file carries a local mtime newer than its S3 object, so a
whole-face sync would push ``Restarts/`` and ``StateVector.nc`` back into the
bucket they came from. Those are already archived and are left alone.

``CS_grids/overpass_sample_utc_hour.nc`` is the exception worth naming: it is
built on the first overpass run from an ``OutputDir`` file the prune later
deletes, so once a face is fully pruned it cannot be regenerated.

The rest of ``CS_grids/`` goes up in a second pass using ``--size-only``. It all
came down from the bucket, so every local copy has a newer mtime and a normal
sync would re-upload the lot on every face; comparing size alone uploads only
what actually differs — which is exactly the weight files the operator had to
rebuild, since a truncated file and a good one differ in length. Uploading them
means a repair is not repeated on every fetch.

.. warning::

   A weight file damaged in transit *down* that the run never read was never
   validated, and being a different size from the object it came from, it would
   be uploaded over a good copy. Without bucket versioning that is not
   reversible. The exposure is narrow — every weight file the run does read is
   validated and rebuilt by ``read_regrid_weights`` — but it is not zero.

.. _many-faces:

Many Faces at Once
------------------

``run_face_batch.sh`` keeps several cycles running and starts another as each
one finishes, until every face is done.

.. code-block:: bash

   cd scripts/postprocess

   # look first: steps 1-3 per face, nothing deleted
   ./run_face_batch.sh --faces 1-3 --concurrency 2

   # then in the background
   nohup ./run_face_batch.sh --faces 1-220 --skip T005 --concurrency 10 \
         --execute --stop-file "$PWD/STOP_BATCH" > /dev/null 2>&1 &

   tail -f ../../logs_C36S10/run_face_batch_*.log

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Control
     - Effect
   * - ``--concurrency 10``
     - cycles running at once
   * - ``--budget-tib 30``
     - ceiling on face data resident on disk
   * - ``--skip T005``
     - hold a face back; takes ``5``, ``T5`` or ``T005``
   * - ``--halt-on-failure``
     - stop starting new faces after the first failure
   * - ``--retry-failed``
     - re-attempt faces previously recorded as failed
   * - ``--stop-file PATH``
     - stop launching; running faces finish

Progress is recorded per face in ``logs_C36S10/face_batch_state.tsv``, so
re-running the same command resumes rather than reprocessing. A failed face is
recorded and the run moves on.

**The budget is measured, not accumulated.** It sums the face directories
actually on disk, because step 8 removes a face only when it succeeded — a
failed one still occupies its space, as does one left by an earlier run. If
failures fill the budget the driver reports ``STALLED`` and exits rather than
overflowing.

Several cycles coexist because each takes a **per-face lock**; two cycles on
the same face still refuse, since they would regenerate one config and prune
one directory against each other.

Stopping
--------

.. code-block:: bash

   ./stop_processing.sh                  # show what is running, change nothing
   ./stop_processing.sh --graceful       # stop between faces
   ./stop_processing.sh --now            # signal every process group
   ./stop_processing.sh --now --cancel-jobs

``--graceful`` reads each ``--stop-file`` from the PID files and touches it, so
running faces finish cleanly. ``--now`` signals **process groups**, so the
python readers, the aws transfers and the waiting ``sbatch`` go too rather than
being orphaned; it skips its own group, since a driver started without job
control shares the pgid of whatever launched it.

.. important::

   Slurm jobs are **not** cancelled unless you pass ``--cancel-jobs``. Killing a
   waiting ``sbatch -W`` only stops the waiter — the job keeps running. The
   script lists the jobs and prints the ``scancel`` command either way.

Manual: Step by Step
--------------------

The same sequence, run by hand, for a single face. Repeated here in full so the
block can be followed start to finish — see :ref:`shell-variables` for what the
first four lines do:

.. code-block:: bash

   cd scripts/postprocess
   source local_env.sh                    # defines S3_BUCKET, via local_env.local.sh

   BUCKET="$S3_BUCKET"
   FACE=T005
   CFG=../../configs_C36S10/config_${FACE}.yml

   # 1. download
   ./fetch_from_s3.sh face ${FACE}

   # 2. generate the config and preflight paths
   ./run_face_local.sh ${FACE} --dry-run

   # 3. verify what round-tripped through S3; both append to one list,
   #    because the repair is the same deletion
   ../../src/utilities/check_overpass_complete.py ${CFG} >  bad_${FACE}.txt
   ../../src/utilities/check_data_converted.py    ${CFG} >> bad_${FACE}.txt

   # 4. delete what failed, and retire the marker of whichever stage lost files
   ./delete_files_from_list.sh bad_${FACE}.txt --execute
   grep -q /OverpassDiagnostics/     bad_${FACE}.txt && rm -f <run_dirs>/overpass_complete.*
   grep -q /inversion/data_converted/ bad_${FACE}.txt && rm -f <run_dirs>/inversion_complete.*

   # 5. process; writes both markers and the manifest on success
   ./run_face_local.sh ${FACE}

   # 6. prune locally, recording what went
   ../../src/utilities/prune_outputdir.py ${CFG} --execute --record-deleted pruned_${FACE}.txt

   # 7. upload products, verify, delete retired objects
   ./s3_upload_and_prune.sh ${CFG} ${BUCKET} --deleted-list pruned_${FACE}.txt --execute

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
