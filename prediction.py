"""Command-line entrypoint for rebuilding the packaged prediction artifacts."""
import json
from pathlib import Path
import pandas as pd
from boundary_core.prediction import build

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    result = build(pd.read_csv(root / 'data/matches.csv.gz', keep_default_na=False,
                              dtype={'match_id': str, 'season': str}))
    print(json.dumps(result['test'], indent=2))
