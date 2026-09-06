import csv
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LeaderTrackHealthMatrixV2Test(unittest.TestCase):
    def test_health_matrix_v2_distribution(self):
        with (ROOT / "TABELA_SAUDE_EMOCIONAL.csv").open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f, delimiter=";"))

        self.assertEqual(len(rows), 97)
        self.assertEqual(
            Counter(
                str(row["DIMENSAO_SAUDE_EMOCIONAL"]).strip().replace(
                    "Equilíbrio Vida- Trabalho",
                    "Equilíbrio Vida-Trabalho",
                )
                for row in rows
            ),
            Counter({
                "Ambiente Psicológico Seguro": 22,
                "Prevenção de Estresse": 21,
                "Comunicação Positiva": 20,
                "Suporte Emocional": 18,
                "Equilíbrio Vida-Trabalho": 16,
            }),
        )


if __name__ == "__main__":
    unittest.main()
