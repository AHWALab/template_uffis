#!/usr/bin/env python3
"""Build the Comoros context layers for the UFFIS viewer.

Reads the FIM area-of-concern polygons that ship with the TITO Comoros
configuration (fim_config/aoc/Comoros_*_aoc.geojson) and writes one rounded
GeoJSON file into the viewer:

  data/gis_comoros/fim_communes.geojson  all Comoros FIM communes

prepare_cycle.py filters this layer down to the triggered sites of each
cycle (data/<cycle>/fim/triggered_sites.geojson) for the viewer outline.

Usage:
  python scripts/prepare_comoros_gis.py <aoc_dir> [--out data/gis_comoros]
"""
import argparse
import glob
import json
import os
import unicodedata


def round_coords(c, nd=6):
    if isinstance(c[0], (int, float)):
        return [round(c[0], nd), round(c[1], nd)]
    return [round_coords(x, nd) for x in c]


def ascii_name(s):
    """ADM3 name to plain ASCII for display (Mlédjélé -> Mledjele)."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("aoc_dir", help="folder with Comoros_*_aoc.geojson files")
    ap.add_argument("--out", default="data/gis_comoros",
                    help="output folder for the viewer layer")
    args = ap.parse_args()

    features = []
    for path in sorted(glob.glob(os.path.join(args.aoc_dir,
                                              "Comoros_*_aoc.geojson"))):
        gj = json.load(open(path))
        for f in gj["features"]:
            props = f["properties"]
            features.append({
                "type": "Feature",
                "properties": {"pcode": props["pcode"],
                               "name": ascii_name(props["name"]),
                               "name_src": props["name"],
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


if __name__ == "__main__":
    main()
