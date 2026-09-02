import json
import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LEADERTRACK_SNAPSHOT_ADMIN_KEY", "snapshot-test-key")
import app as backend
from leadertrack_devolutivas import build_diagnostic_prompt


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
        prompt = build_diagnostic_prompt({}, {}, {}, []).lower()
        self.assertIn("no maximo dois itens por lista", prompt)
        self.assertIn("todos os campos", prompt)
        self.assertIn("nao e prova automatica de desmotivacao", prompt)
        self.assertIn("nao use saude emocional", prompt)


if __name__ == "__main__":
    unittest.main()
