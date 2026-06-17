import kirim_manja as km


def make_sheet_values():
    values = [["" for _ in range(24)] for _ in range(9)]

    # MANJA B5:F => B tiket, C jam booking, D STO, E SA, F DISTRIK
    values[4][1] = "INC-MANJA-BTM"
    values[4][2] = "2026-06-01 15:00:00.0"
    values[4][3] = "SLU"
    values[4][4] = "SA SAGULUNG"
    values[4][5] = "Batam"

    values[5][1] = "INC-MANJA-BKT"
    values[5][2] = "2026-06-01 16:00:00.0"
    values[5][3] = "BKT"
    values[5][4] = "SA BUKITTINGGI"
    values[5][5] = "Bukit Tinggi"

    values[6][1] = "INC-MANJA-UNK"
    values[6][2] = "2026-06-01 17:00:00.0"
    values[6][3] = "UNK"
    values[6][4] = "SA UNKNOWN"
    values[6][5] = "Riau"

    # DIAMOND H5:L => H tiket, I lama, J STO, K SA, L DISTRIK
    values[4][7] = "INC-DIAMOND-PKU"
    values[4][8] = "1"
    values[4][9] = "PKU"
    values[4][10] = "SA PEKANBARU"
    values[4][11] = "Pekanbaru"

    # PLATINUM N5:R => N tiket, O lama, P STO, Q SA, R DISTRIK
    values[4][13] = "INC-PLATINUM-DUM"
    values[4][14] = "6"
    values[4][15] = "DUM"
    values[4][16] = "SA DUMAI"
    values[4][17] = "Dumai"

    # JAM72 U5:X => U tiket, V lama, W STO, X DISTRIK
    values[4][20] = "INC-72-PDG"
    values[4][21] = "72"
    values[4][22] = "PDG"
    values[4][23] = "Padang"

    values[5][20] = "INC-72-OTHER"
    values[5][21] = "80"
    values[5][22] = "OTH"
    values[5][23] = "Other"

    return values


def test_kolom_ke_indeks_uses_zero_based_indices():
    assert km.kolom_ke_indeks("A") == 0
    assert km.kolom_ke_indeks("B") == 1
    assert km.kolom_ke_indeks("L") == 11
    assert km.kolom_ke_indeks("X") == 23


def test_normalisasi_distrik_handles_target_variants():
    assert km.normalisasi_distrik(" Batam ") == "BATAM"
    assert km.normalisasi_distrik("Pekanbaru") == "PEKANBARU"
    assert km.normalisasi_distrik("Dumai") == "DUMAI"
    assert km.normalisasi_distrik("Bukit Tinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("BUKIT TINGGI") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Bukittinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Padang") == "PADANG"


def test_ekstrak_table_groups_known_districts_and_logs_unknown_rows():
    data = km.ekstrak_table(km.TABLE_CONFIGS["MANJA"], make_sheet_values())

    assert data.by_district["BATAM"] == [
        ["INC-MANJA-BTM", "2026-06-01 15:00:00.0", "SLU", "SA SAGULUNG"]
    ]
    assert data.by_district["BUKITTINGGI"] == [
        ["INC-MANJA-BKT", "2026-06-01 16:00:00.0", "BKT", "SA BUKITTINGGI"]
    ]
    assert data.by_district["PEKANBARU"] == []
    assert data.by_district["DUMAI"] == []
    assert data.by_district["PADANG"] == []
    assert data.skipped == [
        (7, "Riau", ["INC-MANJA-UNK", "2026-06-01 17:00:00.0", "UNK", "SA UNKNOWN"])
    ]


def test_jam72_keeps_all_rows_for_inti_even_when_district_is_unknown():
    data = km.ekstrak_table(km.TABLE_CONFIGS["JAM72"], make_sheet_values())

    assert data.by_district["PADANG"] == [["INC-72-PDG", "72", "PDG", "Padang"]]
    assert data.by_district["BATAM"] == []
    assert data.all_rows == [
        ["INC-72-PDG", "72", "PDG", "Padang"],
        ["INC-72-OTHER", "80", "OTH", "Other"],
    ]
    assert data.skipped == [
        (6, "Other", ["INC-72-OTHER", "80", "OTH", "Other"])
    ]


def test_buat_pesan_data_uses_expected_manja_format():
    text = km.buat_pesan_data(
        km.TABLE_CONFIGS["MANJA"],
        "Batam",
        [["INC49847623", "2026-06-01 15:00:00.0", "SLU", "SA SAGULUNG"]],
    )

    assert text == "\n".join([
        "Alarm 3 Jam Manja Open | Batam",
        "==============",
        "Tiket | Jam Booking | STO | SA",
        "INC49847623 | 2026-06-01 15:00:00.0 | SLU | SA SAGULUNG",
    ])


def test_buat_pesan_clear_uses_expected_format():
    text = km.buat_pesan_clear(km.TABLE_CONFIGS["JAM72"], "")

    assert text == "\n".join([
        "Alarm 72 Jam Tiket Open",
        "==============",
        "CLEAR - Tidak ada tiket aktif.",
    ])


def test_proses_target_sends_first_run_data_and_skips_unchanged_rows():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    changed = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed is True
    assert len(sent) == 1
    assert sent[0][0] == "group-batam@g.us"
    assert sent[0][1].splitlines()[0] == "Alarm 3 Jam Diamond | Batam"

    changed_again = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed_again is False
    assert len(sent) == 1


def test_proses_target_sends_clear_when_existing_rows_become_empty():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    km.proses_target(
        snapshot,
        ("PLATINUM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM"],
        "Dumai",
        rows,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("PLATINUM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM"],
        "Dumai",
        [],
        fake_send,
    )

    assert changed is True
    assert sent[-1] == (
        "group-dumai@g.us",
        "\n".join([
            "Alarm 6 Jam Platinum | Dumai",
            "==============",
            "CLEAR - Tidak ada tiket aktif.",
        ]),
    )


def test_proses_target_ignores_volatile_duration_change():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows_awal = [["INC-72-PDG", "72", "PDG", "Padang"]]
    rows_jam_naik = [["INC-72-PDG", "80", "PDG", "Padang"]]

    km.proses_target(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        "",
        rows_awal,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        "",
        rows_jam_naik,
        fake_send,
    )

    assert changed is False
    assert len(sent) == 1


def test_proses_target_still_triggers_when_ticket_set_changes():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows_awal = [["INC-72-PDG", "72", "PDG", "Padang"]]
    rows_tiket_baru = [
        ["INC-72-PDG", "73", "PDG", "Padang"],
        ["INC-72-NEW", "10", "SLU", "Padang"],
    ]

    km.proses_target(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        "",
        rows_awal,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        "",
        rows_tiket_baru,
        fake_send,
    )

    assert changed is True
    assert len(sent) == 2


def test_proses_target_does_not_update_snapshot_when_send_fails():
    def failing_send(chat_id, text):
        return False

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    changed = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        failing_send,
    )

    assert changed is False
    assert snapshot == {}


def test_proses_siklus_routes_per_district_and_jam72_to_inti(monkeypatch):
    sent = []

    class FakeWorksheet:
        def get_all_values(self):
            return make_sheet_values()

    def fake_buka_worksheet():
        return FakeWorksheet()

    def fake_send(chat_id, text, mentions=None):
        sent.append((chat_id, text))
        return True

    logs = []

    monkeypatch.setattr(km, "buka_worksheet", fake_buka_worksheet)
    monkeypatch.setattr(km, "kirim_teks_wa", fake_send)
    monkeypatch.setattr(km, "catat_log", lambda pesan: logs.append(pesan))

    snapshot = {}
    changed = km.proses_siklus(snapshot)

    assert changed is True
    assert len(sent) == 7
    assert all("CLEAR" not in text for _, text in sent)
    assert any(chat_id == km.DISTRIK_GRUP["BATAM"] and text.startswith("Alarm 3 Jam Manja Open | Batam") for chat_id, text in sent)
    assert any(chat_id == km.DISTRIK_GRUP["BUKITTINGGI"] and text.startswith("Alarm 3 Jam Manja Open | Bukittinggi") for chat_id, text in sent)
    assert any(chat_id == km.DISTRIK_GRUP["PEKANBARU"] and text.startswith("Alarm 3 Jam Diamond | Pekanbaru") for chat_id, text in sent)
    assert any(chat_id == km.DISTRIK_GRUP["DUMAI"] and text.startswith("Alarm 6 Jam Platinum | Dumai") for chat_id, text in sent)
    assert any(chat_id == km.DISTRIK_GRUP["PADANG"] and text.startswith("Alarm 72 Jam Tiket Open | Padang") for chat_id, text in sent)
    assert any(chat_id == km.GRUP_INTI and text.startswith("Alarm 72 Jam Tiket Open | SBT\n") for chat_id, text in sent)
    assert any(chat_id == km.GRUP_INTI and text.startswith("Alarm 3 Jam Manja Open | SBT\n") for chat_id, text in sent)
    assert any("dilewati" in pesan for pesan in logs)

    sent.clear()
    changed_again = km.proses_siklus(snapshot)

    assert changed_again is False
    assert sent == []


def test_normalisasi_nomor_handles_common_formats():
    assert km.normalisasi_nomor("+62 813-7683-6000") == "6281376836000"
    assert km.normalisasi_nomor("081277200469") == "6281277200469"
    assert km.normalisasi_nomor("+62853 6311 8159") == "6285363118159"
    assert km.normalisasi_nomor("8126771-5408") == "6281267715408"
    assert km.normalisasi_nomor("") == ""


def test_buat_pesan_inti_groups_by_district_with_cc_and_dedup_mentions():
    rows_with_distrik = [
        (["INC1", "90", "TAK", "DUMAI"], "DUMAI"),
        (["INC2", "90", "TAK", "PEKAN BARU"], "PEKANBARU"),
    ]

    teks, mentions = km.buat_pesan_inti(
        km.TABLE_CONFIGS["JAM72"], km.SUFFIX_INTI, rows_with_distrik
    )

    # Dikelompokkan per distrik mengikuti urutan TARGET_DISTRIK (Pekanbaru sebelum Dumai).
    assert teks == "\n".join([
        "Alarm 72 Jam Tiket Open | SBT",
        "==============",
        "Tiket | Open Berjalan (Jam) | STO | Distrik",
        "INC2 | 90 | TAK | PEKAN BARU",
        "cc @6281261323575 @628126465895",
        "",
        "INC1 | 90 | TAK | DUMAI",
        "cc @6281275566031 @628126465895",
    ])
    # Nomor 628126465895 dipakai dua distrik tapi hanya muncul sekali di mentions.
    assert mentions == [
        "6281261323575@c.us",
        "628126465895@c.us",
        "6281275566031@c.us",
    ]


def test_buat_pesan_inti_one_cc_per_district_block():
    rows_with_distrik = [
        (["INC1", "90", "TAK", "DUMAI"], "DUMAI"),
        (["INC2", "85", "TAK", "DUMAI"], "DUMAI"),
    ]

    teks, mentions = km.buat_pesan_inti(
        km.TABLE_CONFIGS["JAM72"], km.SUFFIX_INTI, rows_with_distrik
    )

    # Semua tiket Dumai dikumpulkan dulu, baru SATU baris cc di bawahnya.
    assert teks == "\n".join([
        "Alarm 72 Jam Tiket Open | SBT",
        "==============",
        "Tiket | Open Berjalan (Jam) | STO | Distrik",
        "INC1 | 90 | TAK | DUMAI",
        "INC2 | 85 | TAK | DUMAI",
        "cc @6281275566031 @628126465895",
    ])
    assert teks.count("cc @") == 1
    assert mentions == ["6281275566031@c.us", "628126465895@c.us"]


def test_buat_pesan_inti_shared_number_once_per_block_dedup_in_mentions():
    rows_with_distrik = [
        (["INC1", "90", "TAK", "PEKAN BARU"], "PEKANBARU"),
        (["INC2", "80", "TAK", "PEKAN BARU"], "PEKANBARU"),
        (["INC3", "70", "TAK", "DUMAI"], "DUMAI"),
        (["INC4", "60", "TAK", "DUMAI"], "DUMAI"),
    ]

    teks, mentions = km.buat_pesan_inti(
        km.TABLE_CONFIGS["JAM72"], km.SUFFIX_INTI, rows_with_distrik
    )

    # Dua distrik -> dua baris cc (satu per blok), bukan satu per tiket.
    assert teks.count("cc @") == 2
    # Nomor share muncul sekali di tiap blok (2x di teks) tapi sekali di mentions.
    assert teks.count("@628126465895") == 2
    assert mentions.count("628126465895@c.us") == 1


def test_buat_pesan_inti_unknown_district_has_no_cc():
    rows_with_distrik = [(["INC9", "90", "OTH", "Other"], "OTHER")]

    teks, mentions = km.buat_pesan_inti(
        km.TABLE_CONFIGS["JAM72"], km.SUFFIX_INTI, rows_with_distrik
    )

    assert mentions == []
    assert "cc " not in teks
    assert teks.endswith("INC9 | 90 | OTH | Other")


def test_proses_target_inti_ignores_jam_change_but_sends_mentions():
    captured = []

    def fake_send(chat_id, text, mentions=None):
        captured.append((chat_id, text, mentions))
        return True

    snapshot = {}
    rows_awal = [(["INC1", "72", "TAK", "PADANG"], "PADANG")]
    rows_jam_naik = [(["INC1", "90", "TAK", "PADANG"], "PADANG")]

    km.proses_target_inti(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        km.SUFFIX_INTI,
        rows_awal,
        fake_send,
    )
    changed = km.proses_target_inti(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        km.SUFFIX_INTI,
        rows_jam_naik,
        fake_send,
    )

    assert changed is False
    assert len(captured) == 1
    _, text, mentions = captured[0]
    assert mentions == ["628116393933@c.us", "6282284545038@c.us"]
    assert "cc @628116393933 @6282284545038" in text


def test_proses_target_inti_triggers_when_district_changes():
    sent = []

    def fake_send(chat_id, text, mentions=None):
        sent.append((chat_id, text, mentions))
        return True

    snapshot = {}
    rows_awal = [(["INC1", "72", "TAK", "PADANG"], "PADANG")]
    rows_pindah = [(["INC1", "72", "TAK", "BATAM"], "BATAM")]

    km.proses_target_inti(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        km.SUFFIX_INTI,
        rows_awal,
        fake_send,
    )
    changed = km.proses_target_inti(
        snapshot,
        ("JAM72", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["JAM72"],
        km.SUFFIX_INTI,
        rows_pindah,
        fake_send,
    )

    assert changed is True
    assert len(sent) == 2
    assert sent[-1][2] == ["6281376836000@c.us", "6281277200469@c.us", "6281363210112@c.us"]


def test_main_polls_once_and_sleeps_with_reset_interval(monkeypatch):
    logs = []
    calls = []
    sleeps = []

    def fake_proses_siklus(snapshot):
        calls.append(dict(snapshot))
        snapshot["seen"] = True
        return True

    def fake_sleep(interval):
        sleeps.append(interval)
        raise KeyboardInterrupt

    monkeypatch.setattr(km, "proses_siklus", fake_proses_siklus)
    monkeypatch.setattr(km, "catat_log", lambda pesan: logs.append(pesan))
    monkeypatch.setattr(km.time, "sleep", fake_sleep)

    try:
        km.main()
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("main() should stop when sleep is interrupted")

    assert calls == [{}]
    assert sleeps == [30]
    assert logs == [
        "Program Kirim Manja aktif. Memulai polling Google Sheet.",
        "Perubahan terkirim. Interval polling kembali ke 30 detik.",
        "Program dihentikan oleh pengguna.",
    ]
