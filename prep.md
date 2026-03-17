Braze | Platform Engineer II
Guidelines: Live Coding Interview
Overview
This interview assesses your troubleshooting skills, platform engineering fundamentals, and
problem-solving approach. You'll work through a realistic scenario involving a Kubernetes
deployment, review some CI/CD artifacts, and discuss your experience with building and
maintaining systems in production.
Duration: 75 minutes
Format: Screen share (you drive)
What to expect
Section Duration Description
Incident Troubleshooting 40 minutes Debug a broken Kubernetes

deployment.
CI/CD & Dockerfile Review 20 minutes Review and suggest
improvements to build
artifacts.

Discussion 15 minutes Talk through your approach to
incidents, understanding of
production ML systems, and
tooling.

Prerequisites
Please have the following ready before the interview:
- A local Kubernetes environment (e.g. minikube, microk8s, kind, Docker Desktop with
Kubernetes enabled)
- kubectl CLI installed and configured
- Docker installed
- The ability to push local images to your cluster (reference your local clusters
documentation, for example: https://minikube.sigs.k8s.io/docs/handbook/pushing/ )
- Your preferred IDE or text editor

Shell
You can verify your local setup by running the following commands:

# Check kubectl is working
kubectl version --client
# Check you can access your local cluster
kubectl get nodes
# Check Docker is running
docker info

If any of these fail, please troubleshoot before the interview so we can maximize our time
together.
What you can use
- Any tools you normally use for debugging purposes (e.g. IDE, terminal tools, browser)
- AI coding assistants are welcome - we’re interested in how you use them, not whether
you avoid them
- Documentation, man pages, Stack Overflow - whatever you would use in your normal
workflow
What we’re looking for
- Your thought process - think aloud as you work; we want to understand how you
approach problems, not just see the solution
- Systematic debugging - how you gather information, form hypotheses, and verify fixes
- Communication - can you explain what you’re seeing and why you’re taking certain
actions?
This isn't about getting everything perfect. We want to see how you work through unfamiliar
problems under realistic conditions.
Questions?
If you have any questions about the format or setup, reach out to your recruiter. Best of luck!
Braze Talent Acquisition Team
