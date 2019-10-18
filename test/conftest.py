import pytest

from os.path import dirname, join
from scipy.constants import speed_of_light

# TODO create various kinds of default sme structures
# then run test on all of the relevant ones
from pysme.sme import SME_Struct
from pysme.vald import ValdFile
from pysme.solve import synthesize_spectrum


@pytest.fixture
def sme_empty():
    sme = SME_Struct()
    return sme


@pytest.fixture
def testcase1():
    c_light = speed_of_light * 1e-3

    # TODO get better test case for this
    cwd = dirname(__file__)
    fname = join(cwd, "testcase1.inp")
    sme = SME_Struct.load(fname)
    sme = synthesize_spectrum(sme)

    rv = 10
    x_syn = sme.wave[0] * (1 - rv / c_light)
    y_syn = sme.synth[0]
    return sme, x_syn, y_syn, rv


@pytest.fixture
def sme_2segments():
    cwd = dirname(__file__)

    sme = SME_Struct()
    sme.teff = 5000
    sme.logg = 4.4
    sme.vmic = 1
    sme.vmac = 1
    sme.vsini = 1
    sme.set_abund(0, "asplund2009", "")
    sme.linelist = ValdFile(f"{cwd}/testcase1.lin").linelist
    sme.atmo.source = "marcs2012p_t2.0.sav"
    sme.atmo.method = "grid"

    sme.wran = [[6550, 6560], [6560, 6574]]

    sme.vrad_flag = "none"
    sme.cscale_flag = "none"
    return sme
