import os
import uvicorn

port_raw = os.environ.get("PORT", "8000")
try:
    port = int(port_raw)
except (ValueError, TypeError):
    port = 8000

uvicorn.run("backend.app:app", host="0.0.0.0", port=port)
