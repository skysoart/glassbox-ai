"""One-off backfill for the cost_known column.

Runs recorded before cost_known existed were all given the column default of
true, but many of them were priced at $0.00 only because the model was missing
from the pricing table. This marks those as unknown so the dashboard stops
presenting a fabricated zero as a real total.

A step is treated as unpriced when it reported token usage but zero cost.

    python scripts/backfill_cost_known.py           # show what would change
    python scripts/backfill_cost_known.py --apply   # write the changes
"""
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.database.database import engine, ensure_schema  # noqa: E402

UNPRICED_STEPS = """
    SELECT step_id FROM trace_steps
    WHERE cost_known = 1
      AND (cost IS NULL OR cost = 0)
      AND token_usage IS NOT NULL
      AND token_usage != 'null'
"""


def main():
    apply_changes = "--apply" in sys.argv
    ensure_schema()

    with engine.begin() as connection:
        step_ids = [row[0] for row in connection.execute(text(UNPRICED_STEPS))]

        if not step_ids:
            print("Nothing to backfill: every step with token usage already has a cost.")
            return 0

        run_ids = [
            row[0] for row in connection.execute(text(
                "SELECT DISTINCT run_id FROM trace_steps WHERE step_id IN ("
                + ",".join("'" + s + "'" for s in step_ids) + ")"
            ))
        ]

        print("Steps to mark as unpriced: " + str(len(step_ids)))
        print("Runs to mark as unpriced:  " + str(len(run_ids)))

        if not apply_changes:
            print("\nDry run. Re-run with --apply to write these changes.")
            return 0

        connection.execute(text(
            "UPDATE trace_steps SET cost_known = 0 WHERE step_id IN ("
            + ",".join("'" + s + "'" for s in step_ids) + ")"
        ))
        connection.execute(text(
            "UPDATE runs SET cost_known = 0 WHERE run_id IN ("
            + ",".join("'" + r + "'" for r in run_ids) + ")"
        ))
        print("\nDone.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
