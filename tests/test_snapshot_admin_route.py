import os
import importlib.util
import unittest
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LEADERTRACK_SNAPSHOT_ADMIN_KEY", "snapshot-test-key")

HAS_FLASK = importlib.util.find_spec("flask") is not None
if not HAS_FLASK:
    raise unittest.SkipTest("Flask nao esta instalado no runtime local de testes")
import app as backend


class SnapshotAdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = backend.app.test_client()

    def test_rejects_request_without_admin_key(self):
        response = self.client.post(
            "/gerar-snapshots-executivos-leadertrack",
            json={"codrodada": "r1", "persistir": False},
        )
        self.assertEqual(response.status_code, 403)

    def test_snapshot_read_rejects_request_without_admin_key(self):
        response = self.client.post(
            "/buscar-snapshot-executivo-leadertrack",
            json={"codrodada": "r1", "holding_id": "holding-a"},
        )
        self.assertEqual(response.status_code, 403)

    @patch.object(backend, "buscar_snapshots_contexto_rodada")
    def test_snapshot_read_returns_only_matching_holding(self, search):
        search.return_value = [
            {
                "id": 10,
                "codrodada": "r1",
                "versao_regras": "v1",
                "pacote_completo": {
                    "scope": {"tipo": "contexto", "holding_id": "holding-b"},
                    "health": {"score_final": 90},
                },
            },
            {
                "id": 11,
                "codrodada": "r1",
                "versao_regras": "v1",
                "pacote_completo": {
                    "scope": {"tipo": "contexto", "holding_id": "holding-a"},
                    "health": {
                        "score_final": 80,
                        "rastreio_afirmacoes": [{"codigo": "Q01"}],
                    },
                },
            },
        ]
        response = self.client.post(
            "/buscar-snapshot-executivo-leadertrack",
            headers={"X-HRKey-Snapshot-Key": "snapshot-test-key"},
            json={"codrodada": "r1", "holding_id": "holding-a"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["metadados"]["pacote_id"], 11)
        self.assertEqual(data["snapshot"]["health"]["score_final"], 80)
        self.assertNotIn("rastreio_afirmacoes", data["snapshot"]["health"])

    @patch.object(backend, "buscar_snapshots_contexto_rodada")
    def test_snapshot_read_returns_selected_company_instead_of_context(self, search):
        search.return_value = [{
            "id": 21,
            "codrodada": "r1",
            "empresa_codigo": "up",
            "versao_regras": "v2",
            "pacote_completo": {
                "scope": {"tipo": "empresa", "empresa": "up"},
                "health": {"score_final": 77},
            },
        }]
        response = self.client.post(
            "/buscar-snapshot-executivo-leadertrack",
            headers={"X-HRKey-Snapshot-Key": "snapshot-test-key"},
            json={"codrodada": "r1", "holding_id": "holding-a", "empresa": "UP"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["metadados"]["pacote_id"], 21)
        self.assertEqual(data["snapshot"]["scope"]["empresa"], "up")
        search.assert_called_once_with("r1", empresa="up")

    @patch.object(backend, "construir_snapshots_executivos_rodada")
    def test_dry_run_returns_all_discovered_companies(self, build):
        build.return_value = {
            "codrodada": "r1",
            "empresas_encontradas": ["empresa_a", "empresa_b"],
            "fontes": {"consolidados_arquetipos": 2, "consolidados_microambiente": 2},
            "snapshots": [
                {
                    "scope": {"tipo": "empresa", "empresa": "empresa_a"},
                    "status": "concluido",
                    "sample": {"respondentes_arquetipos": 5, "respondentes_microambiente": 5},
                    "health": {"score_final": 80.0},
                    "cuts": [],
                    "findings": [],
                    "source_hash": "hash-a",
                },
                {
                    "scope": {"tipo": "empresa", "empresa": "empresa_b"},
                    "status": "amostra_insuficiente",
                    "sample": {"respondentes_arquetipos": 2, "respondentes_microambiente": 2},
                    "health": None,
                    "cuts": [],
                    "findings": [],
                    "source_hash": "hash-b",
                },
            ],
        }
        response = self.client.post(
            "/gerar-snapshots-executivos-leadertrack",
            headers={"X-HRKey-Snapshot-Key": "snapshot-test-key"},
            json={"codrodada": "r1", "persistir": False},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "previsualizacao_sem_gravacao")
        self.assertEqual(data["quantidade_empresas"], 2)
        self.assertEqual(len(data["snapshots"]), 2)


if __name__ == "__main__":
    unittest.main()
