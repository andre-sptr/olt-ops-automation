import kirim_manja as km


def make_sheet_values():
    """Build a fake sheet with enough columns (up to AD = index 29) and rows."""
    values = [["" for _ in range(30)] for _ in range(9)]

    # MANJA3JAM: display_cols O(14), Q(16), P(15), R(17) — district_col R(17)
    # Row 5 (index 4): BATAM ticket
    values[4][14] = "INC-MANJA-BTM"       # O = Tiket
    values[4][16] = "2026-06-01 15:00"     # Q = Jam Booking
    values[4][15] = "SLU"                  # P = STO
    values[4][17] = "Batam"                # R = Distrik
    # Row 6 (index 5): BUKITTINGGI ticket
    values[5][14] = "INC-MANJA-BKT"
    values[5][16] = "2026-06-01 16:00"
    values[5][15] = "BKT"
    values[5][17] = "Bukit Tinggi"
    # Row 7 (index 6): Unknown district ticket
    values[6][14] = "INC-MANJA-UNK"
    values[6][16] = "2026-06-01 17:00"
    values[6][15] = "UNK"
    values[6][17] = "Riau"

    # PLATINUM6JAM: display_cols V(21), W(22), U(20), X(23) — district_col X(23)
    # Row 5 (index 4): DUMAI ticket
    values[4][21] = "INC-PLAT-DUM"         # V = Tiket
    values[4][22] = "6"                    # W = Jam Open
    values[4][20] = "DUM"                  # U = STO
    values[4][23] = "Dumai"                # X = Distrik

    # OPEN24JAM: display_cols AB(27), AA(26), AC(28), AD(29) — district_col AD(29)
    # Row 5 (index 4): PADANG ticket
    values[4][27] = "INC-OPEN-PDG"         # AB = Tiket
    values[4][26] = "PDG"                  # AA = STO
    values[4][28] = "72"                   # AC = Umur (Jam)
    values[4][29] = "Padang"               # AD = Distrik
    # Row 6 (index 5): Unknown district ticket
    values[5][27] = "INC-OPEN-OTHER"
    values[5][26] = "OTH"
    values[5][28] = "80"
    values[5][29] = "Other"

    return values


def test_kolom_ke_indeks_uses_zero_based_indices():
    assert km.kolom_ke_indeks("A") == 0
    assert km.kolom_ke_indeks("B") == 1
    assert km.kolom_ke_indeks("O") == 14
    assert km.kolom_ke_indeks("R") == 17
    assert km.kolom_ke_indeks("V") == 21
    assert km.kolom_ke_indeks("X") == 23
    assert km.kolom_ke_indeks("AA") == 26
    assert km.kolom_ke_indeks("AB") == 27
    assert km.kolom_ke_indeks("AD") == 29


def test_normalisasi_distrik_handles_target_variants():
    assert km.normalisasi_distrik(" Batam ") == "BATAM"
    assert km.normalisasi_distrik("Pekanbaru") == "PEKANBARU"
    assert km.normalisasi_distrik("Dumai") == "DUMAI"
    assert km.normalisasi_distrik("Bukit Tinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("BUKIT TINGGI") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Bukittinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Padang") == "PADANG"


def test_ekstrak_table_groups_known_districts_and_logs_unknown_rows():
    data = km.ekstrak_table(km.TABLE_CONFIGS["MANJA3JAM"], make_sheet_values())

    assert data.by_district["BATAM"] == [
        ["INC-MANJA-BTM", "2026-06-01 15:00", "SLU", "Batam"]
    ]
    assert data.by_district["BUKITTINGGI"] == [
        ["INC-MANJA-BKT", "2026-06-01 16:00", "BKT", "Bukit Tinggi"]
    ]
    assert data.by_district["PEKANBARU"] == []
    assert data.by_district["DUMAI"] == []
    assert data.by_district["PADANG"] == []
    assert data.skipped == [
        (7, "Riau", ["INC-MANJA-UNK", "2026-06-01 17:00", "UNK", "Riau"])
    ]


def test_open24jam_keeps_all_rows_for_inti_even_when_district_is_unknown():
    data = km.ekstrak_table(km.TABLE_CONFIGS["OPEN24JAM"], make_sheet_values())

    assert data.by_district["PADANG"] == [["INC-OPEN-PDG", "PDG", "72", "Padang"]]
    assert data.by_district["BATAM"] == []
    assert data.all_rows == [
        ["INC-OPEN-PDG", "PDG", "72", "Padang"],
        ["INC-OPEN-OTHER", "OTH", "80", "Other"],
    ]
    assert data.skipped == [
        (6, "Other", ["INC-OPEN-OTHER", "OTH", "80", "Other"])
    ]


def test_buat_pesan_data_uses_expected_manja3jam_format():
    text = km.buat_pesan_data(
        km.TABLE_CONFIGS["MANJA3JAM"],
        "Batam",
        [["INC49847623", "2026-06-01 15:00", "SLU", "Batam"]],
    )

    assert text == "\n".join([
        "Alarm TTR 3 Jam Manja | Batam",
        "==============",
        "Tiket | Jam Booking | STO | Distrik",
        "1. INC49847623 | 2026-06-01 15:00 | SLU | Batam",
    ])


def test_buat_pesan_data_numbers_multiple_rows():
    text = km.buat_pesan_data(
        km.TABLE_CONFIGS["OPEN24JAM"],
        "Padang",
        [
            ["INC-A", "PDG", "72", "Padang"],
            ["INC-B", "SLU", "80", "Padang"],
        ],
    )

    lines = text.splitlines()
    assert lines[0] == "Alarm Tiket Open > 24 Jam | Padang"
    assert lines[2] == "Tiket | STO | Umur (Jam) | Distrik"
    assert lines[3] == "1. INC-A | PDG | 72 | Padang"
    assert lines[4] == "2. INC-B | SLU | 80 | Padang"


def test_buat_pesan_clear_uses_expected_format():
    text = km.buat_pesan_clear(km.TABLE_CONFIGS["OPEN24JAM"], "")

    assert text == "\n".join([
        "Alarm Tiket Open > 24 Jam",
        "==============",
        "CLEAR - Tidak ada tiket aktif.",
    ])


def test_proses_target_sends_first_run_data_and_skips_unchanged_rows():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "2026-06-01 15:00", "SLU", "Batam"]]

    changed = km.proses_target(
        snapshot,
        ("MANJA3JAM", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["MANJA3JAM"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed is True
    assert len(sent) == 1
    assert sent[0][0] == "group-batam@g.us"
    assert sent[0][1].splitlines()[0] == "Alarm TTR 3 Jam Manja | Batam"

    changed_again = km.proses_target(
        snapshot,
        ("MANJA3JAM", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["MANJA3JAM"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed_again is False
    assert len(sent) == 1


def test_proses_target_returns_false_when_rows_empty():
    """Empty rows now return False immediately — no CLEAR message is sent."""
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "6", "DUM", "Dumai"]]

    km.proses_target(
        snapshot,
        ("PLATINUM6JAM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM6JAM"],
        "Dumai",
        rows,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("PLATINUM6JAM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM6JAM"],
        "Dumai",
        [],
        fake_send,
    )

    assert changed is False
    assert len(sent) == 1  # Only the first call sent a message


def test_proses_target_ignores_volatile_duration_change():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows_awal = [["INC-OPEN-PDG", "PDG", "72", "Padang"]]
    rows_jam_naik = [["INC-OPEN-PDG", "PDG", "80", "Padang"]]

    km.proses_target(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
        "",
        rows_awal,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
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
    rows_awal = [["INC-OPEN-PDG", "PDG", "72", "Padang"]]
    rows_tiket_baru = [
        ["INC-OPEN-PDG", "PDG", "73", "Padang"],
        ["INC-OPEN-NEW", "SLU", "10", "Padang"],
    ]

    km.proses_target(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
        "",
        rows_awal,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
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
    rows = [["INC49847623", "2026-06-01 15:00", "SLU", "Batam"]]

    changed = km.proses_target(
        snapshot,
        ("MANJA3JAM", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["MANJA3JAM"],
        "Batam",
        rows,
        failing_send,
    )

    assert changed is False
    assert snapshot == {}


def test_proses_siklus_routes_per_district_and_inti_for_all_configs(monkeypatch):
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

    # Expected messages:
    # MANJA3JAM: BATAM district, BUKITTINGGI district, inti = 3
    # PLATINUM6JAM: DUMAI district, inti = 2
    # OPEN24JAM: PADANG district, inti = 2
    # Total = 7 (empty districts are skipped because proses_target returns False)
    assert len(sent) == 7
    assert all("CLEAR" not in text for _, text in sent)

    # MANJA3JAM per-district
    assert any(
        chat_id == km.DISTRIK_GRUP["BATAM"]
        and text.startswith("Alarm TTR 3 Jam Manja | Batam")
        for chat_id, text in sent
    )
    assert any(
        chat_id == km.DISTRIK_GRUP["BUKITTINGGI"]
        and text.startswith("Alarm TTR 3 Jam Manja | Bukittinggi")
        for chat_id, text in sent
    )
    # MANJA3JAM inti
    assert any(
        chat_id == km.GRUP_INTI
        and text.startswith("Alarm TTR 3 Jam Manja | SBT\n")
        for chat_id, text in sent
    )

    # PLATINUM6JAM per-district
    assert any(
        chat_id == km.DISTRIK_GRUP["DUMAI"]
        and text.startswith("Alarm TTR 6 Jam P | Dumai")
        for chat_id, text in sent
    )
    # PLATINUM6JAM inti
    assert any(
        chat_id == km.GRUP_INTI
        and text.startswith("Alarm TTR 6 Jam P | SBT\n")
        for chat_id, text in sent
    )

    # OPEN24JAM per-district
    assert any(
        chat_id == km.DISTRIK_GRUP["PADANG"]
        and text.startswith("Alarm Tiket Open > 24 Jam | Padang")
        for chat_id, text in sent
    )
    # OPEN24JAM inti
    assert any(
        chat_id == km.GRUP_INTI
        and text.startswith("Alarm Tiket Open > 24 Jam | SBT\n")
        for chat_id, text in sent
    )

    # Skipped rows logged
    assert any("dilewati" in pesan for pesan in logs)

    # Second cycle — no changes → no new sends
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
        km.TABLE_CONFIGS["OPEN24JAM"], km.SUFFIX_INTI, rows_with_distrik
    )

    # Grouped by TARGET_DISTRIK order: Pekanbaru (row 1) before Dumai (row 2).
    # Running counter across blocks.
    assert teks == "\n".join([
        "Alarm Tiket Open > 24 Jam | SBT",
        "==============",
        "Tiket | STO | Umur (Jam) | Distrik",
        "1. INC2 | 90 | TAK | PEKAN BARU",
        "cc @6281261323575 @628126465895",
        "",
        "2. INC1 | 90 | TAK | DUMAI",
        "cc @6281275566031 @628126465895",
    ])
    # 628126465895 shared between two districts but appears once in mentions.
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
        km.TABLE_CONFIGS["OPEN24JAM"], km.SUFFIX_INTI, rows_with_distrik
    )

    # All DUMAI tickets grouped, then ONE cc line below.
    assert teks == "\n".join([
        "Alarm Tiket Open > 24 Jam | SBT",
        "==============",
        "Tiket | STO | Umur (Jam) | Distrik",
        "1. INC1 | 90 | TAK | DUMAI",
        "2. INC2 | 85 | TAK | DUMAI",
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
        km.TABLE_CONFIGS["OPEN24JAM"], km.SUFFIX_INTI, rows_with_distrik
    )

    # Two districts → two cc lines (one per block), not one per ticket.
    assert teks.count("cc @") == 2
    # Shared number appears in both blocks (2x in text) but once in mentions.
    assert teks.count("@628126465895") == 2
    assert mentions.count("628126465895@c.us") == 1


def test_buat_pesan_inti_unknown_district_has_no_cc():
    rows_with_distrik = [(["INC9", "OTH", "90", "Other"], "OTHER")]

    teks, mentions = km.buat_pesan_inti(
        km.TABLE_CONFIGS["OPEN24JAM"], km.SUFFIX_INTI, rows_with_distrik
    )

    assert mentions == []
    assert "cc " not in teks
    assert teks.endswith("1. INC9 | OTH | 90 | Other")


def test_proses_target_inti_ignores_jam_change_but_sends_mentions():
    captured = []

    def fake_send(chat_id, text, mentions=None):
        captured.append((chat_id, text, mentions))
        return True

    snapshot = {}
    rows_awal = [(["INC1", "PDG", "72", "PADANG"], "PADANG")]
    rows_jam_naik = [(["INC1", "PDG", "90", "PADANG"], "PADANG")]

    km.proses_target_inti(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
        km.SUFFIX_INTI,
        rows_awal,
        fake_send,
    )
    changed = km.proses_target_inti(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
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
    rows_awal = [(["INC1", "PDG", "72", "PADANG"], "PADANG")]
    rows_pindah = [(["INC1", "TAK", "72", "BATAM"], "BATAM")]

    km.proses_target_inti(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
        km.SUFFIX_INTI,
        rows_awal,
        fake_send,
    )
    changed = km.proses_target_inti(
        snapshot,
        ("OPEN24JAM", "__INTI__"),
        km.GRUP_INTI,
        km.TABLE_CONFIGS["OPEN24JAM"],
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
        "Program Kirim Manja2 aktif. Memulai polling Google Sheet.",
        "Perubahan terkirim. Interval polling kembali ke 30 detik.",
        "Program dihentikan oleh pengguna.",
    ]
