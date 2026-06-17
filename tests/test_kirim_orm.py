from unittest import TestCase, mock

import kirim_orm as ko


def make_sheet_values():
    return [
        ["DISTRICT", "LIST", "ORM / NON", "TARGET", "DONE", "ACH %", "PROGRESS"],
        ["PADANG", "ONT-Nisasi 14 Site", "ORM", "14", "3", "21,43%", "Sudah nodin"],
        [
            "PADANG",
            "Link Radio IP LH from Siberut Utara to Bukit Silasung",
            "ORM",
            "1",
            "",
            "0,00%",
            "",
        ],
        [
            "PADANG",
            "QE ASK025 -> nitip di project bges",
            "NON-ORM",
            "1",
            "0,5",
            "50,00%",
            "Titip project BGES",
        ],
        ["PEKAN BARU", "QE SSI544", "Non ORM", "5", "1", "20,00%", ""],
        ["OTHER", "Tidak dipakai", "ORM", "1", "", "0,00%", ""],
        ["PADANG", "", "NON-ORM", "1", "", "0,00%", ""],
        ["PADANG", "Jenis tidak valid", "TODO", "1", "", "0,00%", ""],
    ]


class KirimOrmTests(TestCase):
    def test_kolom_ke_indeks_uses_zero_based_indices(self):
        self.assertEqual(ko.kolom_ke_indeks("A"), 0)
        self.assertEqual(ko.kolom_ke_indeks("B"), 1)
        self.assertEqual(ko.kolom_ke_indeks("F"), 5)
        self.assertEqual(ko.kolom_ke_indeks("G"), 6)

    def test_normalisasi_jenis_handles_orm_and_non_orm_variants(self):
        self.assertEqual(ko.normalisasi_jenis("ORM"), "ORM")
        self.assertEqual(ko.normalisasi_jenis("NON-ORM"), "NON-ORM")
        self.assertEqual(ko.normalisasi_jenis("Non ORM"), "NON-ORM")
        self.assertEqual(ko.normalisasi_jenis("non_orm"), "NON-ORM")
        self.assertEqual(ko.normalisasi_jenis("TODO"), "")

    def test_ekstrak_data_per_distrik_splits_orm_and_non_orm(self):
        data = ko.ekstrak_data_per_distrik(make_sheet_values())

        self.assertEqual(data["PADANG"]["ORM"], [
            {"list": "ONT-Nisasi 14 Site", "ach": "21,43%", "progress": "Sudah nodin"},
            {
                "list": "Link Radio IP LH from Siberut Utara to Bukit Silasung",
                "ach": "0,00%",
                "progress": "",
            },
        ])
        self.assertEqual(data["PADANG"]["NON-ORM"], [
            {
                "list": "QE ASK025 -> nitip di project bges",
                "ach": "50,00%",
                "progress": "Titip project BGES",
            }
        ])
        self.assertEqual(data["PEKANBARU"]["NON-ORM"], [
            {"list": "QE SSI544", "ach": "20,00%", "progress": ""}
        ])

    def test_buat_pesan_distrik_uses_expected_bubble_format(self):
        data = ko.ekstrak_data_per_distrik(make_sheet_values())

        text = ko.buat_pesan_distrik("PADANG", data["PADANG"])

        self.assertEqual(text, "\n".join([
            "*List ORM*",
            "Padang",
            "============",
            "ORM:",
            "1. ONT-Nisasi 14 Site | 21,43% | Sudah nodin",
            "2. Link Radio IP LH from Siberut Utara to Bukit Silasung | 0,00% | -",
            "Non-ORM:",
            "1. QE ASK025 -> nitip di project bges | 50,00% | Titip project BGES",
            "cc @6281289149112",
        ]))

    def test_baris_cc_distrik_uses_manja_pic_mapping(self):
        cc_line, mentions = ko.baris_cc_distrik("PADANG")

        self.assertEqual(cc_line, "cc @6281289149112")
        self.assertEqual(mentions, ["6281289149112@c.us"])

    def test_tugas_sends_one_bubble_per_district(self):
        sent = []
        logs = []

        def fake_send(chat_id, text, mentions=None):
            sent.append((chat_id, text, mentions))
            return True

        with (
            mock.patch.object(ko, "ambil_semua_nilai", make_sheet_values),
            mock.patch.object(ko, "kirim_teks_wa", fake_send),
            mock.patch.object(ko, "catat_log", lambda pesan: logs.append(pesan)),
            mock.patch.object(ko.time, "sleep", lambda _: None),
        ):
            ko.tugas()

        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][0], ko.GROUP_ID_TUJUAN)
        self.assertTrue(sent[0][1].startswith("*List ORM*\nPekanbaru\n============\nORM:"))
        self.assertTrue(sent[1][1].startswith("*List ORM*\nPadang\n============\nORM:"))
        self.assertEqual(sent[0][2], ["6281372264429@c.us"])
        self.assertEqual(sent[1][2], ["6281289149112@c.us"])
        self.assertTrue(any("Ditemukan 4 list ORM/NON-ORM" in pesan for pesan in logs))
