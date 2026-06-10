import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from backfill_perform import (
    BackfillRecord,
    BackfillPeriod,
    build_site_district_map,
    build_archive_values,
    is_target_month,
    parse_blackout_message,
    parse_recovery_message,
    resolve_recovery_context,
)


class BackfillPerformTest(unittest.TestCase):
    def test_filters_messages_by_january_in_wib(self):
        january_wib = datetime(2026, 1, 31, 16, 30, tzinfo=timezone.utc)
        february_wib = datetime(2026, 1, 31, 17, 30, tzinfo=timezone.utc)
        period = BackfillPeriod.for_month(1)

        self.assertTrue(is_target_month(january_wib, period))
        self.assertFalse(is_target_month(february_wib, period))

    def test_february_period_starts_on_day_20(self):
        period = BackfillPeriod.for_month(2)

        self.assertFalse(
            is_target_month(
                datetime(2026, 2, 19, 16, 59, tzinfo=timezone.utc),
                period,
            )
        )
        self.assertTrue(
            is_target_month(
                datetime(2026, 2, 19, 17, 0, tzinfo=timezone.utc),
                period,
            )
        )
        self.assertEqual(period.label, "Februari 2026")
        self.assertEqual(period.destination_title, "Arsip Februari 2026")

    def test_parses_olt_recovery_record(self):
        message = SimpleNamespace(
            date=datetime(2026, 1, 10, 3, 0, tzinfo=timezone.utc),
            text="""✅✅Notifikasi OLT Recovery!✅✅
Node ID : GPON00-D1-DUM-3UJT
Witel : RIDAR
Down Duration : 2 Jam 48 Menit""",
        )

        record = parse_recovery_message(
            message,
            district="DUM",
            rca="PLN",
            period=BackfillPeriod.for_month(1),
        )

        self.assertEqual(
            record,
            BackfillRecord(
                table="6h",
                hostname="GPON00-D1-DUM-3UJT",
                district="DUM",
                rca="PLN",
                duration=168,
                day=10,
            ),
        )

    def test_parses_closed_blackout_record(self):
        message = SimpleNamespace(
            date=datetime(2026, 1, 10, 3, 0, tzinfo=timezone.utc),
            text="""REPORT INTERNAL TELKOM GROUP
Current Status: Closed
Lokasi: PEKANBARU (RIDAR)
GPON00-D1-RGT-3BKL TO GPON00-D1-RGT-3XYZ
RCA: BLACKOUT
Duration: 4 Jam 5 Menit""",
        )

        record = parse_blackout_message(
            message,
            period=BackfillPeriod.for_month(1),
        )

        self.assertEqual(
            record,
            BackfillRecord(
                table="3h",
                hostname="GPON00-D1-RGT-3BKL",
                district="PKU",
                rca="BLACKOUT",
                duration=245,
                day=10,
            ),
        )

    def test_resolves_nearest_program_zero_context_before_recovery(self):
        recovery_date = datetime(2026, 1, 10, 3, 0, tzinfo=timezone.utc)
        messages = [
            SimpleNamespace(
                date=datetime(2026, 1, 9, 3, 0, tzinfo=timezone.utc),
                text="""!PROGRAM ZERO GAMAS OLT!
ALL NE/PLN DOWN - DISTRICT DUMAI
GPON00-D1-DUM-3UJT
PLN00-D1-DUM-3UJT""",
            ),
            SimpleNamespace(
                date=datetime(2026, 1, 11, 3, 0, tzinfo=timezone.utc),
                text="""!PROGRAM ZERO GAMAS OLT!
- DISTRICT PADANG
GPON00-D1-DUM-3UJT""",
            ),
        ]

        district, rca = resolve_recovery_context(
            "GPON00-D1-DUM-3UJT",
            recovery_date,
            messages,
        )

        self.assertEqual(district, "DUM")
        self.assertEqual(rca, "PLN")

    def test_builds_two_tables_and_places_day_10_in_d10(self):
        template = [[""] * 37 for _ in range(8)]
        template[1][1] = "Maret 2026"
        template[1][2] = "Durasi Down (Menit) - TTR 6 Jam (360 Menit)"
        template[2][1] = "NE Hostname"
        template[4][1] = "Maret 2026"
        template[4][2] = "Durasi Down (Menit) - TTR 3 Jam (180 Menit)"
        template[5][1] = "NE Hostname"

        period = BackfillPeriod.for_month(1)
        values = build_archive_values(
            template,
            [
                BackfillRecord("6h", "OLT-A", "DUM", "PLN", 168, 10),
                BackfillRecord("3h", "OLT-B", "PKU", "BLACKOUT", 245, 10),
            ],
            period,
        )

        self.assertEqual(values[1][1], "Januari 2026")
        self.assertEqual(values[4][1], "Januari 2026")
        self.assertEqual(values[3][1], "OLT-A")
        self.assertEqual(values[3][13], 168)
        self.assertEqual(values[3][35], "C")
        self.assertEqual(values[3][36], "Januari 2026")
        self.assertEqual(values[6][1], "OLT-B")
        self.assertEqual(values[6][13], 245)
        self.assertEqual(values[6][35], "NC")

    def test_six_hour_only_keeps_second_table_empty(self):
        template = [[""] * 37 for _ in range(8)]
        template[1][1] = "Maret 2026"
        template[1][2] = "Durasi Down (Menit) - TTR 6 Jam (360 Menit)"
        template[2][1] = "NE Hostname"
        template[4][1] = "Maret 2026"
        template[4][2] = "Durasi Down (Menit) - TTR 3 Jam (180 Menit)"
        template[5][1] = "NE Hostname"

        values = build_archive_values(
            template,
            [BackfillRecord("6h", "OLT-A", "DUM", "PLN", 168, 20)],
            BackfillPeriod.for_month(2),
        )

        self.assertEqual(values[1][1], "Februari 2026")
        self.assertEqual(values[3][1], "OLT-A")
        self.assertEqual(values[3][23], 168)
        self.assertEqual(values[4][1], "Februari 2026")
        self.assertEqual(values[5][1], "NE Hostname")
        self.assertEqual(len(values), 6)

    def test_builds_district_fallback_from_any_archive_tab(self):
        archive = SimpleNamespace(
            title="Arsip Mei 2026",
            get_all_values=lambda: [
                ["", "GPON00-D1-PPN-2MTO", "DUM"],
            ],
        )
        unrelated = SimpleNamespace(
            title="KPI",
            get_all_values=lambda: [
                ["", "GPON00-D1-PPN-2MTO", "WRONG"],
            ],
        )
        spreadsheet = SimpleNamespace(
            worksheets=lambda: [unrelated, archive],
        )

        mapping = build_site_district_map(spreadsheet)

        self.assertEqual(mapping["GPON00-D1-PPN-2MTO"], "DUM")
        self.assertEqual(mapping["PPN"], "DUM")


if __name__ == "__main__":
    unittest.main()
