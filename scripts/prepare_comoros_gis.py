#!/usr/bin/env python3
"""Build the Comoros context layers for the UFFIS viewer.

Reads the FIM area-of-concern polygons that ship with the TITO Comoros
configuration (fim_config/aoc/Comoros_*_aoc.geojson) and writes two rounded
GeoJSON files into the viewer:

  data/gis_comoros/fim_communes.geojson  all Comoros FIM communes
  data/gis_comoros/fim_site.geojson      outline of the active FIM site

The active site is the FIM store grid that the prepared cycles were run on.
For the exported 20251225 cycles that is Moimbassa (KM323, Moheli); pass
--site to change it when a deployment moves to another FIM site.

Usage:
  python scripts/prepare_comoros_gis.py <aoc_dir> [--site KM323]
                                        [--out data/gis_comoros]
"""
import argparse
import glob
import json
import os


def round_coords(c, nd=6):
    if isinstance(c[0], (int, float)):
        return [round(c[0], nd), round(c[1], nd)]
    return [round_coords(x, nd) for x in c]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("aoc_dir", help="folder with Comoros_*_aoc.geojson files")
    ap.add_argument("--site", default="KM323",
                    help="pcode of the active FIM site (default KM323)")
    ap.add_argument("--out", default="data/gis_comoros",
                    help="output folder for the viewer layers")
    args = ap.parse_args()

    features = []
    for path in sorted(glob.glob(os.path.join(args.aoc_dir,
                                              "Comoros_*_aoc.geojson"))):
        gj = json.load(open(path))
        for f in gj["features"]:
            props = f["properties"]
            features.append({
                "type": "Feature",
                "properties": {"pcode": props["pcode"], "name": props["name"],
                               "island": props["island"]},
                "geometry": {"type": f["geometry"]["type"],
                             "coordinates": round_coords(
                                 f["geometry"]["coordinates"])}})

    os.makedirs(args.out, exist_ok=True)
    all_path = os.path.join(args.out, "fim_communes.geojson")
    with open(all_path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features},
                  fh, separators=(",", ":"))
    print("wrote", all_path, len(features), "features")

    site = [f for f in features if f["properties"]["pcode"] == args.site]
    if not site:
        raise SystemExit("site %s not found in %s" % (args.site, args.aoc_dir))
    site_path = os.path.join(args.out, "fim_site.geojson")
    with open(site_path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": site},
                  fh, separators=(",", ":"))
    print("wrote", site_path, site[0]["properties"]["name"],
          "(%s)" % site[0]["properties"]["island"])


if __name__ == "__main__":
    main()
