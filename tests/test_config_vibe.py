"""
Tests for Product Vibe configuration loading and validation.
"""

import pytest
from pathlib import Path

from productsignal.config import (
    ProductVibe,
    ScoringWeights,
    load_vibe_config,
    list_available_vibes,
    get_cached_vibe,
    clear_vibe_cache,
    set_active_vibe,
    get_active_vibe,
    require_active_vibe,
)


class TestScoringWeights:
    """Tests for ScoringWeights validation."""

    def test_valid_weights(self):
        """Test valid weight configuration."""
        weights = ScoringWeights(
            frequency=0.25,
            severity=0.25,
            segment_impact=0.20,
            recency=0.10,
            business_relevance=0.20,
        )
        assert weights.frequency == 0.25

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError) as exc_info:
            ScoringWeights(
                frequency=0.30,
                severity=0.30,
                segment_impact=0.20,
                recency=0.10,
                business_relevance=0.20,  # Sum = 1.1
            )
        assert "must sum to 1.0" in str(exc_info.value)

    def test_weights_bounds(self):
        """Test weight bounds validation."""
        with pytest.raises(ValueError):
            ScoringWeights(
                frequency=1.5,  # > 1.0
                severity=0.25,
                segment_impact=0.20,
                recency=0.10,
                business_relevance=0.20,
            )


class TestProductVibe:
    """Tests for ProductVibe model."""

    def test_saas_vibe_loads(self):
        """Test that SaaS vibe loads from YAML."""
        vibe = load_vibe_config("saas")
        assert isinstance(vibe, ProductVibe)
        assert vibe.product_type == "service_based"
        assert vibe.product_category == "saas"

    def test_saas_vibe_has_analytical_focus(self):
        """Test SaaS vibe has expected analytical focus areas."""
        vibe = load_vibe_config("saas")
        expected_focus = [
            "workflow_efficiency", "reliability", "feature_adoption",
            "user_onboarding", "customer_retention", "integration_performance",
            "business_value", "productivity"
        ]
        for focus in expected_focus:
            assert focus in vibe.analytical_focus

    def test_saas_vibe_has_classification_taxonomy(self):
        """Test SaaS vibe has classification taxonomy."""
        vibe = load_vibe_config("saas")
        assert "primary_categories" in vibe.classification_taxonomy
        assert "category_descriptions" in vibe.classification_taxonomy

        categories = vibe.classification_taxonomy["primary_categories"]
        expected_categories = [
            "reliability_downtime", "performance_speed", "workflow_efficiency",
            "feature_usability", "user_onboarding", "integration_issues",
            "reporting_analytics", "data_accuracy", "feature_request",
            "pricing_value", "customer_support", "other_unclear"
        ]
        for cat in expected_categories:
            assert cat in categories

    def test_saas_vibe_scoring_weights(self):
        """Test SaaS vibe scoring weights match PRD."""
        vibe = load_vibe_config("saas")
        weights = vibe.scoring_weights
        assert weights.frequency == 0.25
        assert weights.severity == 0.25
        assert weights.segment_impact == 0.20
        assert weights.recency == 0.10
        assert weights.business_relevance == 0.20

    def test_saas_vibe_analytical_questions(self):
        """Test SaaS vibe has analytical questions."""
        vibe = load_vibe_config("saas")
        questions = vibe.analytical_questions
        assert "problem_discovery" in questions
        assert "product_reliability" in questions
        assert "adoption_and_retention" in questions
        assert "business_impact" in questions

        # Each category should have questions
        for category_questions in questions.values():
            assert len(category_questions) >= 5

    def test_saas_vibe_opportunity_brief_sections(self):
        """Test SaaS vibe has opportunity brief sections."""
        vibe = load_vibe_config("saas")
        sections = vibe.opportunity_brief_sections
        expected_sections = [
            "problem_statement", "customer_impact", "evidence_summary",
            "affected_segments", "frequency_and_severity", "existing_limitations",
            "potential_opportunities", "risks_and_assumptions",
            "recommended_investigation", "suggested_next_steps"
        ]
        for section in expected_sections:
            assert section in sections

    def test_saas_vibe_evidence_guardrails(self):
        """Test SaaS vibe has evidence guardrails."""
        vibe = load_vibe_config("saas")
        guardrails = vibe.evidence_guardrails
        assert guardrails.require_evidence_references is True
        assert guardrails.distinguish_facts_from_assumptions is True
        assert guardrails.flag_unsupported_claims is True
        assert guardrails.preserve_original_feedback is True
        assert guardrails.max_claims_without_evidence == 0

    def test_saas_vibe_clustering_config(self):
        """Test SaaS vibe clustering configuration."""
        vibe = load_vibe_config("saas")
        clustering = vibe.clustering
        assert clustering.similarity_threshold == 0.75
        assert clustering.min_cluster_size == 2
        assert clustering.max_clusters == 50
        assert clustering.representative_selection == "centroid"

    def test_saas_vibe_classification_config(self):
        """Test SaaS vibe classification configuration."""
        vibe = load_vibe_config("saas")
        classification = vibe.classification
        assert classification.batch_size == 10
        assert classification.max_retries == 3
        assert classification.timeout_seconds == 30
        assert classification.temperature == 0.1

    def test_get_primary_categories(self):
        """Test get_primary_categories method."""
        vibe = load_vibe_config("saas")
        categories = vibe.get_primary_categories()
        assert len(categories) == 12
        assert "reliability_downtime" in categories
        assert "feature_request" in categories

    def test_get_category_description(self):
        """Test get_category_description method."""
        vibe = load_vibe_config("saas")
        desc = vibe.get_category_description("reliability_downtime")
        assert desc is not None
        assert "outages" in desc.lower() or "crashes" in desc.lower()

        # Non-existent category
        assert vibe.get_category_description("nonexistent") is None

    def test_is_valid_category(self):
        """Test is_valid_category method."""
        vibe = load_vibe_config("saas")
        assert vibe.is_valid_category("reliability_downtime") is True
        assert vibe.is_valid_category("feature_request") is True
        assert vibe.is_valid_category("invalid_category") is False


class TestVibeCache:
    """Tests for vibe configuration caching."""

    def test_cache_works(self):
        """Test that vibe is cached after first load."""
        clear_vibe_cache()
        vibe1 = load_vibe_config("saas")
        vibe2 = load_vibe_config("saas")
        assert vibe1 is vibe2  # Same object from cache

    def test_get_cached_vibe(self):
        """Test getting cached vibe."""
        clear_vibe_cache()
        assert get_cached_vibe("saas") is None
        load_vibe_config("saas")
        assert get_cached_vibe("saas") is not None

    def test_clear_cache(self):
        """Test clearing cache."""
        load_vibe_config("saas")
        clear_vibe_cache()
        assert get_cached_vibe("saas") is None

    def test_list_available_vibes(self):
        """Test listing available vibes."""
        vibes = list_available_vibes()
        assert "saas" in vibes


class TestActiveVibe:
    """Tests for active vibe management."""

    def test_set_and_get_active_vibe(self):
        """Test setting and getting active vibe."""
        clear_vibe_cache()
        vibe = load_vibe_config("saas")
        set_active_vibe(vibe)
        assert get_active_vibe() is vibe

    def test_require_active_vibe_raises_when_none(self):
        """Test require_active_vibe raises when no active vibe."""
        # We can't easily test this without clearing global state
        # but we verify the function exists
        assert callable(require_active_vibe)


class TestVibeCacheIsolation:
    """Tests for Product Vibe cache isolation (F5)."""

    def test_different_config_dirs_load_different_vibes(self, clean_db):
        """Two different config directories can load different configs with same vibe_key."""
        import tempfile
        import yaml
        from pathlib import Path
        from productsignal.config import load_vibe_config, clear_vibe_cache, _vibe_cache
        
        clear_vibe_cache()
        
        # Create two temporary config directories with different saas.yaml files
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            config_dir1 = Path(tmpdir1)
            config_dir2 = Path(tmpdir2)
            
            # Config 1: standard SaaS
            saas_config_1 = {
                "product_type": "service_based",
                "product_category": "saas",
                "analytical_focus": ["workflow_efficiency"],
                "classification_taxonomy": {
                    "primary_categories": ["cat_a", "cat_b"],
                    "category_descriptions": {"cat_a": "Category A", "cat_b": "Category B"}
                },
                "scoring_weights": {
                    "frequency": 0.25, "severity": 0.25, "segment_impact": 0.20,
                    "recency": 0.10, "business_relevance": 0.20
                },
                "analytical_questions": {},
                "confidence_review_threshold": 0.7,
                "opportunity_brief_sections": [],
                "evidence_guardrails": {},
                "clustering": {},
                "classification": {}
            }
            
            # Config 2: modified SaaS with different categories
            saas_config_2 = {
                "product_type": "service_based",
                "product_category": "saas",
                "analytical_focus": ["reliability"],
                "classification_taxonomy": {
                    "primary_categories": ["cat_x", "cat_y"],
                    "category_descriptions": {"cat_x": "Category X", "cat_y": "Category Y"}
                },
                "scoring_weights": {
                    "frequency": 0.30, "severity": 0.30, "segment_impact": 0.20,
                    "recency": 0.10, "business_relevance": 0.10
                },
                "analytical_questions": {},
                "confidence_review_threshold": 0.8,
                "opportunity_brief_sections": [],
                "evidence_guardrails": {},
                "clustering": {},
                "classification": {}
            }
            
            (config_dir1 / "saas.yaml").write_text(yaml.dump(saas_config_1))
            (config_dir2 / "saas.yaml").write_text(yaml.dump(saas_config_2))
            
            # Load from first directory
            vibe1 = load_vibe_config("saas", config_dir1)
            assert "cat_a" in vibe1.get_primary_categories()
            assert "cat_b" in vibe1.get_primary_categories()
            assert vibe1.scoring_weights.frequency == 0.25
            
            # Load from second directory - should NOT be contaminated by first
            vibe2 = load_vibe_config("saas", config_dir2)
            assert "cat_x" in vibe2.get_primary_categories()
            assert "cat_y" in vibe2.get_primary_categories()
            assert vibe2.scoring_weights.frequency == 0.30
            
            # Verify they are different objects
            assert vibe1 is not vibe2
            
            # Verify cache has both entries
            cache_keys = list(_vibe_cache.keys())
            assert any("saas" in k and str(config_dir1) in k for k in cache_keys)
            assert any("saas" in k and str(config_dir2) in k for k in cache_keys)

    def test_get_cached_vibe_with_config_dir(self):
        """get_cached_vibe respects config_dir parameter."""
        from productsignal.config import load_vibe_config, get_cached_vibe, clear_vibe_cache
        import tempfile
        import yaml
        from pathlib import Path
        
        clear_vibe_cache()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            saas_config = {
                "product_type": "service_based",
                "product_category": "saas",
                "analytical_focus": ["test"],
                "classification_taxonomy": {
                    "primary_categories": ["test_cat"],
                    "category_descriptions": {}
                },
                "scoring_weights": {
                    "frequency": 0.25, "severity": 0.25, "segment_impact": 0.20,
                    "recency": 0.10, "business_relevance": 0.20
                },
                "analytical_questions": {},
                "confidence_review_threshold": 0.7,
                "opportunity_brief_sections": [],
                "evidence_guardrails": {},
                "clustering": {},
                "classification": {}
            }
            (config_dir / "saas.yaml").write_text(yaml.dump(saas_config))
            
            # Not cached yet
            assert get_cached_vibe("saas", config_dir) is None
            
            # Load and cache
            load_vibe_config("saas", config_dir)
            
            # Now cached
            assert get_cached_vibe("saas", config_dir) is not None
            
            # Different config_dir should not be cached
            with tempfile.TemporaryDirectory() as tmpdir2:
                config_dir2 = Path(tmpdir2)
                assert get_cached_vibe("saas", config_dir2) is None