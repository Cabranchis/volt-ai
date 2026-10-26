"""Save the metrics of the newest stored training run to a JSON file (for the model card)."""

import json
import sys

from sqlalchemy import text

from voltia import db

eng = db.make_engine()
with eng.connect() as c:
    run_id, trained_at, data_end, metrics = c.execute(
        text("select run_id, trained_at, data_end, metrics from model_runs order by trained_at desc limit 1")
    ).one()
payload = metrics if isinstance(metrics, dict) else json.loads(metrics)
payload["run"] = {"run_id": run_id, "trained_at": str(trained_at), "data_end": str(data_end)}
json.dump(payload, open(sys.argv[1], "w"), indent=1)
print(run_id, data_end)
