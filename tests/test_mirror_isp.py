import asyncio
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase, mock


class _FakeTelegramClient:
    def __init__(self, *args, **kwargs):
        pass

    def on(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


sys.modules.setdefault(
    "telethon",
    SimpleNamespace(
        TelegramClient=_FakeTelegramClient,
        events=SimpleNamespace(NewMessage=lambda *args, **kwargs: object()),
    ),
)

import mirror_isp as mi


class TestBuatMappingMetadata(TestCase):
    def test_normalizes_hostname_and_severity(self):
        values = [
            [" gpon00-d1-amk-2ukui ", "", "", "", "", "", "", "critical", "OLO1", "K2A", "K3A"],
            ["GPON00-D1-ARK-3SGA", "", "", "", "", "", "", "Minor", "", "", ""],
            ["GPON00-D1-NON-1ABC", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "Major", "", "", ""],
            ["GPON-TIDAK-VALID", "", "", "", "", "", "", "Unknown", "", "", ""],
        ]

        mapping = mi.buat_mapping_metadata(values)

        self.assertIn("GPON00-D1-AMK-2UKUI", mapping)
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"]["severity"], "Critical")
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"]["olo"], "OLO1")
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"]["k2"], "K2A")
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"]["k3"], "K3A")
        self.assertIn("GPON00-D1-ARK-3SGA", mapping)
        self.assertEqual(mapping["GPON00-D1-ARK-3SGA"]["severity"], "Minor")
        self.assertIn("GPON00-D1-NON-1ABC", mapping)
        self.assertEqual(mapping["GPON00-D1-NON-1ABC"]["severity"], "")
        # Empty hostname skipped
        self.assertNotIn("", mapping)
        # "Unknown" is not a valid severity
        self.assertEqual(mapping["GPON-TIDAK-VALID"]["severity"], "")


class TestBuatMappingDH(TestCase):
    def test_dualhoming_maps_to_dh(self):
        values = [
            ["GPON00-D1-AMK-2UKUI", "ignore", "DUALHOMING"],
            [" gpon00-d1-ark-3sga ", "ignore", "dualhoming"],
        ]
        mapping = mi.buat_mapping_dh(values)
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"], "DH")
        self.assertEqual(mapping["GPON00-D1-ARK-3SGA"], "DH")

    def test_non_dualhoming_maps_to_non(self):
        values = [
            ["GPON00-D1-AMK-2UKUI", "ignore", "SINGLE"],
            ["GPON00-D1-ARK-3SGA", "ignore", ""],
            ["GPON00-D1-NON-1ABC", "ignore", "NON DUALHOMING"],
        ]
        mapping = mi.buat_mapping_dh(values)
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"], "NON")
        self.assertEqual(mapping["GPON00-D1-ARK-3SGA"], "NON")
        self.assertEqual(mapping["GPON00-D1-NON-1ABC"], "NON")

    def test_empty_hostname_skipped(self):
        values = [
            ["", "ignore", "DUALHOMING"],
            ["GPON00-D1-AMK-2UKUI", "ignore", "DUALHOMING"],
        ]
        mapping = mi.buat_mapping_dh(values)
        self.assertNotIn("", mapping)
        self.assertEqual(len(mapping), 1)

    def test_short_row_padded(self):
        """Row with only hostname (no F column) should default to NON."""
        values = [
            ["GPON00-D1-AMK-2UKUI"],
        ]
        mapping = mi.buat_mapping_dh(values)
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"], "NON")

    def test_empty_rows_skipped(self):
        values = [[], ["GPON00-D1-AMK-2UKUI", "", "DUALHOMING"]]
        mapping = mi.buat_mapping_dh(values)
        self.assertEqual(len(mapping), 1)
        self.assertEqual(mapping["GPON00-D1-AMK-2UKUI"], "DH")


class TestFormatBarisDown(TestCase):
    def setUp(self):
        self.data_down_lama = mi.data_gpon_down.copy()
        self.data_up_lama = mi.data_gpon_up.copy()
        mi.data_gpon_down.clear()
        mi.data_gpon_up.clear()

    def tearDown(self):
        mi.data_gpon_down.clear()
        mi.data_gpon_down.update(self.data_down_lama)
        mi.data_gpon_up.clear()
        mi.data_gpon_up.update(self.data_up_lama)

    def test_format_includes_dh_column(self):
        info = (
            "DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "NodeB-123 | PLN-456"
        )
        metadata = {
            "GPON00-D1-AMK-2UKUI": {
                "severity": "Critical",
                "olo": "OLO1",
                "k2": "K2A",
                "k3": "K3A",
                "dh": "DH",
            }
        }
        baris = mi.format_baris_down(1, info, metadata)
        self.assertEqual(
            baris,
            "1. DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "\U0001f7e5 Critical | NodeB-123 | OLO1 | K2A | K3A | DH | -",
        )

    def test_format_shows_non_for_non_dualhoming(self):
        info = "PADANG | GPON00-D1-XYZ | 00:20 | NB | PLN"
        metadata = {
            "GPON00-D1-XYZ": {
                "severity": "Minor",
                "olo": "0",
                "k2": "0",
                "k3": "0",
                "dh": "NON",
                "ds": "NOK",
            }
        }
        baris = mi.format_baris_down(1, info, metadata)
        self.assertTrue(baris.endswith("| NON | NOK"))

    def test_format_dh_dash_when_metadata_none(self):
        """When metadata sheet fails entirely, DH should be '-'."""
        info = "PADANG | GPON00-D1-UNKNOWN | 10 Menit"
        baris = mi.format_baris_down(2, info, None)
        self.assertTrue(baris.endswith("| -"))

    def test_format_dh_dash_when_hostname_not_in_mapping(self):
        info = "PADANG | GPON00-D1-UNKNOWN | 10 Menit | NB | PLN"
        baris = mi.format_baris_down(1, info, {})
        self.assertTrue(baris.endswith("| -"))

    def test_format_severity_emoji_critical(self):
        info = (
            "DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "NodeB-123 | PLN-456"
        )
        metadata = {
            "GPON00-D1-AMK-2UKUI": {
                "severity": "Critical",
                "olo": "0",
                "k2": "0",
                "k3": "0",
                "dh": "DH",
            }
        }
        baris = mi.format_baris_down(1, info, metadata)
        self.assertIn("\U0001f7e5 Critical", baris)

    def test_format_uses_very_low_for_missing_severity(self):
        baris = mi.format_baris_down(
            2,
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit",
            {},
        )
        self.assertIn("\u2b50 Very Low", baris)


class TestHipotesaDown(TestCase):
    def setUp(self):
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_kabel_cut_when_pln_and_gpon_start_within_five_minutes(self):
        mi.data_pln_down["PLN00-D1-SGD-2TMP"] = (
            "PEKANBARU | PLN00-D1-SGD-2TMP | 01:58 | 1 | ID-PLN"
        )

        hipotesa = mi.tentukan_hipotesa_down(
            "GPON00-D1-SGD-2TMP",
            "01:55",
        )

        self.assertEqual(hipotesa, "Kabel CUT")

    def test_battery_exhausted_when_pln_started_more_than_five_minutes_before_gpon(self):
        mi.data_pln_down["PLN00-D1-BAG-3KYM"] = (
            "DUMAI | PLN00-D1-BAG-3KYM | 03:20 | 0 | ID-PLN"
        )

        hipotesa = mi.tentukan_hipotesa_down(
            "GPON00-D1-BAG-3KYM",
            "00:10",
        )

        self.assertEqual(hipotesa, "Baterai Habis dan OLT DOWN")


class TestBuatLaporanList(TestCase):
    def setUp(self):
        self.data_down_lama = mi.data_gpon_down.copy()
        self.data_up_lama = mi.data_gpon_up.copy()
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_gpon_down.clear()
        mi.data_gpon_up.clear()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_gpon_down.clear()
        mi.data_gpon_down.update(self.data_down_lama)
        mi.data_gpon_up.clear()
        mi.data_gpon_up.update(self.data_up_lama)
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_header_includes_dh(self):
        mi.data_gpon_down["GPON00-D1-ARK-3SGA"] = (
            "BATAM | GPON00-D1-ARK-3SGA | 00:15 | NB-1 | ID-1"
        )
        metadata = {
            "GPON00-D1-ARK-3SGA": {
                "severity": "Minor",
                "olo": "0",
                "k2": "0",
                "k3": "0",
                "dh": "DH",
            }
        }
        laporan = mi.buat_laporan_list(metadata)
        self.assertTrue(laporan.startswith("*OLT DOWN*\n"))
        self.assertIn(
            "NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | "
            "NodeB | OLO | K2 | K3 | DH | DS",
            laporan,
        )

    def test_laporan_row_includes_dh_ds_and_hypothesis(self):
        mi.data_gpon_down["GPON00-D1-BAG-3KYM"] = (
            "DUMAI | GPON00-D1-BAG-3KYM | 00:10 | 0 | ID-1"
        )
        mi.data_pln_down["PLN00-D1-BAG-3KYM"] = (
            "DUMAI | PLN00-D1-BAG-3KYM | 03:20 | 0 | ID-1"
        )
        metadata = {
            "GPON00-D1-BAG-3KYM": {
                "severity": "",
                "olo": "0",
                "k2": "0",
                "k3": "0",
                "dh": "NON",
                "ds": "NOK",
            }
        }
        laporan = mi.buat_laporan_list(metadata)
        self.assertIn(
            "1. DUMAI | GPON00-D1-BAG-3KYM | 00:10 | "
            "\u2b50 Very Low | 0 | 0 | 0 | 0 | NON | NOK\n"
            "Hipotesa : Baterai Habis dan OLT DOWN",
            laporan,
        )

    def test_laporan_uses_dash_when_sheet_read_fails(self):
        """When ambil_mapping_metadata raises, all metadata columns become '-'."""
        mi.data_gpon_down["GPON00-D1-UNKNOWN"] = (
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit | NB-2 | ID-2"
        )

        with (
            mock.patch.object(
                mi,
                "ambil_mapping_metadata",
                side_effect=RuntimeError("sheet unavailable"),
            ),
            mock.patch.object(mi, "simpan_log") as simpan_log_mock,
        ):
            laporan = mi.buat_laporan_list()

        # mapping_metadata = None -> severity="-", dh="-"
        self.assertIn(
            "1. PADANG | GPON00-D1-UNKNOWN | 10 Menit | "
            "- | NB-2 | 0 | 0 | 0 | - | -\n"
            "Hipotesa : Kabel CUT",
            laporan,
        )
        log_messages = [call.args[0] for call in simpan_log_mock.call_args_list]
        self.assertTrue(
            any("menggunakan '-'" in msg for msg in log_messages)
        )


class TestProsesPesanBaru(TestCase):
    def setUp(self):
        self.data_down_lama = mi.data_gpon_down.copy()
        self.data_up_lama = mi.data_gpon_up.copy()
        self.data_down_meta_lama = mi.data_gpon_down_meta.copy()
        self.data_pln_down_lama = mi.data_pln_down.copy()
        self.data_pln_down_meta_lama = mi.data_pln_down_meta.copy()
        mi.data_gpon_down.clear()
        mi.data_gpon_up.clear()
        mi.data_gpon_down_meta.clear()
        mi.data_pln_down.clear()
        mi.data_pln_down_meta.clear()

    def tearDown(self):
        mi.data_gpon_down.clear()
        mi.data_gpon_down.update(self.data_down_lama)
        mi.data_gpon_up.clear()
        mi.data_gpon_up.update(self.data_up_lama)
        mi.data_gpon_down_meta.clear()
        mi.data_gpon_down_meta.update(self.data_down_meta_lama)
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)
        mi.data_pln_down_meta.clear()
        mi.data_pln_down_meta.update(self.data_pln_down_meta_lama)

    def test_gpon_down_line_with_id_pln_field_is_still_recorded(self):
        event = SimpleNamespace(
            text=(
                "!PROGRAM ZERO GAMAS OLT!\n"
                "- DISTRICT PEKANBARU\n"
                "GPON00-D1-AMK-2KMT | 01:55 | 1 | PLN-456\n"
                "PLN00-D1-AMK-2KMT | 01:55 | 1 | PLN-456"
            ),
            date=datetime(2026, 6, 19, 10, 0),
        )

        with (
            mock.patch.object(mi, "ambil_mapping_metadata", return_value={}),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "kirim_pesan_wa"),
            mock.patch.object(mi, "simpan_log"),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        self.assertIn("GPON00-D1-AMK-2KMT", mi.data_gpon_down)
        self.assertIn("PLN00-D1-AMK-2KMT", mi.data_pln_down)


class TestHelperRekap(TestCase):
    def test_header_punya_14_kolom_urutan_benar(self):
        self.assertEqual(
            mi.HEADER_REKAP,
            ["NO", "DISTRICT", "HOSTNAME", "DURASI DOWN", "SEVERITY",
             "NodeB", "OLO", "K2", "K3", "DH", "DS", "HIPOTESA",
             "STATUS", "TIMESTAMP"],
        )
        self.assertEqual(mi.GID_SHEET_REKAP, 320650666)

    def test_format_timestamp_rekap(self):
        from datetime import datetime
        hasil = mi.format_timestamp_rekap(datetime(2026, 6, 20, 7, 8, 24))
        self.assertEqual(hasil, "20/06/2026 07:08:24")

    def test_hitung_durasi_total_jam_menit(self):
        from datetime import datetime
        started = datetime(2026, 6, 20, 1, 18, 24)
        up = datetime(2026, 6, 20, 7, 8, 24)
        self.assertEqual(mi.hitung_durasi_total(started, up), "05:50")

    def test_hitung_durasi_total_none_saat_started_kosong(self):
        from datetime import datetime
        self.assertIsNone(mi.hitung_durasi_total(None, datetime(2026, 6, 20, 7, 0)))

    def test_hitung_durasi_total_none_saat_negatif(self):
        from datetime import datetime
        started = datetime(2026, 6, 20, 8, 0)
        up = datetime(2026, 6, 20, 7, 0)
        self.assertIsNone(mi.hitung_durasi_total(started, up))
