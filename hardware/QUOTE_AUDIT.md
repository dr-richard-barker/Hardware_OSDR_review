# Quote audit of curated hardware values

Audit date: 2026-10-12. An independent auditor checked 40 parameter records, sampled at random from `hardware/*.yaml`. The sample is in `data/curated/quote_audit_sample.csv`, and the result for each record is in `data/curated/quote_audit_results.csv`.

## Method

- **Sources opened directly.** The auditor opened each cited source:
  - NTRS, J-STAGE, NIH and NASA PDFs were downloaded with curl and their text extracted with pypdf.
  - The Neurolab report has no text layer, so its page was read with Tesseract OCR.
  - The JAXA repository PDF is encrypted, so its text was extracted with Ghostscript.
  - Journal articles were read as Europe PMC full-text XML.
  - The patent, the JAXA AQH page and the TTU repository bitstreams were fetched directly.
- **OSDR records.** OSDR registry, SPLASH and biodata records were checked against the frozen snapshot in `data/raw/2026-10-12/`.
- **Search method.** Quotes were matched after normalising case, whitespace and punctuation. Close matches were then read in context.
- **Note sources.** Where a value carries more than its cited source supports, the auditor also opened the secondary source named in the record's note, where one was given.

## Counts

| | yes | partial | no | source_unreachable |
|---|---|---|---|---|
| quote_found | 40 | – | 0 | 0 |
| value_supported | 28 | 12 | 0 | – |

Every quote exists in its cited source, and every numeric value matches it. No record was unsupported.

All 12 partials are composite values: the cited source supports the core value, but part of the text comes from a different source. In 10 of the 12, the extra text was confirmed in another source. One partial has a real inconsistency (#22), and one contains an element the auditor could not confirm (#37).

## Records not rated yes/yes

| # | file · path | Reason |
|---|---|---|
| 5 | abrs · location | "EXPRESS Rack 2" is not in SPLASH 64. It is confirmed in the note's Cox 2010 slides (NTRS 20110942664). |
| 6 | adf · ventilation.inlet | The patent supports the outer cabin-air loop through the left-side vent. "Incubator-cabin exchange through a filtered port" comes from OSDR registry 1001, which the record does not cite. |
| 8 | veggie · walls.material | "Teflon" is not in Massa NTRS 20160006558, which says "fluorinated polymer". It is confirmed as "Teflon Bellows" in the note's NTRS 20150021302. |
| 11 | mvp · nutrients.detail | The label "MVP2-Cell-03" is not in Hwang 2023, which says SpaceX-20. It is confirmed in OSDR registry payload MVP2-Cell-03. |
| 12 | adsep · geometry.specimen_container | "Lunchbox size" is not in the OSD-961 protocol. It is confirmed in the Redwire 2021 newsroom post. |
| 19 | jaxa_mhu · walls.material | Shimbo 2016 supports polycarbonate only. PulSheet appears in Shiba 2017 Suppl. Table 1, and the photocatalytic spray in the Shiba 2017 main text. Neither is cited, and the note does not mention the spray. |
| 22 | mds · nutrients.detail | **Inconsistency.** Cancedda 2012 says "2 food bars ... total ~90 g". The 149 × 73 × 7.5 mm dimensions come from Liu 2009, which describes **one** bar of that size weighing ~90 g per cage. The value combines the two, which implies ~45 g bars of the 90 g bar's size. This needs reconciling. |
| 23 | jaxa_mhu · environment.light | IR LEDs are not in the cited Supplemental Table 1. They appear in the Shiba 2017 main text ("LED/IR video camera") and on the JAXA page named in the note. |
| 26 | emcs · geometry.layout | The 174 mm and 206 mm cassette radii are not in registry 1057. They are confirmed in Herranz 2019 (PMC6889863), which the note names. |
| 27 | aem · nutrients.detail | "Slide-in" plates is not in Moyer 2016. It is confirmed in OSDR registry 133. The ration values match Moyer word for word. |
| 30 | aem_t · location | "Middeck-locker" and "Cygnus" are not in registry 1380. They are confirmed in Niederwieser ICES-2014-101, but that paper lists Cygnus only as a carrier to be upgraded (design intent). |
| 37 | jellyfish_kit · specimen.type | "(1-2 mm)" is confirmed in the note's NTRS 19990062734. The species name "aurita" and "moon jellyfish" are not in either source. **Not confirmed.** |

## Caveats on records rated yes/yes

- **#16 (aqh · geometry.layout).** The note says the aquarium branch layout is "not published". However, the flow diagram on the cited JAXA AQH page shows two parallel aquarium branches. The note could be updated.
- **#17 (jaxa_mhu · specimen_load.h2o_flux) and #38 (rahf · specimen_load.heat_W).** These are organism-level values transferred from other enclosures: conventional cages with bedding for #17, a mock AEM for #38. Both notes say so.
- **#24 (mvp · environment.temperature_C).** SPLASH gives "14-40C" for both MVP (36) and ADSEP (46). This is a facility range, not a set point.
- **#40 (emcs · environment.o2_percent).** The article was e-published 8 Jan 2024 in volume 14, which is the 2023 collection. It is cited as 2023.

## Access notes

- **PubMed (#37).** The page returned a cookie wall to both curl and WebFetch. The same abstract was read through Europe PMC.
- **JAXA repository (#33).** A request with a Chrome user-agent got HTTP 406. The default curl user-agent worked.
- **Login and email.** No logins were used, and no email address was sent in any request.

## Corrections applied after the audit (2026-10-12)
- `jellyfish_kit.yaml` specimen.type: removed "moon jellyfish" / "aurita" (in neither cited source).
- `mds.yaml` nutrients.detail: the food-bar number/size combination of Cancedda 2012 (2 bars, ~90 g total)
  and Liu 2009 (one 149 x 73 x 7.5 mm bar of ~90 g) is inconsistent; the value no longer combines them and
  the conflict is recorded in the note. Food bars are not part of the CFD model.
- `aem_t.yaml` location: Cygnus removed (ICES-2014-101 names it only as a future carrier); value now
  restates the cited registry sentence.
The remaining partials are records whose descriptive wording partly comes from a second source named
in the note; their values are supported.
