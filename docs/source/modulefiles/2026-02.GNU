#%Module1.0####################################################################

proc ModulesHelp { } {
    puts stderr "GEOS-Chem High Performance (GCHP) build and runtime environment (GNU/OpenMPI)."
}

module-whatis "GCHP build and runtime dependencies (GNU/OpenMPI)"

# ---- Core stack ----
if { ![is-loaded openmpi/4.1.7] } {
    module load openmpi/4.1.7
}
if { ![is-loaded cmake/4.2.3] } {
    module load cmake/4.2.3
}
if { ![is-loaded hdf5/1.14.6] } {
    module load hdf5/1.14.6
}
if { ![is-loaded netcdf-c/4.9.3] } {
    module load netcdf-c/4.9.3
}
if { ![is-loaded netcdf-fortran/4.6.2] } {
    module load netcdf-fortran/4.6.2
}
if { ![is-loaded esmf/8.6.1] } {
    module load esmf/8.6.1
}

if { ![is-loaded udunits/2.2.28] } {
    module load udunits/2.2.28
}
if { ![is-loaded nco/5.2.8] } {
    module load nco/5.2.8
}
if { ![is-loaded cdo/2.5.4] } {
    module load cdo/2.5.4
}

setenv COMPILER GNU
setenv CC   gcc
setenv CXX  g++
setenv FC   gfortran
setenv F90  gfortran
setenv F77  gfortran

setenv ESMF_COMM openmpi

setenv OMP_NUM_THREADS 1

# Version tag
set version 2026.02-GNU
setenv GCHP_ENV_VERSION $version
