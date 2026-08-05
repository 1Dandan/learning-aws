.. _imi-pruning-overview:

Concepts: Markers, Cutoff, and Why Pruning Is Safe
===================================================

This page explains *why* the procedure works. The step-by-step instructions are
separate: :ref:`imi-pruning-local` and :ref:`imi-pruning-aws`.

The Problem
-----------

A one-year global ensemble at C36S10 produces roughly 220 target faces, each
holding hundreds of Jacobian run directories. Nearly all of the storage is
``jacobian_runs/*/OutputDir``: hourly 3D GEOS-Chem fields, written so that two
postprocessing steps can consume them.

- **Satellite overpass diagnostics** sample those fields at local overpass
  time, producing ``OverpassDiagnostics/``
- **The inversion** applies the TROPOMI operator, producing
  ``inversion/data_converted/``

Both products are a small fraction of the input. Once they exist and are
verified, the input is referenced by nothing, and 168 TB can become a fraction
of that.

The difficulty is not *how* to delete. It is knowing, without inspecting 220
faces by hand, that deleting is safe.

.. warning::

   ``OutputDir`` cannot be regenerated without re-running the GEOS-Chem
   simulations. Every deletion is permanent.

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

The Two Markers
---------------

Each processing stage writes an empty marker into the run directory on
successful completion::

  .overpass_complete.20250101_20250815
  .inversion_complete.20250101_20250815

The name carries the window covered. ``S`` grows as runs advance, so writing a
new marker removes the superseded one: a face holds exactly two markers, never
two per round.

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
#. Every Jacobian run holds an overpass file for every date in the window,
   compared as an explicit set rather than a count. A count still matches when
   one date is missing and another is duplicated.
#. ``inversion/data_converted`` agrees with its manifest.

Every one of these is a path check. Nothing reads file contents, so the prune
behaves identically wherever it runs and costs nothing at scale.

Any failure blocks that face and leaves it untouched. A per-face
``.outputdir_pruned.json`` records what was removed and when, which also makes
a re-run a no-op.

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
