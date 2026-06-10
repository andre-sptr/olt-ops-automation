# Perform History Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a standalone February–May 2026 TTR 6-hour Telegram history backfill.

**Architecture:** Keep period filtering, parsing, context resolution, and row construction testable in `backfill_perform.py`. Runtime orchestration scans Telegram, previews results, and safely copies the source layout into one destination tab per month.

**Tech Stack:** Python 3, Telethon, gspread, pytest.

---

### Task 1: Period and parser behavior

**Files:**
- Create: `backfill_perform.py`
- Create: `tests/test_backfill_perform.py`

- [x] Test February beginning on February 20.
- [x] Test full-month filtering for March through May.
- [x] Test recovery duration, day-column placement, RCA, and district resolution.
- [x] Test that the TTR 3-hour table remains empty.

### Task 2: Telegram collection and preview

**Files:**
- Modify: `backfill_perform.py`

- [x] Scan `TR1 - OM NE Akses` without unreliable server-side text filtering.
- [x] Resolve PROGRAM ZERO context per hostname and month.
- [x] Print monthly counts and record previews.
- [x] Verify February, March, April, and May counts before writing.

### Task 3: Safe archive creation

**Files:**
- Modify: `backfill_perform.py`

- [x] Copy the `Gamas ISP` layout to the destination workbook.
- [x] Resize and populate only the TTR 6-hour table.
- [x] Reject existing tabs and roll back tabs created by a failed run.
- [x] Read back and verify all four destination tabs.
