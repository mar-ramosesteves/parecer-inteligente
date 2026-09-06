import unittest

from leadertrack_executive_snapshots import (
    build_archetype_microenvironment_correlations,
    build_archetype_relative_signature,
    build_executive_microenvironment_gap_summary,
    build_scope_snapshot,
    group_source_rows_by_company,
    snapshot_for_frontend,
    snapshot_matches_context,
    source_hash,
)


def health_calculator(archetypes, microenvironment):
    n = len([row for row in microenvironment if row.get("tipo") == "equipe"])
    return {"score_final": float(70 + n), "dimensoes": {"teste": float(70 + n)}}


def summarizer(archetypes, microenvironment):
    return {
        "auto_lideres": len([row for row in archetypes if row.get("tipo") == "autoavaliacao"]),
        "auto_micro_lideres": len([row for row in microenvironment if row.get("tipo") == "autoavaliacao"]),
        "equipe": len([row for row in microenvironment if row.get("tipo") == "equipe"]),
    }


def rich_summarizer(archetypes, microenvironment):
    archetype_values = [row.get("arq") for row in archetypes if row.get("tipo") == "equipe"]
    micro_values = [row.get("micro") for row in microenvironment if row.get("tipo") == "equipe"]
    arq_mean = sum(archetype_values) / len(archetype_values) if archetype_values else None
    micro_mean = sum(micro_values) / len(micro_values) if micro_values else None
    return {
        "arquetipos": {
            "mediaEquipe": {
                "Resoluto": arq_mean,
                "Cuidativo": 100 - arq_mean if arq_mean is not None else None,
            } if arq_mean is not None else {},
        },
        "microambiente": {
            "media_dimensao": {
                "dados": [{
                    "DIMENSAO": "Nitidez",
                    "REAL_%": micro_mean,
                }]
            } if micro_mean is not None else {"dados": []},
        },
    }


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.archetypes = [
            {"tipo": "autoavaliacao", "email_lider": "lider1@example.com", "respostas": {"Q01": 5}},
            {"tipo": "autoavaliacao", "email_lider": "lider2@example.com", "respostas": {"Q01": 4}},
        ]
        self.microenvironment = [
            {"tipo": "autoavaliacao", "email_lider": "lider1@example.com", "respostas": {"Q01C": 5}},
            {"tipo": "autoavaliacao", "email_lider": "lider2@example.com", "respostas": {"Q01C": 4}},
        ]
        for index in range(6):
            demographic = {
                "sexo": "Mulher" if index < 5 else "Homem",
                "etnia": "Negra" if index < 3 else "Branca",
                "departamento": "Operações",
                "cargo": "Analista",
            }
            self.archetypes.append({
                "tipo": "equipe",
                "email_lider": "lider1@example.com",
                "respostas": {"Q01": 5},
                **demographic,
            })
            self.microenvironment.append({
                "tipo": "equipe",
                "email_lider": "lider1@example.com",
                "respostas": {"Q01C": 5, "Q01k": 6},
                **demographic,
            })

    def build(self, minimum_sample=5, include_cuts=True, max_cuts=40):
        return build_scope_snapshot(
            scope={"tipo": "empresa", "empresa": "empresa_a", "codrodada": "r1"},
            archetype_records=self.archetypes,
            microenvironment_records=self.microenvironment,
            archetype_rows=[{"id": 1, "empresa": "empresa_a"}],
            microenvironment_rows=[{"id": 2, "empresa": "empresa_a"}],
            health_calculator=health_calculator,
            leadertrack_summarizer=summarizer,
            minimum_sample=minimum_sample,
            include_cuts=include_cuts,
            max_cuts=max_cuts,
        )

    def test_discovers_companies_dynamically(self):
        grouped = group_source_rows_by_company([
            {"empresa": "Empresa_A"},
            {"empresa": "empresa_b"},
            {"empresa": "EMPRESA_A"},
        ])
        self.assertEqual(sorted(grouped), ["empresa_a", "empresa_b"])
        self.assertEqual(len(grouped["empresa_a"]), 2)

    def test_cut_filters_team_and_keeps_all_leaders(self):
        snapshot = self.build()
        women = next(item for item in snapshot["cuts"] if item["filters"] == {"sexo": "Mulher"})
        self.assertEqual(women["sample"]["respondentes_microambiente"], 5)
        self.assertEqual(women["sample"]["autoavaliacoes_arquetipos"], 2)
        self.assertEqual(women["leadertrack"]["auto_lideres"], 2)
        self.assertEqual(women["leadertrack"]["auto_micro_lideres"], 2)

    def test_suppresses_cut_below_minimum_sample(self):
        snapshot = self.build()
        black_women = [
            item for item in snapshot["cuts"]
            if item["filters"] == {"sexo": "Mulher", "etnia": "Negra"}
        ]
        self.assertEqual(black_women, [])

    def test_company_below_minimum_has_no_metrics(self):
        snapshot = self.build(minimum_sample=7)
        self.assertEqual(snapshot["status"], "amostra_insuficiente")
        self.assertIsNone(snapshot["health"])
        self.assertIsNone(snapshot["leadertrack"])
        self.assertEqual(snapshot["cuts"], [])

    def test_company_general_snapshot_does_not_store_cuts(self):
        snapshot = self.build(include_cuts=False)
        self.assertEqual(snapshot["status"], "concluido")
        self.assertIsNotNone(snapshot["health"])
        self.assertEqual(snapshot["cuts"], [])

    def test_context_snapshot_limits_number_of_cuts(self):
        snapshot = self.build(max_cuts=2)
        self.assertLessEqual(len(snapshot["cuts"]), 2)

    def test_source_hash_is_order_independent_for_json_keys(self):
        first = source_hash([{"id": 1, "dados_json": {"b": 2, "a": 1}}], [])
        second = source_hash([{"dados_json": {"a": 1, "b": 2}, "id": 1}], [])
        self.assertEqual(first, second)

    def test_snapshot_context_requires_matching_holding(self):
        snapshot = {"scope": {"tipo": "contexto", "holding_id": "holding-a"}}
        self.assertTrue(snapshot_matches_context(snapshot, {"holding_id": "holding-a"}))
        self.assertFalse(snapshot_matches_context(snapshot, {"holding_id": "holding-b"}))

    def test_frontend_snapshot_removes_internal_health_trace(self):
        snapshot = {
            "source_hash": "internal",
            "health": {"score_final": 80, "rastreio_afirmacoes": [{"codigo": "Q01"}]},
            "cuts": [{
                "label": "sexo: Mulher",
                "health": {"score_final": 78, "rastreio_afirmacoes": [{"codigo": "Q02"}]},
            }],
        }
        public = snapshot_for_frontend(snapshot)
        self.assertNotIn("source_hash", public)
        self.assertNotIn("rastreio_afirmacoes", public["health"])
        self.assertNotIn("rastreio_afirmacoes", public["cuts"][0]["health"])
        self.assertIn("rastreio_afirmacoes", snapshot["health"])

    def test_executive_gap_summary_uses_10_20_35_bands(self):
        leadertrack = {
            "microambiente": {
                "analitico": {
                    "dados": [
                        {"QUESTAO": "Q01", "DIMENSAO": "Nitidez", "GAP": 9.9},
                        {"QUESTAO": "Q02", "DIMENSAO": "Nitidez", "GAP": 10},
                        {"QUESTAO": "Q03", "DIMENSAO": "Performance", "GAP": 20},
                        {"QUESTAO": "Q04", "DIMENSAO": "Reconhecimento", "GAP": 35},
                    ]
                }
            }
        }
        summary = build_executive_microenvironment_gap_summary(leadertrack)
        self.assertEqual(summary["total_afirmacoes"], 4)
        self.assertEqual(summary["quantidades"]["acima_10"], 3)
        self.assertEqual(summary["quantidades"]["acima_20"], 2)
        self.assertEqual(summary["quantidades"]["acima_35"], 1)
        self.assertEqual(summary["principais_sinais"][0]["faixa"], "critico")
        self.assertEqual(summary["principais_sinais"][-1]["faixa"], "monitoramento")

    def test_archetype_relative_signature_uses_context_as_base_100(self):
        leadertrack = {
            "arquetipos": {
                "mediaEquipe": {"Resoluto": 60, "Cuidativo": 40}
            }
        }
        leaders = [
            {"arquetipos": {"Resoluto": 72, "Cuidativo": 36}},
            {"arquetipos": {"Resoluto": 48, "Cuidativo": 44}},
        ]
        signature = build_archetype_relative_signature(leadertrack, leaders)
        self.assertEqual(signature["escala_fixa"]["base"], 100.0)
        resoluto = next(item for item in signature["arquetipos"] if item["arquetipo"] == "Resoluto")
        self.assertEqual(resoluto["indice_relativo_medio"], 100.0)
        self.assertEqual(resoluto["lideres_acima_da_media"], 1)

    def test_archetype_microenvironment_correlations_need_minimum_sample(self):
        small = [
            {
                "arquetipos": {"Resoluto": value},
                "microambiente_dimensoes": {"Nitidez": value},
            }
            for value in range(9)
        ]
        self.assertEqual(
            build_archetype_microenvironment_correlations(small)["correlacoes"],
            [],
        )

        enough = [
            {
                "arquetipos": {"Resoluto": value},
                "microambiente_dimensoes": {"Nitidez": value},
            }
            for value in range(10)
        ]
        correlations = build_archetype_microenvironment_correlations(enough)["correlacoes"]
        self.assertEqual(correlations[0]["arquetipo"], "Resoluto")
        self.assertEqual(correlations[0]["dimensao_microambiente"], "Nitidez")
        self.assertEqual(correlations[0]["r"], 1.0)

    def test_scope_snapshot_includes_parallel_executive_layers(self):
        archetypes = []
        microenvironment = []
        for index in range(10):
            archetypes.append({
                "tipo": "equipe",
                "email_lider": f"lider{index}@example.com",
                "arq": 40 + index,
            })
            microenvironment.append({
                "tipo": "equipe",
                "email_lider": f"lider{index}@example.com",
                "micro": 40 + index,
            })
        snapshot = build_scope_snapshot(
            scope={"tipo": "empresa", "empresa": "empresa_a", "codrodada": "r1"},
            archetype_records=archetypes,
            microenvironment_records=microenvironment,
            archetype_rows=[{"id": 1, "empresa": "empresa_a"}],
            microenvironment_rows=[{"id": 2, "empresa": "empresa_a"}],
            health_calculator=health_calculator,
            leadertrack_summarizer=rich_summarizer,
            minimum_sample=5,
            include_cuts=False,
        )
        self.assertEqual(snapshot["archetype_relative_signature"]["escala_fixa"]["base"], 100.0)
        resoluto = next(
            item for item in snapshot["archetype_microenvironment_correlations"]["correlacoes"]
            if item["arquetipo"] == "Resoluto"
        )
        self.assertEqual(resoluto["r"], 1.0)


if __name__ == "__main__":
    unittest.main()
