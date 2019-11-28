"""
Module for handling linelist data from the VALD3 database (http://vald.astro.uu.se/).


"""
import logging
from io import StringIO
import re

import numpy as np
import pandas as pd
from astropy import units as u

from .abund import Abund
from .linelist import FileError, LineList
from .util import air2vac, vac2air

logger = logging.getLogger(__name__)


class ValdError(FileError):
    """ Vald Data File Error """


class ValdFile:
    """Atomic data for a list of spectral lines.
    """

    def __init__(self, filename, medium="vac"):
        self._filename = filename
        self._wavelo = None
        self._wavehi = None
        self._nlines = None
        self._nlines_proc = None
        self._vmicro = None
        self.medium = None
        self.desired_medium = medium
        self.unit = None
        self._read(filename)

    @property
    def filename(self):
        """str: Source filename """
        return self._filename

    @property
    def n(self):
        """int: number of spectral lines """
        return self._nlines

    @property
    def linelist(self):
        """LineList: LineList data """
        return self._linelist

    @property
    def valdatmo(self):
        """str: Atmopshere used by Vald """
        return self._valdatmo

    @property
    def abund(self):
        """Abund: Elemental abundances used by Vald """
        return self._abund

    @staticmethod
    def read(filename):
        """
        Read line data file from the VALD extract stellar service

        Parameters
        ----------
        filename : str
            Name of the VALD linelist file to read

        Returns
        -------
        vald : ValdFile
            Parsed vald file
        """
        return ValdFile(filename)

    def _read(self, filename):
        logger.info("Loading VALD file %s", filename)

        with open(filename, "r") as file:
            lines = file.readlines()

        self.parse_header(lines[0])
        self.parse_columns(lines[2])
        # TODO how to recognise extended format
        fmt = "long" if lines[4][:2] == "' " else "short"

        try:
            if fmt == "long":
                linedata = lines[3 : 3 + self.n * 4]
                atmodata = lines[3 + self.n * 4]
                abunddata = lines[4 + self.n * 4 : 22 + self.n * 4]
            elif fmt == "short":
                linedata = lines[3 : 3 + self.n]
                atmodata = lines[3 + self.n]
                abunddata = lines[4 + self.n : 22 + self.n]
        except IndexError:
            msg = "Linelist file is shorter than it should be according to the number of lines. Is it incomplete?"
            logger.error(msg)
            raise IOError(msg)

        self._linelist = self.parse_linedata(linedata, fmt=fmt)
        self._valdatmo = self.parse_valdatmo(atmodata)
        self._abund = self.parse_abund(abunddata)

    def parse_header(self, line):
        """
        Parse header line from a VALD line data file
        and sets the internal parameters

        Parameters
        ----------
        line : str
            header line of a vald file

        Raises
        ------
        ValdError
            If the header is not understood
        """
        words = [w.strip() for w in line.split(",")]
        if len(words) < 5 or words[5] != "Wavelength region":
            raise ValdError(f"{self._filename} is not a VALD line data file")
        try:
            self._wavelo = float(words[0])
            self._wavehi = float(words[1])
            self._nlines = int(words[2])
            self._nlines_proc = int(words[3])
            self._vmicro = float(words[4])
        except:
            raise ValdError(f"{self._filename} is not a VALD line data file")

    def parse_columns(self, line):
        match = re.search("WL_(air|vac)\((.*?)\)", line)
        medium = match.group(1)
        unit = match.group(2)

        match = re.search("E_low\((.*?)\)", line)
        energy_unit = match.group(1)

        if medium == "air":
            self.medium = "air"
        elif medium == "vac":
            self.medium = "vac"
        else:
            raise ValueError(
                "Could not determine the medium that the wavelength is based on (air or vacuum)"
            )

        if unit == "A":
            self.unit = u.AA
        elif unit == "nm":
            self.unit = u.AA
        elif unit == "cm^-1":
            self.unit = 1 / u.cm
        else:
            raise ValueError("Could not determine the unit of the wavelength")

        if energy_unit == "eV":
            self.energy_unit = u.eV
        elif energy_unit == "cm^-1":
            self.energy_unit = 1 / u.cm
        else:
            raise ValueError("could not determine the unit of the energy levels")

        # columns = re.split("\s\s+", line)
        # return columns

    def parse_linedata(self, lines, fmt="short"):
        """Parse line data from a VALD line data file

        Parameters
        ----------
        lines : list of str
            lines of the input data file
        fmt : {"short", "long"}, optional
            linelist format, short format has one
            line of data per spectral line, while the
            long format uses four lines per spectral line.
            The default is "short"

        Returns
        -------
        linelist : LineList
            the parsed linelist
        """

        if fmt == "short":
            names = [
                "species",
                "wlcent",
                "excit",
                "vmic",
                "gflog",
                "gamrad",
                "gamqst",
                "gamvw",
                "lande",
                "depth",
                "reference",
            ]

        elif fmt == "long":
            names = [
                "species",
                "wlcent",
                "gflog",
                "excit",
                "j_lo",
                "e_upp",
                "j_up",
                "lande_lower",
                "lande_upper",
                "lande",
                "gamrad",
                "gamqst",
                "gamvw",
                "depth",
            ]
            term_lower = lines[1::4]
            term_upper = lines[2::4]
            comment = lines[3::4]
            lines = lines[::4]

        data = StringIO("".join(lines))
        linelist = pd.read_csv(
            data,
            sep=",",
            names=names,
            header=None,
            quotechar="'",
            skipinitialspace=True,
            usecols=range(len(names)),
        )

        if fmt == "long":
            # Convert from cm^-1 to eV
            if self.energy_unit == 1 / u.cm:
                conversion_factor = 8065.544
                linelist["excit"] /= conversion_factor
                linelist["e_upp"] /= conversion_factor

            comment = [c.replace("'", "").strip() for c in comment]
            linelist["reference"] = comment

            # Parse energy level terms
            term_lower = [t.replace("'", "").split(maxsplit=1) for t in term_lower]
            term_upper = [t.replace("'", "").split(maxsplit=1) for t in term_upper]
            term_lower = [t[-1][:-1] if len(t) != 0 else "" for t in term_lower]
            term_upper = [t[-1][:-1] if len(t) != 0 else "" for t in term_upper]

            linelist["term_lower"] = term_lower
            linelist["term_upper"] = term_upper

            # extract error data
            error = np.array([s[:10].strip() for s in comment])
            error = LineList.parse_line_error(error, linelist["depth"])
            linelist["error"] = error

        # Convert from whatever unit to Angstrom
        factor = self.unit.to(u.AA)
        linelist["wlcent"] *= factor
        self.unit = "Angstrom"

        if self.medium == "air" and self.desired_medium == "vac":
            linelist["wlcent"] = air2vac(linelist["wlcent"])
            self.medium = "vac"
        elif self.medium == "vac" and self.desired_medium == "air":
            linelist["wlcent"] = vac2air(linelist["wlcent"])
            self.medium = "air"

        linelist = LineList(linelist, lineformat=fmt)

        return linelist

    def parse_valdatmo(self, line):
        """Parse VALD model atmosphere line from a VALD line data file

        Parameters
        ----------
        line : str
            line form the model atmosphere

        Returns
        -------
        atmo : str
            Name of the model atmosphere

        Raises
        ------
        ValdError
            If the line is not from a model atmosphere
        """
        lstr = line.strip()
        if lstr[0] != "'" or lstr[-2:] != "',":
            raise ValdError(f"error parsing model atmosphere: {lstr}")
        return lstr[1:-2]

    def parse_abund(self, lines):
        """Parse VALD abundance lines from a VALD line data file

        Parameters
        ----------
        lines : list of str
            Lines containing the VALD abundance data

        Returns
        -------
        abund : Abund
            Parsed abundance data

        Raises
        ------
        ValdError
            If the data could not be parsed
        """
        abstr = "".join(["".join(line.split()) for line in lines])
        words = [w[1:-1] for w in abstr.split(",")]
        if len(words) != 100 or words[99] != "END":
            raise ValdError(f"Error parsing abundances: {abstr}")
        pattern = [w.split(":") for w in words[:-1]]
        pattern = {el: float(ab) for el, ab in pattern}
        monh = 0
        return Abund(monh, pattern, type="sme")
