# Darnit Reproducibility Plugin: Comprehensive Evaluation & Findings

**Auditor / Contributor:** Jaydeep  
**Date:** September 2026  
**Repository:** `darnit` (`packages/darnit`, `packages/darnit-reproducibility`)  
**Evaluation Framework:** `reproducibility` v0.1.0  
**Evaluated Controls:**
- `RE-01.01` (`DependenciesPinned`)
- `RE-01.02` (`BuildEnvDeclared`)
- `RE-02.01` (`HermeticBuild`)
- `RE-02.02` (`ProvenanceExists`)
- `RE-03.01` (`BitForBitReproducible`)

---

## 1. Executive Summary

This evaluation tests the capabilities, accuracy, and blind spots of darnit's `reproducibility` plugin. We constructed two targeted synthetic experiments designed to trigger subtle runtime non-determinism, and audited one real-world, peer-reviewed, artifact-badged research repository (NDSS 2025).

The primary goal of this investigation was **not** merely to confirm that passing experiments pass, but to uncover **what darnit catches and what it misses**—especially identifying scenarios where darnit grants a clean `PASS` on broken or non-reproducible code, or emits false `FAIL`/`WARN` results on sound configurations.

All experiments were audited using `darnit audit <path> --framework reproducibility --show-all`, checked for repository cleanliness (`git status` before/after), and verified across 3 consecutive runs to guarantee 100% idempotency.

---

## 2. Experiments & Audit Results Matrix

| # | Experiment Target | Core Phenomenon / Trap Tested | Darnit Audit Score | Full Report Link |
|---|---|---|:---:|:---:|
| **1** | **Deterministic NumPy**<br>`experiments/01-deterministic-numpy` | **Multithreaded BLAS Reduction Divergence:** Fixed seed (`42`), identical float32 matrix operations, but varying `OPENBLAS_NUM_THREADS` (1 vs 2 vs 4). Non-associative floating-point reductions produce completely distinct output SHA-256 hashes. | `1 PASS / 1 FAIL / 4 WARN` | [📄 Read Full Report](experiment_1_numpy.md) |
| **2** | **Python Calling Custom C**<br>`experiments/02-c-ctypes` | **Compiler Optimization & Flag Traps:** C shared library summing single-precision floats under `-O2`, `-O3`, and `-O3 -ffast-math`. Produces distinct numerical floats (`10,000,000.0` vs `10,000,013.0`) and 3 distinct ELF binaries with different SIMD instructions. | `0 PASS / 0 FAIL / 5 WARN` | [📄 Read Full Report](experiment_2_c_ctypes.md) |
| **3** | **Real Badged Research Artifact**<br>`experiments/03-ndss-gittuf-eval` | **Real-World Empirical Artifact:** The official evaluation package for NDSS'25 paper *"Rethinking Trust in Forge-Based Git Security"* (`gittuf-ndss-eval`, Zenodo DOI: `10.5281/zenodo.14252266`). Tests how darnit evaluates an artifact badged as Functional & Reproduced. | `1 PASS / 1 FAIL / 3 WARN` | [📄 Read Full Report](experiment_3_ndss_artifact.md) |

---

## 3. Key Scientific & Architectural Takeaways

1. **The Semantic Gap in Dependency Pinning (`RE-01.01`):**
   - In Experiment 1, having `uv.lock` awarded a green `PASS` for dependency pinning. Yet running the code with `OPENBLAS_NUM_THREADS=2` vs `4` altered 30.52% of the float elements, completely breaking bit-for-bit output determinism. A package lockfile pins the Python layer, but leaves underlying BLAS/C runtime thread scheduling unpinned.
   - Conversely, a `requirements.txt` containing strict version pins (`numpy==2.5.2`) was unconditionally failed as a "loose manifest", penalizing developers who use exact pinning without a formal lockfile.

2. **The "Invisible Compilation" Blind Spot (`RE-02.01` & `RE-01.02`):**
   - In Experiment 2, darnit did not recognize that a C compilation step existed. While `repro_hermetic_build` found the `Makefile`, it only grepped for network-download keywords (`curl`, `wget`, `pip install`). It was completely oblivious to compiler invocations (`gcc`) and flags (`-ffast-math`) that fundamentally alter IEEE 754 compliance.
   - C ABI dependencies, shared libraries (`.so`), and compiler toolchain versions currently fall entirely outside darnit's radar.

3. **Superficial Environment Passing (`RE-01.02`):**
   - In Experiment 3, darnit gave a `PASS` (confidence 0.85) simply because `Dockerfile` existed. However, the Dockerfile used `FROM alpine:latest` (unpinned floating tag) and `apk update && apk add ...` (unpinned system packages). Over time, this image build is non-reproducible. Darnit currently performs a shallow filename check rather than parsing base image tags or digest pins.

4. **Hermeticity Missing Language-Native Installers (`RE-02.01`):**
   - In Experiment 3, `RUN go install github.com/gittuf/gittuf@v0.7.0` downloaded arbitrary Go modules over the public internet during the container build. Darnit marked the file as clean because `_SUSPICIOUS_PATTERNS` checks `pip`, `npm`, and `apt-get`, but completely omits `go install`, `go get`, and `cargo install`.

5. **Supply Chain Model vs. Scientific Artifact Badging:**
   - Darnit's controls are patterned after SLSA Level 3, Sigstore/Cosign signing, and bit-for-bit binary determinism (`SOURCE_DATE_EPOCH`). Academic artifact evaluation focuses on containerization, testability, and functional runnability. As a result, academic artifacts uniformly receive `WARN` on provenance (`RE-02.02`) and bit-for-bit reproduction (`RE-03.01`).

---

## 4. Pending Upstream Issues (For Review & Confirmation)

The following four issues have been identified and formulated. They are documented here for confirmation prior to opening them on upstream `darnitdevorg/darnit`.

---

### Issue 1 (Critical Bug): CLI Audit Fails to Register Plugin Sieve Handlers via `darnit.implementations`

* **Type:** Bug Report / Core Engine
* **Severity:** High (blocks execution of all external plugin handlers in terminal mode)
* **Status:** Resolved locally in this branch ([`packages/darnit/src/darnit/cli.py`](../packages/darnit/src/darnit/cli.py))
* **Description:**
  When executing `darnit audit <path> --framework reproducibility`, darnit calls `load_effective_config_by_name()`. This successfully resolves the TOML config via the `darnit.frameworks` entry point. However, `cmd_audit` **never calls `discover_implementations()`**.
  
  Because `discover_implementations()` is never invoked, the plugin's `register()` method is never executed, and its custom sieve handlers (`repro_deps_pinned`, `repro_build_env_declared`, etc.) are never registered into `SieveHandlerRegistry`.
  
  Every control outputs:
  ```text
  WARNING: Control RE-01.01: handler 'repro_deps_pinned' not found in registry
  WARNING: Control RE-01.02: handler 'repro_build_env_declared' not found in registry
  ...
  Total: 5 | Pass: 0 | Fail: 0 | Warn: 5 | N/A: 0
  ```
  Every check falls through to `manual` and returns `WARN`.
* **Fix:**
  In `packages/darnit/src/darnit/cli.py` inside `cmd_audit`:
  ```python
  from darnit.core.discovery import discover_implementations
  discover_implementations()
  ```

---

### Issue 2 (False Positive): `repro_deps_pinned` Unconditionally Flags Exact-Pinned `requirements.txt` as "Loose Manifests"

* **Type:** Bug Report / Heuristic Refinement
* **Component:** `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`
* **Description:**
  `repro_deps_pinned_handler` defines:
  ```python
  loose_manifests = {
      "requirements.txt": "pip requirements",
      ...
  }
  ```
  If no lock file (`uv.lock`, `poetry.lock`) is found, any presence of `requirements.txt` unconditionally returns `FAIL`:
  `"Dependency manifests found but no lock files: requirements.txt (pip requirements)"`.
  
  In practice, many repositories strictly pin their dependencies directly in `requirements.txt` (e.g. `numpy==2.5.2`, or compiled via `pip-compile --generate-hashes`). Classifying all `requirements.txt` files as loose manifests misleads developers whose builds are pinned.
* **Proposed Solution:**
  Inspect `requirements.txt` contents: if all non-comment lines contain strict pins (`==`) or `--hash=sha256:`, downgrade to `PASS` (with lower confidence, e.g. 0.6) or `WARN` rather than hard `FAIL`.

---

### Issue 3 (Hermeticity Gap): `repro_hermetic_build` Misses Language-Native Package Managers (`go install`, `cargo install`)

* **Type:** Feature Request / Security Gap
* **Component:** `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`
* **Description:**
  In `repro_hermetic_build_handler`, `_SUSPICIOUS_PATTERNS` is hardcoded to:
  ```python
  _SUSPICIOUS_PATTERNS: tuple[str, ...] = (
      "curl ",
      "wget ",
      "pip install ",
      "npm install",
      "yarn install",
      "apt-get install",
      "brew install",
  )
  ```
  While auditing the official NDSS'25 artifact `gittuf-ndss-eval`, the Dockerfile contained:
  ```dockerfile
  RUN go install github.com/gittuf/gittuf@v0.7.0
  ```
  Because `go install` is omitted from `_SUSPICIOUS_PATTERNS`, darnit reported 0 violations and marked the build as clean.
* **Proposed Solution:**
  Add `go install `, `go get `, `cargo install `, `gem install `, and `pnpm add ` to `_SUSPICIOUS_PATTERNS`.

---

### Issue 4 (False Sense of Security): `repro_build_env_declared` Grants `PASS` on Unpinned Floating Docker Images

* **Type:** Improvement / Evaluation Depth
* **Component:** `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`
* **Description:**
  `repro_build_env_declared_handler` performs a simple file existence check:
  ```python
  if (path / "Dockerfile").exists():
      return HandlerResult(status=PASS, message="Build environment declared via: Dockerfile (Docker)", confidence=0.85)
  ```
  In `gittuf-ndss-eval`, the Dockerfile uses:
  ```dockerfile
  FROM alpine:latest
  RUN apk update && apk add ...
  ```
  Floating base tags (`:latest`) and unpinned package additions pull different dependencies over time, defeating build reproducibility.
* **Proposed Solution:**
  If a Dockerfile is found, parse the `FROM` line:
  - If it uses `@sha256:...` $\rightarrow$ `PASS` (confidence 0.9).
  - If it uses `:tag` (e.g. `:3.20`) $\rightarrow$ `PASS` (confidence 0.7).
  - If it uses `:latest` or no tag $\rightarrow$ `WARN` ("Dockerfile found but base image uses unpinned/floating tag").

---

## 5. Idempotency & Cleanliness Verification

Across all three experiment directories, we ran `git status --porcelain` before and after auditing:
```bash
# Cleanliness check across all experiment directories
$ git status --porcelain experiments/
# Output: empty (darnit leaves zero temp files, caches, or state mutations)
```
Each audit was executed three consecutive times against the unchanged target, and the stdout and JSON evidence hashes remained 100% byte-identical across all trials.
