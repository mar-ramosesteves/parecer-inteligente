import unittest

from leadertrack_executive_analysis import (
    build_executive_analysis_prompt,
    compact_snapshot_for_analysis,
    normalize_executive_analysis,
)


class ExecutiveAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "scope": {"holding_id": "h1"},
            "sample": {"lideres": 11},
            "health": {"score_final": 75.9, "rastreio_afirmacoes": [{"codigo": "Q01"}]},
            "leadertrack": {
                "arquetipos": {"autoavaliacao": {"Resoluto": 67}, "mediaEquipe": {"Resoluto": 64}},
                "microambiente": {
                    "analitico": {"dados": [{"QUESTAO": "Q01"}]},
                    "auto_media_dimensao": {"dados": [{"DIMENSAO": "Nitidez", "REAL_%": 74}]},
                    "media_dimensao": {"dados": [{"DIMENSAO": "Nitidez", "REAL_%": 76}]},
                },
            },
            "cuts": [{
                "label": "sexo: feminino",
                "sample": {"respondentes_arquetipos": 11, "respondentes_microambiente": 12},
                "health": {"score_final": 79.1},
                "delta_health_pp": 3.2,
                "leadertrack": {},
            }],
        }

    def test_compact_package_excludes_question_level_analytics(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        serialized = str(package)
        self.assertNotIn("rastreio_afirmacoes", serialized)
        self.assertNotIn("QUESTAO", serialized)
        self.assertEqual(package["recortes_elegiveis"][0]["delta_saude_pp"], 3.2)

    def test_normalization_reapplies_canonical_cut_metrics(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "leitura_por_recortes": [{
                "recorte": "sexo: feminino",
                "score_saude_emocional": 12,
                "delta_saude_pp": 99,
                "leitura": "Sinal prudente.",
            }],
            "acoes_organizacionais": [{
                "titulo": "Auditar dados",
                "dono_recomendado": "Area inventada",
            }],
        }
        normalized = normalize_executive_analysis(analysis, package)
        cut = normalized["leitura_por_recortes"][0]
        self.assertEqual(cut["score_saude_emocional"], 79.1)
        self.assertEqual(cut["delta_saude_pp"], 3.2)
        self.assertEqual(normalized["acoes_organizacionais"][0]["dono_recomendado"], "RH")

    def test_prompt_protects_archetype_meaning_and_small_deltas(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        prompt = build_executive_analysis_prompt(package)
        self.assertIn("Arquetipos sao perfis de estilo", prompt)
        self.assertIn("Percentual baixo nao e deficiencia", prompt)
        self.assertIn("delta absoluto abaixo de 5 p.p.", prompt)
        self.assertIn("variacao exploratoria de menor intensidade", prompt)


if __name__ == "__main__":
    unittest.main()
