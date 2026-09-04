# UFFIS viewer

Web viewer for the Urban Flash Flood Information and Forecasting System
(UFFIS) forecast products in Guatemala. A single static page (Leaflet, no
build step) that can be hosted on GitHub Pages.

## Segments

1. **Current conditions.** QPE based EF5 products: the runs driven by the
   observed satellite rainfall (IMERG stream and SCaMPR), combined on the
   model grid. Rainfall accumulation, max unit streamflow, soil saturation.
2. **Flood forecast.** QPF based EF5 products from the 50 member StormLab
   rainfall ensemble. Same three products.
3. **Flood inundation mapping.** Flood map library probabilities of the
   Santa Ines Petapa pilot: P(depth >= 0.10, 0.30, 0.70, 1.00 m), combined
   routines, overbank view, 5 m grid.
4. **Impact based forecasting.** Grid warning level on the flood risk
   matrix (Speight et al. 2018 / Flood Guidance Statement standard):
   likelihood bands of the minor (0.10 m), significant (0.30 m) and severe
   (0.70 m) thresholds, worst matrix cell per grid cell.

Every EF5 product has Min, Median and Max buttons (ensemble statistic) and
each layer shows the national 900 m grid with the 90 m domain drawn on
top. Administrative and local layers (departments, municipios, municipal
vulnerability, main roads, flood prone settlements, municipal capitals,
Cuenca Villalobos) can be toggled and restyle themselves to stay readable
on the satellite basemap.

## Repository layout

```
index.html                 the whole app
scripts/prepare_cycle.py   raw cycle folder -> web assets
data/cycles.json           list of available cycles, newest first
data/gis/                  static context layers (GeoJSON)
data/<cycle>/manifest.json bounds, legends and cycle facts
data/<cycle>/ef5/          colorized EF5 overlays (PNG)
data/<cycle>/fim/          flood probability overlays (PNG)
data/<cycle>/ibf/          warning level overlay (PNG)
```

## Adding a new forecast cycle

1. Unzip the cycle folder the pipeline produced (it must contain
   `guatemala_900m/summary`, `guatemala_90m/summary` and
   `guatemala_90m/fim`).
2. Run:

   ```
   python scripts/prepare_cycle.py path/to/20260903.160000 data
   ```

   Requirements: `rasterio`, `numpy`, `pillow`.
3. Commit and push. The viewer always opens the newest cycle in
   `data/cycles.json`.

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
