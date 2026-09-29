# Running the sweep on RunPod

`run_on_runpod.sh` creates a pod, uploads the `simulation` folder, runs the test
suite and the Monte Carlo sweep, downloads the results into `simulation/results`,
and terminates the pod (also on error or after `MAX_HOURS`).

```bash
RUNPOD_API_KEY=XXXXXXX SAMPLES=5000 ./run_on_runpod.sh
```

* Put your key in a file `.runpodapi` at the repository root (it is listed in
  `.gitignore`, so git never commits it):

  ```
  RUNPOD_API_KEY=XXXXXXX
  ```

  or pass it on the command line. Never commit a real key; revoke temporary keys after use.
* The sweep is CPU work. GPU pods are used because they come with many vCPUs.
  The published 5,000-sample run (full trace chemistry) used a 16-vCPU pod with
  a 13-CPU container quota ($0.74/hr): 1,345 s of wall time, about $0.30.
  `GPU_TYPE` lists fallbacks, since a given GPU type is often sold out.
* The pod image is python:3.10-slim and installs the pinned `requirements.txt`;
  newer library versions stalled some feeds in testing.
* RunPod's proxy answers with its own HTML pages (HTTP 200) while a pod starts,
  so the driver checks the job server's own replies, not status codes.
* The pod reports the host's core count (256), not its quota. The sweep reads
  the cgroup quota itself (`sweep.available_cpus()`) and the driver sets one
  BLAS/OpenMP thread per worker; without both, hundreds of workers thrash.
* Progress: the driver mirrors the sweep's latest `STATUS` line into its own
  log every minute. Run it detached so a closed terminal does not stop it:

  ```bash
  SAMPLES=5000 nohup setsid ./run_on_runpod.sh > ../../results/log_runpod_5000.txt 2>&1 &
  ```

* If this machine dies, the pod keeps running (and billing) and nothing
  terminates it. List pods with `curl -H "Authorization: Bearer $KEY"
  https://rest.runpod.io/v1/pods`; the run's `X-Token` is in the pod's `env`
  (`JOB_TOKEN`), so results can still be fetched before you delete the pod.
* The sweep on the pod checkpoints each finished sample, so re-sending the job
  resumes an interrupted run.
* `job_server.py` is the tiny HTTP server the pod runs. Every request needs the
  random `X-Token` generated for that run.
