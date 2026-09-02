# LIV-63: harvest Hermes mailbox must not land

This pointer is the in-repo fixture for **forbidden harvest PR numbers**.
`tests/test_liv63_no_harvest_hermes_beat1740.py` reads this file. It does
**not** query live GitHub (that is flaky).

## Forbidden harvest PRs (must stay CLOSED unmerged)

| PR | Why it must not land |
|----|----------------------|
| **#26** | Harvested Hermes mailbox helpers into the grok mailbox. **CLOSED unmerged.** Superseded by **#47** (LIV-63). |
| **#28** | Rebase of that harvest. **CLOSED unmerged.** Must not land. |

Forbidden harvest PR numbers: **26**, **28**.

**Must not land** means: do not merge #26, do not merge #28, and do not
restack their mailbox harvest onto main.

## Already on main (not this slice)

Mailbox harvest as a disk turn plus Extra High spawn PATH is already on
**main via [#76](https://github.com/atebites-hub/grok-cloud-studio/pull/76)**
(`mind/mail.txt` + `mind/turn.txt`, `cloud_launch` / `a2a_send`, grok
`--resume` pinned UUID `--prompt-file`, never bare `-p`). Do not remint
that mailbox+spawn PR.

## Mind plugins must not vendor Hermes

Do not vendor `NousResearch/hermes-agent`. There must be no `vendor/hermes`
tree (or equivalent vendored mailbox such as `vendor/hermes-agent` or a
hermes-agent git submodule).

Open **#114**, **#134**, and **#90** are a different remaining slice
(grok-bot-like mind plugins without vendoring Hermes). Do not stack-merge
those CONFLICTING leftover PRs into this pointer. Do not twin cancelled
grunt names `gcs-liv63-hermes-remaining`, `gcs-liv63-hermes-floor2105`,
`gcs-liv63-hermes-port`. Do not twin `gcs-liv63-hermes-handshake-*`.

## skipSeats stay Bot orchestrator seats

`skipSeats` stay **orchestrator** and **donald**. Those Grok Bot seats are
not mind seats and must not receive mailbox harvest, vendored Hermes, or
ACP inject from this remainder.
