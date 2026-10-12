"""Physical properties used by the CFD cases, each with its source.

Air and water properties are computed (not typed) with CoolProp, which implements
the reference formulations (air: Lemmon et al. 2000 J. Phys. Chem. Ref. Data 29:331
equation of state; Lemmon & Jacobsen 2004 Int. J. Thermophys. 25:21 viscosity and
thermal conductivity). Gas diffusivities in air are the tabulated values of
Monteith & Unsworth (2008) Principles of Environmental Physics, 3rd ed., Table A.3,
as transcribed in the photobiologyPlants R package (R/D-water-CO2.R,
github.com/aphalo/photobiologyPlants), linearly interpolated in temperature.
"""
from __future__ import annotations

import numpy as np
import CoolProp
import CoolProp.CoolProp as CP

COOLPROP = (f"CoolProp {CoolProp.__version__} (Bell et al. 2014 Ind. Eng. Chem. Res. 53:2498); air: Lemmon et al. "
            "2000 J. Phys. Chem. Ref. Data 29:331 and Lemmon & Jacobsen 2004 Int. J. Thermophys. 25:21")
MU_TABLE = ("Monteith J.L., Unsworth M.H. (2008) Principles of Environmental Physics, 3rd ed., Table A.3 "
            "(values as transcribed in photobiologyPlants R/D-water-CO2.R)")
_T = np.arange(-5, 46, 5, dtype=float)
_D_H2O = np.array([20.5, 21.2, 22.0, 22.7, 23.4, 24.2, 24.9, 25.7, 26.4, 27.2, 28.0]) * 1e-6
_D_CO2 = np.array([12.4, 12.9, 13.3, 13.8, 14.2, 14.7, 15.1, 15.6, 16.0, 16.5, 17.0]) * 1e-6
R_GAS = 8.314462618  # J mol-1 K-1, CODATA 2018 exact (SI 2019 definition)


def molar_mass_g_mol(fluid: str) -> float:
    """Molar mass from CoolProp's reference equations of state (Air, CO2, Water)."""
    return CP.PropsSI("M", fluid) * 1000.0


def D_CO2(t_c: float) -> float:
    return float(np.interp(t_c, _T, _D_CO2))


def D_H2O(t_c: float) -> float:
    return float(np.interp(t_c, _T, _D_H2O))


def air(t_c: float, p_kpa: float = 101.325) -> dict:
    T, P = t_c + 273.15, p_kpa * 1e3
    rho = CP.PropsSI("D", "T", T, "P", P, "Air")
    mu = CP.PropsSI("V", "T", T, "P", P, "Air")
    k = CP.PropsSI("L", "T", T, "P", P, "Air")
    cp = CP.PropsSI("C", "T", T, "P", P, "Air")
    return {"rho": rho, "nu": mu / rho, "k": k, "cp": cp, "Pr": mu * cp / k, "beta": 1.0 / T,
            "molar_density": P / (R_GAS * T), "T_K": T, "p_Pa": P, "source": COOLPROP,
            "beta_note": "ideal-gas expansion coefficient 1/T"}


def water(t_c: float, p_kpa: float = 101.325) -> dict:
    T, P = t_c + 273.15, p_kpa * 1e3
    rho = CP.PropsSI("D", "T", T, "P", P, "Water")
    mu = CP.PropsSI("V", "T", T, "P", P, "Water")
    return {"rho": rho, "nu": mu / rho, "Pr": CP.PropsSI("PRANDTL", "T", T, "P", P, "Water"),
            "beta": CP.PropsSI("ISOBARIC_EXPANSION_COEFFICIENT", "T", T, "P", P, "Water"),
            "cp": CP.PropsSI("C", "T", T, "P", P, "Water"), "source": f"CoolProp {CoolProp.__version__} (IAPWS)"}


def p_sat_water_kpa(t_c: float) -> float:
    """Saturation vapour pressure over liquid water (IAPWS-95 via CoolProp)."""
    return CP.PropsSI("P", "T", t_c + 273.15, "Q", 0, "Water") / 1000.0


def provenance(t_c: float, p_kpa: float = 101.325) -> dict:
    a = air(t_c, p_kpa)
    return {"T_C": t_c, "p_kPa": p_kpa, "air": {k: v for k, v in a.items() if k != "source"},
            "air_source": a["source"], "D_CO2_m2_s": D_CO2(t_c), "D_H2O_m2_s": D_H2O(t_c),
            "diffusivity_source": MU_TABLE}
