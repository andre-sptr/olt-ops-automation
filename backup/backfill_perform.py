import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


API_ID = 35153027
API_HASH = "275a7916b30391e446366433d5427086"

ID_GRUP_NE_AKSES = -172352509
ID_GRUP_SIAGA_SERVO = -1001688234308
ID_GRUP_BTM = -1001267017385
ID_GRUP_DUM = -332267455
ID_GRUP_PKU = -1001481602761
ID_GRUP_PDG = -1001281180665
ID_GRUP_BKT = -1003652501250

SOURCE_SPREADSHEET_ID = "10hfFq_TjiAqUI2I5L99k6gtbVd4EY4eRPwbcO7oySpA"
SOURCE_WORKSHEET_GID = 769106930
DESTINATION_SPREADSHEET_ID = "13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do"
TIMEZONE_WIB = ZoneInfo("Asia/Jakarta")

MONTH_NAMES = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

MAP_DISTRIK = {
    "PEKANBARU": "PKU",
    "PADANG": "PDG",
    "BUKITTINGGI": "BKT",
    "BATAM": "BTM",
    "DUMAI": "DUM",
}
WITEL_TARGET = {"SUMBAR", "RIKEP", "RIDAR"}
DISTRIK_TARGET = set(MAP_DISTRIK) | set(MAP_DISTRIK.values())
CHAT_DISTRIK = {
    ID_GRUP_BTM: "BTM",
    ID_GRUP_DUM: "DUM",
    ID_GRUP_PKU: "PKU",
    ID_GRUP_PDG: "PDG",
    ID_GRUP_BKT: "BKT",
}
SITE_DISTRIK_OVERRIDES = {
    "PWG": "PKU",
}


@dataclass(frozen=True)
class BackfillRecord:
    table: str
    hostname: str
    district: str
    rca: str
    duration: int
    day: int


@dataclass(frozen=True)
class BackfillPeriod:
    year: int
    month: int
    start_day: int = 1

    @classmethod
    def for_month(cls, month: int):
        if month not in range(1, 13):
            raise ValueError(f"Bulan harus 1-12, ditemukan {month}")
        return cls(
            year=2026,
            month=month,
            start_day=20 if month == 2 else 1,
        )

    @property
    def start(self) -> datetime:
        return datetime(
            self.year,
            self.month,
            self.start_day,
            tzinfo=TIMEZONE_WIB,
        )

    @property
    def end(self) -> datetime:
        if self.month == 12:
            return datetime(self.year + 1, 1, 1, tzinfo=TIMEZONE_WIB)
        return datetime(self.year, self.month + 1, 1, tzinfo=TIMEZONE_WIB)

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]} {self.year}"

    @property
    def destination_title(self) -> str:
        return f"Arsip {self.label}"

    def contains(self, value: datetime) -> bool:
        local = local_datetime(value)
        return self.start <= local < self.end


def local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=TIMEZONE_WIB)
    return value.astimezone(TIMEZONE_WIB)


def is_target_month(
    value: datetime,
    period: BackfillPeriod | None = None,
) -> bool:
    return (period or BackfillPeriod.for_month(1)).contains(value)


def duration_minutes(value: str) -> int | None:
    text = str(value or "").strip().lower()
    total = 0
    found = False

    days = re.search(r"(\d+)\s*(?:hari|day|days)", text)
    hours = re.search(r"(\d+)\s*(?:jam|hour|hours|hr|hrs)", text)
    minutes = re.search(r"(\d+)\s*(?:menit|mnt|min|mins|minute|minutes)", text)
    clock = re.search(r"\b(\d{1,3}):(\d{2})(?::\d{2})?\b", text)

    if days:
        total += int(days.group(1)) * 1440
        found = True
    if hours:
        total += int(hours.group(1)) * 60
        found = True
    if minutes:
        total += int(minutes.group(1))
        found = True
    if clock and not found:
        total = int(clock.group(1)) * 60 + int(clock.group(2))
        found = True

    return total if found else None


def _label(text: str, names: tuple[str, ...]) -> str:
    for line in str(text or "").splitlines():
        for name in names:
            match = re.match(rf"(?i)^\s*{re.escape(name)}\s*:\s*(.*?)\s*$", line)
            if match:
                return match.group(1)
    return ""


def parse_recovery_message(
    message,
    district: str,
    rca: str,
    period: BackfillPeriod | None = None,
) -> BackfillRecord | None:
    text = getattr(message, "text", None) or getattr(message, "message", "") or ""
    upper = text.upper()
    if "NOTIFIKASI OLT RECOVERY" not in upper and "NOTIFIKASI FLICKER RECOVERY" not in upper:
        return None

    hostname = _label(text, ("Node ID",))
    duration = duration_minutes(_label(text, ("Down Duration", "Flicker Duration")))
    message_date = getattr(message, "date", None)
    if (
        not hostname
        or duration is None
        or message_date is None
        or not is_target_month(message_date, period)
    ):
        return None

    return BackfillRecord(
        table="6h",
        hostname=hostname.strip(),
        district=district.strip(),
        rca=rca.strip() or "Kable CUT",
        duration=duration,
        day=local_datetime(message_date).day,
    )


def resolve_recovery_context(
    hostname: str,
    recovery_date: datetime,
    program_messages,
) -> tuple[str, str]:
    recovery_local = local_datetime(recovery_date)
    candidates = []

    for message in program_messages:
        text = getattr(message, "text", None) or getattr(message, "message", "") or ""
        message_date = getattr(message, "date", None)
        if message_date is None or hostname.upper() not in text.upper():
            continue

        message_local = local_datetime(message_date)
        candidates.append(
            (
                message_local,
                text,
                getattr(message, "chat_id", None),
            )
        )

    if not candidates:
        return "", "Kable CUT"

    prior_candidates = [
        candidate
        for candidate in candidates
        if candidate[0] <= recovery_local
    ]
    selected = max(
        prior_candidates or candidates,
        key=lambda item: item[0],
    )
    _, context, chat_id = selected
    district_match = re.search(
        r"(?im)-\s*DISTRICT\s*:?\s*([A-Z][A-Z ]+?)\s*$",
        context,
    )
    district_raw = district_match.group(1).strip().upper() if district_match else ""
    district = MAP_DISTRIK.get(
        district_raw,
        district_raw or CHAT_DISTRIK.get(chat_id, ""),
    )

    hostname_pln = hostname.upper().replace("GPON", "PLN", 1)
    rca = "Kable CUT"
    if prior_candidates:
        rca = "PLN" if hostname_pln in context.upper() else "Kable CUT"
    return district, rca


def parse_blackout_message(
    message,
    period: BackfillPeriod | None = None,
) -> BackfillRecord | None:
    text = getattr(message, "text", None) or getattr(message, "message", "") or ""
    upper = text.upper()
    if "REPORT INTERNAL TELKOM GROUP" not in upper:
        return None
    if "CURRENT STATUS: CLOSED" not in upper or "BLACKOUT" not in upper:
        return None

    location = _label(text, ("Lokasi",)).upper()
    if not any(witel in location for witel in WITEL_TARGET):
        return None

    district_raw = location.split("(", 1)[0].strip()
    district = MAP_DISTRIK.get(district_raw, district_raw)
    duration = duration_minutes(_label(text, ("Duration",)))
    message_date = getattr(message, "date", None)
    hostname_match = re.search(
        r"(\S+-\S+)\s+(?:TO|-)\s+(\S+-\S+)",
        text,
        re.IGNORECASE,
    )
    if (
        duration is None
        or message_date is None
        or not is_target_month(message_date, period)
    ):
        return None
    if not hostname_match:
        return None

    return BackfillRecord(
        table="3h",
        hostname=re.sub(r"[,.]$", "", hostname_match.group(1).upper()),
        district=district,
        rca="BLACKOUT",
        duration=duration,
        day=local_datetime(message_date).day,
    )


def _ensure_width(row: list, width: int = 37) -> list:
    return list(row[:width]) + [""] * max(0, width - len(row))


def _find_table_rows(values: list[list]) -> tuple[list[int], list[int]]:
    title_rows = []
    header_rows = []
    for index, row in enumerate(values):
        row = _ensure_width(row)
        if "durasi down (menit)" in str(row[2]).casefold():
            title_rows.append(index)
        if str(row[1]).strip().casefold() == "ne hostname":
            header_rows.append(index)
    if len(title_rows) != 2 or len(header_rows) != 2:
        raise RuntimeError("Template harus memiliki dua tabel performansi.")
    return title_rows, header_rows


def _record_row(record: BackfillRecord, period: BackfillPeriod) -> list:
    row = [""] * 37
    row[1] = record.hostname
    row[2] = record.district
    row[3] = record.rca
    row[3 + record.day] = record.duration
    threshold = 360 if record.table == "6h" else 180
    row[35] = "C" if record.duration <= threshold else "NC"
    row[36] = period.label
    return row


def build_archive_values(
    template_values: list[list],
    records: list[BackfillRecord],
    period: BackfillPeriod | None = None,
) -> list[list]:
    period = period or BackfillPeriod.for_month(1)
    values = [_ensure_width(row) for row in template_values]
    title_rows, header_rows = _find_table_rows(values)

    first_table_records = [
        _record_row(record, period)
        for record in records
        if record.table == "6h"
    ]
    second_table_records = [
        _record_row(record, period)
        for record in records
        if record.table == "3h"
    ]

    first_title = values[title_rows[0]]
    first_header = values[header_rows[0]]
    second_title = values[title_rows[1]]
    second_header = values[header_rows[1]]
    first_title[1] = period.label
    second_title[1] = period.label

    return [
        values[0],
        first_title,
        first_header,
        *first_table_records,
        second_title,
        second_header,
        *second_table_records,
    ]


async def fetch_messages_between(
    client,
    entity,
    start: datetime,
    end: datetime,
    search: str | None = None,
):
    messages = []
    async for message in client.iter_messages(
        entity,
        offset_date=end.astimezone(timezone.utc),
        search=search,
    ):
        message_date = getattr(message, "date", None)
        if message_date is None:
            continue

        local = local_datetime(message_date)
        if local < start:
            break
        if local < end:
            messages.append(message)
    return messages


def _site_code(hostname: str) -> str:
    parts = str(hostname or "").strip().upper().split("-")
    return parts[2] if len(parts) >= 3 else ""


def build_site_district_map(spreadsheet) -> dict[str, str]:
    mapping = dict(SITE_DISTRIK_OVERRIDES)
    worksheets = [
        worksheet
        for worksheet in spreadsheet.worksheets()
        if (
            worksheet.title in {"Gamas ISP", "Rekap G.ISP", "Batam"}
            or worksheet.title.startswith("Arsip ")
        )
    ]

    for worksheet in worksheets:
        for row in worksheet.get_all_values():
            if worksheet.title == "Batam":
                hostname = row[3].strip() if len(row) > 3 else ""
                district = row[2].strip() if len(row) > 2 else ""
            else:
                hostname = row[1].strip() if len(row) > 1 else ""
                district = row[2].strip() if len(row) > 2 else ""

            district = MAP_DISTRIK.get(district.upper(), district)
            site_code = _site_code(hostname)
            if site_code and district and district.upper() != "DISTRIK":
                mapping.setdefault(hostname.upper(), district)
                mapping.setdefault(site_code, district)
    return mapping


def _period_for_message(
    message_date: datetime,
    periods: list[BackfillPeriod],
) -> BackfillPeriod | None:
    for period in periods:
        if period.contains(message_date):
            return period
    return None


def _recovery_matches_target(text: str) -> bool:
    witel = _label(text, ("Witel",)).strip().upper()
    district = _label(text, ("District", "Distrik")).strip().upper()
    return witel in WITEL_TARGET or district in DISTRIK_TARGET


async def _program_messages_for_hostname(
    client,
    hostname: str,
    period: BackfillPeriod,
):
    messages = []
    async for message in client.iter_messages(
        None,
        search=hostname,
        offset_date=period.end.astimezone(timezone.utc),
        limit=100,
    ):
        text = getattr(message, "text", None) or getattr(message, "message", "") or ""
        if "!PROGRAM ZERO GAMAS OLT!" in text.upper():
            messages.append(message)
    return messages


async def collect_records(
    client,
    site_district_map: dict[str, str],
    periods: list[BackfillPeriod],
):
    await client.get_dialogs()
    first_start = min(period.start for period in periods)
    last_end = max(period.end for period in periods)
    recovery_messages = await fetch_messages_between(
        client,
        ID_GRUP_NE_AKSES,
        first_start,
        last_end,
    )

    candidates = []
    stats = {
        period.month: {
            "messages_scanned": 0,
            "recovery_messages": 0,
            "target_recovery": 0,
            "skipped_recovery": 0,
            "context_searches": 0,
        }
        for period in periods
    }

    for message in recovery_messages:
        text = getattr(message, "text", None) or getattr(message, "message", "") or ""
        message_date = getattr(message, "date", None)
        if message_date is None:
            continue
        period = _period_for_message(message_date, periods)
        if period is None:
            continue

        month_stats = stats[period.month]
        month_stats["messages_scanned"] += 1
        upper = text.upper()
        if (
            "NOTIFIKASI OLT RECOVERY" not in upper
            and "NOTIFIKASI FLICKER RECOVERY" not in upper
        ):
            continue
        month_stats["recovery_messages"] += 1
        if not _recovery_matches_target(text):
            continue
        month_stats["target_recovery"] += 1

        hostname = _label(text, ("Node ID",)).strip()
        if not hostname:
            month_stats["skipped_recovery"] += 1
            continue
        candidates.append((period, message, hostname))

    contexts = {}
    context_keys = sorted(
        {
            (period.month, hostname.upper())
            for period, _, hostname in candidates
        }
    )
    periods_by_month = {period.month: period for period in periods}
    for index, (month, hostname) in enumerate(context_keys, start=1):
        contexts[(month, hostname)] = await _program_messages_for_hostname(
            client,
            hostname,
            periods_by_month[month],
        )
        if index % 25 == 0:
            print(
                f"Resolusi RCA/distrik: {index}/{len(context_keys)} konteks",
                flush=True,
            )

    records_by_month = {period.month: [] for period in periods}
    for period, message, hostname in candidates:
        text = getattr(message, "text", None) or getattr(message, "message", "") or ""
        message_date = getattr(message, "date", None)
        month_stats = stats[period.month]
        month_stats["context_searches"] += 1

        district, rca = resolve_recovery_context(
            hostname,
            message_date,
            contexts.get((period.month, hostname.upper()), []),
        )
        if not district:
            district = _label(text, ("District", "Distrik")).strip()
            district = MAP_DISTRIK.get(district.upper(), district)
        if not district:
            district = (
                site_district_map.get(hostname.upper())
                or site_district_map.get(_site_code(hostname), "")
            )

        record = parse_recovery_message(
            message,
            district=district,
            rca=rca,
            period=period,
        )
        if record is None:
            month_stats["skipped_recovery"] += 1
            continue
        records_by_month[period.month].append(record)

    for records in records_by_month.values():
        records.sort(
            key=lambda record: (
                record.day,
                record.hostname,
                record.duration,
            )
        )
    return records_by_month, stats


def setup_google_sheets():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "kunci_rahasia_google.json",
        scope,
    )
    client = gspread.authorize(credentials)
    source = client.open_by_key(SOURCE_SPREADSHEET_ID)
    destination = client.open_by_key(DESTINATION_SPREADSHEET_ID)
    return source, destination


def _worksheet_by_title(spreadsheet, title: str):
    for worksheet in spreadsheet.worksheets():
        if worksheet.title == title:
            return worksheet
    return None


def _write_record_rows(
    worksheet,
    start_row: int,
    records: list[BackfillRecord],
    period: BackfillPeriod,
):
    if not records:
        return
    values = [_record_row(record, period)[1:37] for record in records]
    end_row = start_row + len(values) - 1
    worksheet.update(
        values=values,
        range_name=f"B{start_row}:AK{end_row}",
    )


def _write_empty_three_hour_header(
    worksheet,
    title_row: int,
    period: BackfillPeriod,
):
    header_row = title_row + 1
    merge_ranges = (
        f"C{title_row}:AI{title_row}",
        f"AJ{title_row}:AJ{header_row}",
        f"AK{title_row}:AK{header_row}",
    )
    for range_name in merge_ranges:
        worksheet.unmerge_cells(range_name)

    title_values = [
        period.label,
        "Durasi Down (Menit) - TTR 3 Jam (180 Menit)",
        *([""] * 32),
        "COM",
        "BLN",
    ]
    header_values = [
        "NE Hostname",
        "Distrik",
        "RCA",
        *(f"D{day}" for day in range(1, 32)),
        "",
        "",
    ]
    worksheet.update(
        values=[title_values, header_values],
        range_name=f"B{title_row}:AK{header_row}",
    )
    for range_name in merge_ranges:
        worksheet.merge_cells(range_name)


def replace_active_worksheet_data(
    worksheet,
    records: list[BackfillRecord],
    period: BackfillPeriod,
):
    six_hour = [record for record in records if record.table == "6h"]
    if not six_hour:
        raise RuntimeError(
            f"Tidak ada record TTR 6 jam untuk {period.label}; sheet tidak diubah."
        )

    template_values = worksheet.get_all_values()
    title_rows, header_rows = _find_table_rows(template_values)
    first_start_row = header_rows[0] + 2
    second_title_row = title_rows[1] + 1
    first_capacity = second_title_row - first_start_row

    if len(six_hour) > first_capacity:
        extra_rows = len(six_hour) - first_capacity
        worksheet.insert_rows(
            [[""] * 37 for _ in range(extra_rows)],
            row=second_title_row,
            inherit_from_before=True,
        )
        title_rows[1] += extra_rows
        header_rows[1] += extra_rows

    worksheet.batch_clear(
        [
            f"B{first_start_row}:AK{title_rows[1]}",
            f"B{header_rows[1] + 2}:AK{worksheet.row_count}",
        ]
    )
    worksheet.update([[period.label]], f"B{title_rows[0] + 1}")
    worksheet.update([[period.label]], f"B{title_rows[1] + 1}")
    _write_record_rows(
        worksheet,
        first_start_row,
        six_hour,
        period,
    )

    written_values = worksheet.get_all_values()
    written_count = sum(
        1
        for row in written_values
        if len(row) > 36 and row[36].strip() == period.label
    )
    if written_count != len(six_hour):
        raise RuntimeError(
            f"Verifikasi gagal: ditulis {written_count}, "
            f"diharapkan {len(six_hour)}."
        )
    return written_count


def create_archive_worksheet(
    source_spreadsheet,
    destination_spreadsheet,
    records: list[BackfillRecord],
    period: BackfillPeriod,
):
    if not records:
        raise RuntimeError(
            f"Tidak ada record {period.label}; tab tujuan tidak dibuat."
        )
    if _worksheet_by_title(destination_spreadsheet, period.destination_title):
        raise RuntimeError(
            f"Tab {period.destination_title} sudah ada; overwrite dibatalkan."
        )

    source = source_spreadsheet.get_worksheet_by_id(SOURCE_WORKSHEET_GID)
    copy_response = source.copy_to(destination_spreadsheet.id)
    copied = destination_spreadsheet.get_worksheet_by_id(copy_response["sheetId"])

    try:
        copied.update_title(period.destination_title)
        template_values = copied.get_all_values()
        title_rows, header_rows = _find_table_rows(template_values)

        six_hour = [record for record in records if record.table == "6h"]
        first_start_row = header_rows[0] + 2
        second_title_row = title_rows[1] + 1
        first_capacity = second_title_row - first_start_row
        if len(six_hour) > first_capacity:
            extra_rows = len(six_hour) - first_capacity
            copied.insert_rows(
                [[""] * 37 for _ in range(extra_rows)],
                row=second_title_row,
                inherit_from_before=True,
            )
            title_rows[1] += extra_rows
            header_rows[1] += extra_rows

        copied.batch_clear(
            [
                f"B{header_rows[0] + 2}:AK{title_rows[1]}",
                f"B{header_rows[1] + 2}:AK{copied.row_count}",
            ]
        )
        copied.update([[period.label]], f"B{title_rows[0] + 1}")
        _write_empty_three_hour_header(
            copied,
            title_rows[1] + 1,
            period,
        )

        _write_record_rows(
            copied,
            header_rows[0] + 2,
            six_hour,
            period,
        )

        written_values = copied.get_all_values()
        written_count = sum(
            1
            for row in written_values
            if len(row) > 36 and row[36].strip() == period.label
        )
        if written_count != len(records):
            raise RuntimeError(
                f"Verifikasi gagal: ditulis {written_count}, diharapkan {len(records)}."
            )
        return copied
    except Exception:
        destination_spreadsheet.del_worksheet(copied)
        raise


def print_preview(
    period: BackfillPeriod,
    records: list[BackfillRecord],
    stats: dict,
):
    six_hour = [record for record in records if record.table == "6h"]
    print(f"=== Preview Backfill {period.label} ===")
    print(f"Pesan grup dipindai   : {stats['messages_scanned']}")
    print(f"Recovery dipindai     : {stats['recovery_messages']}")
    print(f"Recovery target       : {stats['target_recovery']}")
    print(f"TTR 6 jam valid       : {len(six_hour)}")
    print(f"Recovery dilewati     : {stats['skipped_recovery']}")
    print()

    for record in records[:20]:
        print(
            f"D{record.day:02d} | {record.table:>2} | {record.hostname} | "
            f"{record.district or '-'} | {record.rca} | {record.duration} menit"
        )
    if len(records) > 20:
        print(f"... dan {len(records) - 20} record lainnya")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill performansi TTR 6 jam dari histori Telegram."
    )
    parser.add_argument(
        "--months",
        nargs="+",
        type=int,
        default=[2, 3, 4, 5],
        help="Nomor bulan yang diproses. Default: 2 3 4 5.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Buat tab tujuan setelah preview dan validasi selesai.",
    )
    parser.add_argument(
        "--current-sheet",
        action="store_true",
        help=(
            "Ganti isi tabel TTR 6 jam pada sheet Gamas ISP. "
            "Hanya dapat digunakan untuk satu bulan."
        ),
    )
    return parser.parse_args()


async def main(args):
    from telethon import TelegramClient

    source_spreadsheet, destination_spreadsheet = setup_google_sheets()
    site_district_map = build_site_district_map(source_spreadsheet)
    periods = [BackfillPeriod.for_month(month) for month in args.months]
    if args.current_sheet and len(periods) != 1:
        raise RuntimeError("--current-sheet hanya menerima tepat satu bulan.")

    client = TelegramClient(
        "sesi_backfill_perform",
        API_ID,
        API_HASH,
    )
    await client.start()
    try:
        records_by_month, stats_by_month = await collect_records(
            client,
            site_district_map,
            periods,
        )
    finally:
        await client.disconnect()

    for period in periods:
        print_preview(
            period,
            records_by_month[period.month],
            stats_by_month[period.month],
        )
    if not args.write:
        print("\nMode preview: spreadsheet belum diubah. Gunakan --write untuk menulis.")
        return

    if args.current_sheet:
        period = periods[0]
        worksheet = source_spreadsheet.get_worksheet_by_id(SOURCE_WORKSHEET_GID)
        written_count = replace_active_worksheet_data(
            worksheet,
            records_by_month[period.month],
            period,
        )
        print(
            f"Selesai: {written_count} record ditulis ke "
            f"{worksheet.title} (GID {worksheet.id})."
        )
        return

    for period in periods:
        if not records_by_month[period.month]:
            raise RuntimeError(f"Tidak ada data valid untuk {period.label}.")
        if _worksheet_by_title(
            destination_spreadsheet,
            period.destination_title,
        ):
            raise RuntimeError(
                f"Tab {period.destination_title} sudah ada; tidak ada tab yang ditulis."
            )

    created = []
    try:
        for period in periods:
            records = records_by_month[period.month]
            worksheet = create_archive_worksheet(
                source_spreadsheet,
                destination_spreadsheet,
                records,
                period,
            )
            created.append(worksheet)
            print(
                f"Selesai: {len(records)} record ditulis ke "
                f"{worksheet.title} (GID {worksheet.id})."
            )
    except Exception:
        for worksheet in created:
            destination_spreadsheet.del_worksheet(worksheet)
        raise


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
