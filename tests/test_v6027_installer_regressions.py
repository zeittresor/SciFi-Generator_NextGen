from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V6027InstallerRegressionTests(unittest.TestCase):
    def test_verifier_expects_current_sentence_library(self):
        source = (ROOT / "tools" / "verify_installation.py").read_text(encoding="utf-8")
        self.assertIn("EXPECTED_SENTENCE_FILES = 232", source)
        self.assertNotIn("source_count != 218", source)
        self.assertNotIn("Unexpected sentence-file count for v60.26", source)

    def test_verifier_knows_all_continuity_fragments(self):
        source = (ROOT / "tools" / "verify_installation.py").read_text(encoding="utf-8")
        expected = {
            "continuity_signal_return.ini",
            "continuity_pursuit_return.ini",
            "continuity_anomaly_return.ini",
            "continuity_contact_return.ini",
            "continuity_rescue_return.ini",
            "continuity_ship_return.ini",
            "continuity_response_investigate.ini",
            "continuity_response_cautious.ini",
            "continuity_response_defer.ini",
            "continuity_outcome_resolved.ini",
            "continuity_outcome_deepens.ini",
            "continuity_outcome_false_lead.ini",
            "continuity_outcome_watchlist.ini",
            "continuity_outcome_deferred.ini",
        }
        for filename in expected:
            with self.subTest(filename=filename):
                self.assertIn(filename, source)
                self.assertTrue((ROOT / "data" / "vars" / filename).is_file())

    def test_winrt_cancel_stops_voice_enumeration_process(self):
        source = (ROOT / "tts_services.py").read_text(encoding="utf-8")
        self.assertIn("def _stop_voice_list_process(self)", source)
        cancel_section = source.split("    def cancel(self) -> None:", 1)[1].split("    def release_output", 1)[0]
        self.assertIn("self._stop_voice_list_process()", cancel_section)
        self.assertIn("process.waitForFinished(1000)", source)


if __name__ == "__main__":
    unittest.main()
