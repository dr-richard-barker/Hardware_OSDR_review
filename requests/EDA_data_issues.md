# DRAFT - data issues found in the OSDR Environmental Data App (EDA)

*Not sent. To be sent by Richard Barker through the OSDR help contact page
(<https://www.nasa.gov/osdr-help-contact-us/>). Every item below was reproduced from the EDA API on
12 October 2026. The snapshot and code are in
<https://github.com/dr-richard-barker/Hardware_OSDR_review>: `data/raw/2026-10-12/eda/` and
`src/hwreview/eda.py`. Fill in the bracketed fields before sending.*

---

**Subject:** Possible issues in EDA telemetry (RR-1 column labels, RR-9 dates, held values)

Dear OSDR team,

While using the Environmental Data App API (`/eda/api/missions/{mission}/telemetry_data/` and
`/radiation_data/`) to set cabin conditions for hardware CFD models, I found the following. I would be
grateful if you could confirm or correct them.

1. **RR-1: which column is flight?**
   - Choi et al. (2020, *Sci Rep* 10:2336) report the in-flight U.S. Lab cabin during RR-1
     (25 Sept – 31 Oct 2014) as CO2 788–4690 ppm, 21.3–24.1 °C and 32–58 % RH.
   - Over the same window, these minima and maxima equal those of EDA's **`*_ground`** columns exactly.
   - EDA's `*_iss` columns span 1862–4667 ppm, 21.8–24.0 °C and 31–56 %.
   - Before launch, `co2_ground` reads about 480 ppm (2014-09-20), which looks like room air.

   Are the `iss` and `ground` labels correct for RR-1? Is the paper's range from the ground series?

2. **RR-9 telemetry is dated a year after the mission.**
   - The RR-9 telemetry series runs 2018-08-14 to 2018-09-18.
   - EDA's own RR-9 radiation series and milestones are dated 2017: animal transfer to ISS on
     2017-08-18, LAR on 2017-09-17. The mission is titled "Rodent Research 9 (SpaceX-12)".
   - The 2018 RR-9 telemetry also overlaps RR-7's telemetry, and the two give different ISS cabin
     values at the same timestamps.

3. **RR-1: a held value in `co2_iss`.** It reads 2646 ppm for 1837 consecutive 5-minute samples,
   from 2014-09-21 04:24 to 2014-09-27 13:25 UTC. This looks like a fill value rather than a
   measurement.

4. **RR-18: humidity above 100 %.** `humidity_iss` exceeds 100 % in 1434 samples between 2022-02-21
   and 2022-02-26, with a maximum of 125.8 %.

5. **Duplicated rows.** Every timestamp appears twice in the RR-7 telemetry (43 898 rows, 21 949 times)
   and in RR-10 (86 206 rows, 43 103 times). Some duplicates are partly null.

6. **Plant missions return only nulls.** The `telemetry_data` endpoint returns rows but no values for
   VEG-01A, VEG-01C, APEX-03-1, APEX-03-2 and APEX-04. It returns no rows for VEG-01B, RR-4, RR-8,
   RR-17 and RR-22. The EDA page describes temperature and humidity "collected from both flight and
   ground hardware units" for some missions. Are those available through the API?

Thank you for maintaining this resource; it is very useful for interpreting flight and ground-control
differences.

[Name, affiliation]
[Contact details]
