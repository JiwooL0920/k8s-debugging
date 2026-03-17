# 🔒 ANSWER KEY — Scenario 1 Bugs
# DO NOT READ UNTIL YOU'VE FINISHED DEBUGGING

## Scenario: event-processor deployment is broken

### Bug 1: Wrong image tag + pull policy (Layer 1 — immediate)
- **Symptom**: All pods in `ImagePullBackOff`
- **Root cause**: `image: event-processor:latest` but only `:1.2.0` was loaded into Kind. Also `imagePullPolicy: Always` forces a registry pull, which fails in Kind.
- **Fix**: Change to `image: event-processor:1.2.0` and `imagePullPolicy: IfNotPresent` (or `Never`)
- **How to find it**: `kubectl describe pod <pod>` → Events show pull failure

### Bug 2: Wrong container port (Layer 2 — after image fix)
- **Symptom**: Pods start but enter `CrashLoopBackOff` due to failing liveness probes
- **Root cause**: `containerPort: 3000` and probes target port `3000`, but the app (gunicorn) listens on port `8080`
- **Fix**: Change `containerPort` to `8080`, update both probe `port` fields to `8080`
- **How to find it**: `kubectl logs <pod>` shows gunicorn binding to `0.0.0.0:8080`. Probe failures visible in `kubectl describe pod`.

### Bug 3: Label selector mismatch — Service (Layer 3 — after pods are healthy)
- **Symptom**: `kubectl get endpoints event-processor` shows `<none>`. Port-forwarding the Service gives "no endpoints available".
- **Root cause**: Pod labels say `app: event-processer` (typo, double 's'), Service selector says `app: event-processor` (correct spelling). They don't match.
- **Fix**: Either fix the pod template labels to `event-processor` OR fix the Service selector to `event-processer`. Best practice: fix the typo in the Deployment (selector + template labels) to `event-processor`.
- **How to find it**: `kubectl get pods --show-labels -n scenario-1`, compare with `kubectl describe svc event-processor -n scenario-1 | grep Selector`
- **Note**: Changing `spec.selector.matchLabels` on a Deployment requires delete + recreate (it's immutable).

### Bug 4: Service targetPort mismatch (Layer 3b — even after label fix)
- **Symptom**: Service routes to pods but connection refused
- **Root cause**: `targetPort: 3000` but app listens on `8080`
- **Fix**: Change `targetPort` to `8080`
- **How to find it**: `kubectl port-forward svc/event-processor 7070:80 -n scenario-1` → connection refused to backend

## Debugging Flow (ideal walkthrough)

```
1. kubectl get pods -n scenario-1              → sees ImagePullBackOff
2. kubectl describe pod <pod> -n scenario-1    → sees pull error for :latest
3. Checks Dockerfile / image tags              → realizes :1.2.0 was built
4. Fixes image tag + imagePullPolicy           → pods start, then CrashLoopBackOff
5. kubectl logs <pod> -n scenario-1            → sees gunicorn on :8080
6. kubectl describe pod <pod>                  → sees probe failures on :3000
7. Fixes containerPort + probe ports to 8080   → pods Running + Ready
8. kubectl port-forward svc/event-processor... → no traffic / connection refused
9. kubectl get endpoints event-processor       → <none>
10. kubectl get pods --show-labels              → sees "event-processer" typo
11. Compares with Service selector              → fixes labels + targetPort
12. Verifies with curl                          → 200 OK, done!
```

## Commands to verify final fix
```bash
kubectl port-forward svc/event-processor 7070:80 -n scenario-1 &
curl localhost:7070/
curl localhost:7070/healthz
curl localhost:7070/readyz
```
