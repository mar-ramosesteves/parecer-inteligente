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
                    "auto_media_dimensao": {"dados": [{
                        "DIMENSAO": "Nitidez", "REAL_%": 74, "IDEAL_%": 93, "GAP_%": 19,
                    }]},
                    "media_dimensao": {"dados": [{
                        "DIMENSAO": "Nitidez", "REAL_%": 76, "IDEAL_%": 90, "GAP_%": 14,
                    }]},
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
        micro = package["leadertrack"]["microambiente_dimensoes"]
        dimension = micro["dimensoes_com_comparacao_canonica"][0]
        self.assertEqual(dimension["equipe_como_deveria_ser"], 90)
        self.assertEqual(dimension["referencia_lideres_como_e"], 74)
        self.assertEqual(dimension["delta_equipe_menos_lideres_pp"], 2)
        self.assertEqual(dimension["relacao"], "equipe percebe acima da referencia dos lideres")
        archetype = package["leadertrack"]["arquetipos"]["estilos_com_comparacao_canonica"][0]
        self.assertEqual(archetype["delta_equipe_menos_lideres_pp"], -3)
        self.assertEqual(archetype["relacao"], "equipe percebe abaixo da referencia dos lideres")
        self.assertEqual(package["saude_emocional"]["base_calculo"], "somente respostas da equipe")

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

    def test_small_cut_delta_overclaim_is_replaced_by_canonical_note(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "leitura_por_recortes": [{
                "recorte": "sexo: feminino",
                "leitura": "O grupo tem saude superior e acima da media.",
                "implicacao_prudente": "Intervencao direcionada imediata.",
                "perguntas_de_investigacao": [
                    "Por que este grupo tem maior saude?",
                    "Quais condicoes organizacionais sao percebidas?",
                ],
            }],
        }
        normalized = normalize_executive_analysis(analysis, package)
        cut = normalized["leitura_por_recortes"][0]
        self.assertIn("abaixo do limiar de 5 p.p.", cut["leitura"])
        self.assertIn("Nao sustenta, isoladamente", cut["implicacao_prudente"])
        self.assertNotIn("maior saude", " ".join(cut["perguntas_de_investigacao"]).lower())

    def test_global_comparisons_and_process_only_kpis_are_sanitized(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "resumo_executivo": {"pontos_de_atencao": ["Comercial inferior ao consolidado."]},
            "acoes_organizacionais": [{
                "titulo": "Investigar gap elevado",
                "justificativa": "Gaps elevados no microambiente.",
                "kpis_sem_meta_inventada": ["Numero de entrevistas realizadas"],
            }] * 7,
        }
        normalized = normalize_executive_analysis(analysis, package)
        self.assertIn(
            "proximo ao consolidado",
            normalized["resumo_executivo"]["pontos_de_atencao"][0],
        )
        self.assertEqual(len(normalized["acoes_organizacionais"]), 5)
        self.assertNotIn(
            "Numero de entrevistas realizadas",
            normalized["acoes_organizacionais"][0]["kpis_sem_meta_inventada"],
        )
        self.assertIn(
            "gaps observados",
            normalized["acoes_organizacionais"][0]["justificativa"].lower(),
        )

    def test_demographic_action_is_removed_when_all_health_deltas_are_small(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "acoes_organizacionais": [{
                "titulo": "Intervencao por genero",
                "justificativa": "Atuar no recorte demografico.",
            }, {
                "titulo": "Investigar Nitidez",
                "justificativa": "Maior gap observado da equipe.",
            }],
        }
        normalized = normalize_executive_analysis(analysis, package)
        self.assertEqual(len(normalized["acoes_organizacionais"]), 1)
        self.assertEqual(normalized["acoes_organizacionais"][0]["titulo"], "Investigar Nitidez")

    def test_wrong_ai_archetype_predominance_is_replaced_by_canonical_ranking(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "resumo_executivo": {
                "sintese": "Os arquetipos predominantes sao Imperativo e Prescritivo.",
                "forcas": [],
            },
        }
        normalized = normalize_executive_analysis(analysis, package)
        synthesis = normalized["resumo_executivo"]["sintese"]
        self.assertNotIn("Imperativo e Prescritivo", synthesis)
        self.assertIn("Resoluto (64,0%)", synthesis)
        self.assertTrue(any("Resoluto (64,0%)" in item for item in normalized["findings"]))

    def test_summary_normalization_preserves_decimal_number(self):
        package = compact_snapshot_for_analysis(self.snapshot)
        analysis = {
            "resumo_executivo": {
                "sintese": "Saude emocional em 75.9. Os arquetipos predominantes sao incorretos.",
                "forcas": [],
            },
        }
        normalized = normalize_executive_analysis(analysis, package)
        synthesis = normalized["resumo_executivo"]["sintese"]
        self.assertIn("75.9", synthesis)
        self.assertNotIn("75. 9", synthesis)


if __name__ == "__main__":
    unittest.main()
