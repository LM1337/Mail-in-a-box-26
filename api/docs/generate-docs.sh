#!/usr/bin/env sh

# Requirements:
# - Node.js >= 22.12 (or 20.19+), npm >= 10
# - @redocly/cli 2.69.0, fetched by npx below (or `npm install -g @redocly/cli@2.69.0`
#   and run `redocly build-docs` with the same arguments).
#   redoc-cli is deprecated (last release 0.13.21, 2023); its successor is `redocly build-docs`,
#   which takes the old --options.X settings as --theme.openapi.X.

REDOCLY_TELEMETRY=off npx --yes @redocly/cli@2.69.0 build-docs ../mailinabox.yml \
  -t template.hbs \
  -o api-docs.html \
  --templateOptions.metaDescription="Mail-in-a-Box HTTP API" \
  --title="Mail-in-a-Box HTTP API" \
  --theme.openapi.expandSingleSchemaField \
  --theme.openapi.hideSingleRequestSampleTab \
  --theme.openapi.jsonSampleExpandLevel=10 \
  --theme.openapi.hideDownloadButton \
  --theme.openapi.theme.logo.maxHeight=180px \
  --theme.openapi.theme.logo.maxWidth=180px \
  --theme.openapi.theme.colors.primary.main="#C52" \
  --theme.openapi.theme.typography.fontSize=16px \
  --theme.openapi.theme.typography.fontFamily="Raleway, sans-serif" \
  --theme.openapi.theme.typography.headings.fontFamily="Ubuntu, Arial, sans-serif" \
  --theme.openapi.theme.typography.code.fontSize=15px \
  --theme.openapi.theme.typography.code.fontFamily='"Source Code Pro", monospace'
