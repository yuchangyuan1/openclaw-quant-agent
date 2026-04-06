# OpenClaw Runtime Layer

This directory contains the OpenClaw-native runtime structure for the project.

It separates three concerns:

- `workspaces/`
  - one workspace per agent role
  - role instructions, workflow notes, and local playbooks
- `skills/`
  - reusable capabilities shared across agents
  - standard service invocation contracts
- `runtime/`
  - runtime-oriented helper files and wrappers

The business implementation still lives in the shared `services/` directory.
The OpenClaw layer is responsible for orchestration, routing, role boundaries,
and reusable execution patterns.
