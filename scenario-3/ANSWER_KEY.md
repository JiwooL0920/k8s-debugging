# ANSWER KEY — Scenario 3 Bugs
# DO NOT READ UNTIL YOU'VE FINISHED DEBUGGING

## Scenario: inference-api deployment fails across multiple layers — image, config, resources, probes, and networking

---

### Bug 1: Wrong image tag + imagePullPolicy: Always (Layer 1 — immediate)

- **Symptom**: All pods stuck in `ErrImagePull` or `ImagePullBackOff` immediately after deploy.
- **Root cause**: Two problems working together:
  1. `image: inference-api:v1.2.3` — the image was built and loaded into Kind as `inference-api:1.0.0`. The tag `v1.2.3` doesn't exist anywhere.
  2. `imagePullPolicy: Always` — forces Kubernetes to pull from a remote registry on every pod start. Since this image only lives locally inside the Kind cluster, the pull fails with `ImagePullBackOff`.
- **Fix**: Correct the image tag and change the pull policy:
  ```yaml
  image: inference-api:1.0.0
  imagePullPolicy: IfNotPresent
  ```
- **How to find it**: `kubectl describe pod <pod> -n scenario-3` → Events section shows `Failed to pull image "inference-api:v1.2.3": ... not found`. The `imagePullPolicy: Always` is visible in the same describe output under `Image Pull Policy`.

---

### Bug 2: ConfigMap key mismatch (Layer 2 — after fixing Bug 1)

- **Symptom**: Pods stuck in `CreateContainerConfigError`. They never reach `Running`.
- **Root cause**: The Deployment references `configMapKeyRef.key: DB_CONNECTION_STRING`, but the ConfigMap (`inference-api-config`) defines the key as `DATABASE_URL`. Kubernetes cannot populate the `DATABASE_URL` env var because the requested key doesn't exist in the ConfigMap.
- **Fix**: Change the key reference to match what the ConfigMap actually has:
  ```yaml
  env:
    - name: DATABASE_URL
      valueFrom:
        configMapKeyRef:
          name: inference-api-config
          key: DATABASE_URL
  ```
- **How to find it**: `kubectl describe pod <pod> -n scenario-3` → Events shows `Error: couldn't find key DB_CONNECTION_STRING in ConfigMap scenario-3/inference-api-config`. Cross-reference with `kubectl get configmap inference-api-config -n scenario-3 -o yaml` to see the actual keys.

---

### Bug 3: Resource limits too low — CPU starvation silently kills the pod (Layer 3 — after fixing Bug 2)

- **Symptom**: Pods enter `CrashLoopBackOff`. Restart count climbs. There is no clear log message pointing to the cause.
- **Root cause**: `cpu: "10m"` (10 millicores = 1% of a CPU core) is far too low for Python + Flask + Gunicorn to start in time. The interpreter and framework take 20–60+ seconds to initialize under this level of CPU throttling. The liveness probe starts firing at `initialDelaySeconds: 5` with `failureThreshold: 3` — the container gets killed by the kubelet long before the app finishes booting. Kubernetes then restarts it, and the cycle repeats.

  The tricky part: **nothing in the logs or events explicitly mentions CPU**. The events only say the liveness probe failed (`connection refused` or `context deadline exceeded`), which looks identical to a crashing app. This is what makes it a silent failure.

- **Fix**: Set realistic resource values:
  ```yaml
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "500m"
      memory: "256Mi"
  ```
- **How to find it**: `kubectl describe pod <pod> -n scenario-3` → Events show `Liveness probe failed: dial tcp: connect: connection refused` (not OOMKilled, not an app error). The pod never even reaches the log-emitting stage. The diagnostic signal is `kubectl top pod -n scenario-3` — CPU usage is pinned at the limit with 0 headroom. Cross-referencing this with the low limit in `deployment.yaml` reveals the root cause.

---

### Bug 4: Health probe paths point to non-existent endpoints (Layer 4 — after fixing Bug 3)

- **Symptom**: Pods are `Running` but show `0/2 Ready`. The readiness probe keeps failing.
- **Root cause**: Both probes reference Flask endpoints that don't exist:
  - `livenessProbe.httpGet.path: /healthz` — app exposes `/health`, not `/healthz`
  - `readinessProbe.httpGet.path: /readyz` — app exposes `/ready`, not `/readyz`

  Flask returns `404 Not Found` for both. The liveness probe eventually kills the pod; the readiness probe prevents traffic from ever reaching it.
- **Fix**: Update both probe paths to match the actual endpoints:
  ```yaml
  livenessProbe:
    httpGet:
      path: /health
      port: 8080
  readinessProbe:
    httpGet:
      path: /ready
      port: 8080
  ```
- **How to find it**: `kubectl describe pod <pod> -n scenario-3` → Events show `Readiness probe failed: HTTP probe failed with statuscode: 404`. Open `app/server.py` and search for `@app.route` to confirm the correct paths are `/health` and `/ready`.

---

### Bug 5: Service selector label mismatch (Layer 5 — after fixing Bug 4)

- **Symptom**: Pods are `2/2 Ready` but `kubectl get endpoints inference-api -n scenario-3` shows `<none>`. `make verify` fails to connect.
- **Root cause**: The Service spec has `selector: app: inferenceapi` (no hyphen), while the pod template labels use `app: inference-api` (with hyphen). Kubernetes label selectors are exact-match — no pods are selected, so the endpoint slice stays empty and traffic never reaches the pods.
- **Fix**: Correct the Service selector:
  ```yaml
  spec:
    selector:
      app: inference-api
  ```
- **How to find it**: `kubectl get endpoints -n scenario-3` → shows `<none>`. Then `kubectl describe svc inference-api -n scenario-3` → `Selector: app=inferenceapi`. Compare with `kubectl get pods -n scenario-3 --show-labels` → pods have `app=inference-api`. The mismatch is the single missing hyphen.

---

## Debugging Flow (ideal walkthrough)

```
1.  kubectl get pods -n scenario-3               → ImagePullBackOff
2.  kubectl describe pod <pod> -n scenario-3     → "Failed to pull image: v1.2.3 not found"
3.  Check deployment.yaml image + imagePullPolicy → wrong tag + Always
4.  Fix: image: inference-api:1.0.0 + IfNotPresent → pods still not starting
5.  kubectl describe pod <pod>                   → "CreateContainerConfigError"
6.  Events: "couldn't find key DB_CONNECTION_STRING"
7.  kubectl get configmap inference-api-config -o yaml → key is DATABASE_URL
8.  Fix configMapKeyRef.key: DATABASE_URL        → pods now CrashLoopBackOff
9.  kubectl describe pod <pod>                   → Events: "Liveness probe failed: connection refused"
10. kubectl logs <pod>                           → nothing (app never started)
11. kubectl top pod -n scenario-3               → CPU pinned at 10m limit
12. Check deployment.yaml resources             → cpu: 10m (way too low for Python+Flask+Gunicorn startup)
13. Fix cpu to 100m, memory to 128Mi/256Mi      → pods Running but 0/2 Ready
14. kubectl describe pod <pod>                   → "Readiness probe failed: 404"
14. kubectl describe pod <pod>                   → "Readiness probe failed: 404"
15. Check app/server.py for routes               → /health and /ready (not /healthz /readyz)
16. Fix probe paths                              → pods 2/2 Ready, but verify fails
17. kubectl get endpoints -n scenario-3          → <none>
18. kubectl describe svc inference-api           → Selector: app=inferenceapi
19. kubectl get pods --show-labels               → app=inference-api (hyphen missing in svc)
20. Fix Service selector                         → endpoints populate
21. make verify                                  → 200 OK on all endpoints
```

## Commands to verify final fix

```bash
kubectl get pods -n scenario-3
kubectl get endpoints -n scenario-3
make verify
```
