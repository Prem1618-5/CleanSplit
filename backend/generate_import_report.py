"""Generate the assignment import report using the production CSV parser."""

import argparse
from pathlib import Path

from services.importer import parse_csv, render_import_report_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = REPO_ROOT / "data" / "expenses_export.csv"
DEFAULT_OUTPUT = REPO_ROOT / "IMPORT_REPORT.md"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--usd-inr-rate", type=float, default=85.0)
    args = parser.parse_args()

    rows = parse_csv(args.csv.read_bytes(), usd_inr_rate=args.usd_inr_rate)
    report = render_import_report_markdown(
        rows,
        filename=args.csv.name,
        session_status="baseline staging report before reviewer decisions",
        usd_inr_rate=args.usd_inr_rate,
    )
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output} from {len(rows)} CSV rows")


if __name__ == "__main__":
    main()
