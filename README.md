# UFFIS viewer

Web viewer for the Urban Flash Flood Information and Forecasting System
(UFFIS) forecast products. A single static page (Leaflet, no build step)
that can be hosted on GitHub Pages. Two regions are wired in and can be
switched in the header:

- **Comoros** (deployment default, `DEFAULT_REGION` in index.html): the
  three STREAM-Sat + StormLab cycles of 2025-12-25 11:00, 12:00 and 13:00
  UTC, with the EF5 summary products on the 30 m grid, the pluvial flood
  map library of the Moimbassa (Moheli) FIM site and the IBF warning
  level. Context layers are the active FIM site outline and the 55
  Comoros FIM communes.
- **Guatemala** (template example): cycle 20260903.160000 with the
  national 900 m and basin 90 m EF5 products, the Santa Ines Petapa FIM
  library, IBF, gauge hydrographs and the full administrative context.

## Segments

1. **Current conditions.** QPE based EF5 products: the runs driven by the
   observed satellite rainfall (IMERG and SCaMPR in Guatemala, STREAM-Sat
   in the Comoros), combined on the model grid. Rainfall accumulation,
   max unit streamflow, soil saturation.
2. **Flood forecast.** QPF based EF5 products from the StormLab rainfall
   ensemble. Same three products.
3. **Flood inundation mapping.** Flood map library probabilities:
   P(depth >= 0.10, 0.30, 0.70, 1.00 m), overbank view of the matched
   scenarios (Santa Ines Petapa 5 m in Guatemala, Moimbassa 30 m in the
   Comoros).
4. **Impact based forecasting.** Grid warning level on the flood risk
   matrix (Speight et al. 2018 / Flood Guidance Statement standard):
   likelihood bands of the minor (0.10 m), significant (0.30 m) and severe
   (0.70 m) thresholds, worst matrix cell per grid cell.

Every EF5 product has Min, Median and Max buttons (ensemble statistic).
In Guatemala each layer shows the national 900 m grid with the 90 m
domain drawn on top; in the Comoros there is a single 30 m grid.

## Repository layout

```
index.html                      the whole app
scripts/prepare_cycle.py        raw cycle folder -> web assets
scripts/prepare_comoros_gis.py  FIM area-of-concern geojson -> context layers
data/cycles.json                list of available cycles, newest first
data/gis/                       Guatemala context layers (GeoJSON)
data/gis_comoros/               Comoros context layers (GeoJSON)
data/<cycle>/manifest.json      bounds, legends, region and cycle facts
data/<cycle>/ef5/               colorized EF5 overlays (PNG)
data/<cycle>/fim/               flood probability overlays (PNG)
data/<cycle>/ibf/               warning level overlay (PNG)
data/<cycle>/ts/                gauge hydrograph envelopes (Guatemala)
```

## Adding a new forecast cycle

1. Take the raw cycle folder the pipeline produced. It needs one
   `<name>_<res>/summary` folder per model domain and, when FIM ran, its
   `<name>_<res>/fim/<routine>/` products (Guatemala writes
   combined_overbank, Comoros pluvial_overbank; the script picks the
   first available variant).
2. Run:

   ```
   python scripts/prepare_cycle.py path/to/20251225.120000 data --region comoros
   ```

   Requirements: `rasterio`, `numpy`, `pillow`. The region key drives the
   labels and start view; it is inferred from the model folder name when
   `--region` is omitted (`comoros_30m` -> `comoros`).
3. Commit and push. The viewer lists all cycles of `data/cycles.json`
   grouped by region and opens the first cycle of `DEFAULT_REGION`
   (index.html). Cycles sort newest first.

Comoros context layers are rebuilt from the TITO FIM configuration with:

```
python scripts/prepare_comoros_gis.py <tito>/fim_config/aoc --site KM323
```

`--site` is the pcode of the FIM store grid the exported cycles were run
on; it selects which outline becomes `fim_site.geojson`.

## Comoros data notes

- The 20251225 11:00-13:00 cycles were run on the Moimbassa (KM323,
  Moheli) FIM store grid (EPSG:5629, Moznet / UTM zone 38S): the product
  rasters match `fim_store/Comoros/fim_store_KM323_Moimbassa_v1.zarr`
  exactly. Their `pf_summary.json` still reports
  `"region": "Comoros_Vouani"` from the site config, but the grid and
  georeference are Moimbassa, so the viewer frames the products with the
  Moimbassa outline. The summary mismatch is worth checking upstream.
- The Comoros FIM rasters carry a bare `LOCAL_CS` WKT without an EPSG
  code, so `bounds_4326()` falls back to a local UTM inverse transform
  when rasterio cannot reproject them.

## Publishing on GitHub Pages

Push this repository to GitHub, then in Settings, Pages choose the main
branch and the root folder. The site appears at
`https://<user>.github.io/<repo>/`.

## Conventions

- All display text is plain ASCII: no em dashes, arrows, bullets or other
  special symbols.
- Point layers never use the hazard palette: Muy Alta settlements are
  black dots with a white rim, Alta are white dots with a black rim.
- Boundaries are dashed and roads are solid; both switch to white over
  the satellite basemap.
- Palettes: rainfall in a green to purple accumulation ramp, max unit
  streamflow in the operational FLASH palette, soil saturation in a brown
  to teal ramp, flood probability in the blue to purple product scale,
  IBF in the green, yellow, amber, red matrix colors.
