.. _imi-pruning-overview:

Concepts: Markers, Cutoff, and Why Pruning Is Safe
===================================================

This page explains *why* the procedure works. The step-by-step instructions are
separate: :ref:`imi-pruning-local` and :ref:`imi-pruning-aws`.

The Problem
-----------

A one-year global ensemble at C36S10 has 220 target faces. Each face holds up
to seven Jacobian run directories: state vector elements are grouped
``NumJacobianTracers`` at a time, so at 200 tracers per run a face with 1296
elements needs seven runs, and a small face with 47 elements needs one.

Nearly all of the storage is ``jacobian_runs/*/OutputDir``: hourly 3D
GEOS-Chem fields, written so that two postprocessing steps can consume them.

- **Satellite overpass diagnostics** sample those fields at local overpass
  time, producing ``OverpassDiagnostics/``
- **The inversion** applies the TROPOMI operator, producing
  ``inversion/data_converted/``

``OutputDir`` **is temporary.** It exists only so those two steps can run, and
it has to be deleted once they have. Left in place it is what makes the bucket
unmanageable: 168 TB at present, and growing with every face that finishes.
The products that replace it are a small fraction of that.

The difficulty is not *how* to delete. It is knowing, without inspecting 220
faces by hand, that deleting is safe.

.. warning::

   ``OutputDir`` cannot be regenerated without re-running the GEOS-Chem
   simulations. Every deletion is permanent.

Directory Layout
----------------

Per target face, under ``OutputPath``:

.. code-block:: text

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
  ├── .overpass_complete.<StartDate>_S<S>   <- marker
  └── .inversion_complete.<StartDate>_S<S>  <- marker

The Shared End Date
-------------------

``S``, the *shared end date*, is the minimum across all Jacobian runs of each
run's latest checkpoint. It is the date to which **every** run has progressed,
and all the date arithmetic keys off it.

Overpass output for local date ``L`` reads ``OutputDir`` for both ``L`` and
``L+1``. So while runs are still advancing:

- ``OutputDir`` holds UTC dates through ``S-1``
- overpass output can therefore only reach local date ``S-2``
- the earliest work a later round can do is local date ``S-1``, which needs
  ``OutputDir`` from ``S-1`` onward

**Files dated** ``S-2`` **or earlier are referenced by nothing.** That is the
cutoff. Once ``S`` reaches ``EndDate`` there is no further day to wait for, and
the cutoff becomes ``EndDate-1``.

The inversion is looser: with ``SatDiagOperator: false`` it reads UTC dates up
to ``S-1``, and its next round starts at ``S``.

``S`` tracks *progress*, not *intent*. It can exceed ``EndDate`` if ``EndDate``
is lowered below what has already been simulated, so a sub-range inversion of a
complete ensemble needs a reworked precomputed-Jacobian path rather than a
narrowed ``EndDate``.

The Two Markers
---------------

Each processing stage writes an empty marker into the run directory on
successful completion:

.. code-block:: text

  .overpass_complete.20250101_S20250815
  .inversion_complete.20250101_S20250815

The fields are the configured ``StartDate`` and the shared end date the stage
ran against. They are **not** a coverage range: overpass output spans local
dates ``StartDate-1`` to ``S-2``, while ``data_converted`` spans granule dates
``StartDate`` to ``S-1``. The ``S`` prefix keeps the second field from reading
as an end date.

What the two markers share is ``S``, which is the point of putting it there.
``S`` grows as runs advance, so writing a new marker removes the superseded
one: a face holds exactly two markers, never two per round.

Pruning requires **both markers, carrying the same** ``S``. The cutoff is taken
from the marker, never recomputed from the checkpoints as they stand at prune
time — recomputing would delete past what the markers actually cover. This is
the single easiest thing to get wrong.

The data_converted Manifest
---------------------------

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
no pickle is otherwise indistinguishable from one never processed, so
completeness could only be inferred from which dates happen to have output, and
any such rule either accepts real gaps or rejects healthy faces.

What the Prune Checks
---------------------

#. Exactly one marker per stage, both carrying the same start date and ``S``.
#. The cutoff comes from the marker's ``S``.
#. **Every** Jacobian run directory holds an overpass file for every date in
   the window, compared as an explicit set rather than a count. A count still
   matches when one date is missing and another is duplicated.
#. ``inversion/data_converted`` agrees with its manifest.

Every one of these is a path check. Nothing reads file contents, so the prune
behaves identically wherever it runs and costs nothing at scale.

Deletion is all-or-nothing per face: ``data_converted`` draws on every
Jacobian run, so one incomplete run blocks the whole face and no ``OutputDir``
file is removed from any of its runs. **Reporting** is per run, so an entirely
unprocessed run is distinguishable from one missing a single date:

.. code-block:: text

  [BLOCKED] ..._T001: 2 of 3 Jacobian run(s) have incomplete overpass output
      ..._T001_0001: complete (27)
      ..._T001_0002: 1 of 9 missing, first GEOSChem.CH4col.overpass.20250104_1330.nc4
      ..._T001_0003: NONE of 9 present -- this run was never processed

The base run expects three files per date, the sampled ``SpeciesConc`` and
``StateMetLevEdge`` collections on top of ``CH4col``, so its count is higher
than the others'. The expected counts are derived per run rather than assumed
uniform.

A failure blocks that face and leaves it untouched. A per-face
``.outputdir_pruned.json`` records what was removed and when, which also makes
a re-run a no-op.

What Gets Deleted
-----------------

Once those checks pass, two things go, both gated identically:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Path
     - Rule
   * - ``jacobian_runs/*/OutputDir/GEOSChem.*.nc4``
     - dated at or before the cutoff
   * - ``jacobian_runs/*/Restarts/gcchem_internal_checkpoint.*.nc4``
     - dated **strictly before** ``S``, and never a run's newest

Why Checkpoints Are Kept From ``S`` Onward
------------------------------------------

Checkpoints exist to re-simulate, and re-simulation is the only repair for a
corrupt ``OutputDir`` file. So which ones to keep follows from which
``OutputDir`` data has actually been validated.

**Dates through** ``S-1`` **were opened during processing.** Overpass sampling
of local date ``L`` reads ``OutputDir`` for ``L`` and ``L+1`` and runs to
``L = S-2``, so it touches ``S-1``; the inversion reads granules to ``S-1``
too. Corruption in that range would already have surfaced. Deleting the
checkpoints below ``S`` therefore gives up the ability to regenerate only data
that has been read.

**Dates at or after** ``S`` **were never opened.** They exist only in runs that
ran ahead of the others, and the prune retains them, since the cutoff is
``S-2``. Keeping every checkpoint from ``S`` onward is what preserves the
ability to re-simulate that unvalidated tail.

The rule is *strictly* before ``S``, not at or before, and the difference
matters. ``S`` is the minimum across runs of each run's maximum, so the slowest
run's newest checkpoint is dated exactly ``S``. A rule of ``<= S`` would strip
that run of every checkpoint, and ``get_shared_end_date`` would fall back to
``StartDate`` and raise — breaking every later run on the face.

With ``S = 20250110``:

.. code-block:: text

  run _0001 (ahead)    20250103 20250106 20250110 20250113 20250116
    keeps                                20250110 20250113 20250116

  run _0002 (slowest)  20250103 20250106 20250110
    keeps                                20250110

.. note::

   ``get_shared_end_date`` reads exactly this file set, taking the maximum per
   run and the minimum across runs. Every run's maximum is ``>= S``, so it is
   always kept and ``S`` is unchanged by pruning. Were that not so, pruning
   would move the very date every marker and cutoff is pinned to.

``--keep-checkpoints N`` sets how many newest are kept regardless of date
(default 1); ``0`` disables checkpoint pruning altogether.

Checking ``OutputDir`` Before Pruning
--------------------------------------

``check_outputdir_integrity.py`` reads every ``OutputDir`` file — opening it,
finding a float variable, and reading from both ends — and reports any that
cannot be read. Reading both ends is the point: HDF5 keeps metadata at the
front, so a truncated file opens cleanly and only fails when a chunk near the
end is touched.

.. code-block:: bash

   ./check_outputdir_integrity.py ../../configs_C36S10/config_T005.yml > corrupt.txt
   ./check_outputdir_integrity.py ../../configs_C36S10/config_T005.yml --sample 0.05

It is a readability check, not a completeness one: no NaN scan, no date
coverage. Run it before pruning, while an earlier checkpoint could still
repair what it finds. ``--sample`` gives a quick look for systematic damage;
only a full scan proves every file readable.

Until a face has come through it cleanly, ``--keep-checkpoints 0`` keeps every
checkpoint. They are one file per run per date, a rounding error beside
``OutputDir``, and they are the only insurance against corruption that the
processing steps did not touch.

.. warning::

   **Faces processed before the run-indexing fix are missing their last
   Jacobian run's overpass output.** The driver derived its loop bound from the
   *number* of run directories rather than their names, so with
   ``DisableRun0000: true`` it stopped one short; a single-run face got nothing.

   ``data_converted`` is unaffected. Re-run the overpass step for those faces:
   already-written files are skipped, so only the missing run is computed, and
   the marker is written once the whole face is complete. A face processed
   before markers existed simply has none, so the prune blocks it until then.

Why Freshly Written Data Need Not Be Re-Verified
-------------------------------------------------

Content verification is a one-time step, applied only to data that has
round-tripped through storage. Data produced by the current pipeline is written
by code that:

- **cannot leave a partial file** — every diagnostic is written to a temporary
  file and moved into place atomically
- **cannot write a silent all-NaN file** — a missing ``OutputDir`` input for a
  date inside the simulation window is a hard error, not an empty result
- **never rewrites a finished file** — completed output is skipped

The second guard is what makes pruning safe at all. Without it, a later run
over a pruned date would regenerate the overpass file as silent all-NaN rather
than failing, and that corruption would be indistinguishable from real output.

Corruption therefore does not originate in the writer. It originates in the
storage round trip, which is what the verification step is for, and why it is
needed once and then not again.

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
re-run. The overpass archive restores that option: under
``SatDiagOperator: true`` it is the input from which ``data_converted`` can be
recomputed, long after ``OutputDir`` is gone.

``jacobian.py`` adjusts the granule bound accordingly. A granule dated ``D``
carries observations whose local date is ``D`` or ``D-1``, since local time is
UTC + lon/15 across a 24-hour span. Under ``SatDiagOperator: true`` the
operator opens one overpass file per local date, and overpass output stops at
``S-2`` while runs advance, so granules dated ``S-1`` would ask for a file that
cannot exist yet. The bound drops one further day in that mode, and the two
modes coincide once ``S`` reaches ``EndDate``.

To recompute ``data_converted`` from the archive you need, besides
``OverpassDiagnostics``: the TROPOMI granules, ``StateVector.nc``, and
``CS_grids/``. The prune only ever removes ``OutputDir``, so these survive it,
but they must also survive whatever else is done to shrink storage.

Verifying Uploads
-----------------

An object's ``ETag`` equals its MD5 only for single-part uploads. ``aws s3 cp``
goes multipart above 8 MB, after which the ``ETag`` is an MD5 of part MD5s with
a ``-N`` suffix and will never match a local ``md5sum``. Compare **sizes**
instead: authoritative for truncation, and no download needed.

The upload is already integrity-checked end to end: the CLI sends a per-part
checksum and S3 rejects any part that does not match, so a successful ``sync``
proves the bytes landed intact. For a true hash comparison with no download,
upload with ``--checksum-algorithm CRC32C`` and read it back with
``head-object --checksum-mode ENABLED``.
