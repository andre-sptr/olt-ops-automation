from unittest import TestCase, mock

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
            "\U0001f7e5 Critical | NodeB-123 | OLO1 | K2A | K3A | PLN-456 | DH",
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
            }
        }
        baris = mi.format_baris_down(1, info, metadata)
        self.assertTrue(baris.endswith("| NON"))

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


class TestBuatLaporanList(TestCase):
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
        self.assertIn(
            "NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | "
            "NodeB | OLO | K2 | K3 | IdPLN | DH",
            laporan,
        )

    def test_laporan_row_includes_dh_value(self):
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
        self.assertIn(
            "1. BATAM | GPON00-D1-ARK-3SGA | 00:15 | "
            "\U0001f7e0 Minor | NB-1 | 0 | 0 | 0 | ID-1 | DH",
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
            "- | NB-2 | 0 | 0 | 0 | ID-2 | -",
            laporan,
        )
        log_messages = [call.args[0] for call in simpan_log_mock.call_args_list]
        self.assertTrue(
            any("menggunakan '-'" in msg for msg in log_messages)
        )
