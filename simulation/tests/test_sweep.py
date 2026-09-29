"""Sweep plumbing: CPU detection and crash-safe checkpoint/resume."""
import json

from paramanu_sim import sweep
from paramanu_sim.sweep import SweepConfig, available_cpus, run


def _fake_evaluate(params):
    return {"sample": params["sample"], "P_atm": params["P_atm"]}


def test_available_cpus_is_positive_and_bounded():
    import os
    n = available_cpus()
    assert 1 <= n <= (os.cpu_count() or n)


def test_checkpoint_resumes_without_recomputing(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "evaluate", _fake_evaluate)
    ckpt = tmp_path / "sweep.partial.jsonl"
    cfg = SweepConfig(samples=6)
    # a previous run finished samples 0 and 3, then died mid-write
    ckpt.write_text(json.dumps({"sample": 0, "P_atm": -1.0}) + "\n"
                    + json.dumps({"sample": 3, "P_atm": -1.0}) + "\n" + '{"sample": 4, "P_')
    seen = []
    df = run(cfg, backend="serial", checkpoint=ckpt,
             progress=lambda done, total, resumed: seen.append((done, total, resumed)))
    assert list(df["sample"]) == list(range(6))
    # finished samples were kept, not recomputed; the torn one was redone
    assert df.set_index("sample").loc[[0, 3], "P_atm"].tolist() == [-1.0, -1.0]
    assert df.set_index("sample").loc[4, "P_atm"] != -1.0
    assert seen[0] == (3, 6, 2) and seen[-1] == (6, 6, 2)
    # every line in the checkpoint is valid JSON again after the resume
    rows = [json.loads(line) for line in ckpt.read_text().splitlines() if line.startswith('{"sample": ') and line.endswith("}")]
    assert sorted(r["sample"] for r in rows) == list(range(6))
