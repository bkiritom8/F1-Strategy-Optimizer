# TurboQuant_prod Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw float32 embeddings in the LLM cache with 4-bit TurboQuant_prod compressed vectors, reducing per-entry storage 3.5× and preserving cosine similarity accuracy.

**Architecture:** New `src/llm/turboquant.py` implements the TurboQuant_prod codec (random rotation → 3-bit Lloyd-Max quantization + 1-bit QJL on residual). `src/llm/cache.py` is modified to store `TurboQuantVector` objects instead of `list[float]` and use the codec for similarity scoring. Public cache interfaces are unchanged.

**Tech Stack:** NumPy (already in requirements), Python 3.12, pytest.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/llm/turboquant.py` | Create | TurboQuantVector dataclass, TurboQuantCodec, module singleton |
| `src/llm/cache.py` | Modify | Replace list[float] embeddings with TurboQuantVector; use codec for similarity |
| `tests/unit/llm/test_turboquant.py` | Create | Unit tests for codec correctness |

---

## Task 1: Create `turboquant.py` skeleton — dataclass, constants, singleton

**Files:**
- Create: `src/llm/turboquant.py`
- Create: `tests/unit/llm/test_turboquant.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/llm/test_turboquant.py`:

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/bhargav/Documents/F1-Strategy-Optimizer
python -m pytest tests/unit/llm/test_turboquant.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'src.llm.turboquant'`

- [ ] **Step 3: Create `src/llm/turboquant.py`**

```python
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

import math
import numpy as np

# ── Codebook constants ────────────────────────────────────────────────────────
# Optimal 3-bit Lloyd-Max quantizer for N(0, σ²), σ = 1/√768.
# Boundary and centroid values are the analytically known N(0,1) optima scaled by σ.
_SIGMA: float = 1.0 / math.sqrt(768)

_BOUNDARIES_NORM = np.array([-1.748, -1.050, -0.501, 0.0, 0.501, 1.050, 1.748], dtype=np.float32)
_CENTROIDS_NORM  = np.array([-2.152, -1.344, -0.756, -0.245, 0.245, 0.756, 1.344, 2.152], dtype=np.float32)

BOUNDARIES: np.ndarray = (_BOUNDARIES_NORM * _SIGMA).astype(np.float32)  # shape (7,)
CENTROIDS:  np.ndarray = (_CENTROIDS_NORM  * _SIGMA).astype(np.float32)  # shape (8,)

_DIM = 768


# ── Data structure ────────────────────────────────────────────────────────────


@dataclass
class TurboQuantVector:
    """Compressed representation of one embedding vector.

    codes      — shape (768,) uint8, values 0-7 (3-bit Lloyd-Max code per dim)
    qjl_signs  — shape (96,)  uint8, 768 packed sign bits (1 bit QJL per dim)
    """

    codes: np.ndarray      # (768,) uint8
    qjl_signs: np.ndarray  # (96,)  uint8


# ── Codec ─────────────────────────────────────────────────────────────────────


class TurboQuantCodec:
    """TurboQuant_prod codec.  One instance shared across the process (see get_codec()).

    R and J matrices are generated lazily on first use — no startup cost.
    """

    def __init__(self) -> None:
        self._R: np.ndarray | None = None   # (768, 768) float32 — orthogonal rotation
        self._J: np.ndarray | None = None   # (768, 768) float32 — QJL ±1/√768 matrix

    # ── Lazy matrix init ──────────────────────────────────────────────────────

    def _rotation(self) -> np.ndarray:
        if self._R is None:
            rng = np.random.default_rng(42)
            G = rng.standard_normal((_DIM, _DIM)).astype(np.float32)
            Q, _ = np.linalg.qr(G)
            self._R = Q.astype(np.float32)
        return self._R

    def _qjl(self) -> np.ndarray:
        if self._J is None:
            rng = np.random.default_rng(43)
            signs = (rng.integers(0, 2, size=(_DIM, _DIM), dtype=np.int8) * 2 - 1).astype(np.float32)
            self._J = signs / math.sqrt(_DIM)
        return self._J

    # ── Public API ────────────────────────────────────────────────────────────

    def encode(self, vec: list[float]) -> TurboQuantVector:
        """Compress a 768-dim L2-normalised embedding into a TurboQuantVector."""
        k = np.array(vec, dtype=np.float32)
        k_tilde = self._rotation() @ k                      # (768,) rotated
        codes = np.digitize(k_tilde, BOUNDARIES).astype(np.uint8)  # (768,) 0-7
        y_hat = CENTROIDS[codes]                            # (768,) decoded approximation
        r = k_tilde - y_hat                                 # (768,) quantisation residual
        proj = self._qjl() @ r                              # (768,) QJL projections
        raw_bits = (proj >= 0).astype(np.uint8)             # 1 = positive, 0 = negative
        qjl_signs = np.packbits(raw_bits)                   # (96,) packed
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
        y_hat = CENTROIDS[compressed.codes]                     # (768,)
        s1 = float(np.dot(q_prepared, y_hat))                   # MSE component
        proj = self._qjl() @ q_prepared                         # (768,) query projections
        z = np.unpackbits(compressed.qjl_signs).astype(np.float32) * 2 - 1  # (768,) ±1
        s2 = float((math.pi / (2.0 * _DIM)) * np.dot(proj, z)) # QJL correction
        return s1 + s2

    def cosine_similarity(self, query: list[float], compressed: TurboQuantVector) -> float:
        """Convenience wrapper — rotates query then calls score().

        Use prepare_query() + score() in loops for better performance.
        """
        return self.score(self.prepare_query(query), compressed)


# ── Module singleton ──────────────────────────────────────────────────────────

_codec: TurboQuantCodec | None = None


def get_codec() -> TurboQuantCodec:
    """Return the shared TurboQuantCodec instance (created on first call)."""
    global _codec
    if _codec is None:
        _codec = TurboQuantCodec()
    return _codec
```

- [ ] **Step 4: Run the tests — all three must pass**

```bash
python -m pytest tests/unit/llm/test_turboquant.py -v
```

Expected:
```
PASSED tests/unit/llm/test_turboquant.py::test_codec_singleton
PASSED tests/unit/llm/test_turboquant.py::test_encode_returns_turboquantvector
PASSED tests/unit/llm/test_turboquant.py::test_encode_shape
```

- [ ] **Step 5: Commit**

```bash
git add src/llm/turboquant.py tests/unit/llm/test_turboquant.py
git commit -m "feat: add TurboQuantCodec skeleton — dataclass, codebook constants, singleton"
```

---

## Task 2: Validate encode() correctness

**Files:**
- Modify: `tests/unit/llm/test_turboquant.py`

- [ ] **Step 1: Add correctness tests to the test file**

Append to `tests/unit/llm/test_turboquant.py`:

```python
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
```

- [ ] **Step 2: Run new tests — expect PASS (encode is already implemented)**

```bash
python -m pytest tests/unit/llm/test_turboquant.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/llm/test_turboquant.py
git commit -m "test: add encode correctness tests for TurboQuantCodec"
```

---

## Task 3: Validate cosine_similarity() accuracy

**Files:**
- Modify: `tests/unit/llm/test_turboquant.py`

- [ ] **Step 1: Add similarity tests to the test file**

Append to `tests/unit/llm/test_turboquant.py`:

```python
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
```

- [ ] **Step 2: Run new tests — expect PASS**

```bash
python -m pytest tests/unit/llm/test_turboquant.py -v
```

Expected: all 10 tests PASS.

If `test_cosine_identity` fails with sim < 0.85, the centroids scaling is wrong — check that `_SIGMA = 1/sqrt(768)` and that `CENTROIDS = _CENTROIDS_NORM * _SIGMA`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/llm/test_turboquant.py
git commit -m "test: add cosine similarity accuracy tests for TurboQuantCodec"
```

---

## Task 4: Wire TurboQuantCodec into `src/llm/cache.py`

**Files:**
- Modify: `src/llm/cache.py`

- [ ] **Step 1: Add the import at the top of `src/llm/cache.py`**

In `src/llm/cache.py`, after the existing imports block (after `import vertexai`), add:

```python
from src.llm.turboquant import TurboQuantVector, get_codec
```

- [ ] **Step 2: Delete `_cosine()` and update `_GenericEntry`**

Remove the entire `_cosine()` function (lines 64–70 in the current file):

```python
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
```

Change `_GenericEntry.embedding` type annotation:

```python
# Before
@dataclass
class _GenericEntry:
    question: str
    embedding: list[float]
    answer: str

# After
@dataclass
class _GenericEntry:
    question: str
    embedding: TurboQuantVector
    answer: str
```

Also remove `import math` from the top of `cache.py` — it was only used by `_cosine()`. Verify no other usage of `math` exists in the file before removing it.

- [ ] **Step 3: Update `_RealtimeEntry`**

```python
# Before
@dataclass
class _RealtimeEntry:
    embedding: list[float]
    state_hash: str
    answer: str
    model_predictions: dict
    created_at: float = field(default_factory=time.time)

# After
@dataclass
class _RealtimeEntry:
    embedding: TurboQuantVector
    state_hash: str
    answer: str
    model_predictions: dict
    created_at: float = field(default_factory=time.time)
```

- [ ] **Step 4: Update `GenericCache.warm()`**

Find the line inside `_run()` that creates `_GenericEntry`:

```python
# Before
entries.append(
    _GenericEntry(question=q, embedding=emb, answer=answer)
)
```

Replace with:

```python
# After
entries.append(
    _GenericEntry(question=q, embedding=get_codec().encode(emb), answer=answer)
)
```

- [ ] **Step 5: Update `GenericCache.lookup()`**

Replace the similarity loop in `lookup()`:

```python
# Before
with self._lock:
    best_score, best_answer = 0.0, None
    for entry in self._entries:
        score = _cosine(q_emb, entry.embedding)
        if score > best_score:
            best_score, best_answer = score, entry.answer
```

```python
# After
codec = get_codec()
q_prepared = codec.prepare_query(q_emb)
with self._lock:
    best_score, best_answer = 0.0, None
    for entry in self._entries:
        score = codec.score(q_prepared, entry.embedding)
        if score > best_score:
            best_score, best_answer = score, entry.answer
```

- [ ] **Step 6: Update `GenericCache.async_lookup()`**

Same change as Step 5 — replace the `_cosine` loop with `codec.prepare_query` + `codec.score`:

```python
# After
codec = get_codec()
q_prepared = codec.prepare_query(q_emb)
with self._lock:
    best_score, best_answer = 0.0, None
    for entry in self._entries:
        score = codec.score(q_prepared, entry.embedding)
        if score > best_score:
            best_score, best_answer = score, entry.answer
```

- [ ] **Step 7: Update `RealtimeCache.lookup()`**

Replace the `_cosine` loop:

```python
# Before
with self._lock:
    self._entries = [e for e in self._entries if not self._is_expired(e)]
    best_score, best_entry = 0.0, None
    for entry in self._entries:
        if entry.state_hash != state_hash:
            continue
        score = _cosine(q_emb, entry.embedding)
        if score > best_score:
            best_score, best_entry = score, entry
```

```python
# After
codec = get_codec()
q_prepared = codec.prepare_query(q_emb)
with self._lock:
    self._entries = [e for e in self._entries if not self._is_expired(e)]
    best_score, best_entry = 0.0, None
    for entry in self._entries:
        if entry.state_hash != state_hash:
            continue
        score = codec.score(q_prepared, entry.embedding)
        if score > best_score:
            best_score, best_entry = score, entry
```

- [ ] **Step 8: Update `RealtimeCache.async_lookup()`**

Same change as Step 7:

```python
# After
codec = get_codec()
q_prepared = codec.prepare_query(q_emb)
with self._lock:
    self._entries = [e for e in self._entries if not self._is_expired(e)]
    best_score, best_entry = 0.0, None
    for entry in self._entries:
        if entry.state_hash != state_hash:
            continue
        score = codec.score(q_prepared, entry.embedding)
        if score > best_score:
            best_score, best_entry = score, entry
```

- [ ] **Step 9: Update `RealtimeCache.store()`**

```python
# Before
with self._lock:
    if len(self._entries) >= REALTIME_MAX_SIZE:
        self._entries.sort(key=lambda e: e.created_at)
        self._entries = self._entries[REALTIME_MAX_SIZE // 4 :]
    self._entries.append(
        _RealtimeEntry(
            embedding=q_emb,
            state_hash=state_hash,
            answer=answer,
            model_predictions=model_predictions,
        )
    )
```

```python
# After
with self._lock:
    if len(self._entries) >= REALTIME_MAX_SIZE:
        self._entries.sort(key=lambda e: e.created_at)
        self._entries = self._entries[REALTIME_MAX_SIZE // 4 :]
    self._entries.append(
        _RealtimeEntry(
            embedding=get_codec().encode(q_emb),
            state_hash=state_hash,
            answer=answer,
            model_predictions=model_predictions,
        )
    )
```

- [ ] **Step 10: Update `RealtimeCache.async_store()`**

Same as Step 9 — replace `embedding=q_emb` with `embedding=get_codec().encode(q_emb)`:

```python
# After
with self._lock:
    if len(self._entries) >= REALTIME_MAX_SIZE:
        self._entries.sort(key=lambda e: e.created_at)
        self._entries = self._entries[REALTIME_MAX_SIZE // 4 :]
    self._entries.append(
        _RealtimeEntry(
            embedding=get_codec().encode(q_emb),
            state_hash=state_hash,
            answer=answer,
            model_predictions=model_predictions,
        )
    )
```

- [ ] **Step 11: Run the existing test suite to verify nothing broke**

```bash
python -m pytest tests/unit/llm/ -v
```

Expected: all tests in `tests/unit/llm/` pass (including `test_gemini_client.py` and all turboquant tests).

- [ ] **Step 12: Commit**

```bash
git add src/llm/cache.py
git commit -m "feat: integrate TurboQuant_prod into LLM embedding cache"
```

---

## Task 5: Pre-push checks and final verification

**Files:** none (checks only)

- [ ] **Step 1: Black formatting check**

```bash
black --check src/llm/turboquant.py src/llm/cache.py
```

If it fails, auto-fix and re-check:

```bash
black src/llm/turboquant.py src/llm/cache.py
black --check src/llm/turboquant.py src/llm/cache.py
```

- [ ] **Step 2: Bandit security scan**

```bash
bandit -r src/llm/turboquant.py src/llm/cache.py -ll
```

Expected: no MEDIUM or HIGH findings. NumPy random with a fixed seed is fine — it's not a security-sensitive RNG.

- [ ] **Step 3: mypy type check**

```bash
mypy src/llm/turboquant.py src/llm/cache.py --ignore-missing-imports
```

Expected: no errors.

If mypy flags `np.ndarray | None` as an error, add `from __future__ import annotations` at the top of `turboquant.py` (already present) and use `Optional[np.ndarray]` if needed for older mypy.

- [ ] **Step 4: Run full turboquant test suite one final time**

```bash
python -m pytest tests/unit/llm/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit formatting fixes if any were needed**

```bash
git add src/llm/turboquant.py src/llm/cache.py
git commit -m "fix: black formatting on turboquant.py and cache.py"
```

(Skip this commit if black made no changes.)
