# Project: claude-code-tts — Repo Security Hardening

## Problem Statement

Public repo shared with contributors has no branch protections or access controls. Anyone with push access can force-push to `main`, merge without reviews, or bypass CI. Need to lock down before unwanted changes land.

## Success Criteria

- [x] Branch protection active on `main` with PR reviews required
- [x] CI status checks required before merge
- [x] Force pushes and branch deletion blocked
- [x] Delete-branch-on-merge enabled
- [x] CODEOWNERS file requiring owner review
- [x] Wiki and projects disabled
- [x] Conversation resolution required

## Phases

### MVP
All P0 items: branch protection on `main` requiring PR reviews and CI checks, force push/deletion blocked, delete-branch-on-merge enabled.

### v1.1
P1 items: CODEOWNERS file, disable unused features (wiki, projects), require conversation resolution.

### Later / Icebox
- Require signed commits
- Dependabot configuration for dependency security alerts
- Release branch protections

## Backlog

| # | Feature | Priority | Phase | Status | Notes |
|---|---------|----------|-------|--------|-------|
| 1 | Branch protection on main | P0 | MVP | done | PR reviews, block force push/deletion |
| 2 | Require CI status checks | P0 | MVP | done | All 4 pytest matrix jobs required |
| 3 | Delete branch on merge | P0 | MVP | done | |
| 4 | CODEOWNERS file | P1 | v1.1 | done | @mpaarating owns all files |
| 5 | Disable wiki and projects | P1 | v1.1 | done | |
| 6 | Require conversation resolution | P1 | v1.1 | done | |
| 7 | Require signed commits | P2 | Later | not started | |
| 8 | Dependabot config | P2 | Later | not started | |
| 9 | Release branch protections | P2 | Later | not started | |

## Research Questions

(none — all items resolved)

## Key Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-14 | Project scope defined | Initial intake |
| 2026-04-14 | Admin bypass enabled (enforce_admins: false) | Owner wants ability to push quick fixes directly in emergencies |
| 2026-04-14 | All P0 and P1 items implemented | Straightforward chore, no research needed |
