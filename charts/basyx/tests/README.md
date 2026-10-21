Install the Helm unittest plugin once:

```bash
helm plugin install https://github.com/helm-unittest/helm-unittest --verify=false
```

Run the chart tests with:

```bash
helm unittest .
```

From the repository root, test the schema-wait shell script with:

```bash
sh .github/scripts/test-schema-wait.sh
```

`ci/startup-values.yaml` enables a real AAS Environment backend during
chart-testing installs. To reproduce a fresh startup test in an isolated
namespace on a cluster with CloudNativePG and cert-manager installed:

```bash
helm install startup charts/basyx \
  --namespace basyx-startup-test --create-namespace \
  --values charts/basyx/ci/startup-values.yaml \
  --wait --wait-for-jobs --timeout 20m
```

For upgrades from chart 3.16.1, `fixtures/legacy-upgrade.yaml` supplies values
without the new schema-wait block. Test these paths in separate disposable
namespaces after the old release and backend are healthy:

- Upgrade with the same values file: the new chart defaults enable schema waiting.
- Upgrade with `--reuse-values`: old defaults are retained and schema waiting
  stays disabled when its configuration is absent.
- Upgrade with `--reset-then-reuse-values`: the new defaults are merged with
  existing user overrides and schema waiting is enabled.

Check that the database/PVC and test data survive and that the upgraded
backend is healthy. Bootstrap the old chart without `--wait`, because its
`post-install` migration hook can otherwise block initial backend readiness.

The suites cover stable chart contracts such as:

- default ABAC config and derived trust list
- ABAC enablement, disablement and legacy override compatibility
- precedence of service-local ABAC overrides over global defaults
- ABAC mounts and rollout checksum annotations in backend deployments
- optional AAS Environment deployment, ingress and ABAC wiring
- optional DPP API deployment, ingress and ABAC wiring
- Catena-X example values and marker-based ABAC wiring
- common OIDC and ingress configuration
- Web UI infrastructure pruning of disabled chart-managed components
- structured logging, optional OTLP traces and metrics, telemetry Secret wiring, and CloudNativePG PodMonitors
- additional custom CA certificate mounts and trust-store wiring
- runtime `helm test` hook for custom CA mount checks
- service account helper behavior
- digest-aware image rendering
- schema-gated backend startup, per-service overrides, and install/upgrade Job lifecycle
- schema validation for required values and basic formats
- managed PostgreSQL storage, WAL, resources, scheduling and parameters
- optional CloudNativePG read-write and read-only Pooler rendering, reader routing, and monitoring
- optional CPU and memory HorizontalPodAutoscalers for every shared BaSyx Go backend deployment
- shared per-pod PostgreSQL pool defaults and Configuration Service propagation
- keycloak init resources and a runtime `helm test` realm check
- Gateway API HTTPRoute rendering, parentRefs precedence and fail-fast validation
- optional self-managed Gateway rendering, className validation and derived HTTPRoute parentRefs
- optional BaSyx Studio deployment, derived infrastructure, Keycloak client, Ingress and HTTPRoute, and Secret handling
- a Studio data key that GitOps renders (Argo CD) cannot generate or replace
