import unittest
from datetime import datetime
from types import SimpleNamespace

from backup.isp_data import (
    HEADER,
    ID_GRUP_DUM,
    ISPRecord,
    daftar_grup_target,
    format_sheet_values,
    kumpulkan_records_dari_messages,
    parse_recovery_message,
)


class ISPDataBackfillTest(unittest.TestCase):
    def test_target_group_only_dumai(self):
        self.assertEqual(daftar_grup_target, [ID_GRUP_DUM])

    def test_parse_recovery_message_reads_node_id_and_down_duration(self):
        pesan = """Notifikasi OLT Recovery!
Node ID : GPON00-D1-MIS-3CLB
Witel : RIDAR
District : DUMAI
Recovered At : 2026-05-29 15:27:25
Down Duration : 14 Jam 10 Menit"""

        recovery = parse_recovery_message(pesan)

        self.assertEqual(recovery.hostname, "GPON00-D1-MIS-3CLB")
        self.assertEqual(recovery.durasi_down, "14 Jam 10 Menit")
        self.assertEqual(recovery.distrik, "Dumai")
        self.assertEqual(recovery.tanggal, "29-05-2026")

    def test_collect_history_uses_tr1_recovery_duration_not_dumai_warning_duration(self):
        messages = [
            SimpleNamespace(
                id=1,
                date=datetime(2026, 5, 29, 15, 0),
                text="""!PROGRAM ZERO GAMAS OLT!
- DISTRICT DUMAI
GPON01-D1-PPN-3BGJ | 00:10
PLN01-D1-PPN-3BGJ | PLN PADAM""",
            ),
            SimpleNamespace(
                id=2,
                date=datetime(2026, 5, 29, 15, 28),
                text="DUM | GPON01-D1-PPN-3BGJ | UP",
            ),
            SimpleNamespace(
                id=3,
                date=datetime(2026, 5, 29, 15, 29),
                text="""Notifikasi OLT Recovery!
Node IP : 172.26.194.138
Node ID : GPON01-D1-PPN-3BGJ
Status : UP
District : DUMAI
Down At : 2026-05-29 14:57:37
Recovered At : 2026-05-29 15:27:25
Down Duration : 29 Menit
Timestamp : 2026-05-29 15:28:29""",
            ),
        ]

        records = kumpulkan_records_dari_messages(messages, tahun=2026)

        self.assertEqual(
            records,
            [
                ISPRecord(
                    hostname="GPON01-D1-PPN-3BGJ",
                    rca="PLN",
                    durasi_down="29 Menit",
                    tanggal="29-05-2026",
                    distrik="Dumai",
                )
            ],
        )

    def test_pipe_up_without_tr1_recovery_does_not_write_row(self):
        messages = [
            SimpleNamespace(
                id=1,
                date=datetime(2026, 2, 17, 23, 0),
                text="""!PROGRAM ZERO GAMAS OLT!
- DISTRICT DUMAI
GPON00-D1-MIS-3CLB | 11:10""",
            ),
            SimpleNamespace(
                id=2,
                date=datetime(2026, 2, 17, 23, 30),
                text="DUM | GPON00-D1-MIS-3CLB | UP",
            ),
        ]

        records = kumpulkan_records_dari_messages(messages, tahun=2026)

        self.assertEqual(records, [])

    def test_collect_history_still_uses_recovery_down_duration_when_present(self):
        messages = [
            SimpleNamespace(
                id=1,
                date=datetime(2026, 3, 10, 10, 0),
                text="""!PROGRAM ZERO GAMAS OLT!
- DISTRICT DUMAI
GPON00-D1-DMI-1ABC | 30 Menit""",
            ),
            SimpleNamespace(
                id=2,
                date=datetime(2026, 3, 10, 10, 45),
                text="""Notifikasi OLT Recovery!
Node ID : GPON00-D1-DMI-1ABC
Down Duration : 45 Menit""",
            ),
        ]

        records = kumpulkan_records_dari_messages(messages, tahun=2026)

        self.assertEqual(records[0].rca, "Kable CUT")
        self.assertEqual(records[0].durasi_down, "45 Menit")

    def test_format_sheet_values_includes_rca_column(self):
        values = format_sheet_values(
            [
                ISPRecord(
                    hostname="GPON00-D1-MIS-3CLB",
                    rca="PLN",
                    durasi_down="11:40",
                    tanggal="18-02-2026",
                    distrik="Dumai",
                )
            ]
        )

        self.assertEqual(values[0], HEADER)
        self.assertEqual(
            values[1],
            [1, "GPON00-D1-MIS-3CLB", "PLN", "11:40", "18-02-2026", "Dumai"],
        )


if __name__ == "__main__":
    unittest.main()
