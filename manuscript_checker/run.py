"""Start the web app from any directory:

    python run.py                 # from inside manuscript_checker/
    python manuscript_checker/run.py
    python run.py --port 8501     # another port

Then open http://localhost:8000 (or the port you chose).
"""

import argparse
import sys
from pathlib import Path

# Make `manuscript_checker` importable regardless of the current directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the submission check web app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"Submission check running at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    uvicorn.run("manuscript_checker.server:app", host=args.host, port=args.port)
