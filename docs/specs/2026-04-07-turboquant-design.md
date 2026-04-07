# TurboQuant_prod Integration — LLM Embedding Cache

**Date:** 2026-04-07  
**Branch:** pipeline  
**Paper:** [TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate](https://arxiv.org/abs/2504.19874) (ICLR 2026)

---

## Summary

Replace raw float32 embeddings in `src/llm/cache.py` with 4-bit TurboQuant_prod compressed vectors. This gives 8× memory reduction per cache entry and inner-product-preserving similarity estimation — with zero accuracy loss at 4 bits per the paper.

---

## Scope

| File | Change |
|---|---|
| `src/llm/turboquant.py` | New — TurboQuant_prod codec |
| `src/llm/cache.py` | Modified — use codec for storage and similarity |

No changes to: `src/llm/provider.py`, `src/llm/model_bridge.py`, `src/llm/gemini_client.py`, `src/llm/async_embed.py`, or any upstream/downstream code. Public cache interfaces (`lookup`, `store`, `async_lookup`, `async_store`) are unchanged.

---

## Algorithm

**TurboQuant_prod at 4 bits** = 3-bit Lloyd-Max MSE quantizer + 1-bit QJL on residual.

### Encoding a key vector `k` (768-dim, L2-normalized)

```
k̃ = R · k                          # random rotation (fixed seed 42)
codes = digitize(k̃, boundaries)    # 3-bit Lloyd-Max → int8 codes 0–7
ŷ = centroids[codes]               # reconstruct from codebook (float32)
r = k̃ - ŷ                          # quantization residual
raw_signs = sign(J · r)            # 768 projections, QJL matrix (seed 43)
qjl_signs = packbits(raw_signs)    # packed into 96 uint8 bytes
```

Store: `codes` (uint8 ×768, values 0–7), `qjl_signs` (uint8 ×96, 768 packed sign bits).

### Estimating `⟨q, k⟩` given full-precision query `q`

```
q̃ = R · q                           # rotate query once per lookup batch
ŷ = centroids[codes]                 # decode 3-bit codes → float32 (fast numpy index)
s1 = dot(q̃, ŷ)                      # MSE inner product component
proj = J · q̃                         # 768 QJL projections of query
z = unpackbits(qjl_signs) * 2 - 1   # ±1 from stored sign bits
s2 = (π / (2·768)) · dot(proj, z)   # unbiased QJL residual correction
cosine ≈ s1 + s2
```

Since Vertex AI `text-embedding-004` returns L2-normalized vectors, cosine similarity = inner product.

---

## Precomputed Lloyd-Max Codebook

Optimal 3-bit (8-level) Lloyd-Max quantizer for `N(0, σ²)` with `σ = 1/√768 ≈ 0.03608`.  
Boundary and centroid values are the analytically known N(0,1) optima scaled by σ.

| Code | Boundary (lower) | Centroid |
|------|-----------------|---------|
| 0 | −∞ | −2.152σ |
| 1 | −1.748σ | −1.344σ |
| 2 | −1.050σ | −0.756σ |
| 3 | −0.501σ | −0.245σ |
| 4 | 0 | +0.245σ |
| 5 | +0.501σ | +0.756σ |
| 6 | +1.050σ | +1.344σ |
| 7 | +1.748σ | +2.152σ |

Boundaries: `[-1.748, -1.050, -0.501, 0, +0.501, +1.050, +1.748]` × σ  
Centroids: `[-2.152, -1.344, -0.756, -0.245, +0.245, +0.756, +1.344, +2.152]` × σ

---

## Data Structures

### `TurboQuantVector` (dataclass)

```python
@dataclass
class TurboQuantVector:
    codes: np.ndarray      # shape (768,), dtype uint8, values 0–7 (3-bit Lloyd-Max code)
    qjl_signs: np.ndarray  # shape (96,),  dtype uint8, 768 packed sign bits
```

`ŷ = centroids[codes]` is decoded inline during lookup — one NumPy fancy-index op, negligible cost. Not stored to avoid negating compression gains.

### `TurboQuantCodec` (module-level singleton)

```python
class TurboQuantCodec:
    dim: int = 768
    bits: int = 4          # 3-bit MSE + 1-bit QJL
    _R: np.ndarray         # (768, 768) float32, lazy-init, seed 42
    _J: np.ndarray         # (768, 768) float32, lazy-init, seed 43
    _boundaries: np.ndarray  # (7,) float32 — precomputed constants
    _centroids: np.ndarray   # (8,) float32 — precomputed constants

    def encode(self, vec: list[float]) -> TurboQuantVector: ...
    def cosine_similarity(self, query: list[float], compressed: TurboQuantVector) -> float: ...
```

R and J are generated once per process (lazy, on first encode/lookup call) using a seeded RNG — no disk I/O, no startup cost. R is orthogonalized via QR decomposition. J entries are ±1/√768.

---

## Cache Changes

### `_GenericEntry` (cache.py)
```python
# Before
embedding: list[float]

# After
embedding: TurboQuantVector
```

### `_RealtimeEntry` (cache.py)
```python
# Before
embedding: list[float]

# After
embedding: TurboQuantVector
```

### `_cosine()` helper
Deleted. Replaced by `codec.cosine_similarity()`.

### `GenericCache.warm()`
After `_embed_one(q)`, encode immediately: `embedding = codec.encode(emb)`.

### `GenericCache.lookup()` / `async_lookup()`
- Embed query → `q_emb: list[float]` (stays full precision, never compressed)
- Replace `_cosine(q_emb, entry.embedding)` with `codec.cosine_similarity(q_emb, entry.embedding)`
- Compute `q̃ = R · q` once before the loop, reuse across all entry comparisons

### `RealtimeCache.store()` / `async_store()`
Encode embedding before appending: `embedding = codec.encode(q_emb)`.

### `RealtimeCache.lookup()` / `async_lookup()`
Same pattern as GenericCache.

### Similarity thresholds
Unchanged: `GENERIC_THRESHOLD = 0.85`, `REALTIME_THRESHOLD = 0.88`.  
TurboQuant_prod at 4 bits is quality-neutral per the paper (zero accuracy loss at 3.5 bits/channel).

---

## Memory Impact

| | Before | After |
|---|---|---|
| Per embedding | 3,072 bytes (768 × float32) | 864 bytes (768 uint8 codes + 96 uint8 QJL) |
| 256 RealtimeCache entries | 768 KB | 216 KB |
| R matrix (one-time) | — | 2.25 MB |
| J matrix (one-time) | — | 2.25 MB |
| Net change at full cache | 768 KB embeddings | 216 KB embeddings + 4.5 MB matrices |

**3.5× compression** on embedding storage using uint8 codes. Packing codes to 3 bits (288 bytes instead of 768) would reach 8×, but uint8 is simpler and the gain is already significant. R and J are a one-time fixed process cost.

---

## Testing

New test file: `tests/unit/llm/test_turboquant.py`

- `test_encode_shape` — encoded vector has correct shapes/dtypes
- `test_cosine_identity` — `cosine_similarity(v, encode(v)) ≈ 1.0` (within 0.05)
- `test_cosine_orthogonal` — orthogonal vectors give similarity ≈ 0.0
- `test_cosine_similar` — two semantically similar random unit vectors score higher than dissimilar
- `test_codec_singleton` — `get_codec()` returns the same instance

Existing cache tests in `tests/unit/llm/` (if any) should continue to pass with no interface changes.

---

## Non-Goals

- No change to `ml/features/feature_store.py` — it does key-value lookup, not vector search
- No GPU/Triton kernels — Cloud Run is CPU-only
- No quantization of query vectors — queries are transient, full precision is fine
- No persistence of compressed vectors to GCS — cache is in-memory only
