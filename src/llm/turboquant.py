"""TurboQuant_prod: 4-bit online vector quantization for inner product preservation.

Algorithm (TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate,
ICLR 2026, https://arxiv.org/abs/2504.19874):

Encoding key k (768-dim, L2-normalized):
  1. k̃ = R · k              random rotation (orthogonal R, seed 42)
  2. codes = Q₃(k̃)          3-bit Lloyd-Max scalar quantizer → uint8 codes 0-7
  3. ŷ = centroids[codes]   reconstruct float32 approximation
  4. r = k̃ - ŷ              quantisation residual
  5. z = sign(J · r)        1-bit QJL on residual (J: ±1/√768 matrix, seed 43)
  6. qjl_signs = packbits(z ≥ 0)   96 uint8 bytes

Estimating ⟨q, k⟩ given full-precision query q:
  q̃  = R · q
  ŷ  = centroids[codes]
  s1 = dot(q̃, ŷ)                     MSE component
  s2 = (π/2m) dot(J·q̃, unpack(z))   QJL correction (m=768)
  cosine ≈ s1 + s2

Storage per 768-dim vector: 768 bytes (uint8 codes) + 96 bytes (QJL) = 864 bytes
vs 3072 bytes raw float32 → 3.5× compression.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading

import math
import numpy as np

# ── Codebook constants ────────────────────────────────────────────────────────
# Optimal 3-bit Lloyd-Max quantizer for N(0, σ²), σ = 1/√768.
# Boundary and centroid values are the analytically known N(0,1) optima scaled by σ.
_SIGMA: float = 1.0 / math.sqrt(768)

_BOUNDARIES_NORM = np.array(
    [-1.748, -1.050, -0.501, 0.0, 0.501, 1.050, 1.748], dtype=np.float32
)
_CENTROIDS_NORM = np.array(
    [-2.152, -1.344, -0.756, -0.245, 0.245, 0.756, 1.344, 2.152], dtype=np.float32
)

BOUNDARIES: np.ndarray = (_BOUNDARIES_NORM * _SIGMA).astype(np.float32)  # shape (7,)
CENTROIDS: np.ndarray = (_CENTROIDS_NORM * _SIGMA).astype(np.float32)  # shape (8,)

_DIM = 768


# ── Data structure ────────────────────────────────────────────────────────────


@dataclass(eq=False)
class TurboQuantVector:
    """Compressed representation of one embedding vector.

    codes      — shape (768,) uint8, values 0-7 (3-bit Lloyd-Max code per dim)
    qjl_signs  — shape (96,)  uint8, 768 packed sign bits (1 bit QJL per dim)
    """

    codes: np.ndarray  # (768,) uint8
    qjl_signs: np.ndarray  # (96,)  uint8


# ── Codec ─────────────────────────────────────────────────────────────────────


class TurboQuantCodec:
    """TurboQuant_prod codec.  One instance shared across the process (see get_codec()).

    R and J matrices are generated lazily on first use — no startup cost.
    """

    def __init__(self) -> None:
        self._R: np.ndarray | None = None  # (768, 768) float32 — orthogonal rotation
        self._J: np.ndarray | None = None  # (768, 768) float32 — QJL ±1/√768 matrix
        self._init_lock = threading.Lock()

    # ── Lazy matrix init ──────────────────────────────────────────────────────

    def _rotation(self) -> np.ndarray:
        if self._R is None:
            with self._init_lock:
                if self._R is None:
                    rng = np.random.default_rng(42)
                    G = rng.standard_normal((_DIM, _DIM)).astype(np.float32)
                    Q, _ = np.linalg.qr(G)
                    self._R = Q.astype(np.float32)
        return self._R

    def _qjl(self) -> np.ndarray:
        if self._J is None:
            with self._init_lock:
                if self._J is None:
                    rng = np.random.default_rng(43)
                    signs = (
                        rng.integers(0, 2, size=(_DIM, _DIM), dtype=np.int8) * 2 - 1
                    ).astype(np.float32)
                    self._J = signs / math.sqrt(_DIM)
        return self._J

    # ── Public API ────────────────────────────────────────────────────────────

    def encode(self, vec: list[float]) -> TurboQuantVector:
        """Compress a 768-dim L2-normalised embedding into a TurboQuantVector."""
        k = np.array(vec, dtype=np.float32)
        k_tilde = self._rotation() @ k  # (768,) rotated
        codes: np.ndarray = np.digitize(k_tilde, BOUNDARIES).astype(
            np.uint8
        )  # (768,) 0-7
        y_hat = CENTROIDS[codes]  # (768,) decoded approximation
        r = k_tilde - y_hat  # (768,) quantisation residual
        proj = self._qjl() @ r  # (768,) QJL projections
        raw_bits = (proj >= 0).astype(np.uint8)  # 1 = positive, 0 = negative
        qjl_signs = np.packbits(raw_bits)  # (96,) packed
        return TurboQuantVector(codes=codes, qjl_signs=qjl_signs)

    def prepare_query(self, query: list[float]) -> np.ndarray:
        """Rotate a query vector once.  Pass result to score() for each cache entry.

        Separating rotation from scoring avoids recomputing R·q for every entry
        in a lookup loop (O(n·d²) → O(d²) + O(n·d)).
        """
        q = np.array(query, dtype=np.float32)
        return self._rotation() @ q  # (768,) float32

    def score(self, q_prepared: np.ndarray, compressed: TurboQuantVector) -> float:
        """Estimate cosine similarity given a pre-rotated query and a compressed key."""
        y_hat = CENTROIDS[compressed.codes]  # (768,)
        s1 = float(np.dot(q_prepared, y_hat))  # MSE component
        proj = self._qjl() @ q_prepared  # (768,) query projections
        z = np.unpackbits(compressed.qjl_signs).astype(np.float32) * 2 - 1  # (768,) ±1
        s2 = float((math.pi / (2.0 * _DIM)) * np.dot(proj, z))  # QJL correction
        return s1 + s2

    def cosine_similarity(
        self, query: list[float], compressed: TurboQuantVector
    ) -> float:
        """Convenience wrapper — rotates query then calls score().

        Use prepare_query() + score() in loops for better performance.
        """
        return self.score(self.prepare_query(query), compressed)


# ── Module singleton ──────────────────────────────────────────────────────────

_codec: TurboQuantCodec | None = None
_codec_lock = threading.Lock()


def get_codec() -> TurboQuantCodec:
    """Return the shared TurboQuantCodec instance (created on first call)."""
    global _codec
    if _codec is None:
        with _codec_lock:
            if _codec is None:
                _codec = TurboQuantCodec()
    return _codec
