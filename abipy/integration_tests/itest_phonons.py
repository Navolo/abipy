"""Integration tests for phonon flows."""
from __future__ import print_function, division, unicode_literals

import pytest
import numpy as np
import abipy.data as abidata
import abipy.abilab as abilab

from abipy.core.testing import has_abinit


# Tests in this module require abinit >= 7.9.0 and pseudodojo.
pytestmark = pytest.mark.skipif(not has_abinit("7.9.0"), reason="Requires abinit >= 7.9.0")


def scf_ph_inputs(tvars):
    """
    This function constructs the input files for the phonon calculation:
    GS input + the input files for the phonon calculation.
    """
    # Crystalline AlAs: computation of the second derivative of the total energy
    structure = abidata.structure_from_ucell("AlAs")
    pseudos = abidata.pseudos("13al.981214.fhi", "33as.pspnc")

    # List of q-points for the phonon calculation (4,4,4) mesh.
    qpoints = [
             0.00000000E+00,  0.00000000E+00,  0.00000000E+00,
             2.50000000E-01,  0.00000000E+00,  0.00000000E+00,
             5.00000000E-01,  0.00000000E+00,  0.00000000E+00,
             2.50000000E-01,  2.50000000E-01,  0.00000000E+00,
             5.00000000E-01,  2.50000000E-01,  0.00000000E+00,
            -2.50000000E-01,  2.50000000E-01,  0.00000000E+00,
             5.00000000E-01,  5.00000000E-01,  0.00000000E+00,
            -2.50000000E-01,  5.00000000E-01,  2.50000000E-01,
            ]

    qpoints = np.reshape(qpoints, (-1,3))

    # Global variables used both for the GS and the DFPT run.
    global_vars = dict(nband=4,
                       ecut=3.0,
                       ngkpt=[4, 4, 4],
                       shiftk=[0, 0, 0],
                       tolvrs=1.0e-8,
                       paral_kgb=tvars.paral_kgb,
                    )

    inp = abilab.AbiInput(pseudos=pseudos, ndtset=1+len(qpoints))

    inp.set_structure(structure)
    inp.set_variables(**global_vars)

    for i, qpt in enumerate(qpoints):
        # Response-function calculation for phonons.
        inp[i+2].set_variables(
            nstep=20,
            rfphon=1,        # Will consider phonon-type perturbation
            nqpt=1,          # One wavevector is to be considered
            qpt=qpt,         # This wavevector is q=0 (Gamma)
            )

            #rfatpol   1 1   # Only the first atom is displaced
            #rfdir   1 0 0   # Along the first reduced coordinate axis
            #kptopt   2      # Automatic generation of k points, taking

    # Split input into gs_inp and ph_inputs
    return inp.split_datasets()


def itest_phonon_flow(fwp, tvars):
    """
    Create an `AbinitFlow` for phonon calculations:

        1) One workflow for the GS run.

        2) nqpt workflows for phonon calculations. Each workflow contains
           nirred tasks where nirred is the number of irreducible phonon perturbations
           for that particular q-point.
    """
    if tvars.paral_kgb == 1:
        pytest.xfail("Phonon flow with paral_kgb==1 is expected to fail (implementation problem)")

    all_inps = scf_ph_inputs(tvars)
    scf_input, ph_inputs = all_inps[0], all_inps[1:]

    flow = abilab.phonon_flow(fwp.workdir, fwp.manager, scf_input, ph_inputs)
    flow.build_and_pickle_dump()

    t0 = flow[0][0]
    t0.start_and_wait()

    flow.check_status()
    assert t0.status == t0.S_OK
    flow.show_status()

    for work in flow[1:]:
        for task in work:
            task.start_and_wait()
            assert task.status == t0.S_DONE

    flow.check_status()
    flow.show_status()

    # We should have a DDB files with IFC(q) in work.outdir
    ddb_files = []
    for work in flow[1:]:
        ddbs = work.outdir.list_filepaths(wildcard="*DDB")
        assert len(ddbs) == 1
        ddb_files.append(ddbs[0])

    # TODO: Check automatic restart
    assert all(work.finalized for work in flow)
    assert flow.all_ok

    # Merge the DDB files
    out_ddb = flow.outdir.path_in("flow_DDB")
    ddb_path = abilab.Mrgddb().merge(ddb_files, out_ddb=out_ddb, description="DDB generated by %s" % __file__,
                                     cwd=flow.outdir.path)
    assert ddb_path == out_ddb

    # Build new workflow with Anaddb tasks.
    # Construct a manager with mpi_ncpus==1 since  anaddb do not support mpi_ncpus > 1 (except in elphon)
    shell_manager = fwp.manager.to_shell_manager(mpi_ncpus=1)
    awork = abilab.Workflow(manager=shell_manager)

    # Phonons bands and DOS with gaussian method
    anaddb_input = abilab.AnaddbInput.phbands_and_dos(
        scf_input.structure, ngqpt=(4, 4, 4), ndivsm=5, nqsmall=10, dos_method="gaussian: 0.001 eV")

    atask = abilab.AnaddbTask(anaddb_input, ddb_node=ddb_path, manager=shell_manager)
    awork.register(atask)

    # Phonons bands and DOS with gaussian method
    anaddb_input = abilab.AnaddbInput.phbands_and_dos(
        scf_input.structure, ngqpt=(4, 4, 4), ndivsm=5, nqsmall=10, dos_method="tetra")

    atask = abilab.AnaddbTask(anaddb_input, ddb_node=ddb_path, manager=shell_manager)
    awork.register(atask)

    flow.register_work(awork)
    flow.allocate()
    flow.build()

    for i, atask in enumerate(awork):
        print("about to run anaddb task: %d" % i)
        atask.start_and_wait()
        assert atask.status == atask.S_DONE
        atask.check_status()
        assert atask.status == atask.S_OK

        # TODO: output files are not produced in outdir
        #assert len(atask.outdir.list_filepaths(wildcard="*PHBST.nc")) == 1
        #assert len(atask.outdir.list_filepaths(wildcard="*PHDOS.nc")) == 1

