"""Copy the series tables from the database to a local CSV file the experiments read.

Experiments never touch the database; they work on this snapshot, which stays out of git.
"""

from __future__ import annotations

from pathlib import Path

from voltia import db

OUT = Path(__file__).parent / "data" / "history.csv"


def main() -> None:
    engine = db.make_engine()
    history = db.read_series(engine)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(OUT, index_label="day")
    print(f"{len(history)} days, {history.shape[1]} series, {history.index[0].date()} to {history.index[-1].date()} -> {OUT}")


if __name__ == "__main__":
    main()
