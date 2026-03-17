# ANSWER KEY — Scenario 2 Bugs
# DO NOT READ UNTIL YOU'VE FINISHED DEBUGGING

## Scenario: data-processor deployment crashes and won't serve traffic

### Bug 1: Memory limit too low — OOMKilled (Layer 1 — immediate)
- **Symptom**: All pods in `CrashLoopBackOff`. Restart count climbs rapidly.
- **Root cause**: `resources.limits.memory: "10Mi"` and `resources.requests.memory: "10Mi"`. Python + Flask + Gunicorn needs at minimum ~50MB to start. With only 10Mi, the container is immediately killed by the OOM killer when it exceeds the memory limit.
- **Fix**: Increase memory to reasonable values:
  ```yaml
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "500m"
      memory: "256Mi"
  ```
- **How to find it**: `kubectl describe pod <pod>` → in the "Last State" section, you'll see `Reason: OOMKilled` with `Exit Code: 137`. Also visible in `kubectl get pods` — the STATUS alternates between `OOMKilled` and `CrashLoopBackOff`.

### Bug 2: Container command override with wrong module (Layer 2 — after memory fix)
- **Symptom**: Pods still in `CrashLoopBackOff`, but now for a different reason. Restart count keeps climbing.
- **Root cause**: The Deployment specifies `command: ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:create_app()"]`. This overrides the Dockerfile's `CMD`. The module `app` doesn't exist — the file is `server.py` and the WSGI callable is `app` in module `server`. Gunicorn fails with `ModuleNotFoundError: No module named 'app'`.
- **Fix**: Remove the `command` field entirely (let the Dockerfile `CMD` handle it), or correct it to:
  ```yaml
  command: ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
  ```
  Removing the `command` field is the cleaner approach — the Dockerfile already has the correct CMD.
- **How to find it**: `kubectl logs <pod>` → shows `ModuleNotFoundError: No module named 'app'` or `Failed to find attribute 'create_app()' in 'app'`. Compare with the Dockerfile's CMD to see the correct module reference.

### Bug 3: Readiness probe points to POST-only endpoint (Layer 3 — after command fix)
- **Symptom**: Pods are `Running` but show `0/2 Ready`. `kubectl get endpoints data-processor` shows `<none>`. Port-forwarding the Service fails with "no endpoints available".
- **Root cause**: `readinessProbe.httpGet.path: "/api/v1/data"` — but this endpoint only accepts `POST` requests. The kubelet sends a `GET` request for the probe, which returns `405 Method Not Allowed`. The readiness probe fails, so the pod is never added to the Service's endpoints.
- **Fix**: Change the readiness probe path to `/readyz`:
  ```yaml
  readinessProbe:
    httpGet:
      path: /readyz
      port: 8080
  ```
- **How to find it**: `kubectl describe pod <pod>` → Events show `Readiness probe failed: HTTP probe failed with statuscode: 405`. Check the `server.py` to see that `/api/v1/data` is `methods=["POST"]` only, while `/readyz` is the actual readiness endpoint.

## Debugging Flow (ideal walkthrough)

```
1. kubectl get pods -n scenario-2              → sees CrashLoopBackOff, multiple restarts
2. kubectl describe pod <pod> -n scenario-2    → Last State shows OOMKilled, Exit Code 137
3. Checks resource limits in deployment.yaml   → memory: 10Mi is far too low
4. Fixes memory limits (128Mi/256Mi)           → pods still CrashLoopBackOff
5. kubectl logs <pod> -n scenario-2            → "ModuleNotFoundError: No module named 'app'"
6. Checks Dockerfile CMD                       → correct: "server:app"
7. Checks deployment.yaml command field        → wrong: "app:create_app()"
8. Removes command override from deployment    → pods Running but 0/2 Ready
9. kubectl describe pod <pod>                  → readiness probe failed: 405
10. Checks readiness probe path                → /api/v1/data (POST-only endpoint)
11. Checks server.py for correct readiness path → /readyz
12. Fixes readiness probe to /readyz            → pods 2/2 Ready
13. make verify                                 → 200 OK, done!
```

## Commands to verify final fix
```bash
kubectl port-forward svc/data-processor 7070:80 -n scenario-2 &
curl localhost:7070/
curl localhost:7070/healthz
curl localhost:7070/readyz
```
