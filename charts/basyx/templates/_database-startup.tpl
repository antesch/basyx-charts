{{/* Wait on the effective writer connection without Kubernetes API permissions. */}}
{{- define "basyx.database.waitForSchema" -}}
{{- $root := .root -}}
{{- $values := index $root.Values .component -}}
{{- $globalWait := $root.Values.database.waitForSchema | default dict -}}
{{- $wait := mergeOverwrite (deepCopy $globalWait) ($values.waitForSchema | default dict) -}}
{{- if $wait.enabled }}
{{- $expectedVersion := required "waitForSchema.expectedVersion must be set when enabled; use --reset-then-reuse-values to merge new chart defaults on upgrades" $wait.expectedVersion -}}
{{- range $key := list "image" "intervalSeconds" "timeoutSeconds" "connectTimeoutSeconds" -}}
{{- $_ := required (printf "waitForSchema.%s must be set when enabled; use --reset-then-reuse-values to merge new chart defaults on upgrades" $key) (get $wait $key) -}}
{{- end -}}
{{- range $key := list "repository" "pullPolicy" -}}
{{- $_ := required (printf "waitForSchema.image.%s must be set when enabled" $key) (get $wait.image $key) -}}
{{- end -}}
initContainers:
  - name: wait-for-schema
    image: {{ include "basyx.image" (dict "root" $root "image" $wait.image) | quote }}
    imagePullPolicy: {{ $wait.image.pullPolicy }}
    securityContext:
      {{- toYaml $values.securityContext | nindent 6 }}
    command:
      - /bin/sh
      - -ec
      - |
        {{- $root.Files.Get "files/wait-for-schema.sh" | nindent 8 }}
    env:
      {{- include "common-database-config" . | nindent 6 }}
      {{- range $key, $value := $values.environment | default dict }}
      {{- if hasPrefix "POSTGRES_" $key }}
      - name: {{ $key }}
        value: {{ tpl (print $value) $root | quote }}
      {{- end }}
      {{- end }}
      - name: EXPECTED_SCHEMA_VERSION
        value: {{ $expectedVersion | quote }}
      - name: SCHEMA_WAIT_TIMEOUT_SECONDS
        value: {{ $wait.timeoutSeconds | quote }}
      - name: SCHEMA_WAIT_INTERVAL_SECONDS
        value: {{ $wait.intervalSeconds | quote }}
      - name: SCHEMA_CONNECT_TIMEOUT_SECONDS
        value: {{ $wait.connectTimeoutSeconds | quote }}
    resources:
      {{- toYaml ($wait.resources | default dict) | nindent 6 }}
    volumeMounts:
      {{- with $values.volumeMounts }}
      {{- toYaml . | nindent 6 }}
      {{- end }}
      {{- include "common.certs.volumeMounts" $root | nindent 6 }}
{{- end -}}
{{- end -}}
