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
