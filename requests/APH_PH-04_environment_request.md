# DRAFT - request for Advanced Plant Habitat environmental telemetry (PH-04, OSD-772)

*Not sent. To be sent by Richard Barker through the LSDA data-request page
(<https://nlsp.nasa.gov/explore/lsdahome/datarequest>) and/or the OSDR help contact page
(<https://www.nasa.gov/osdr-help-contact-us/>); both routes are linked from the OSDR Environmental
Data App. Fill in the bracketed fields before sending.*

---

**Subject:** Request for Advanced Plant Habitat chamber telemetry, PH-04 (OSD-772), flight and ground control

Dear OSDR / LSDA team,

I am requesting the environmental telemetry recorded inside the Advanced Plant Habitat (APH) during
Plant Habitat-04 (PH-04; OSDR study OSD-772; launched on SpaceX CRS-22, 3 June 2021), and from its
ground-control run.

**Purpose.** We are building computational fluid dynamics (CFD) models of the specimen environment in
spaceflight hardware, for flight (0 g) and ground-control (1 g) conditions. For APH the model is driven
by the PH-04 set-points, and it predicts the CO2 drawdown and air age in the pepper canopy. The models,
code and data are public:

- project page: <https://dr-richard-barker.github.io/Hardware_OSDR_review/>
- repository: <https://github.com/dr-richard-barker/Hardware_OSDR_review>

Chamber telemetry is the only data that can test these predictions. Cabin-level data cannot, because
it describes the air outside the habitat.

**What we checked first** (12 October 2026):
- the OSD-772 file list (221 files, all amplicon sequencing or study metadata; no environmental files);
- the OSDR hardware-registry payload record for PH-04 (`files: []`);
- the OSDR Environmental Data App, which has no PH-04 mission. Its 24 missions are Rodent Research,
  VEG-01 and APEX experiments.

**Requested data** for the whole PH-04 grow-out (flight unit and ground-control unit), at the native
logging interval, with timestamps in UTC:

1. Chamber air temperature, relative humidity and CO2 concentration, with the location of each sensor
   in the chamber.
2. CO2 control actions (injection and scrubbing events or rates) and set-point changes.
3. Fan or blower speed settings, and any measured airflow or air velocity, including where it was
   measured.
4. Lighting: LED channel settings and photosynthetic photon flux density at canopy height.
5. Science Carrier / root-zone sensors: substrate moisture, temperature and O2, if recorded.
6. ISS location of the habitat (module and rack) and, if available, cabin conditions at that location.
7. Any documentation of sensor calibration, data gaps and unit conventions.

A CSV or similar text format is ideal. If the data cannot be released openly, I would be glad to follow
the LSDA's restricted-access procedure.

If the same data exist for earlier APH experiments (PH-01 to PH-03), these would also be valuable.

Thank you for your help.

[Name, affiliation]
[Contact details]
