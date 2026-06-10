# Perform History Backfill Design

## Goal

Create standalone TTR 6-hour archive tabs for February through May 2026 in spreadsheet `13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do`.

## Scope

- Do not modify `mirror_perform.py`.
- Read OLT and flicker recovery history from `TR1 - OM NE Akses`.
- Process February 20–28, 2026.
- Process all of March, April, and May 2026.
- Include only RIDAR, SUMBAR, and RIKEP target records.
- Populate only `Durasi Down (Menit) - TTR 6 Jam (360 Menit)`.
- Preserve the TTR 3-hour table layout but leave its data section empty.
- Create one destination tab per month and never overwrite an existing tab.

## Data Flow

1. Scan Telegram history once for the complete February–May range.
2. Filter recovery messages into configured monthly periods.
3. Resolve district and RCA from historical PROGRAM ZERO messages, direct recovery fields, and spreadsheet reference data.
4. Preview record counts and samples.
5. Copy the `Gamas ISP` layout into the destination spreadsheet.
6. Clear copied data, resize the first table, write records, and update both month headers.
7. Read each tab back and verify row counts, date ranges, and an empty TTR 3-hour table.

## Safety

- Preview is the default mode.
- `--write` is required to create tabs.
- Preflight rejects existing destination names and empty monthly datasets.
- A failed multi-month write removes tabs created during that run.
