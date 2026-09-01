# Project direction

This repository is an independent development base derived from
`Andrem19/work-researcher-mcp`.

The inherited MCP search, ranking, candidate-profile, local-CV and application
tracking behavior is the working baseline. No bot-specific runtime has been
implemented during project bootstrap.

Planned later, in separate changes:

- run continuously on a server;
- execute vacancy checks on a daily schedule;
- select and summarize newly discovered vacancies;
- send results and operational notifications to Telegram;
- define deployment, secrets and failure-recovery behavior.

Until those decisions are implemented, use and test this repository exactly as
the original MCP baseline described in `README.md` and `SETUP.md`.
