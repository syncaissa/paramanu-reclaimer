#!/usr/bin/env bash
# Run any PARAMANU experiment script on a RunPod pod and bring its results back.
#
#   JOB_SCRIPT="20_falsification.py --gens 20" OUTPUTS="falsification.csv" \
#   KEY_PREFIX=falsification LOG_NAME=log_20_falsification.txt ./run_job_on_runpod.sh
#
# The script's STATUS lines are mirrored into this script's output; the files in
# OUTPUTS (under results/) are downloaded, and key_numbers.json entries whose
# name starts with KEY_PREFIX are merged into the local key_numbers.json.
#
# Never commit a real key: keep XXXXXXX in this file and pass the key in the
# environment. The pod is terminated automatically when the sweep ends or after
# MAX_HOURS. The sweep uses CPU cores only; a GPU pod is used here because GPU
# pods come with many vCPUs (e.g. RTX 3090: 32 vCPU, 125 GB RAM, ~$0.50/hr).
set -euo pipefail
# Wrapped in main so bash parses the whole script before running it: editing
# this file during a run would otherwise make bash resume mid-line.
main() {
# key: environment first, else the git-ignored file .runpodapi at the repository root
KEYFILE="$(cd "$(dirname "$0")/../../.." && pwd)/.runpodapi"
if [ -z "${RUNPOD_API_KEY:-}" ] && [ -f "$KEYFILE" ]; then
  RUNPOD_API_KEY="$(grep -E '^RUNPOD_API_KEY=' "$KEYFILE" | cut -d= -f2-)"
fi
RUNPOD_API_KEY="${RUNPOD_API_KEY:-XXXXXXX}"
JOB_SCRIPT="${JOB_SCRIPT:?set JOB_SCRIPT}"
OUTPUTS="${OUTPUTS:-}"
KEY_PREFIX="${KEY_PREFIX:?set KEY_PREFIX}"
LOG_NAME="${LOG_NAME:-log_runpod_job.txt}"
# comma-separated fallbacks: RunPod picks the first type with free capacity
GPU_TYPE="${GPU_TYPE:-NVIDIA GeForce RTX 3090,NVIDIA GeForce RTX 4090,NVIDIA RTX A5000,NVIDIA RTX A4500,NVIDIA RTX A4000,NVIDIA GeForce RTX 3080}"
MAX_HOURS="${MAX_HOURS:-3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SIM="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d)"
[ "$RUNPOD_API_KEY" = "XXXXXXX" ] && { echo "set RUNPOD_API_KEY"; exit 1; }

TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
tar -czf "$WORK/sim.tar.gz" -C "$SIM/.." --exclude='__pycache__' \
    --exclude='simulation/results/*.csv' --exclude='simulation/results/*.p*' --exclude='simulation/results/superseded' simulation
BODY=$(python3 - "$(base64 -w0 "$HERE/job_server.py")" "$TOKEN" "$GPU_TYPE" <<'PY'
import json, sys
srv, tok, gpu = sys.argv[1:]
print(json.dumps({"name": "paramanu-job", "computeType": "GPU", "gpuTypeIds": [g.strip() for g in gpu.split(",")], "gpuCount": 1,
                  "imageName": "python:3.10-slim", "containerDiskInGb": 20, "ports": ["8000/http"],
                  "env": {"JOB_TOKEN": tok, "SRV_B64": srv},
                  "dockerStartCmd": ["bash", "-c", "echo $SRV_B64 | base64 -d > /srv.py && exec python /srv.py"]}))
PY
)
POD=$(curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $RUNPOD_API_KEY" \
      -d "$BODY" https://rest.runpod.io/v1/pods | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r.get("id") or sys.exit("pod not created: %s" % r))')
URL="https://$POD-8000.proxy.runpod.net"
terminate() { curl -s -X DELETE -H "Authorization: Bearer $RUNPOD_API_KEY" "https://rest.runpod.io/v1/pods/$POD" >/dev/null; echo "pod $POD terminated"; }
trap terminate EXIT
echo "pod $POD"

# While a pod starts, RunPod's proxy answers with its own HTML pages and HTTP 200,
# so every check below looks for our job server's own reply, not the status code.
until curl -s -m 15 -H "X-Token: $TOKEN" "$URL/" | grep -q "Directory listing for /"; do sleep 10; done
until [ "$(curl -s -m 120 -X PUT -H "X-Token: $TOKEN" --data-binary @"$WORK/sim.tar.gz" "$URL/upload")" = "uploaded" ]; do
  echo "upload failed, retrying"; sleep 10
done
echo "uploaded"
# Workers default to the container's CPU quota (sweep.available_cpus), not the
# host's core count; one BLAS/OpenMP thread per worker. Otherwise hundreds of
# workers x dozens of threads thrash a ~31-CPU quota.
JOB="cd /work/simulation && pip install -q -r requirements.txt && python -m pytest -q -p no:cacheprovider | tail -1; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; cd scripts && python -W ignore $JOB_SCRIPT > /work/sweep.log 2>&1; echo EXIT=\$? > /work/DONE"
until [ "$(curl -s -m 30 -X POST -H "X-Token: $TOKEN" --data-binary "$JOB" "$URL/run")" = "started" ]; do
  echo "job start failed, retrying"; sleep 10
done
echo "job started"

START=$(date +%s)
until curl -s -m 20 -H "X-Token: $TOKEN" "$URL/DONE" | grep -q "^EXIT="; do
  if [ $(( $(date +%s) - START )) -gt $(( MAX_HOURS * 3600 )) ]; then
    echo "timeout"
    curl -s -f -H "X-Token: $TOKEN" "$URL/sweep.log" -o "$SIM/results/$LOG_NAME"
    exit 1
  fi
  sleep 60
  # mirror the sweep's latest STATUS line into this script's log
  echo "$(date -u '+%F %T') pod $POD: $(curl -s -m 20 -H "X-Token: $TOKEN" "$URL/sweep.log" | grep STATUS | tail -1)"
done
for f in $OUTPUTS; do
  curl -s -f -H "X-Token: $TOKEN" "$URL/simulation/results/$f" -o "$SIM/results/$f" && echo "downloaded $f"
done
# merge only the sweep's own entries, so numbers recorded locally meanwhile survive
curl -s -f -H "X-Token: $TOKEN" "$URL/simulation/results/key_numbers.json" -o "$WORK/key_numbers_pod.json" && \
python3 - "$WORK/key_numbers_pod.json" "$SIM/results/key_numbers.json" "$KEY_PREFIX" <<'PY'
import json, sys
pod, local = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
local.update({k: v for k, v in pod.items() if k.startswith(sys.argv[3])})
open(sys.argv[2], "w").write(json.dumps(local, indent=2, sort_keys=True))
print("merged", sys.argv[3], "entries into key_numbers.json")
PY
curl -s -f -H "X-Token: $TOKEN" "$URL/sweep.log" -o "$SIM/results/$LOG_NAME" && echo "downloaded log"
curl -s -H "X-Token: $TOKEN" "$URL/sweep.log" | tail -1
}
main "$@"
exit
