import unittest
import os
from unittest.mock import patch, Mock
from leadertrack_admission import (
    MICRO_FORM_KEYS, admission_enabled, answers, build_individual_reports, sample_fingerprint,
    select_sample, temporal_status, fetch_admission_rows,
)


def row(i, admitted="2020-01-01", responded="2026-07-20", kind="LIDER_2", module="microambiente"):
    return {"resposta_id": str(i), "email_respondente": f"{i}@example.test",
            "admission_date": admitted, "data_criacao": responded, "modulo": module,
            "tipo_relacao_lider": kind, "inicio_lider_2": "2026-07-01",
            "dados_json": {"Q01C": "3", "Q01k": "6", "Q10C": "4", "Q10k": "5"}}


class AdmissionTests(unittest.TestCase):
    def test_admission_query_uses_server_credential_not_legacy_key(self):
        response = Mock()
        response.json.return_value = [{**row(1), "holding": "LEVEN"}]
        get = Mock(return_value=response)
        with patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "test-server-only"}):
            fetch_admission_rows("https://test.invalid", {"apikey": "legacy"}, "umi", "avleven0726", "test", get=get)
        self.assertEqual("test-server-only", get.call_args.kwargs["headers"]["apikey"])
        self.assertEqual("Bearer test-server-only", get.call_args.kwargs["headers"]["Authorization"])

    def test_admission_query_fails_closed_without_server_credential(self):
        get = Mock()
        with patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "credencial de servidor"):
                fetch_admission_rows("https://test.invalid", {}, "umi", "avleven0726", "test", get=get)
        get.assert_not_called()

    def test_coordinated_activation_and_rollback(self):
        with patch.dict(os.environ, {'LEADERTRACK_ADMISSION_ROUNDS': ''}):
            self.assertFalse(admission_enabled('avleven0726'))
        with patch.dict(os.environ, {'LEADERTRACK_ADMISSION_ROUNDS': 'avleven0726'}):
            self.assertTrue(admission_enabled('avleven0726'))
            self.assertFalse(admission_enabled('av1225'))

    def test_old_admission_ignores_imported_link(self):
        self.assertEqual("eligible", temporal_status(row(1)))

    def test_exact_90_day_boundary(self):
        self.assertEqual("eligible", temporal_status(row(1, "2026-04-21")))
        self.assertEqual("recent", temporal_status(row(1, "2026-04-22")))

    def test_response_date_not_today_controls_eligibility(self):
        self.assertEqual("recent", temporal_status(row(1, "2026-05-04", "2026-07-30")))

    def test_unknown_invalid_or_future_dates_are_pending(self):
        for admitted, responded in [(None, "2026-07-20"), ("wrong", "2026-07-20"),
                                     ("2026-07-21", "2026-07-20"), ("2020-01-01", None)]:
            self.assertEqual("pending", temporal_status(row(1, admitted, responded)))

    def test_only_team_has_admission_cutoff_and_minimum(self):
        rows = [row(1), row(2), row(3, "2026-07-01"), row(4, None), row(5, kind="AUTOAVALIACAO")]
        eligible, auto, meta = select_sample(rows, "microambiente")
        self.assertEqual((2, 1), (len(eligible), len(auto)))
        self.assertEqual((4, 2, 1, 1, 0), tuple(meta[k] for k in
            ("respostas_equipe", "elegiveis_media", "menos_de_3_meses", "pendentes_admissao", "respostas_utilizadas")))
        self.assertTrue(meta["insuficiente"])

    def test_three_eligible_are_used(self):
        self.assertEqual(3, select_sample([row(i) for i in range(3)], "microambiente")[2]["respostas_utilizadas"])

    def test_first_response_is_kept_without_cherry_picking(self):
        rows = [row(1, "2026-05-01", "2026-08-20"), row(1, "2026-05-01", "2026-07-01")]
        self.assertEqual(0, len(select_sample(rows, "microambiente")[0]))

    def test_form_mapping_matches_individual_micro_api(self):
        self.assertEqual("Q10", MICRO_FORM_KEYS["Q02"])
        self.assertEqual("Q33", MICRO_FORM_KEYS["Q27"])
        self.assertEqual("Q09", MICRO_FORM_KEYS["Q48"])
        self.assertEqual(48, len(set(MICRO_FORM_KEYS.values())))
        self.assertEqual("4", answers(row(1), micro=True)["Q02C"])

    def test_no_team_data_reaches_calculator_below_minimum(self):
        calls = []
        def calculator(module, team, auto):
            calls.append((module, len(team), len(auto)))
            return {module: {"dados": []}}
        reports = build_individual_reports([row(1), row(2)], calculator)
        self.assertEqual(0, calls[1][1])
        self.assertEqual(2, reports["microambiente"]["amostra"]["elegiveis_media"])

    def test_fingerprint_invalidates_changed_admission_and_scores(self):
        self.assertNotEqual(sample_fingerprint([row(1)]), sample_fingerprint([row(1, "2026-07-01")]))
        changed = row(1)
        changed["dados_json"]["Q01C"] = "6"
        self.assertNotEqual(sample_fingerprint([row(1)]), sample_fingerprint([changed]))


if __name__ == "__main__":
    unittest.main()

