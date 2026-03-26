# Architecture Notes

This directory is reserved for subsystem-level architecture notes that sit below the canonical top-level specifications.

Use this area for documents that answer questions such as:

- what a module owns and does not own
- what inputs and outputs cross a boundary
- which dependencies are allowed
- which actions are explicitly forbidden inside that module
- how the module is verified

Keep the current top-level specs in `docs/` as the canonical source until a dedicated migration task moves them.
