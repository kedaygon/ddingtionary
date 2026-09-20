import argparse
import sys

import importer
import pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version")
    ap.add_argument("--repo-path")
    ap.add_argument("--cache-root", default=pipeline.default_cache_root())
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for v in importer.list_versions():
            print(v)
        return 0

    s = pipeline.do_import(
        version=args.version,
        cache_root=args.cache_root,
        out=args.out,
        force=args.force,
        repo_path=args.repo_path,
        progress=lambda st, m: print("[%s] %s" % (st, m), flush=True),
    )

    print()
    print("=== import report ===")
    for k in ("version", "out", "characters", "distinct", "skills", "scalings",
              "scaling_values", "terms", "links", "nodes",
              "param_unresolved", "scaling_unparsed", "link_dangling", "elapsed"):
        print("%-18s: %s" % (k, s[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
