"""python -m ctw <step> [args]. Steps run independently and communicate through files in $CTW_WORK (./work)."""
import argparse, sys
from . import common as C


def main(argv=None):
    p = argparse.ArgumentParser(prog="ctw")
    sub = p.add_subparsers(dest="step", required=True)
    sub.add_parser("plan", help="print the job matrix (models, TerraClimate variables, latest year) as JSON")
    a = sub.add_parser("cmip6"); a.add_argument("--model", required=True)
    a = sub.add_parser("terraclimate"); a.add_argument("--var", required=True, choices=["tmax", "tmin", "ppt", "vap"])
    sub.add_parser("adaptwest"); sub.add_parser("prism"); sub.add_parser("gazetteer"); sub.add_parser("sealevel")
    sub.add_parser("analogs"); sub.add_parser("export")
    a = sub.add_parser("validate"); a.add_argument("--previous", default=None, help="previous release summary.json")
    sub.add_parser("site"); sub.add_parser("watch")
    a = sub.add_parser("all", help="every step in order, locally (slow; for testing)")
    args = p.parse_args(argv)
    cfg = C.config()
    if args.step == "plan":
        import json
        from .terraclimate import latest_year
        print(json.dumps({"models": [m["name"] for m in C.models(cfg)], "tc_vars": ["tmax", "tmin", "ppt", "vap"],
                          "latest_year": latest_year(cfg)}))
    elif args.step == "cmip6":
        from . import cmip6; cmip6.run(args.model, cfg)
    elif args.step == "terraclimate":
        from . import terraclimate; terraclimate.run(args.var, cfg)
    elif args.step == "adaptwest":
        from . import adaptwest; adaptwest.run(cfg)
    elif args.step == "prism":
        from . import prism; prism.run(cfg)
    elif args.step == "gazetteer":
        from . import gazetteer; gazetteer.run(cfg)
    elif args.step == "sealevel":
        from . import sealevel; sealevel.run(cfg)
    elif args.step == "analogs":
        from . import analogs; analogs.run(cfg)
    elif args.step == "export":
        from . import export; export.run(cfg)
    elif args.step == "validate":
        from . import validate; sys.exit(validate.run(cfg, args.previous))
    elif args.step == "site":
        from . import site; site.run(cfg)
    elif args.step == "watch":
        from . import watch; sys.exit(watch.run(cfg))
    elif args.step == "all":
        from . import cmip6, terraclimate, adaptwest, prism, gazetteer, analogs, export, site
        for m in C.models(cfg): cmip6.run(m["name"], cfg)
        for v in ("tmax", "tmin", "ppt", "vap"): terraclimate.run(v, cfg)
        adaptwest.run(cfg); prism.run(cfg); gazetteer.run(cfg)
        analogs.run(cfg); export.run(cfg); site.run(cfg)


if __name__ == "__main__":
    main()
