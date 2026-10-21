{{/* Wait on the effective writer connection without Kubernetes API permissions. */}}
{{- define "basyx.database.waitForSchema" -}}
{{- $root := .root -}}
{{- $values := index $root.Values .component -}}
{{- $wait := mergeOverwrite (deepCopy $root.Values.database.waitForSchema) ($values.waitForSchema | default dict) -}}
{{- if $wait.enabled }}
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
        value: {{ required "database.waitForSchema.expectedVersion must not be empty" $wait.expectedVersion | quote }}
      - name: SCHEMA_WAIT_TIMEOUT_SECONDS
        value: {{ $wait.timeoutSeconds | quote }}
      - name: SCHEMA_WAIT_INTERVAL_SECONDS
        value: {{ $wait.intervalSeconds | quote }}
      - name: SCHEMA_CONNECT_TIMEOUT_SECONDS
        value: {{ $wait.connectTimeoutSeconds | quote }}
    resources:
      {{- toYaml $wait.resources | nindent 6 }}
    volumeMounts:
      {{- with $values.volumeMounts }}
      {{- toYaml . | nindent 6 }}
      {{- end }}
      {{- include "common.certs.volumeMounts" $root | nindent 6 }}
{{- end -}}
{{- end -}}
