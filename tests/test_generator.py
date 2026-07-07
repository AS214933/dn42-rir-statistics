from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dn42_rir_statistics.generator import generate_statistics, validate_output


class GeneratorTest(unittest.TestCase):
    def test_generate_lowercase_delegated_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry"
            output = root / "public"
            write_sample_registry(registry)

            result = generate_statistics(registry, output, "2026-01-02")

            self.assertEqual(result.generation_date, "20260102")
            self.assertEqual(result.record_counts["dn42"], 3)
            self.assertEqual(result.record_counts["apnic"], 1)

            dn42_file = output / "stats" / "dn42" / "delegated-dn42-20260102"
            latest_file = output / "stats" / "dn42" / "delegated-dn42-latest"
            self.assertTrue(dn42_file.is_file())
            self.assertTrue(latest_file.is_file())
            self.assertTrue(dn42_file.with_name("delegated-dn42-20260102.md5").is_file())
            self.assertEqual(dn42_file.read_text(), latest_file.read_text())

            content = dn42_file.read_text()
            self.assertEqual(content, content.lower())
            self.assertIn("2|dn42|20260102|3|20260102|20260102|+0000\n", content)
            self.assertIn("dn42|*|asn|*|1|summary\n", content)
            self.assertIn("dn42|*|ipv4|*|1|summary\n", content)
            self.assertIn("dn42|*|ipv6|*|1|summary\n", content)
            self.assertIn("dn42|zz|asn|4242420001|1|00000000|assigned\n", content)
            self.assertIn("dn42|de|ipv4|172.20.0.0|256|00000000|assigned\n", content)
            self.assertIn("dn42|us|ipv6|fd00::|48|00000000|assigned\n", content)

            apnic_file = output / "stats" / "apnic" / "delegated-apnic-20260102"
            self.assertIn("apnic|zz|asn|17830|1|00000000|assigned\n", apnic_file.read_text())

            validation = validate_output(output)
            self.assertTrue(validation.ok, validation.errors)
            self.assertEqual(validation.checked_files, 4)


def write_sample_registry(root: Path) -> None:
    (root / "data" / "registry").mkdir(parents=True)
    (root / "data" / "aut-num").mkdir()
    (root / "data" / "inetnum").mkdir()
    (root / "data" / "inet6num").mkdir()

    (root / "data" / "registry" / "DN42").write_text(
        "registry:           DN42\nsource:             DN42\n",
        encoding="utf-8",
    )
    (root / "data" / "registry" / "APNIC").write_text(
        "registry:           APNIC\nsource:             DN42\n",
        encoding="utf-8",
    )

    (root / "data" / "aut-num" / "AS4242420001").write_text(
        "aut-num:            AS4242420001\nsource:             DN42\n",
        encoding="utf-8",
    )
    (root / "data" / "aut-num" / "AS17830").write_text(
        "aut-num:            AS17830\nsource:             APNIC\n",
        encoding="utf-8",
    )
    (root / "data" / "inetnum" / "172.20.0.0_24").write_text(
        "\n".join(
            (
                "inetnum:            172.20.0.0 - 172.20.0.255",
                "country:            DE",
                "status:             ASSIGNED",
                "source:             DN42",
                "",
            )
        ),
        encoding="utf-8",
    )
    (root / "data" / "inet6num" / "fd00::_48").write_text(
        "\n".join(
            (
                "inet6num:           fd00:0000:0000:0000:0000:0000:0000:0000 - fd00:0000:0000:ffff:ffff:ffff:ffff:ffff",
                "cidr:               fd00::/48",
                "country:            US",
                "status:             ASSIGNED",
                "source:             DN42",
                "",
            )
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
