# Living Sky Linear (LIV-*)

Hive stamps **Living Sky** Linear (`linear.app/livingsky`, team key `LIV`)
only after **real evidence**:

| Evidence | Trigger |
|---|---|
| Mind turn | `mind.py` `process_once` after runner exit 0 and offset advance (`MIND_TURN`) |
| Extra High launch | `CLOUD_LAUNCH_OK` + bc-id from `launch-cloud-extra-high.sh` / `sdk/launch.ts` |

Hub `TASK_STATE_COMPLETED` (A2A `message:send` ACK) is a **receipt**, not a
turn (LIV-85). `scripts/a2a/hub.py` must not stamp Linear.

## Fail closed

`LINEAR_API_KEY` (or `GCS_LINEAR_API_KEY`) may be unset. Then a stamp that
would have posted a `LIV-*` comment logs `LINEAR_STAMP_FAIL reason=no-key`
and **does not** invent a comment id or write a success artifact.

Mail without a `LIV-*` identifier (keep-alives, ACP_PING) is
`LINEAR_STAMP_SKIP reason=no-issue` and does not require a key.

## Never

- Black Swan / team keys other than `LIV` / `GCS_LINEAR_TEAM_KEY=BSM`
- Grok Bot CloudAgent / `skipSeats` (`donald`, `orchestrator`)
- Vendoring Hermes
- Faking a stamp so a dashboard looks green

Implementation: `scripts/directors/liv_evidence_stamp.py`.
Stdlib GraphQL to `https://api.linear.app/graphql`. Never print the key.

Disable (tests/ops): `GCS_LINEAR_STAMP=0`.
