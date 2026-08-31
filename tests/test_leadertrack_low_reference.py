import unittest

from leadertrack_devolutivas import (
    build_empty_devolutiva,
    build_weekly_prompt,
    integrated_attention_items,
    low_reference_prompt_rules,
    parse_json_response,
    repair_truncated_json,
    single_week_schema,
)


def item(question, real, ideal, gap=None):
    return {
        "questao": question,
        "afirmacao": f"Afirmacao {question}",
        "dimensao": "Performance",
        "subdimensao": "Qualidade Superior",
        "real_percentual": real,
        "ideal_percentual": ideal,
        "gap_percentual": ideal - real if gap is None else gap,
        "criticidade": "relevante",
    }


class IntegratedAttentionItemsTests(unittest.TestCase):
    def test_only_low_reference_items_become_attention_points(self):
        low_reference = [item(f"Q{i}", 55 + i, 60 + i) for i in range(1, 6)]
        points = integrated_attention_items([], low_reference)

        self.assertEqual(5, len(points))
        self.assertTrue(all(point["baixa_referencia"] for point in points))
        self.assertTrue(all(not point["gap_relevante"] for point in points))
        self.assertTrue(all(point["tipo_ponto_atencao"] == "baixa_referencia" for point in points))

    def test_overlap_is_counted_once_and_preserves_both_origins(self):
        gaps = [item("Q1", 40, 65, 25), item("Q2", 60, 85, 25)]
        low_reference = [
            item("Q1", 40, 65, 25),
            item("Q3", 55, 65, 10),
            item("Q4", 50, 60, 10),
            item("Q5", 58, 68, 10),
        ]

        points = integrated_attention_items(gaps, low_reference)
        shared = next(point for point in points if point["questao"] == "Q1")

        self.assertEqual(5, len(points))
        self.assertEqual(["gap_relevante", "baixa_referencia"], shared["origens_atencao"])
        self.assertEqual("gap_e_baixa_referencia", shared["tipo_ponto_atencao"])

    def test_empty_devolutiva_groups_low_reference_for_action_plan(self):
        low_reference = [item("Q1", 55, 65, 10), item("Q2", 60, 68, 8)]
        result = build_empty_devolutiva(
            empresa="ump",
            contexto="UMP",
            codrodada="avleven0726",
            email_lider="lider@example.com",
            nome_lider="Lider",
            gaps=[],
            arquetipos={},
            maximo_gaps_por_ciclo=4,
            todas_afirmacoes=low_reference,
            baixa_referencia=low_reference,
        )

        self.assertEqual("elevacao_de_referencia", result["modo_devolutiva"]["modo"])
        self.assertEqual(2, len(result["pontos_atencao_integrados"]))
        self.assertTrue(result["agrupamentos_tematicos"])
        self.assertEqual(2, result["agrupamentos_tematicos"][0]["total_baixa_referencia"])
        self.assertEqual(2, result["resumo_severidade"]["pontos_atencao_integrados"])

    def test_prompt_treats_low_reference_as_hypothesis(self):
        rules = low_reference_prompt_rules().lower()

        self.assertIn("nao e prova automatica de desmotivacao", rules)
        self.assertIn("hipotese", rules)
        self.assertIn("elevacao", rules)

    def test_consolidated_mode_does_not_add_low_reference_to_pdi(self):
        low_reference = [item("Q1", 55, 65, 10)]
        result = build_empty_devolutiva(
            empresa="ump",
            contexto="UMP",
            codrodada="avleven0726",
            email_lider="todos",
            nome_lider="Todos os lideres",
            gaps=[],
            arquetipos={},
            maximo_gaps_por_ciclo=4,
            todas_afirmacoes=low_reference,
            baixa_referencia=low_reference,
            integrar_baixa_referencia_no_pdi=False,
        )

        self.assertEqual("sustentacao_e_repertorio", result["modo_devolutiva"]["modo"])
        self.assertEqual([], result["pontos_atencao_integrados"])

    def test_single_week_prompt_limits_output_without_removing_depth(self):
        prompt = build_weekly_prompt(
            leader={"nome": "Lider"},
            arquetipos={},
            gap=item("Q1", 55, 65, 10),
            diagnostic={},
            start_week=1,
            end_week=1,
            indicadores_disponiveis=[],
        )

        self.assertIn("exatamente uma semana", prompt)
        self.assertIn("no maximo 2 itens por lista", prompt)
        self.assertIn("Priorize roteiro pratico, speech, evidencias", prompt)
        self.assertIn("terminar como JSON valido", prompt)

    def test_single_week_schema_keeps_execution_fields_without_redundancy(self):
        schema = single_week_schema(1)
        week = schema["plano_12_semanas"][0]

        self.assertEqual(1, week["semana"])
        self.assertIn("speech_sugerido_do_lider", week)
        self.assertIn("registro_do_lider_antes_de_avancar", week)
        self.assertIn("compromisso_de_agenda", week)
        self.assertIn("indicador", week)
        self.assertNotIn("gamificacao", week)
        self.assertNotIn("visao_geral_do_plano", schema)

    def test_parse_json_response_repairs_string_truncated_at_end(self):
        raw = '{"plano_12_semanas":[{"semana":4,"resultado_esperado":"Decisao registrada'

        parsed = parse_json_response(raw)

        self.assertEqual(4, parsed["plano_12_semanas"][0]["semana"])
        self.assertEqual("Decisao registrada", parsed["plano_12_semanas"][0]["resultado_esperado"])

    def test_repair_truncated_json_removes_trailing_comma(self):
        raw = '{"plano_12_semanas":[{"semana":4},'

        repaired = repair_truncated_json(raw)
        parsed = parse_json_response(repaired)

        self.assertEqual(4, parsed["plano_12_semanas"][0]["semana"])


if __name__ == "__main__":
    unittest.main()
