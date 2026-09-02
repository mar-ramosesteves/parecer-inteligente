import json
import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LEADERTRACK_SNAPSHOT_ADMIN_KEY", "snapshot-test-key")
import app as backend
from leadertrack_devolutivas import (
    build_diagnostic_prompt, build_weekly_prompt,
    individual_reference_reading, validate_diagnostic_reference,
)


class DiagnosticTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.client = backend.app.test_client()
        self.gap = {
            "questao": "Q22", "afirmacao": "Afirmacao de teste",
            "dimensao": "Nitidez", "subdimensao": "Obrigacoes e Deveres",
            "real_percentual": 69.44, "ideal_percentual": 94.44,
            "gap_percentual": 25,
        }
        self.payload = {
            "empresa": "teste", "codrodada": "r1", "emailLider": "lider@example.com",
            "gapId": backend.leadertrack_gap_id(self.gap), "etapa": "diagnostico", "usarCache": True, "gravarCache": True,
        }
        self.cache = self.mock("buscar_cache_leadertrack", return_value=None)
        self.save = self.mock("salvar_cache_leadertrack", return_value={"status": "salvo_no_historico_cache"})
        self.reports = self.mock("buscar_json_supabase", return_value={"test": True})
        self.mock("buscar_json_microambiente", return_value={"test": True})
        self.mock("archetype_summary", return_value={})
        self.mock("microenvironment_affirmations", return_value=[self.gap])
        self.mock("carregar_prompt_leadertrack", return_value="Prompt de teste")
        self.ai = self.mock("gerar_resposta_ia_leadertrack_enxuta")

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(backend, name, **kwargs))

    def post(self):
        return self.client.post("/gerar-pdi-leadertrack-afirmacao", json=self.payload)

    def test_diagnosis_gets_longer_single_attempt_and_preserves_payload(self):
        diagnostic = {"diagnostico_tecnico": {"sintese_executiva": "Diagnostico de teste"}}
        self.ai.return_value = json.dumps(diagnostic)
        response = self.post()
        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual(diagnostic, response.get_json()["diagnostico"])
        self.assertEqual(75, self.ai.call_args.kwargs["timeout"])
        self.assertEqual(0, self.ai.call_args.kwargs["max_retries"])
        self.save.assert_called_once()

    def test_timeout_returns_actionable_504_and_does_not_save(self):
        self.ai.side_effect = backend.APITimeoutError(request=MagicMock())
        response = self.post()
        self.assertEqual(504, response.status_code)
        self.assertIn("tempo de resposta", response.get_json()["erro"])
        self.assertEqual("https://gestor.thehrkey.tech", response.headers["Access-Control-Allow-Origin"])
        self.save.assert_not_called()

    def test_cache_hit_does_not_generate_or_reload_reports(self):
        self.cache.return_value = {"diagnostico": {"diagnostico_tecnico": {"sintese_executiva": "Salvo"}}}
        self.assertEqual(200, self.post().status_code)
        self.ai.assert_not_called()
        self.reports.assert_not_called()
        self.save.assert_not_called()

    def test_empty_diagnosis_is_not_saved_as_success(self):
        self.ai.return_value = "{}"
        self.assertEqual(500, self.post().status_code)
        self.save.assert_not_called()

    def test_incorrect_low_reference_is_rejected_without_saving(self):
        self.ai.return_value = json.dumps({"diagnostico_tecnico": {
            "sintese_executiva": "Ha um gap de clareza.",
            "hipoteses_provaveis": ["Baixa referencia do lider e da equipe por acomodacao."],
        }})
        response = self.post()
        self.assertEqual(500, response.status_code)
        self.assertIn("nao corresponde aos numeros", response.get_json()["erro"])
        self.save.assert_not_called()

    def test_old_diagnostic_cache_is_not_reused_and_both_lookups_use_same_version(self):
        old_key = backend.leadertrack_cache_key("teste", "r1", "lider@example.com", "direta", self.payload["gapId"], "diagnostico")
        self.cache.side_effect = lambda company, email, key: {"diagnostico": "antigo"} if key == old_key else None
        self.ai.return_value = json.dumps({"diagnostico_tecnico": {"sintese_executiva": "Orientar tarefas"}})
        self.assertEqual(200, self.post().status_code)
        keys = [call.args[2] for call in self.cache.call_args_list]
        self.assertEqual(2, len(keys))
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(old_key, keys[0])
        self.assertIn("diag_ref_v2_t70", keys[0])
        self.ai.assert_called_once()

    def test_cache_and_prompt_honor_selected_threshold(self):
        self.payload["baixaReferenciaThreshold"] = 65
        self.ai.return_value = json.dumps({"diagnostico_tecnico": {"sintese_executiva": "Orientar tarefas"}})
        self.assertEqual(200, self.post().status_code)
        self.assertIn("diag_ref_v2_t65", self.cache.call_args.args[2])
        self.assertIn('"limite_baixa_referencia": 65.0', self.ai.call_args.kwargs["pergunta"])

    def test_actual_low_reference_diagnosis_remains_supported(self):
        self.gap.update(real_percentual=58.33, ideal_percentual=66.67, gap_percentual=8.34)
        self.ai.return_value = json.dumps({"diagnostico_tecnico": {
            "sintese_executiva": "Baixa referencia a investigar, sem concluir desmotivacao."
        }})
        response = self.post()
        self.assertEqual(200, response.status_code, response.get_json())
        self.save.assert_called_once()


class DiagnosticClientTests(unittest.TestCase):
    def test_retry_override_is_local_not_global(self):
        with patch.object(backend, "openai_client") as client:
            backend.gerar_resposta_ia_leadertrack_enxuta("p", "s", timeout=75, max_retries=0)
            client.with_options.assert_called_once_with(max_retries=0)
            self.assertEqual(75, client.with_options.return_value.chat.completions.create.call_args.kwargs["timeout"])
            client.chat.completions.create.assert_not_called()

    def test_other_stages_keep_existing_defaults(self):
        with patch.object(backend, "openai_client") as client:
            backend.gerar_resposta_ia_leadertrack_enxuta("p", "s")
            client.with_options.assert_not_called()
            self.assertEqual(25, client.chat.completions.create.call_args.kwargs["timeout"])

    def test_prompt_is_concise_without_removing_low_reference_cautions(self):
        prompt = build_diagnostic_prompt({}, {}, {"real_percentual": 55, "ideal_percentual": 65}, []).lower()
        self.assertIn("no maximo dois itens por lista", prompt)
        self.assertIn("todos os campos", prompt)
        self.assertIn("nao e prova automatica de desmotivacao", prompt)
        self.assertIn("nao use saude emocional", prompt)


class DiagnosticReferenceTests(unittest.TestCase):
    def test_q22_has_high_ideal_even_if_stale_flag_says_otherwise(self):
        gap = {"real_percentual": 69.44, "ideal_percentual": 94.44, "baixa_referencia": True}
        prompt = build_diagnostic_prompt({}, {}, gap, [])
        self.assertIn('"baixa_referencia": false', prompt)
        self.assertIn("real=69.44% e ideal=94.44%", prompt)
        self.assertIn("Nao sugira elevar um ideal que ja e alto", prompt)
        self.assertNotIn("comece por compreender o significado do ideal", prompt)

    def test_both_scores_must_be_strictly_below_threshold(self):
        for real, ideal, expected in [(69, 69, True), (70, 69, False), (69, 70, False), (80, 50, False)]:
            with self.subTest(real=real, ideal=ideal):
                self.assertIs(expected, individual_reference_reading({"real_percentual": real, "ideal_percentual": ideal})["baixa_referencia"])

    def test_custom_threshold_and_unknown_data(self):
        self.assertFalse(individual_reference_reading({"real_percentual": 64, "ideal_percentual": 66}, 65)["baixa_referencia"])
        for gap in [{}, {"real_percentual": 50}, {"real_percentual": "NaN", "ideal_percentual": 60}, {"real_percentual": -1, "ideal_percentual": 50}]:
            self.assertIsNone(individual_reference_reading(gap)["baixa_referencia"])

    def test_guard_rejects_unsupported_terms_in_generated_prose(self):
        gap = {"real_percentual": 69.44, "ideal_percentual": 94.44}
        for text in ["Baixa refer\u00eancia", "acomoda\u00e7\u00e3o", "baixa ambi\u00e7\u00e3o", "descren\u00e7a na melhoria"]:
            with self.assertRaises(ValueError):
                validate_diagnostic_reference({"diagnostico_tecnico": {"hipoteses_provaveis": [text]}}, gap)
        validate_diagnostic_reference({"diagnostico_tecnico": {"sintese_executiva": "Orientacao insuficiente para atingir o padrao desejado."}}, gap)

    def test_weekly_prompt_prioritizes_numbers_over_old_diagnostic(self):
        prompt = build_weekly_prompt({}, {}, {"real_percentual": 69.44, "ideal_percentual": 94.44},
            {"diagnostico_tecnico": {"hipoteses_provaveis": ["Baixa referencia"]}}, 1, 1, [])
        self.assertIn('"baixa_referencia": false', prompt)
        self.assertIn("prevalece sobre rotulos, flags e textos de diagnosticos anteriores", prompt)


if __name__ == "__main__":
    unittest.main()
