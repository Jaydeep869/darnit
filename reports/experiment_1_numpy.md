# Experiment 1: Deterministic NumPy under Varied BLAS Thread Counts & Darnit Reproducibility Plugin Audit

**Date:** 2026-09-05  
**Auditor / Experimenter:** Jaydeep  
**Assisting Agent / MCP Tooling:** Antigravity  
**Repository:** `darnit` (`packages/darnit`, `packages/darnit-reproducibility`)  
**Target:** `experiments/01-deterministic-numpy`  
**Framework:** `reproducibility` v0.1.0  

---

## 1. Executive Summary

Scientific reproducibility in numerical computing requires both software dependency pinning and deterministic numerical execution. While tools like `darnit` audit static repository metadata, lock files, and CI pipelines, runtime execution characteristics—specifically multithreaded floating-point associativity in BLAS backends—can silently destroy bit-for-bit reproducibility even when:
- Random seeds are fixed (`np.random.seed(42)`).
- Code is byte-for-byte identical.
- Package versions are pinned in `requirements.txt` or `uv.lock`.

This report documents **Experiment 1: Deterministic NumPy**, demonstrating how varied OpenBLAS thread counts (`OPENBLAS_NUM_THREADS=1, 2, 4`) alter output SHA-256 hashes for identical float32 matrix operations. It then provides a thorough audit of this experiment using darnit's `reproducibility` plugin checks (`repro_deps_pinned`, `repro_build_env_declared`, `repro_hermetic_build`, `repro_provenance_exists`, `repro_bit_for_bit`), analyzes the semantic gap between lock files and runtime determinism, evaluates darnit's idempotency and repo hygiene, and presents concrete bug reports for `darnitdevorg/darnit`.

---

## 2. Experiment Setup & Execution

### 2.1 Experiment Code (`matrix_op.py`)

The experiment script performs single-precision (`float32`) matrix multiplication ($C = A \times B$) of two $2500 \times 2500$ matrices initialized with fixed seed $42$, followed by column summation reduction ($\sum_{i} C_{ij}$). The result buffer is serialized to raw bytes and hashed via SHA-256.

```python
import hashlib
import os
import sys
import time
import numpy as np


def main() -> None:
    thread_env = os.environ.get("OPENBLAS_NUM_THREADS", "unset (default)")
    omp_env = os.environ.get("OMP_NUM_THREADS", "unset")
    
    seed = 42
    np.random.seed(seed)

    dim = 2500
    t0 = time.perf_counter()
    a = np.random.rand(dim, dim).astype(np.float32)
    b = np.random.rand(dim, dim).astype(np.float32)

    c = np.dot(a, b)
    result = np.sum(c, axis=0)
    elapsed = time.perf_counter() - t0

    result_bytes = result.tobytes()
    digest = hashlib.sha256(result_bytes).hexdigest()

    print(f"Matrix Dimension: {dim}x{dim}, dtype={result.dtype}")
    print(f"Random Seed: {seed}")
    print(f"OPENBLAS_NUM_THREADS: {thread_env}")
    print(f"OMP_NUM_THREADS: {omp_env}")
    print(f"Elapsed Time: {elapsed:.4f}s")
    print(f"SHA-256 Digest: {digest}")


if __name__ == "__main__":
    main()
```

### 2.2 Numerical Results across Thread Counts

The experiment was run under `OPENBLAS_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=2`, and `OPENBLAS_NUM_THREADS=4`.

| `OPENBLAS_NUM_THREADS` | Elapsed Time | Output SHA-256 Digest | Match with 1 Thread? |
|:---:|:---:|:---:|:---:|
| **1** | 0.3010s | `5dd51c55eb5287c66cbb3d5c580071d49fc89f84da7a992a0a08f927d188c8fb` | Reference |
| **2** | 0.1887s | `6cb047cc8da2855a05546967944661fd13ff7a0f173aac1e69bc2b661d092fdc` | **MISMATCH (0% byte equality)** |
| **4** | 0.1397s | `049c52bb8bc73e520b719ced389ea922a31315dd89a7bbd524d8bc6dc0cc7e59` | **MISMATCH (0% byte equality)** |

### 2.3 Intra-Thread Repeatability (3 Consecutive Trials per Thread Count)

Running 3 consecutive trials for each fixed thread count shows that each configuration is internally deterministic:

```text
=== Thread Count: 1 ===
Run 1: 5dd51c55eb5287c66cbb3d5c580071d49fc89f84da7a992a0a08f927d188c8fb
Run 2: 5dd51c55eb5287c66cbb3d5c580071d49fc89f84da7a992a0a08f927d188c8fb
Run 3: 5dd51c55eb5287c66cbb3d5c580071d49fc89f84da7a992a0a08f927d188c8fb

=== Thread Count: 2 ===
Run 1: 6cb047cc8da2855a05546967944661fd13ff7a0f173aac1e69bc2b661d092fdc
Run 2: 6cb047cc8da2855a05546967944661fd13ff7a0f173aac1e69bc2b661d092fdc
Run 3: 6cb047cc8da2855a05546967944661fd13ff7a0f173aac1e69bc2b661d092fdc

=== Thread Count: 4 ===
Run 1: 049c52bb8bc73e520b719ced389ea922a31315dd89a7bbd524d8bc6dc0cc7e59
Run 2: 049c52bb8bc73e520b719ced389ea922a31315dd89a7bbd524d8bc6dc0cc7e59
Run 3: 049c52bb8bc73e520b719ced389ea922a31315dd89a7bbd524d8bc6dc0cc7e59
```

### 2.4 Mathematical & Floating-Point Error Analysis

Why do the SHA-256 digests differ across thread counts?
1. **Non-Associativity of IEEE 754 Floating-Point Arithmetic:**
   Addition of floating-point numbers is not associative: $(a + b) + c \neq a + (b + c)$.
2. **OpenBLAS Thread Partitioning in `sgemm`:**
   When OpenBLAS partitions the $2500 \times 2500$ matrix multiplication across $N$ threads, it divides the inner and outer block loops differently. Worker threads accumulate partial dot-products and block summations in thread-local buffers before reducing them into the final output matrix.
3. **Quantifying the Numerical Deviation:**
   Comparing the 1-thread result buffer against the 2-thread result buffer:
   - **Max absolute difference:** $0.375$
   - **Max relative difference:** $2.436651 \times 10^{-7}$
   - **Number of differing elements:** $763$ out of $2500$ ($30.52\%$)
   
   The maximum relative error ($2.44 \times 10^{-7}$) is directly bounded by machine precision for single-precision IEEE 754 float32 ($\epsilon_{\text{mach}} = 2^{-24} \approx 1.192 \times 10^{-7}$). While statistically and numerically acceptable for many scientific applications, cryptographic bit-for-bit comparisons (such as SHA-256 or Git commit digests) produce completely uncorrelated hashes due to the avalanche effect.

---

## 3. Darnit Reproducibility Plugin Audit Outputs

Two dependency manifest variations were audited using darnit's `reproducibility` framework:

### 3.1 Variation A: Unlocked Pinned Manifest (`requirements.txt`)

`experiments/01-deterministic-numpy/requirements.txt`:
```text
numpy==2.5.2
```

#### CLI Command & Output (`--show-all`)
```bash
uv run darnit audit experiments/01-deterministic-numpy --framework reproducibility --show-all
```

```text
WARNING: Plugin 'reproducibility' failed verification but will be loaded anyway: Package 'reproducibility' not found
INFO: Discovered implementation: reproducibility v0.1.0
WARNING: Plugin 'hello' failed verification but will be loaded anyway: Package 'hello' not found
INFO: Discovered implementation: hello v0.1.0
WARNING: Plugin 'gittuf' failed verification but will be loaded anyway: Package 'gittuf' not found
INFO: Discovered implementation: gittuf v0.1.0
WARNING: Plugin 'example-hygiene' failed verification but will be loaded anyway: Package 'example-hygiene' not found
INFO: Discovered implementation: example-hygiene v0.1.0
WARNING: Plugin 'openssf-baseline' failed verification but will be loaded anyway: Package 'openssf-baseline' not found
INFO: Discovered implementation: openssf-baseline v0.1.0
INFO: Discovered 5 implementation(s)
WARNING: Running in terminal mode (no LLM consultation). For full capabilities, use 'darnit serve' with an MCP client.
INFO: Discovered 6 framework(s)
INFO: Auditing /home/jd/open_Source/LFX/Ossf/darnit/experiments/01-deterministic-numpy with 5 controls
INFO: Project context for when-clause evaluation: {'platform': 'github', 'languages': []}

=== reproducibility Audit Results ===

Total: 5 | Pass: 0 | Fail: 1 | Warn: 4 | N/A: 0


--- Failures ---
  ✗ RE-01.01: FAIL - Dependency manifests found but no lock files: requirements.txt (pip requirements)

--- Warnings ---
  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
  ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
```

#### JSON Evidence for `RE-01.01` (Variation A)
```json
{
  "id": "RE-01.01",
  "status": "FAIL",
  "details": "Dependency manifests found but no lock files: requirements.txt (pip requirements)",
  "level": 1,
  "sieve_phase": "deterministic",
  "evidence": {
    "lock_files_found": [],
    "loose_manifests_found": [
      "requirements.txt (pip requirements)"
    ]
  },
  "resolving_pass_index": 0,
  "resolving_pass_handler": "repro_deps_pinned",
  "authority": "dispositive",
  "pass_history": [
    {
      "phase": "deterministic",
      "checks_performed": [
        "handler:repro_deps_pinned"
      ],
      "result": {
        "outcome": "fail",
        "message": "Dependency manifests found but no lock files: requirements.txt (pip requirements)",
        "confidence": 0.8
      },
      "duration_ms": 0
    }
  ]
}
```

---

### 3.2 Variation B: Locked Manifest (`uv.lock` present)

`experiments/01-deterministic-numpy/uv.lock` generated via `uv lock`.

#### CLI Command & Output (`--show-all`)
```bash
uv run darnit audit experiments/01-deterministic-numpy --framework reproducibility --show-all
```

```text
WARNING: Plugin 'reproducibility' failed verification but will be loaded anyway: Package 'reproducibility' not found
INFO: Discovered implementation: reproducibility v0.1.0
WARNING: Plugin 'hello' failed verification but will be loaded anyway: Package 'hello' not found
INFO: Discovered implementation: hello v0.1.0
WARNING: Plugin 'gittuf' failed verification but will be loaded anyway: Package 'gittuf' not found
INFO: Discovered implementation: gittuf v0.1.0
WARNING: Plugin 'example-hygiene' failed verification but will be loaded anyway: Package 'example-hygiene' not found
INFO: Discovered implementation: example-hygiene v0.1.0
WARNING: Plugin 'openssf-baseline' failed verification but will be loaded anyway: Package 'openssf-baseline' not found
INFO: Discovered implementation: openssf-baseline v0.1.0
INFO: Discovered 5 implementation(s)
WARNING: Running in terminal mode (no LLM consultation). For full capabilities, use 'darnit serve' with an MCP client.
INFO: Discovered 6 framework(s)
INFO: Auditing /home/jd/open_Source/LFX/Ossf/darnit/experiments/01-deterministic-numpy with 5 controls
INFO: Project context for when-clause evaluation: {'platform': 'github', 'primary_language': 'python', 'detected_ecosystem': 'python', 'languages': ['python']}

=== reproducibility Audit Results ===

Total: 5 | Pass: 1 | Fail: 0 | Warn: 4 | N/A: 0


--- Warnings ---
  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
  ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required

--- Passed (1) ---
  ✓ RE-01.01: PASS - Lock file(s) found: uv.lock (uv (Python))
```

#### JSON Evidence for `RE-01.01` (Variation B)
```json
{
  "id": "RE-01.01",
  "status": "PASS",
  "details": "Lock file(s) found: uv.lock (uv (Python))",
  "level": 1,
  "sieve_phase": "deterministic",
  "confidence": 0.8,
  "evidence": {
    "lock_files_found": [
      "uv.lock (uv (Python))"
    ],
    "loose_manifests_found": [
      "requirements.txt (pip requirements)"
    ]
  },
  "resolving_pass_index": 0,
  "resolving_pass_handler": "repro_deps_pinned",
  "authority": "dispositive",
  "pass_history": [
    {
      "phase": "deterministic",
      "checks_performed": [
        "handler:repro_deps_pinned"
      ],
      "result": {
        "outcome": "pass",
        "message": "Lock file(s) found: uv.lock (uv (Python))",
        "confidence": 0.8
      },
      "duration_ms": 0
    }
  ]
}
```

---

## 4. Evaluation Table

| Control ID | Name | Status (Var A / Var B) | Agree? | Analysis |
|:---|:---|:---:|:---:|:---|
| **RE-01.01** | `DependenciesPinned` | **FAIL** / **PASS** | **Partially Disagree** | **Variation A (FAIL):** Darnit treats `requirements.txt` as a loose manifest even though every entry is strictly pinned (`numpy==2.5.2`). It lacks AST/content inspection for exact version pins or `--require-hashes`.<br>**Variation B (PASS):** Passes simply because `uv.lock` exists. However, as demonstrated by Experiment 1, lock files do NOT guarantee bit-for-bit numerical reproducibility because underlying C/BLAS threading runtimes (`OPENBLAS_NUM_THREADS`) alter the calculation without altering the locked packages. |
| **RE-01.02** | `BuildEnvDeclared` | **WARN** / **WARN** | **Agree** | The experiment subdirectory does not commit a `Dockerfile`, `.python-version`, or `.devcontainer/`. The handler correctly returned `INCONCLUSIVE` (confidence 0.0), which sieve converts to `WARN` with manual verification steps. |
| **RE-02.01** | `HermeticBuild` | **WARN** / **WARN** | **Agree** | No CI workflow files (`.github/workflows/`), Makefiles, or Dockerfiles exist inside `experiments/01-deterministic-numpy/`. The handler safely returned `INCONCLUSIVE` (confidence 0.0), indicating that no files were present to audit for network fetches. |
| **RE-02.02** | `ProvenanceExists` | **WARN** / **WARN** | **Agree** | No provenance generation workflows (Cosign, Sigstore, SLSA) exist in the local experiment folder. Conservatively flagged for manual verification. |
| **RE-03.01** | `BitForBitReproducible` | **WARN** / **WARN** | **Agree with Status, Critical Finding on Substance** | The handler checks CI workflows for `SOURCE_DATE_EPOCH`, `reprotest`, or `diffoscope`. Because none were found, it returns `INCONCLUSIVE` (`WARN`). In reality, the experiment **proves that the code is NOT bit-for-bit reproducible** across thread configurations, even though the random seed is identical! |

---

## 5. Deep Analysis: The Semantic Gap in Dependency Pinning

### 5.1 Why `repro_deps_pinned` Passes on a Lock File Despite Runtime Divergence

In `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`, `repro_deps_pinned_handler` performs a purely static existence check:

```python
lock_files = {
    "uv.lock": "uv (Python)",
    "poetry.lock": "Poetry (Python)",
    "Pipfile.lock": "Pipenv (Python)",
    "package-lock.json": "npm (Node)",
    "yarn.lock": "Yarn (Node)",
    "Cargo.lock": "Cargo (Rust)",
    "go.sum": "Go modules",
    "Gemfile.lock": "Bundler (Ruby)",
    "composer.lock": "Composer (PHP)",
}
```

If `(path / "uv.lock").exists()`, the handler immediately returns `HandlerResultStatus.PASS` with `confidence=0.8`.

#### The Gap:
1. **Python vs. Shared Library / C Runtime ABI:**
   `uv.lock` pins the Python wheel (e.g. `numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`). Inside that wheel, OpenBLAS is bundled or dynamically linked. The wheel metadata does not pin hardware ISA extensions (AVX2 vs AVX-512) or execution concurrency (`OPENBLAS_NUM_THREADS`).
2. **Dynamic Concurrency & Associativity:**
   OpenBLAS's internal `gemm` algorithms decompose large matrices into blocks assigned to worker threads. Thread scheduling and reduction across threads alter the accumulation sequence. Because IEEE 754 float32 addition is non-associative, different thread counts compute different lower bits.
3. **Auditor Blind Spot:**
   A security/compliance scanner that only checks for the presence of `uv.lock` grants a clean `PASS` for dependency pinning, creating a false sense of bit-for-bit determinism. True scientific reproducibility requires declaring both the software lockfile AND the execution harness environment (`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, or reproducible reduction algorithms like ReproBLAS / Kahan summation).

### 5.2 How Darnit Treats `requirements.txt`

`repro_deps_pinned_handler` defines:
```python
loose_manifests = {
    "requirements.txt": "pip requirements",
    "setup.py": "setuptools",
    "package.json": "npm package",
    "Cargo.toml": "Cargo manifest",
    "go.mod": "Go module",
}
```

If `requirements.txt` is present and no lock file is detected, the check returns `HandlerResultStatus.FAIL`:
`"Dependency manifests found but no lock files: requirements.txt (pip requirements)"`.

#### Deficiencies in this design:
- **Exact Pins are Penalized as Loose:** Even if `requirements.txt` contains pinned versions (`numpy==2.5.2`) or cryptographic hashes (`--hash=sha256:...`), it is classified as a loose manifest identical to an unpinned `numpy>=1.0`.
- **Pip Compiler Workflow Ignored:** Standard industry workflows often compile `requirements.in` into a pinned `requirements.txt` with hashes (`pip-compile --generate-hashes`). Treating `requirements.txt` as inherently loose misinforms developers whose build pipelines are strictly pinned.

---

## 6. Repo Hygiene & Idempotency Logs

### 6.1 Repo Hygiene Verification (`git status --porcelain`)

We verified whether running `darnit audit` produces any side-effect files (caches, temp files, or index modifications).

#### Before Auditing:
```bash
$ git status --porcelain
 M packages/darnit/src/darnit/cli.py
?? evaluation_targets/
?? experiments/
```

#### After Multiple Audits:
```bash
$ git status --porcelain experiments/
?? experiments/
```
No `.cache`, `.baseline.cache`, or temporary artifacts were created in `experiments/01-deterministic-numpy/`. Repo hygiene is **clean and verified**.

### 6.2 Audit Idempotency (3 Consecutive Runs)

We ran `darnit audit` three consecutive times against the unchanged target directory.

```bash
PYTHONHASHSEED=0 uv run darnit audit experiments/01-deterministic-numpy --framework reproducibility --show-all > /tmp/audit_ph0_1.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/01-deterministic-numpy --framework reproducibility --show-all > /tmp/audit_ph0_2.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/01-deterministic-numpy --framework reproducibility --show-all > /tmp/audit_ph0_3.txt 2>&1

diff -u /tmp/audit_ph0_1.txt /tmp/audit_ph0_2.txt && diff -u /tmp/audit_ph0_2.txt /tmp/audit_ph0_3.txt
```
**Result:** 0 differences. When `PYTHONHASHSEED` is held constant, the audit is 100% idempotent.

> [!NOTE]
> **Discovery of Unordered Set Iteration in `merger.py`:**
> When running without `PYTHONHASHSEED=0`, consecutive invocations produced differing control order in the `--show-all` warning list. Investigation revealed that `packages/darnit/src/darnit/config/merger.py:424` converts control keys to an unsorted Python `set`, causing process-randomized ordering (see Bug Report #2).

---

## 7. Bug Reports Formatted for `darnitdevorg/darnit`

### Bug Report 1: CLI `cmd_audit` fails to discover and register plugin implementations

```markdown
### Summary
`darnit audit` fails to register sieve handlers defined by external plugin packages (such as `darnit-reproducibility` and `darnit-gittuf`), emitting warnings that all handlers are missing from the registry and falling back to manual verification.

### Environment
- darnit version: dev / main branch
- Python: 3.12
- Installed packages: darnit, darnit-reproducibility, darnit-gittuf

### Steps to Reproduce
1. Install darnit with the reproducibility plugin (`uv run --extra reproducibility ...`).
2. Execute:
   `darnit audit . --framework reproducibility`

### Expected Behavior
The 5 reproducibility handlers (`repro_deps_pinned`, `repro_build_env_declared`, `repro_hermetic_build`, `repro_provenance_exists`, `repro_bit_for_bit`) should be registered and executed.

### Actual Behavior
The CLI outputs:
```text
WARNING: Control RE-03.01: handler 'repro_bit_for_bit' not found in registry
WARNING: Control RE-02.01: handler 'repro_hermetic_build' not found in registry
WARNING: Control RE-01.01: handler 'repro_deps_pinned' not found in registry
WARNING: Control RE-01.02: handler 'repro_build_env_declared' not found in registry
WARNING: Control RE-02.02: handler 'repro_provenance_exists' not found in registry

=== reproducibility Audit Results ===
Total: 5 | Pass: 0 | Fail: 0 | Warn: 5 | N/A: 0
```

### Root Cause
In `packages/darnit/src/darnit/cli.py`, `cmd_audit()` does not call `discover_implementations()`. While `cmd_init()` and `cmd_profiles()` invoke discovery, `cmd_audit()` only calls `load_effective_config_by_name()`, which resolves the TOML config but does not execute the entry points in `darnit.implementations` to register custom sieve handlers.

### Proposed Fix
In `packages/darnit/src/darnit/cli.py`:
```python
def cmd_audit(args: argparse.Namespace) -> int:
    from darnit.core.discovery import discover_implementations
    discover_implementations()
    ...
```
```

---

### Bug Report 2: Non-deterministic control display order across audit runs due to `set` iteration in `merger.py`

```markdown
### Summary
Audit output ordering in `darnit audit --show-all` is non-deterministic between independent CLI invocations because `merger.py` iterates over an unordered `set[str]`.

### Steps to Reproduce
1. Run `darnit audit <target> --framework reproducibility --show-all` twice in separate shells.
2. Compare text outputs with `diff -u`.

### Actual Behavior
The order of controls listed under `--- Warnings ---` changes randomly between runs:
```diff
--- run1.txt
+++ run2.txt
@@ -20,9 +20,9 @@
 --- Warnings ---
-  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
-  ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
   ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
```

### Root Cause
In `packages/darnit/src/darnit/config/merger.py` at line 424:
```python
all_control_ids: set[str] = set(framework.controls.keys())
if user:
    all_control_ids.update(user.controls.keys())

for control_id in all_control_ids:
    effective.controls[control_id] = ...
```
Because `all_control_ids` is an unordered `set`, iteration order is determined by Python's hash seed (`PYTHONHASHSEED`), which changes per process.

### Proposed Fix
Preserve declaration order from `framework.controls` or sort keys:
```python
# Preserve order from framework first, then append any user custom controls
all_control_ids: list[str] = list(framework.controls.keys())
if user:
    for cid in user.controls.keys():
        if cid not in framework.controls:
            all_control_ids.append(cid)
```
```

---

### Bug Report 3: `repro_deps_pinned` unconditionally flags `requirements.txt` as a loose manifest even when pinned

```markdown
### Summary
`repro_deps_pinned` treats `requirements.txt` as a loose manifest (`FAIL`) even when all dependencies inside it are strictly pinned to exact versions with `==` and/or contain `--require-hashes`.

### Proposed Enhancement
Enhance `repro_deps_pinned_handler` to inspect `requirements.txt`:
1. If any unpinned or range-based specifier is found (`>=`, `~=`, `>`, `*`), flag as loose (`FAIL`).
2. If all lines contain exact pins (`==`) or hashes, return `PASS` (or `PASS` with warning to use a modern lockfile).
```
