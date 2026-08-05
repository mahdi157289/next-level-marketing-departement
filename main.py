"""Local dev entry: `python main.py` (requires uvicorn in env)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
