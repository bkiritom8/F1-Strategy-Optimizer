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
