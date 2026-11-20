"""
Configuration management for ProductSignal.

Handles loading and validation of Product Vibe configurations from YAML.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
import yaml


def _get_project_root() -> Path:
    """
    Get the project root directory.

    Uses the location of this module to find the project root,
    independent of the current working directory.
    """
    # This file is at src/productsignal/config.py
    # Project root is 3 levels up
    return Path(__file__).resolve().parent.parent.parent


def _get_default_config_dir() -> Path:
    """Get the default vibes configuration directory."""
    return _get_project_root() / "config" / "vibes"


class ScoringWeights(BaseModel):
    """Opportunity scoring weights configuration."""

    frequency: float = Field(..., ge=0.0, le=1.0)
    severity: float = Field(..., ge=0.0, le=1.0)
    segment_impact: float = Field(..., ge=0.0, le=1.0)
    recency: float = Field(..., ge=0.0, le=1.0)
    business_relevance: float = Field(..., ge=0.0, le=1.0)

    @field_validator("frequency", "severity", "segment_impact", "recency", "business_relevance", mode="before")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Weights must be between 0.0 and 1.0")
        return v

    def model_post_init(self, __context: Any) -> None:
        total = self.frequency + self.severity + self.segment_impact + self.recency + self.business_relevance
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


class ClusteringConfig(BaseModel):
    """Clustering configuration."""

    similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    min_cluster_size: int = Field(default=2, ge=2)
    max_clusters: int = Field(default=50, ge=1)
    representative_selection: str = Field(default="centroid")


class ClassificationConfig(BaseModel):
    """Classification configuration."""

    batch_size: int = Field(default=10, ge=1)
    max_retries: int = Field(default=3, ge=0)
    timeout_seconds: int = Field(default=30, ge=1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class EvidenceGuardrails(BaseModel):
    """Evidence traceability guardrails."""

    require_evidence_references: bool = True
    distinguish_facts_from_assumptions: bool = True
    flag_unsupported_claims: bool = True
    preserve_original_feedback: bool = True
    max_claims_without_evidence: int = 0


class ProductVibe(BaseModel):
    """
    Product Vibe configuration model.

    Defines the analytical lens for a specific product type/category.
    Loaded from YAML configuration files.
    """

    product_type: str = Field(..., description="Product type: service_based or consumer_facing")
    product_category: str = Field(..., description="Product category: saas, fintech, mobile_app, etc.")

    analytical_focus: List[str] = Field(default_factory=list, description="Analytical focus areas")
    classification_taxonomy: Dict[str, Any] = Field(default_factory=dict, description="Classification categories and descriptions")
    scoring_weights: ScoringWeights = Field(..., description="Opportunity scoring weights")
    analytical_questions: Dict[str, List[str]] = Field(default_factory=dict, description="Analytical questions by category")
    confidence_review_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    opportunity_brief_sections: List[str] = Field(default_factory=list)
    evidence_guardrails: EvidenceGuardrails = Field(default_factory=EvidenceGuardrails)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        valid_types = {"service_based", "consumer_facing"}
        if v not in valid_types:
            raise ValueError(f"product_type must be one of {valid_types}")
        return v

    def get_primary_categories(self) -> List[str]:
        """Get list of valid primary classification categories."""
        return self.classification_taxonomy.get("primary_categories", [])

    def get_category_description(self, category: str) -> Optional[str]:
        """Get description for a classification category."""
        descriptions = self.classification_taxonomy.get("category_descriptions", {})
        return descriptions.get(category)

    def is_valid_category(self, category: str) -> bool:
        """Check if a category is valid for this vibe."""
        return category in self.get_primary_categories()


# Configuration cache
_vibe_cache: Dict[str, ProductVibe] = {}


def load_vibe_config(vibe_key: str, config_dir: Optional[Path] = None) -> ProductVibe:
    """
    Load a Product Vibe configuration from YAML.

    Args:
        vibe_key: The vibe identifier (e.g., "saas")
        config_dir: Optional custom config directory. Defaults to project_root/config/vibes/

    Returns:
        Validated ProductVibe instance

    Raises:
        FileNotFoundError: If vibe configuration file doesn't exist
        ValueError: If configuration validation fails
    """
    # Cache key includes resolved config_dir to support multiple config directories (F5)
    if config_dir is None:
        config_dir = _get_default_config_dir()
    else:
        config_dir = config_dir.resolve()
    
    cache_key = f"{vibe_key}:{config_dir}"
    if cache_key in _vibe_cache:
        return _vibe_cache[cache_key]

    config_path = config_dir / f"{vibe_key}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Vibe configuration not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    vibe = ProductVibe(**raw_config)
    _vibe_cache[cache_key] = vibe
    return vibe


def get_cached_vibe(vibe_key: str, config_dir: Optional[Path] = None) -> Optional[ProductVibe]:
    """Get a cached vibe configuration without loading from disk."""
    if config_dir is None:
        config_dir = _get_default_config_dir()
    else:
        config_dir = config_dir.resolve()
    cache_key = f"{vibe_key}:{config_dir}"
    return _vibe_cache.get(cache_key)


def clear_vibe_cache() -> None:
    """Clear the vibe configuration cache."""
    _vibe_cache.clear()


def list_available_vibes(config_dir: Optional[Path] = None) -> List[str]:
    """List available vibe configuration keys."""
    if config_dir is None:
        config_dir = _get_default_config_dir()

    if not config_dir.exists():
        return []

    return [f.stem for f in config_dir.glob("*.yaml")]


# Global active vibe (set during product context initialization)
_active_vibe: Optional[ProductVibe] = None


def set_active_vibe(vibe: ProductVibe) -> None:
    """Set the globally active vibe for the current session."""
    global _active_vibe
    _active_vibe = vibe


def get_active_vibe() -> Optional[ProductVibe]:
    """Get the currently active vibe."""
    return _active_vibe


def require_active_vibe() -> ProductVibe:
    """Get the active vibe or raise an error if not set."""
    if _active_vibe is None:
        raise RuntimeError("No active Product Vibe. Initialize product context first.")
    return _active_vibe