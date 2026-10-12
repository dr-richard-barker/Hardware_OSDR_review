# Literature curation log (2026-10-12)

Five curation passes, one per hardware family, each bound by `SCHEMA.md`: every non-null
value from a source opened in the session, with a verbatim quote of at most 40 words; no
values from memory, no transfer between hardware items, gaps left null with a note.
Each pass checked its quotes against saved copies of the sources (whitespace/Unicode
normalised). An independent re-check of a random sample of quotes is recorded in
`QUOTE_AUDIT.md`.

Schema additions made by curators (accepted): `specimen.type(s)` (checklist item B1),
`transport_medium` (aquatic habitats: the `ventilation` block then describes the water
loop), `geometry.growing_area_*`, `geometry.water_volume_L`, `geometry.enclosure_external_*`,
`thermal.heat_rejection`.

## Plant growth chambers (veggie, aph, abrs, bps, emcs, cbef_peu)
109 quotes, all matched to saved sources. Only APH has every critical item; the other five
lack an airflow rate in any accessible source.

Source conflicts recorded in the files:
- Veggie growing area 0.11 m2 (Massa et al., NTRS 20160006558) vs 0.15 m2 (NTRS 20150021302);
  the same Massa paper's "usable volume of up to 0.48 m3" is ten times its own dimensions
  (treated as a typo; 50.5 L derived). Pillows per unit: SPLASH "2 or 6" vs slides "1, 2, 3 or 6".
- APH RH 50-90 % (Monje et al. 2020) vs 50-86 % (Massa; SPLASH); CO2 400-5000 vs 500-5000 ppm;
  leak 5 % h-1 measured on ISS vs design "<=10 % by volume a day"; light set-point reference
  height 10 cm (Monje) vs 15 cm (Massa); the 100 L chamber volume is the authors' assumption
  (geometric shoot zone about 74 L).
- ABRS chamber 20.2 x 13.3 x 19.2 cm (SPLASH) vs 20.3 x 13.4 x 19.25 cm (KSC drawing): agree
  within 1 mm; an internally inconsistent comparison table in the same deck was rejected.
- BPS: the KSC 15.2 cm cube conflicts with 260 cm2 growing area, ">6 in" height and ">4 L" per
  chamber from three other sources (low confidence).
- EMCS cassettes per container 6 (SPLASH) vs 5 (four sources); O2 21 % vs 10 % (Seedling Growth-3).
- CBEF/PEU chamber 149 mL (JAXA handbook) vs 120 mL (JAXA web); light 26 / ~110 / 190 umol m-2 s-1.
Inaccessible but likely to fill the airflow gap: Massa et al. 2017 Open Agriculture (Veggie);
Monje et al. 2005 and Stutte et al. 2006 Planta (BPS); Kittang et al. 2014, Brinckmann 2005
(EMCS); Yano et al. 2013 Adv. Space Res. 51:780 (PEU).
Note: OSDR CBEF datasets OSD-75/112/113/425/956 are C. elegans in other experiment units.

## Aquatic, invertebrate and avian (aqh, cebas, vfeu, fruit_fly_lab, vented_fly_box, fit_fly_kit, jellyfish_kit, adf)
Complete: AQH. Vented Fly Box complete with a caveat (94 x 94 x 130 mm is the 2014 HEART
Flies box; the later FFL-02/03 "upgrade" is unconfirmed).
Caveats: Fruit Fly Lab 23-25 C applies to the change-out platform in a cargo bag (FFL-01
flies died of overheating; no value logged). ADF dimensions come from US patent 7,261,860;
its 1.3 CFM per fan is a free-air rating, kept as an upper bound only.
Conflicts: AQH aquarium 0.7 L (JAXA, OSD-83, Chatani 2015) vs 600 cc (IAC-12 abstract);
SPLASH #69's 90 x 70 x 60 cm is the MSPR rack work volume. CEBAS 8.6 L vs 7 L vs ~11 L
(ground prototype); SPLASH #147 values not used (displaced block). VFEU mass 80 vs 77 kg.
Fly food tray 2 vs 3.4 mL; cassette polycarbonate vs aluminium. VFB OSD-207/347 list
SpaceX-11 but their protocols describe the 2014 SpaceX-3 launch. Jellyfish flasks
polyethylene vs polystyrene in the same registry record. ADF CO2 <= 1 % vs < 0.5 %.
The Neurolab Final Report (NTRS 20020073543) is a scan: quotes are OCR transcriptions.

## Bioreactors and facilities (mvp, sabl, adsep, ccm, bioculture, mobias, botex, e150_eue)
None complete. SABL is closest: chamber 420 x 282 x 197 mm, 23.32 L (ICES-2016-418), sealed;
with the CO2 control insert a fan recirculates 140 L/min internally; insert geometry missing.
Findings:
- E150 Experiment Unique Hardware is a walking-test platform used in short sessions inside
  the Spacelab General Purpose Work Station; the rats lived elsewhere -> role override.
- The OSDR registry links MOBIAS to the STS-115 'Microbe' Group Activation Packs; NASA Ames
  and Wilson et al. 2007 (PNAS) describe hand-cranked GAPs in the middeck with no MOBIAS.
  OSD-11 should not be modelled as MOBIAS.
- No OSDR dataset uses the Bioculture System; OSD-344/541 used BioServe BioCells.
Conflicts: SABL chamber 41.9 x 27.9 x 19.4 cm (ICES 2015) vs 42.0 x 28.2 x 19.7 cm (ICES 2016,
used); upper temperature +40 vs +43 C. ADSEP cassettes 3 vs 4; 4-40 vs 14-40 C. Bioculture
pump 0-8 vs 0-15 mL/min. MVP g-range 0-2 vs 0.1-2 g.
