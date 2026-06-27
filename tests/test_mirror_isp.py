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
            mock.patch.object(mi, "tulis_rekap_olt"),
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


class TestBangunBarisRekap(TestCase):
    def setUp(self):
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_baris_down_lengkap_severity_polos(self):
        info = "DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"
        metadata = {
            "GPON00-D1-BGU-3BGB": {
                "severity": "Very Low", "olo": "0", "k2": "0",
                "k3": "0", "dh": "NON", "ds": "NOK",
            }
        }
        baris = mi.bangun_baris_rekap(
            1, info, metadata, "DOWN", "20/06/2026 07:08:24"
        )
        self.assertEqual(
            baris,
            ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
             "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
             "DOWN", "20/06/2026 07:08:24"],
        )

    def test_default_saat_metadata_kosong(self):
        info = "PADANG | GPON00-D1-XYZ | 00:20 | NB"
        baris = mi.bangun_baris_rekap(3, info, {}, "DOWN", "20/06/2026 08:00:00")
        # severity default 'Very Low', olo/k2/k3 '0', dh/ds '-'
        self.assertEqual(baris[0], "3")
        self.assertEqual(baris[4], "Very Low")
        self.assertEqual(baris[5], "NB")
        self.assertEqual(baris[6:11], ["0", "0", "0", "-", "-"])
        self.assertEqual(baris[12], "DOWN")


class TestIndeksInsidenAktif(TestCase):
    def test_hanya_status_down_dan_paling_bawah(self):
        semua_nilai = [
            mi.HEADER_REKAP,
            ["1", "DUMAI", "GPON00-A", "05:50", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "UP", "20/06/2026 07:00:00"],
            ["2", "DUMAI", "GPON00-B", "01:00", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "DOWN", "20/06/2026 07:30:00"],
            ["3", "DUMAI", "GPON00-B", "00:10", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "DOWN", "20/06/2026 09:00:00"],
        ]
        indeks = mi.indeks_insiden_aktif(semua_nilai)
        self.assertNotIn("GPON00-A", indeks)   # UP, bukan aktif
        self.assertEqual(indeks["GPON00-B"], 4)  # baris paling bawah (1-based)

    def test_sheet_kosong_header_saja(self):
        self.assertEqual(mi.indeks_insiden_aktif([mi.HEADER_REKAP]), {})


class TestRencanaTulisRekap(TestCase):
    def setUp(self):
        from datetime import datetime
        self.dt = datetime
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()
        self.metadata = {
            "GPON00-D1-BGU-3BGB": {
                "severity": "Very Low", "olo": "0", "k2": "0",
                "k3": "0", "dh": "NON", "ds": "NOK",
            }
        }

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_down_baru_diappend_dengan_no_berurutan(self):
        semua_nilai = [mi.HEADER_REKAP]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"], [],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        self.assertEqual(appends[0][0], "1")            # NO
        self.assertEqual(appends[0][3], "05:50")        # DURASI
        self.assertEqual(appends[0][12], "DOWN")        # STATUS
        self.assertEqual(appends[0][13], "20/06/2026 07:08:24")

    def test_re_alert_update_in_place_pertahankan_no(self):
        baris_lama = ["7", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 07:08:24"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 06:20 | 0"], [],
            self.dt(2026, 6, 20, 7, 38, 24),
        )
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        self.assertEqual(appends[0][0], "2")            # NO = len(semua_nilai)
        self.assertEqual(appends[0][3], "06:20")        # DURASI refresh
        self.assertEqual(appends[0][12], "DOWN")
        self.assertEqual(appends[0][13], "20/06/2026 07:38:24")

    def test_re_alert_metadata_kosong_mempertahankan_metadata_baris_aktif(self):
        mi.data_pln_down["PLN00-D1-BGU-3BGB"] = (
            "DUMAI | PLN00-D1-BGU-3BGB | 01:05 | 0"
        )
        baris_lama = [
            "42", "DUMAI", "GPON00-D1-BGU-3BGB", "00:10", "Critical",
            "NodeB-Lama", "OLO-X", "K2-X", "K3-X", "DH", "DS-OK",
            "Kabel CUT", "DOWN", "20/06/2026 07:00:00",
        ]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]

        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, {},
            ["PADANG | GPON00-D1-BGU-3BGB | 00:30 | NodeB-Baru"], [],
            self.dt(2026, 6, 20, 7, 30, 0),
        )

        # Append-only: re-alert appends a new row via bangun_baris_rekap
        # with default metadata (mapping_metadata is empty {}).
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        baris = appends[0]
        self.assertEqual(baris[0], "2")                  # NO = len(semua_nilai)
        self.assertEqual(baris[1], "PADANG")             # district from new info
        self.assertEqual(baris[2], "GPON00-D1-BGU-3BGB")
        self.assertEqual(baris[3], "00:30")
        self.assertEqual(baris[4], "Very Low")           # default severity
        self.assertEqual(baris[5], "NodeB-Baru")         # node_b from info
        self.assertEqual(baris[11], "Baterai Habis dan OLT DOWN")
        self.assertEqual(baris[12], "DOWN")
        self.assertEqual(baris[13], "20/06/2026 07:30:00")

    def test_up_finalisasi_bekukan_durasi_total(self):
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:30", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 06:50:00"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata, [],
            [{"hostname": "GPON00-D1-BGU-3BGB",
              "started_at": self.dt(2026, 6, 20, 1, 18, 24)}],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        # Append-only: UP event copies old row data and appends.
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        baris = appends[0]
        self.assertEqual(baris[0], "2")                 # NO = len(semua_nilai)
        self.assertEqual(baris[3], "05:50")             # total outage beku
        self.assertEqual(baris[11], "Kabel CUT")        # HIPOTESA dipertahankan
        self.assertEqual(baris[12], "UP")
        self.assertEqual(baris[13], "20/06/2026 07:08:24")

    def test_up_tanpa_started_at_pertahankan_durasi_lama(self):
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "06:20", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 06:50:00"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata, [],
            [{"hostname": "GPON00-D1-BGU-3BGB", "started_at": None}],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        # Append-only: UP copies old row, preserves old duration when started_at=None
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        baris = appends[0]
        self.assertEqual(baris[3], "06:20")             # durasi lama dipertahankan
        self.assertEqual(baris[12], "UP")

    def test_up_yatim_dilewati(self):
        updates, appends = mi.rencana_tulis_rekap(
            [mi.HEADER_REKAP], self.metadata, [],
            [{"hostname": "GPON00-TIDAK-ADA", "started_at": None}],
            self.dt(2026, 6, 20, 7, 0, 0),
        )
        self.assertEqual((updates, appends), ([], []))

    def test_down_lagi_setelah_up_append_baris_baru(self):
        baris_up = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                    "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                    "UP", "20/06/2026 07:08:24"]
        semua_nilai = [mi.HEADER_REKAP, baris_up]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 00:05 | 0"], [],
            self.dt(2026, 6, 20, 14, 0, 0),
        )
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        self.assertEqual(appends[0][0], "2")            # NO berikutnya
        self.assertEqual(appends[0][12], "DOWN")


class TestTulisRekapOlt(TestCase):
    def setUp(self):
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def _fake_worksheet(self, semua_nilai):
        ws = mock.Mock()
        ws.get_all_values.return_value = semua_nilai
        return ws

    def test_append_baris_baru_dan_header_saat_kosong(self):
        from datetime import datetime
        ws = self._fake_worksheet([])  # sheet benar-benar kosong
        with (
            mock.patch.object(mi, "gspread") as gspread_mock,
            mock.patch.object(mi, "ServiceAccountCredentials"),
            mock.patch.object(mi, "simpan_log"),
        ):
            (gspread_mock.authorize.return_value
             .open_by_key.return_value
             .get_worksheet_by_id.return_value) = ws
            mi.tulis_rekap_olt(
                {"GPON00-D1-BGU-3BGB": {"severity": "Very Low", "olo": "0",
                 "k2": "0", "k3": "0", "dh": "NON", "ds": "NOK"}},
                ["DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"],
                [],
                datetime(2026, 6, 20, 7, 8, 24),
            )
        ws.append_row.assert_called_once_with(
            mi.HEADER_REKAP, value_input_option="RAW"
        )
        ws.append_rows.assert_called_once()
        baris_baru = ws.append_rows.call_args.args[0]
        self.assertEqual(baris_baru[0][2], "GPON00-D1-BGU-3BGB")
        self.assertEqual(baris_baru[0][12], "DOWN")

    def test_re_alert_appends_new_row(self):
        from datetime import datetime
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 07:08:24"]
        ws = self._fake_worksheet([mi.HEADER_REKAP, baris_lama])
        with (
            mock.patch.object(mi, "gspread") as gspread_mock,
            mock.patch.object(mi, "ServiceAccountCredentials"),
            mock.patch.object(mi, "simpan_log"),
        ):
            (gspread_mock.authorize.return_value
             .open_by_key.return_value
             .get_worksheet_by_id.return_value) = ws
            mi.tulis_rekap_olt(
                {}, ["DUMAI | GPON00-D1-BGU-3BGB | 06:20 | 0"], [],
                datetime(2026, 6, 20, 7, 38, 24),
            )
        # Append-only: re-alert now appends, no batch_update
        ws.batch_update.assert_not_called()
        ws.append_rows.assert_called_once()
        baris_baru = ws.append_rows.call_args.args[0]
        self.assertEqual(baris_baru[0][3], "06:20")
        self.assertEqual(baris_baru[0][12], "DOWN")

    def test_noop_saat_tidak_ada_item(self):
        from datetime import datetime
        with mock.patch.object(mi, "gspread") as gspread_mock:
            mi.tulis_rekap_olt({}, [], [], datetime(2026, 6, 20, 7, 0, 0))
        gspread_mock.authorize.assert_not_called()


class TestHookRekapProsesPesan(TestCase):
    def setUp(self):
        self.snapshot = {
            name: getattr(mi, name).copy()
            for name in ("data_gpon_down", "data_gpon_up", "data_gpon_down_meta",
                         "data_pln_down", "data_pln_down_meta")
        }
        for name in self.snapshot:
            getattr(mi, name).clear()

    def tearDown(self):
        for name, nilai in self.snapshot.items():
            getattr(mi, name).clear()
            getattr(mi, name).update(nilai)

    def test_event_down_memanggil_tulis_rekap_dengan_down_items(self):
        event = SimpleNamespace(
            text=(
                "!PROGRAM ZERO GAMAS OLT!\n"
                "- DISTRICT DUMAI\n"
                "GPON00-D1-BGU-3BGB | 05:50 | 0"
            ),
            date=datetime(2026, 6, 20, 7, 8),
        )
        with (
            mock.patch.object(mi, "ambil_mapping_metadata", return_value={}),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "kirim_pesan_wa"),
            mock.patch.object(mi, "tulis_rekap_olt") as tulis_mock,
            mock.patch.object(mi, "simpan_log"),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        tulis_mock.assert_called_once()
        down_items = tulis_mock.call_args.args[1]
        self.assertTrue(any("GPON00-D1-BGU-3BGB" in s for s in down_items))

    def test_event_up_mengirim_started_at(self):
        # Pra-kondisi: OLT sedang down dengan started_at diketahui
        mi.data_gpon_down["GPON00-D1-BGU-3BGB"] = (
            "DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"
        )
        mi.data_gpon_down_meta["GPON00-D1-BGU-3BGB"] = {
            "duration": "05:50",
            "started_at": datetime(2026, 6, 20, 1, 18),
        }
        event = SimpleNamespace(
            text="GPON00-D1-BGU-3BGB | UP",
            date=datetime(2026, 6, 20, 7, 8),
        )
        with (
            mock.patch.object(mi, "ambil_mapping_metadata", return_value={}),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "kirim_pesan_wa"),
            mock.patch.object(mi, "tulis_rekap_olt") as tulis_mock,
            mock.patch.object(mi, "simpan_log"),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        up_items = tulis_mock.call_args.args[2]
        self.assertEqual(up_items[0]["hostname"], "GPON00-D1-BGU-3BGB")
        self.assertEqual(up_items[0]["started_at"], datetime(2026, 6, 20, 1, 18))
