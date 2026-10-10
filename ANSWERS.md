# Part 5 — Written question

## Q1. Migrating ~40 Ingress objects from ingress-nginx to Kubernetes Gateway API with no downtime

- **Inventory first:** Export all Ingresses and identify hosts, paths, TLS secrets, annotations, rewrites, auth, rate limits, timeouts, body-size limits, IP allowlists, and controller-specific behavior. Group routes by application and risk. Capture current traffic/error-rate baselines and define rollback criteria.
- **Validate the target:** Confirm the chosen Gateway API implementation supports the required Gateway API versions and features. Install its CRDs/controller in parallel with ingress-nginx, configure certificates, DNS, policies, observability, and network access. Translate a representative low-risk application first; annotations often have no direct equivalent and may need implementation-specific policies or application changes.
- **Run both paths in parallel:** Create Gateway and HTTPRoute resources without deleting existing Ingresses. Validate route status/conditions, TLS, redirects, headers, health checks, large requests, WebSockets, and authentication. Test from inside and outside the cluster.
- **Shift traffic gradually:** Use a canary hostname or weighted DNS/load-balancer traffic if supported. Increase traffic in stages while comparing latency, 4xx/5xx rates, TLS behavior, and application metrics. Keep ingress-nginx serving the old path throughout the observation window.
- **Rollback safely:** Keep the old Ingresses and controller configuration intact until the new path is proven. Document a fast traffic switch-back and test it before broad migration.
- **Expect breakage:** Controller-specific annotations, rewrite semantics, default backends, path precedence, TLS defaults, client-IP handling, source-IP allowlists, timeouts, auth, and rate limiting are common gaps. DNS and certificate mistakes can also cause outages.

I would migrate in small batches, not all 40 at once. “No downtime” is an objective validated by staged traffic and rollback, not something guaranteed merely by creating Gateway API resources.
