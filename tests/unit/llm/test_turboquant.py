"""Unit tests for TurboQuant_prod codec."""

import numpy as np
import pytest


def _random_unit_vec(dim: int = 768, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


def test_codec_singleton():
    from src.llm.turboquant import get_codec

    c1 = get_codec()
    c2 = get_codec()
    assert c1 is c2


def test_encode_returns_turboquantvector():
    from src.llm.turboquant import get_codec, TurboQuantVector

    codec = get_codec()
    vec = _random_unit_vec()
    result = codec.encode(vec)
    assert isinstance(result, TurboQuantVector)


def test_encode_shape():
    from src.llm.turboquant import get_codec

    codec = get_codec()
    vec = _random_unit_vec()
    enc = codec.encode(vec)
    assert enc.codes.shape == (768,)
    assert enc.codes.dtype == np.uint8
    assert enc.qjl_signs.shape == (96,)
    assert enc.qjl_signs.dtype == np.uint8


def test_encode_codes_in_range():
    """All code values must be 0-7 (3-bit alphabet)."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    vec = _random_unit_vec(seed=1)
    enc = codec.encode(vec)
    assert int(enc.codes.min()) >= 0
    assert int(enc.codes.max()) <= 7


def test_encode_qjl_length():
    """96 bytes = 768 packed bits (one QJL bit per dimension)."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    enc = codec.encode(_random_unit_vec(seed=2))
    assert len(enc.qjl_signs) == 96


def test_encode_deterministic():
    """Same input must always produce the same encoding."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    vec = _random_unit_vec(seed=3)
    enc1 = codec.encode(vec)
    enc2 = codec.encode(vec)
    np.testing.assert_array_equal(enc1.codes, enc2.codes)
    np.testing.assert_array_equal(enc1.qjl_signs, enc2.qjl_signs)


def test_cosine_identity():
    """Cosine similarity of a vector with its own encoding must be close to 1.0."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    vec = _random_unit_vec(seed=10)
    enc = codec.encode(vec)
    sim = codec.cosine_similarity(vec, enc)
    assert 0.85 <= sim <= 1.1, f"Expected ~1.0 but got {sim:.4f}"


def test_cosine_orthogonal():
    """Orthogonal unit vectors must score near 0."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    # Build two orthogonal 768-dim unit vectors via QR of a random matrix
    rng = np.random.default_rng(20)
    M = rng.standard_normal((768, 2)).astype(np.float32)
    Q, _ = np.linalg.qr(M)
    v1, v2 = Q[:, 0].tolist(), Q[:, 1].tolist()
    enc1 = codec.encode(v1)
    sim = codec.cosine_similarity(v2, enc1)
    assert abs(sim) < 0.2, f"Expected ~0.0 for orthogonal vectors but got {sim:.4f}"


def test_cosine_similar_beats_dissimilar():
    """A near-duplicate vector must score higher than a random unrelated vector."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    rng = np.random.default_rng(30)
    # v1: base unit vector
    v1 = rng.standard_normal(768).astype(np.float32)
    v1 /= np.linalg.norm(v1)
    # v2: v1 + tiny noise, renormalised (very similar to v1)
    noise = rng.standard_normal(768).astype(np.float32) * 0.05
    v2 = v1 + noise
    v2 /= np.linalg.norm(v2)
    # v3: completely random unit vector (dissimilar)
    v3 = rng.standard_normal(768).astype(np.float32)
    v3 /= np.linalg.norm(v3)

    enc1 = codec.encode(v1.tolist())
    sim_similar = codec.cosine_similarity(v2.tolist(), enc1)
    sim_dissimilar = codec.cosine_similarity(v3.tolist(), enc1)
    assert sim_similar > sim_dissimilar, (
        f"Similar pair scored {sim_similar:.4f}, dissimilar {sim_dissimilar:.4f}"
    )


def test_prepare_query_plus_score_matches_cosine_similarity():
    """prepare_query() + score() must return the same result as cosine_similarity()."""
    from src.llm.turboquant import get_codec

    codec = get_codec()
    vec = _random_unit_vec(seed=40)
    enc = codec.encode(vec)
    q_prep = codec.prepare_query(vec)
    assert abs(codec.score(q_prep, enc) - codec.cosine_similarity(vec, enc)) < 1e-5
