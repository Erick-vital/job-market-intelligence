from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generate_technical_experience_from_evidence(tmp_path):
    evidence = tmp_path / "repo_evidence.jsonl"
    output = tmp_path / "technical_experience.json"
    evidence.write_text(
        '{"repo":"demo","signal":"fastapi_project","capabilities":["backend_python_api_design"],"skills":["Python","FastAPI"],"confidence":"high"}\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "scripts/generate_technical_experience.py", "--evidence", str(evidence), "--out", str(output)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "wrote" in result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["capabilities"][0]["id"] == "backend_python_api_design"
    assert "FastAPI" in data["capabilities"][0]["skills"]
