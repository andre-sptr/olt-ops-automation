import copy
import re
import unittest
from datetime import datetime

from backup.perform_rollover import (
    indeks_baris_harian,
    label_bulan_indonesia,
    pastikan_bulan_aktif,
)


def make_row(*, month="", title="", hostname="", day=0, duration=""):
    row = [""] * 37
    row[1] = hostname
    row[2] = title
    if day:
        row[indeks_baris_harian(day)] = duration
    row[36] = month
    return row


def sample_sheet_values(month="April 2026"):
    return [
        [""] * 37,
        make_row(month="BLN", title="Durasi Down (Menit) - TTR 6 Jam (360 Menit)", hostname="Maret 2026"),
        make_row(hostname="NE Hostname", title="Distrik"),
        make_row(month=month, hostname="GPON00-D1-AAA-1", day=1, duration=168),
        [""] * 37,
        make_row(month="BLN", title="Durasi Down (Menit) - TTR 3 Jam (180 Menit)", hostname="Maret 2026"),
        make_row(hostname="NE Hostname", title="Distrik"),
        make_row(month=month, hostname="GPON00-D1-BBB-1", day=2, duration=120),
    ]


class FakeWorksheet:
    _next_id = 100

    def __init__(self, title, values, row_count=20, worksheet_id=None):
        self.title = title
        self.values = copy.deepcopy(values)
        self.row_count = row_count
        self.id = worksheet_id if worksheet_id is not None else self._allocate_id()

    @classmethod
    def _allocate_id(cls):
        cls._next_id += 1
        return cls._next_id

    def get(self, range_name):
        return copy.deepcopy(self.values)

    def get_all_values(self):
        return copy.deepcopy(self.values)

    def update(self, values, range_name):
        match = re.fullmatch(r"B(\d+)", range_name)
        if not match:
            raise AssertionError(f"Unexpected update range: {range_name}")
        row_index = int(match.group(1)) - 1
        self.values[row_index][1] = values[0][0]

    def batch_clear(self, ranges):
        for range_name in ranges:
            match = re.fullmatch(r"B(\d+):AK(\d+)", range_name)
            if not match:
                raise AssertionError(f"Unexpected clear range: {range_name}")
            start_row, end_row = (int(value) for value in match.groups())
            for row_number in range(start_row, min(end_row, len(self.values)) + 1):
                for column_index in range(1, 37):
                    self.values[row_number - 1][column_index] = ""


class FakeSpreadsheet:
    def __init__(self, source):
        self._worksheets = [source]

    def worksheets(self):
        return list(self._worksheets)

    def duplicate_sheet(self, source_sheet_id, new_sheet_name):
        source = next(sheet for sheet in self._worksheets if sheet.id == source_sheet_id)
        duplicate = FakeWorksheet(
            new_sheet_name,
            source.get_all_values(),
            row_count=source.row_count,
        )
        self._worksheets.append(duplicate)
        return duplicate


class PerformRolloverTest(unittest.TestCase):
    def test_uses_indonesian_month_label_and_maps_day_10_to_row_index_13(self):
        now = datetime(2026, 6, 10, 8, 30)

        self.assertEqual(label_bulan_indonesia(now), "Juni 2026")
        self.assertEqual(indeks_baris_harian(10), 13)

    def test_archives_old_month_before_clearing_both_tables(self):
        source = FakeWorksheet("Gamas ISP", sample_sheet_values(), worksheet_id=769106930)
        spreadsheet = FakeSpreadsheet(source)

        result = pastikan_bulan_aktif(
            spreadsheet,
            source,
            datetime(2026, 6, 10, 8, 30),
        )

        self.assertTrue(result.archived)
        self.assertEqual(result.archive_name, "Arsip April 2026")

        archive = spreadsheet.worksheets()[1]
        self.assertEqual(archive.values[1][1], "April 2026")
        self.assertEqual(archive.values[3][1], "GPON00-D1-AAA-1")
        self.assertEqual(archive.values[7][1], "GPON00-D1-BBB-1")

        self.assertEqual(source.values[1][1], "Juni 2026")
        self.assertEqual(source.values[5][1], "Juni 2026")
        self.assertEqual(source.values[3][1:37], [""] * 36)
        self.assertEqual(source.values[7][1:37], [""] * 36)

    def test_mixed_months_abort_without_archiving_or_clearing(self):
        values = sample_sheet_values()
        values[7][36] = "Juni 2026"
        source = FakeWorksheet("Gamas ISP", values, worksheet_id=769106930)
        spreadsheet = FakeSpreadsheet(source)
        original = source.get_all_values()

        with self.assertRaisesRegex(RuntimeError, "campuran bulan"):
            pastikan_bulan_aktif(
                spreadsheet,
                source,
                datetime(2026, 6, 10, 8, 30),
            )

        self.assertEqual(len(spreadsheet.worksheets()), 1)
        self.assertEqual(source.get_all_values(), original)


if __name__ == "__main__":
    unittest.main()
