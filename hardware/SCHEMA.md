# Hardware specification files (`hardware/<slug>.yaml`)

One file per hardware item considered for CFD. **Every number carries its source.**
A parameter that cannot be sourced is left `null` with a `searched:` note saying where
we looked. Nothing is filled from memory, typical values, or a different hardware item.

## Parameter record

Every leaf parameter is a mapping:

```yaml
value: 0.3            # number, string, or [min, max]
unit: m/s             # SI or stated unit; '-' for dimensionless / categorical
source: "Monje O. et al. (2020) Front. Plant Sci. 11:673. doi:10.3389/fpls.2020.00673"
url: https://doi.org/10.3389/fpls.2020.00673
quote: "verbatim text from the source, <= 40 words, that states the value"
kind: measured | specified | derived | user_supplied   # derived = computed from other sourced values (say how)
note: optional
```

`user_supplied` is reserved for measurements given by the project PI (R. Barker) and
must carry the date supplied.

## File layout

```yaml
entity_id: HW034                 # from data/derived/entities.json
name: Advanced Plant Habitat
splash_ids: [34]
registry_ids: ["2017"]
location: {value: "ISS EXPRESS rack, quad-locker", ...}
geometry:
  enclosure_internal_mm: {value: [L, W, H], ...}     # rectangular; or
  enclosure_cylinder_mm: {value: [D, H], ...}
  free_air_volume_L: {...}
  specimen_container: {value: "Petri dish 60 mm" | "plant pillow" | "cage", ...}
  specimen_container_mm: {value: [...], ...}
  n_specimen_units: {...}
  layout: {value: "2 x 3 grid", ...}
ventilation:
  mode: {value: forced | passive | sealed, ...}
  flow_rate_L_min: {...}          # or
  air_velocity_m_s: {...}
  inlet: {value: "description / size / position", ...}
  outlet: {...}
environment:
  temperature_C: {...}
  rh_percent: {...}
  co2_ppm: {...}
  o2_percent: {...}
  pressure_kPa: {...}
  light: {value: "red/blue LED, 300 umol m-2 s-1, 16/8 h" | "dark", ...}
nutrients:
  mode: {value: agar | arcillite | hydroponic | culture_medium | food_bar+lixit | water_loop, ...}
  detail: {...}
specimen_load:                    # per specimen or per unit area
  co2_flux: {...}
  o2_flux: {...}
  h2o_flux: {...}
  heat_W: {...}
walls:
  material: {...}
  gas_permeability: {...}
thermal:
  power_W: {...}
searched: |
  where we looked for missing parameters (databases, papers, NASA fact sheets)
```

## Tier after curation

The same critical items as the MI-CFD-HW checklist apply (G1 enclosure dims, G2
specimen container, F1 ventilation mode, F2 flow rate - not required when `mode: sealed`
or `mode: passive`, E1 temperature, B1 specimen). A hardware item is modelled only if
all of them are sourced.
