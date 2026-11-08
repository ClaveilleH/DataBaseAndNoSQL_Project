"""Lance l'interface web : uv run python -m weatherscope.web [--port 8050] [--host 127.0.0.1]"""

import argparse

import uvicorn

p = argparse.ArgumentParser()
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8050)
args = p.parse_args()
print(f"WeatherScope : http://{args.host}:{args.port}/  (API : /api/docs)")
uvicorn.run("weatherscope.web.app:app", host=args.host, port=args.port)
