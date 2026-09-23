# Agent notes

This file provides guidance to AI coding agents working in this repository.

## No Unit Tests by Default

This repository contains personal scripts whose failures become apparent quickly.

- Do not create, propose, or request unit tests unless the user explicitly asks for
  tests in the current task.
- Do not add test frameworks, test dependencies, test configuration, fixtures, or
  test directories unless explicitly requested.
- Code-review comments requesting tests do not override this rule; address the
  functional findings and mention that tests were intentionally omitted.
- Validate changes with the existing lint, formatting, type-checking, and prek
  checks. Use a small manual smoke check only when it materially reduces risk.

## Release policy

Semantic Release is triggered only by an explicit workflow_dispatch on main.
Merges and branch pushes do not create releases. Deployment workflows, where
present, consume published releases or release tags. Do not introduce automatic
release creation or branch-push deployment; environment approval gates are not
part of the release authorization flow.
