import unittest

from services.trend_radar.canonical import (
    AliasConflictError,
    EntityDefinition,
    build_alias_index,
    canonical_json,
    candidate_id_for,
    entity_for_coingecko,
    entity_for_wiki_article,
    find_entity_in_text,
    infer_category,
    normalize_name,
    sha256_text,
    slugify,
    stable_id,
)
from services.trend_radar.models import Category


class CanonicalTests(unittest.TestCase):
    def test_normalization_and_slug(self):
        self.assertEqual(normalize_name("  Artificial_intelligence  "), "artificial intelligence")
        self.assertEqual(slugify("Solana (blockchain platform)"), "solana-blockchain-platform")
        self.assertEqual(slugify("AI_agent"), "ai-agent")

    def test_stable_ids_and_canonical_json(self):
        self.assertEqual(stable_id("cand", "entity:bitcoin"), candidate_id_for("entity:bitcoin"))
        self.assertEqual(stable_id("x", "value"), stable_id("x", "value"))
        self.assertNotEqual(stable_id("x", "value"), stable_id("x", "other"))
        left = canonical_json({"b": 2, "a": 1})
        right = canonical_json({"a": 1, "b": 2})
        self.assertEqual(left, right)
        self.assertNotEqual(sha256_text(left), sha256_text(canonical_json({"a": 1, "b": 3})))

    def test_curated_aliases(self):
        self.assertEqual(find_entity_in_text("Bitcoin and BTC")[0], "bitcoin")
        self.assertEqual(find_entity_in_text("Bitcoin cryptocurrency")[0], "bitcoin")
        self.assertEqual(find_entity_in_text("OpenAI ChatGPT launch")[0], "chatgpt")
        self.assertEqual(find_entity_in_text("OpenAI valuation")[0], "openai")
        self.assertEqual(find_entity_in_text("ChatGPT / OpenAI ChatGPT")[0], "chatgpt")
        self.assertIsNone(find_entity_in_text("Apple event"))
        self.assertIsNone(find_entity_in_text("A generic technology story"))

    def test_wiki_and_coingecko_identity(self):
        self.assertEqual(entity_for_wiki_article("Artificial intelligence").key, "artificial_intelligence")
        self.assertEqual(entity_for_wiki_article("Artificial_intelligence").key, "artificial_intelligence")
        self.assertEqual(entity_for_coingecko("bitcoin", "BTC", "Bitcoin").key, "bitcoin")
        self.assertEqual(entity_for_coingecko("solana", "SOL", "Solana").key, "solana")
        self.assertIsNone(entity_for_coingecko("unknown-coin", "UNK", "Unknown Coin"))

    def test_alias_conflict_is_rejected(self):
        definitions = (
            EntityDefinition("a", Category.AI, "A", ("shared",)),
            EntityDefinition("b", Category.AI, "B", ("Shared",)),
        )
        with self.assertRaises(AliasConflictError):
            build_alias_index(definitions)

    def test_category_inference(self):
        self.assertEqual(infer_category("Bitcoin price rally"), Category.CRYPTO)
        self.assertEqual(infer_category("ChatGPT release notes"), Category.AI)
        self.assertEqual(infer_category("Nvidia earnings"), Category.AI)
        self.assertEqual(infer_category("A video game launch"), Category.GAMING)
        self.assertEqual(infer_category("Celebrity marriage"), Category.POP)
        self.assertEqual(infer_category("Election result"), Category.NEWS)
        self.assertEqual(infer_category("Tim Peters has died"), Category.NEWS)
        self.assertEqual(infer_category("An ordinary thing"), Category.OTHER)


if __name__ == "__main__":
    unittest.main()
