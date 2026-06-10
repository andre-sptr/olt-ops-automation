# Perform Monthly Rollover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive the previous month's `Gamas ISP` sheet, reset both active tables, and write new events into the current Indonesian month and day column.

**Architecture:** Put spreadsheet-independent month and range analysis in `perform_rollover.py`, with one orchestration function that duplicates and verifies the archive before clearing the active sheet. Keep Telegram parsing and event handling in `mirror_perform.py`, which invokes rollover on startup and before writes.

**Tech Stack:** Python 3, gspread, unittest/pytest, Google Sheets API.

---

### Task 1: Specify rollover behavior

**Files:**
- Create: `tests/test_perform_rollover.py`

- [ ] Add tests for Indonesian month labels and day-to-column mapping.
- [ ] Add a fake spreadsheet test proving an April sheet is copied to `Arsip April 2026` before June data ranges are cleared.
- [ ] Add a test proving mixed-month data aborts without clearing the source.
- [ ] Run `python -m pytest tests/test_perform_rollover.py -q` and confirm failure because the rollover module is absent.

### Task 2: Implement verified monthly rollover

**Files:**
- Create: `perform_rollover.py`
- Test: `tests/test_perform_rollover.py`

- [ ] Parse the two table title/header rows and the month values in column `AK`.
- [ ] Duplicate the source sheet and compare archived data rows with the source before clearing.
- [ ] Clear only data ranges in columns `B:AK`, preserving headers and formatting.
- [ ] Update both title rows to the current Indonesian month.
- [ ] Run `python -m pytest tests/test_perform_rollover.py -q` and confirm all tests pass.

### Task 3: Integrate with the Telegram mirror

**Files:**
- Modify: `mirror_perform.py`

- [ ] Run rollover during startup so stale data is corrected without waiting for a Telegram event.
- [ ] Run rollover before both six-hour and three-hour table writes to handle a process crossing month boundaries.
- [ ] Use one WIB timestamp for the month label, day, and target day column.
- [ ] Run the complete test suite with `python -m pytest -q`.

### Task 4: Migrate and verify the live sheet

**Files:**
- No additional source files.

- [ ] Execute the rollover function against spreadsheet `10hfFq_TjiAqUI2I5L99k6gtbVd4EY4eRPwbcO7oySpA`, worksheet `Gamas ISP`.
- [ ] Confirm `Arsip April 2026` exists and contains the original April rows.
- [ ] Confirm both active headers read `Juni 2026`.
- [ ] Confirm both active data sections are empty and ready for June writes through `D10`.
