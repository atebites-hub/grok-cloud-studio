Feature: Node >= 22.13 bootstrap for @cursor/sdk
  Unique remaining vs origin/main: scripts/cloud/sdk/ensure-node.sh
  (GCS_NODE, PATH, cache ~/.cache/gcs-node) so sdk/run.sh can start.
  Studio hosts may still be Node 20. Unit tests must not download
  nodejs.org tarballs; they use fake bins and GCS_NODE / GCS_NODE_CACHE.
  This slice is ensure-node only — do not restack CLOUD_FORCE_REST
  fallback. Do not remint extraHighModel / PAL-48 LIV-67. Never Bot CloudAgent.

  Scenario: GCS_NODE >= 22.13 wins over PATH
    Given GCS_NODE points at a fake node that prints v22.14.0
    And PATH has an older fake node
    And curl is stubbed to refuse downloads
    When ensure-node.sh runs
    Then it prints the GCS_NODE path
    And curl was not invoked

  Scenario: PATH node >= 22.13 is used when GCS_NODE is unset
    Given PATH has a fake node that prints v22.13.0
    And curl is stubbed to refuse downloads
    When ensure-node.sh runs
    Then it prints that PATH node
    And curl was not invoked

  Scenario: cache ~/.cache/gcs-node is used when PATH is too old
    Given PATH has a fake node that prints v20.18.0
    And GCS_NODE_CACHE holds a fake v22.14.0 binary
    And curl is stubbed to refuse downloads
    When ensure-node.sh runs
    Then it prints the cached node path
    And curl was not invoked

  Scenario: missing Node does not download a tarball in unit tests
    Given curl is stubbed to refuse downloads
    And no GCS_NODE, PATH, or cache binary is usable
    When ensure-node.sh runs
    Then it exits 75 with CLOUD_SDK_ERR
    And no tarball is stored in the cache
