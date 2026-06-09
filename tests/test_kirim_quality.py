from unittest import TestCase

import kirim_quality as kq


class KirimQualityTests(TestCase):
    def test_buat_pesan_distrik_adds_quality_title(self):
        text = kq.buat_pesan_distrik("PADANG", [{
            "incident": "INC123",
            "site_id": "PDG001",
            "progres": "On progress",
            "kendala": "Kabel",
            "support": "Tim",
            "plan": "Repair",
        }])

        self.assertTrue(text.startswith("*Tiket Quality Open*\nBranch Padang\n============\n"))
