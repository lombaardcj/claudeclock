#!/usr/bin/env python3
"""
Headroom performance collector — appends a parsed snapshot to perf_history.jsonl
each run, then rebuilds perf_data.json + perf_data.js for the dashboard.

Suggested cron (every minute):
  * * * * * cd /home/chrisl/codetest/claudeclock/headroom-perf && python3 collect.py >> collect.log 2>&1
"""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
HEADROOM_BIN = Path("/home/chrisl/codetest/headroom/.venv/bin/headroom")
HIST_FILE = BASE / "perf_history.jsonl"
DATA_FILE = BASE / "perf_data.json"
JS_FILE = BASE / "perf_data.js"


def run_perf() -> str:
    result = subprocess.run(
        [str(HEADROOM_BIN), "perf"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"headroom perf exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def _int(s: str) -> int:
    return int(s.replace(",", ""))


def _float(s: str) -> float:
    return float(s)


def parse_perf(output: str) -> dict:
    d = {}

    # ── Window ──────────────────────────────────────────────────────────────
    m = re.search(r"Window: last (\d+)h", output)
    if m:
        d["window_hours"] = int(m.group(1))

    m = re.search(r"actual data: ([\d\- :]+?)\s*[→>]\s*([\d\- :]+)", output)
    if m:
        d["window_start"] = m.group(1).strip()
        d["window_end"] = m.group(2).strip()

    # ── Requests & tokens ───────────────────────────────────────────────────
    m = re.search(r"Requests:\s+([\d,]+)", output)
    if m:
        d["requests"] = _int(m.group(1))

    m = re.search(r"Tokens:\s+([\d,]+)\s*->\s*([\d,]+)\s*\(([\d.]+)% reduction\)", output)
    if m:
        d["tokens_in"] = _int(m.group(1))
        d["tokens_out"] = _int(m.group(2))
        d["reduction_pct"] = _float(m.group(3))

    m = re.search(r"Total saved:\s+([\d,]+) tokens", output)
    if m:
        d["tokens_saved"] = _int(m.group(1))

    # ── Per-model breakdown ──────────────────────────────────────────────────
    models = []
    for m in re.finditer(
        r"([\w\-.:]+):\s+(\d+) reqs,\s+([\d,]+) tokens saved \((\d+)%\),\s+list price \$([\d.]+)/MTok\s+~\$([\d.]+) at list price",
        output,
    ):
        models.append({
            "name": m.group(1),
            "reqs": int(m.group(2)),
            "tokens_saved": _int(m.group(3)),
            "reduction_pct": int(m.group(4)),
            "list_price_per_mtok": float(m.group(5)),
            "cost_estimate": float(m.group(6)),
        })
    if models:
        d["models"] = models

    # ── Cache performance ────────────────────────────────────────────────────
    m = re.search(r"Cache read:\s+([\d,]+) tokens", output)
    if m:
        d["cache_read_tokens"] = _int(m.group(1))

    m = re.search(r"Cache write:\s+([\d,]+) tokens", output)
    if m:
        d["cache_write_tokens"] = _int(m.group(1))

    m = re.search(r"Hit rate:\s+([\d.]+)%", output)
    if m:
        d["cache_hit_rate"] = _float(m.group(1))

    m = re.search(r"Unstable:\s+(\d+)/(\d+) requests", output)
    if m:
        d["cache_unstable"] = int(m.group(1))
        d["cache_unstable_checked"] = int(m.group(2))

    m = re.search(r"First 5 avg:\s+read=([\d,]+)\s+write=([\d,]+)", output)
    if m:
        d["cache_first5_read"] = _int(m.group(1))
        d["cache_first5_write"] = _int(m.group(2))

    m = re.search(r"Last 5 avg:\s+read=([\d,]+)\s+write=([\d,]+)", output)
    if m:
        d["cache_last5_read"] = _int(m.group(1))
        d["cache_last5_write"] = _int(m.group(2))

    # ── Optimization overhead ────────────────────────────────────────────────
    m = re.search(r"Average:\s+(\d+)ms", output)
    if m:
        d["overhead_avg_ms"] = int(m.group(1))

    m = re.search(r"Max:\s+(\d+)ms", output)
    if m:
        d["overhead_max_ms"] = int(m.group(1))

    m = re.search(r">500ms:\s+(\d+) requests", output)
    if m:
        d["overhead_over500ms"] = int(m.group(1))

    # ── Throughput (headroom >= 0.27) ────────────────────────────────────────
    m = re.search(r"Input \(wall-clock\):\s+([\d,.]+) tok/s", output)
    if m:
        d["tp_input_wallclock"] = _float(m.group(1).replace(",", ""))

    for label, key in [
        ("Input \\(active p50/95\\)", "tp_input"),
        ("Compression \\(p50/95\\)", "tp_compress"),
        ("Forward \\(p50/95\\)", "tp_forward"),
        ("Generation \\(p50/95\\)", "tp_gen"),
    ]:
        m = re.search(rf"{label}:\s+([\d,.]+) / ([\d,.]+) tok/s", output)
        if m:
            d[f"{key}_p50"] = _float(m.group(1).replace(",", ""))
            d[f"{key}_p95"] = _float(m.group(2).replace(",", ""))

    # ── Conversation size ────────────────────────────────────────────────────
    m = re.search(r"Min msgs:\s+(\d+)", output)
    if m:
        d["conv_min_msgs"] = int(m.group(1))

    m = re.search(r"Max msgs:\s+(\d+)", output)
    if m:
        d["conv_max_msgs"] = int(m.group(1))

    m = re.search(r"Avg msgs:\s+(\d+)", output)
    if m:
        d["conv_avg_msgs"] = int(m.group(1))

    # ── Transform effectiveness ──────────────────────────────────────────────
    m = re.search(
        r"content_router:\s+([\d.]+)% avg reduction,\s+(\d+) uses,\s+([\d,]+) saved",
        output,
    )
    if m:
        d["cr_reduction_pct"] = _float(m.group(1))
        d["cr_uses"] = int(m.group(2))
        d["cr_tokens_saved"] = _int(m.group(3))

    # ── Content Router routing breakdown ────────────────────────────────────
    m = re.search(r"Compressed:\s+(\d+)\s+\((\d+)%\)", output)
    if m:
        d["routing_compressed"] = int(m.group(1))
        d["routing_compressed_pct"] = int(m.group(2))

    m = re.search(r"Excluded:\s+(\d+)\s+\((\d+)%\)", output)
    if m:
        d["routing_excluded"] = int(m.group(1))
        d["routing_excluded_pct"] = int(m.group(2))

    m = re.search(r"Skipped:\s+(\d+)\s+\((\d+)%\)", output)
    if m:
        d["routing_skipped"] = int(m.group(1))
        d["routing_skipped_pct"] = int(m.group(2))

    m = re.search(r"Unchanged:\s+(\d+)\s+\((\d+)%\)", output)
    if m:
        d["routing_unchanged"] = int(m.group(1))
        d["routing_unchanged_pct"] = int(m.group(2))

    # ── TOIN learning ────────────────────────────────────────────────────────
    m = re.search(r"Patterns:\s+(\d+)", output)
    if m:
        d["toin_patterns"] = int(m.group(1))

    m = re.search(r"Compressions:\s+([\d,]+)", output)
    if m:
        d["toin_compressions"] = _int(m.group(1))

    m = re.search(r"Retrievals:\s+(\d+)\s+\(([\d.]+)%\)", output)
    if m:
        d["toin_retrievals"] = int(m.group(1))
        d["toin_retrieval_rate"] = _float(m.group(2))

    # TOIN strategy distribution
    toin_strategies = {}
    for m in re.finditer(r"(\d+) pattern\(s\)\s+(\w+)", output):
        toin_strategies[m.group(2)] = int(m.group(1))
    if toin_strategies:
        d["toin_strategies"] = toin_strategies

    # ── Recommendations (headroom >= 0.31) ───────────────────────────────────
    m = re.search(r"Recommendations\n-+\n(.*?)(?:\n\s*\n|\Z)", output, re.DOTALL)
    if m:
        recs = re.findall(r"^\s*\d+\.\s+(.+)$", m.group(1), re.MULTILINE)
        if recs:
            d["recommendations"] = recs

    # ── Log metadata ─────────────────────────────────────────────────────────
    m = re.search(r"Log files:\s+(\d+)", output)
    if m:
        d["log_files"] = int(m.group(1))

    m = re.search(r"Lines parsed:\s+([\d,]+)", output)
    if m:
        d["log_lines"] = _int(m.group(1))

    return d


def rebuild_data_file():
    readings = []
    if HIST_FILE.exists():
        with open(HIST_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    # exclude raw field from dashboard payload to keep it lean
                    readings.append({k: v for k, v in r.items() if k != "raw"})
                except json.JSONDecodeError:
                    pass
    payload = {
        "readings": readings,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    with open(JS_FILE, "w") as f:
        f.write(f"window.PERF_DATA={json.dumps(payload)};")


def main():
    now = datetime.now(timezone.utc)
    output = run_perf()
    metrics = parse_perf(output)
    metrics["ts"] = now.isoformat()
    metrics["raw"] = output  # preserved in JSONL for user's step-2 processing

    with open(HIST_FILE, "a") as f:
        f.write(json.dumps(metrics) + "\n")

    rebuild_data_file()

    print(
        f"[{now.strftime('%Y-%m-%d %H:%M UTC')}]"
        f"  reqs={metrics.get('requests', '?')}"
        f"  reduction={metrics.get('reduction_pct', '?')}%"
        f"  cache_hit={metrics.get('cache_hit_rate', '?')}%"
        f"  saved={metrics.get('tokens_saved', '?')}"
        f"  overhead={metrics.get('overhead_avg_ms', '?')}ms"
    )


if __name__ == "__main__":
    main()
