from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


BULAN_INDONESIA = (
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

BULAN_KE_NOMOR = {
    name.casefold(): index
    for index, name in enumerate(BULAN_INDONESIA, start=1)
}
BULAN_KE_NOMOR.update(
    {
        name.casefold(): index
        for index, name in enumerate(
            (
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ),
            start=1,
        )
    }
)

WIB = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class RolloverResult:
    archived: bool
    archive_name: str | None = None


def waktu_wib() -> datetime:
    return datetime.now(WIB)


def label_bulan_indonesia(waktu: datetime) -> str:
    return f"{BULAN_INDONESIA[waktu.month - 1]} {waktu.year}"


def normalisasi_label_bulan(label: str) -> str:
    bagian = str(label).strip().split()
    if len(bagian) != 2:
        raise ValueError(f"Format bulan tidak valid: {label!r}")

    nama_bulan, tahun = bagian
    nomor_bulan = BULAN_KE_NOMOR.get(nama_bulan.casefold())
    if nomor_bulan is None or not tahun.isdigit():
        raise ValueError(f"Format bulan tidak valid: {label!r}")

    return f"{BULAN_INDONESIA[nomor_bulan - 1]} {int(tahun)}"


def indeks_baris_harian(tanggal: int) -> int:
    if not 1 <= tanggal <= 31:
        raise ValueError(f"Tanggal harus 1-31, ditemukan {tanggal}")
    return 3 + tanggal


def _nilai(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def _analisis_tabel(values: list[list], row_count: int):
    title_rows = []
    header_rows = []
    data_months = set()

    for row_number, row in enumerate(values, start=1):
        if "durasi down (menit)" in _nilai(row, 2).casefold():
            title_rows.append(row_number)
        if _nilai(row, 1).casefold() == "ne hostname":
            header_rows.append(row_number)

        month_value = _nilai(row, 36)
        if month_value and month_value.casefold() != "bln":
            data_months.add(normalisasi_label_bulan(month_value))

    if len(title_rows) != 2 or len(header_rows) != 2:
        raise RuntimeError(
            "Struktur Gamas ISP tidak valid: harus ada tepat dua judul tabel "
            "dan dua header NE Hostname."
        )

    clear_ranges = []
    for index, header_row in enumerate(header_rows):
        start_row = header_row + 1
        if index + 1 < len(title_rows):
            end_row = title_rows[index + 1] - 1
        else:
            end_row = row_count
        if start_row <= end_row:
            clear_ranges.append(f"B{start_row}:AK{end_row}")

    return title_rows, data_months, clear_ranges


def _data_rows(values: list[list]) -> list[list]:
    return [
        row
        for row in values
        if _nilai(row, 36) and _nilai(row, 36).casefold() != "bln"
    ]


def _set_month_headers(worksheet, title_rows: list[int], month_label: str) -> None:
    for row_number in title_rows:
        worksheet.update([[month_label]], f"B{row_number}")


def _find_worksheet(spreadsheet, title: str):
    for worksheet in spreadsheet.worksheets():
        if worksheet.title == title:
            return worksheet
    return None


def pastikan_bulan_aktif(
    spreadsheet,
    worksheet,
    sekarang: datetime | None = None,
) -> RolloverResult:
    sekarang = sekarang or waktu_wib()
    current_month = label_bulan_indonesia(sekarang)
    source_values = worksheet.get_all_values()
    title_rows, data_months, clear_ranges = _analisis_tabel(
        source_values,
        worksheet.row_count,
    )

    if len(data_months) > 1:
        months = ", ".join(sorted(data_months))
        raise RuntimeError(
            f"Rollover dibatalkan karena ditemukan campuran bulan: {months}"
        )

    if not data_months or data_months == {current_month}:
        _set_month_headers(worksheet, title_rows, current_month)
        return RolloverResult(archived=False)

    previous_month = next(iter(data_months))
    archive_name = f"Arsip {previous_month}"
    archive = _find_worksheet(spreadsheet, archive_name)

    if archive is None:
        archive = spreadsheet.duplicate_sheet(
            source_sheet_id=worksheet.id,
            new_sheet_name=archive_name,
        )

    source_data = _data_rows(source_values)
    archived_values = archive.get_all_values()
    if not source_data or _data_rows(archived_values) != source_data:
        raise RuntimeError(
            f"Arsip {archive_name} gagal diverifikasi; data aktif tidak dihapus."
        )

    archive_title_rows, _, _ = _analisis_tabel(
        archived_values,
        archive.row_count,
    )
    _set_month_headers(archive, archive_title_rows, previous_month)

    worksheet.batch_clear(clear_ranges)
    _set_month_headers(worksheet, title_rows, current_month)

    return RolloverResult(
        archived=True,
        archive_name=archive_name,
    )
