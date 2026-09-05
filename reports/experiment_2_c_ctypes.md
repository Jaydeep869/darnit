# Experiment 2: Python Calling Custom C under Varied Optimization Flags & Darnit Reproducibility Plugin Audit

**Date:** 2026-09-05  
**Auditor / Experimenter:** Jaydeep  
**Assisting Agent / MCP Tooling:** Antigravity  
**Repository:** `darnit` (`packages/darnit`, `packages/darnit-reproducibility`)  
**Target:** `experiments/02-c-ctypes`  
**Framework:** `reproducibility` v0.1.0  

---

## 1. Executive Summary

Scientific and high-performance Python applications routinely rely on native compiled extensions (C, C++, Fortran, Rust, CUDA) interfaced via `ctypes`, CFFI, Cython, or Python C extension modules. While Python-level dependency pinning (e.g. `uv.lock`, `requirements.txt`) addresses package versions, the numerical reproducibility of native code is determined at compile time by compiler toolchains, CPU instruction sets, and optimization flags.

In this experiment, we test darnit's `reproducibility` plugin checks (`repro_deps_pinned`, `repro_build_env_declared`, `repro_hermetic_build`, `repro_provenance_exists`, `repro_bit_for_bit`) against **Experiment 2: Python calling Custom C**. 

We implement a minimal C shared library (`sum.c`) that sums an array of single-precision IEEE 754 floats of differing magnitudes, compile it under three standard optimization regimes (`-O2`, `-O3`, and `-O3 -ffast-math`), invoke it from Python via `ctypes` (`run_sum.py`), and inspect both the numerical output and the resulting ELF binaries.

### Key Findings:
1. **Numerical & Binary Divergence:**
   - **Numerical Values:** Compiling with `-O2` and `-O3` preserves strict IEEE 754 left-to-right sequential addition (`10,000,000.00000000`, hex `0x4b189680`), where small floating-point terms are swallowed by catastrophic precision truncation. Under `-O3 -ffast-math`, GCC treats floating-point addition as associative and vectorizes the accumulation across SIMD vector lanes (`addps`), altering the reduction order and producing a distinct numerical result (`10,000,013.00000000`, hex `0x4b18968d`).
   - **Cryptographic Hashes:** The resulting float SHA-256 digest is completely uncorrelated between strict IEEE 754 and fast-math (`64f690b8...` vs `c002e7ea...`).
   - **Binary Divergence:** All three compiler flag sets produce **three distinct ELF shared libraries** (`libsum.so`), each with a unique SHA-256 checksum and different disassembly (unrolling by 2 in `-O2`, unrolling by 4 in `-O3`, and SIMD 128-bit vectorization in `fastmath`).
2. **Darnit Reproducibility Plugin Blind Spot:**
   - When audited with `darnit audit experiments/02-c-ctypes --framework reproducibility --show-all`, darnit reports `Pass: 0 | Fail: 0 | Warn: 5 | N/A: 0`.
   - **No Compilation Step Recognition:** Darnit does not detect that a native C compilation step exists. While `repro_hermetic_build` finds `Makefile`, it only greps for network fetch patterns (`curl`, `wget`, `pip install`, `apt-get install`). It completely ignores compiler invocations (`gcc`), compiler flags (`-O2`, `-O3`, `-ffast-math`), and assembly instructions.
   - **No Native Toolchain Auditing:** `repro_build_env_declared` checks only for Dockerfiles, Nix flakes, or `.python-version`, completely ignoring `Makefile` and native C/C++ toolchain specifications.
   - **No C/ABI Dependency Tracking:** `repro_deps_pinned` checks only higher-level package manager locks (`uv.lock`, `Cargo.lock`, `package-lock.json`), completely overlooking C shared libraries, glibc, and system toolchains.

---

## 2. Experiment Setup & Codebase

The experiment is located in `experiments/02-c-ctypes`.

### 2.1 C Source Code: `experiments/02-c-ctypes/sum.c`

The C function `sum_array` iterates over an array of single-precision (`float`) numbers and accumulates their sum:

```c
/*
 * sum.c - Floating-point accumulation over single-precision floats
 *
 * Designed to demonstrate IEEE 754 floating-point non-associativity
 * under varied compiler optimization flags (-O2, -O3, -ffast-math).
 *
 * Under strict IEEE 754 (-O2, -O3), additions cannot be reassociated,
 * forcing sequential accumulation where small values are swallowed when
 * added to a growing large accumulator. Under -ffast-math, GCC enables
 * -fassociative-math and vectorizes the loop across SIMD vector lanes,
 * altering the accumulation tree and producing a distinct numerical result.
 */

#include <stddef.h>

float sum_array(const float *arr, size_t n) {
    float total = 0.0f;
    for (size_t i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}
```

### 2.2 Makefile: `experiments/02-c-ctypes/Makefile`

The Makefile provides explicit targets for each optimization configuration:

```makefile
CC ?= gcc
CFLAGS_COMMON = -fPIC -shared

all: opt2

opt2: sum.c
	$(CC) -O2 $(CFLAGS_COMMON) sum.c -o libsum.so

opt3: sum.c
	$(CC) -O3 $(CFLAGS_COMMON) sum.c -o libsum.so

fastmath: sum.c
	$(CC) -O3 -ffast-math $(CFLAGS_COMMON) sum.c -o libsum.so

clean:
	rm -f libsum.so

.PHONY: all opt2 opt3 fastmath clean
```

### 2.3 Python Harness: `experiments/02-c-ctypes/run_sum.py`

The Python script uses `ctypes` to bind to `libsum.so`, constructs a fixed dataset of 8,000 single-precision floats of differing magnitudes (1,000 repetitions of `[10000.0, 1e-4, 1e-3, 2e-4, 5e-5, 0.01, 0.002, 1e-4]`), and outputs the float value, IEEE 754 hex representation, and SHA-256 hashes of both the result bytes and `libsum.so`:

```python
#!/usr/bin/env python3
"""
run_sum.py - Call custom C shared library via ctypes and inspect numerical output.

Loads libsum.so, passes a deterministic array of single-precision floats of
differing magnitudes, and computes the exact float value, IEEE 754 hex representation,
and cryptographic SHA-256 digest of the result.
"""

import ctypes
import hashlib
import os
import struct
import sys
import time


def main() -> None:
    so_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libsum.so")
    if not os.path.exists(so_path):
        print(f"Error: Shared library {so_path} not found. Run 'make <target>' first.", file=sys.stderr)
        sys.exit(1)

    # Compute hash of the shared library binary itself
    with open(so_path, "rb") as f:
        so_bytes = f.read()
    so_hash = hashlib.sha256(so_bytes).hexdigest()

    # Load C shared library
    lib = ctypes.CDLL(so_path)
    lib.sum_array.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
    lib.sum_array.restype = ctypes.c_float

    # Fixed dataset of differing magnitudes:
    # 1000 repetitions of 8 values: 10000.0 followed by 7 small numbers
    pattern = [10000.0, 1e-4, 1e-3, 2e-4, 5e-5, 0.01, 0.002, 1e-4]
    data = pattern * 1000  # 8000 elements total
    n_elements = len(data)

    c_float_array = (ctypes.c_float * n_elements)(*data)

    t0 = time.perf_counter()
    result = lib.sum_array(c_float_array, n_elements)
    elapsed = time.perf_counter() - t0

    # Pack into IEEE 754 32-bit float bytes
    raw_bytes = struct.pack("<f", result)
    hex_bits = f"0x{struct.unpack('<I', raw_bytes)[0]:08x}"
    result_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    print(f"Shared Library Path: {so_path}")
    print(f"Shared Library SHA-256: {so_hash}")
    print(f"Array Size: {n_elements} single-precision floats")
    print(f"Summation Result (Float): {result:.9e} (decimal: {result:.8f})")
    print(f"IEEE 754 Hex Representation: {hex_bits}")
    print(f"Result SHA-256 Digest: {result_sha256}")
    print(f"Execution Time: {elapsed:.6f}s")


if __name__ == "__main__":
    main()
```

---

## 3. Compilation & Execution Results

### 3.1 Compiler Environment
- **Compiler:** `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`
- **Architecture:** x86_64 (`endbr64`, SSE/AVX capable)
- **Host OS:** Linux 6.8.0-52-generic x86_64

### 3.2 Compilation and Execution Commands

```bash
# 1. Target: opt2 (-O2)
make clean && make opt2 && python3 run_sum.py

# 2. Target: opt3 (-O3)
make clean && make opt3 && python3 run_sum.py

# 3. Target: fastmath (-O3 -ffast-math)
make clean && make fastmath && python3 run_sum.py
```

### 3.3 Output Comparison Across Optimization Regimes

| Configuration / Target | Compiler Flags | Shared Library (`libsum.so`) SHA-256 | Summation Result (Float) | IEEE 754 Hex Representation | Result SHA-256 Digest |
|:---|:---|:---:|:---:|:---:|:---:|
| **Target: `opt2`** | `-O2 -fPIC -shared` | `d734e32764d335376179c5c64cb149d242a71aaeda760581ad9f7bf5d88bb01e` | `10000000.00000000` | `0x4b189680` | `64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6` |
| **Target: `opt3`** | `-O3 -fPIC -shared` | `8202b9e740d72a088a82255e4308f4a966cc6ab6d93f2314416b3a01d95d77c2` | `10000000.00000000` | `0x4b189680` | `64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6` |
| **Target: `fastmath`** | `-O3 -ffast-math -fPIC -shared` | `a2addee2b15ce23a47cd21bcbdde8bbdc6fa0db30b60345a166ea57a959091e3` | `10000013.00000000` | `0x4b18968d` | `c002e7ea54b613cd84e804f50e80b5ce0562779a643f10f1398f0428960320d7` |

### 3.4 Summary of Distinct Results Produced

- **Distinct Numerical / Floating-Point Results:** **2** (`10,000,000.0` vs `10,000,013.0`).
- **Distinct Shared Library Binaries (`libsum.so`):** **3**. Every optimization flag produced a completely distinct shared object binary with zero byte equality across them.

### 3.5 Intra-Target Repeatability (3 Consecutive Trials per Target)

Running 3 consecutive executions for each compiled library confirms internal determinism:

```text
=== Target: opt2 ===
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6

=== Target: opt3 ===
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6
Result SHA-256 Digest: 64f690b82af6fa7e41ad0c65ee13b344dc31f7d8cafd58e9c0b4e986fbfa35b6

=== Target: fastmath ===
Result SHA-256 Digest: c002e7ea54b613cd84e804f50e80b5ce0562779a643f10f1398f0428960320d7
Result SHA-256 Digest: c002e7ea54b613cd84e804f50e80b5ce0562779a643f10f1398f0428960320d7
Result SHA-256 Digest: c002e7ea54b613cd84e804f50e80b5ce0562779a643f10f1398f0428960320d7
```

---

## 4. Disassembly & Mathematical Analysis

To understand why the numerical values and binary checksums diverge, we inspected the machine disassembly (`objdump -d`) of `sum_array` across the three shared libraries.

### 4.1 Target `opt2` (`-O2`): Sequential Scalar Loop (Unrolled by 2)

```assembly
0000000000001100 <sum_array>:
    1100: endbr64
    1104: test   %rsi,%rsi
    1107: je     1140 <sum_array+0x40>
    1109: lea    (%rdi,%rsi,4),%rax
    110d: and    $0x1,%esi
    1110: pxor   %xmm0,%xmm0
    1114: je     1128 <sum_array+0x28>
    1116: addss  (%rdi),%xmm0
    111a: add    $0x4,%rdi
    111e: cmp    %rax,%rdi
    1121: je     1145 <sum_array+0x45>
    1123: nopl   0x0(%rax,%rax,1)
    1128: addss  (%rdi),%xmm0
    112c: add    $0x8,%rdi
    1130: addss  -0x4(%rdi),%xmm0
    1135: cmp    %rax,%rdi
    1138: jne    1128 <sum_array+0x28>
    113a: ret
```

In `-O2`, GCC maintains strict IEEE 754 conformance:
- It unrolls the loop by a factor of 2 (lines `1128`–`1130`).
- It uses scalar single-precision addition (`addss`), accumulating strictly into `%xmm0`.
- Because addition is not reassociated, each array element is added sequentially: `total = ((total + arr[0]) + arr[1]) + ...`.

### 4.2 Target `opt3` (`-O3`): Sequential Scalar Loop (Unrolled by 4)

```assembly
0000000000001100 <sum_array>:
    1100: endbr64
    1104: mov    %rdi,%rcx
    1107: test   %rsi,%rsi
    110a: je     1188 <sum_array+0x88>
    ...
    1130: addss  (%rax),%xmm0
    1134: add    $0x10,%rax
    1138: addss  -0xc(%rax),%xmm0
    113d: addss  -0x8(%rax),%xmm0
    1142: addss  -0x4(%rax),%xmm0
    1147: cmp    %rdx,%rax
    114a: jne    1130 <sum_array+0x30>
```

In `-O3`, GCC aggressively unrolls the loop by a factor of 4 (lines `1130`–`1142`). However, because `-ffast-math` is **not** specified, GCC is strictly prohibited by ISO C / IEEE 754 standards from reordering floating-point operations. It must still emit four sequential `addss` instructions into `%xmm0`. 
Therefore, `-O3` produces the **exact same floating-point sum** as `-O2`, but produces a **completely different ELF binary** due to the unrolling factor and jump targets.

### 4.3 Target `fastmath` (`-O3 -ffast-math`): SIMD Vector Loop (`addps`) & Tree Reduction

```assembly
0000000000001100 <sum_array>:
    1100: endbr64
    ...
    1130: movups (%rax),%xmm2
    1133: add    $0x10,%rax
    1137: addps  %xmm2,%xmm0
    113a: cmp    %rdx,%rax
    113d: jne    1130 <sum_array+0x30>
    113f: movaps %xmm0,%xmm1
    1142: movhlps %xmm0,%xmm1
    1145: addps  %xmm0,%xmm1
    1148: movaps %xmm1,%xmm0
    114b: shufps $0x55,%xmm1,%xmm0
    114f: addps  %xmm1,%xmm0
```

With `-ffast-math` (which activates `-fassociative-math`, `-fno-signed-zeros`, `-freciprocal-math`, and `-fno-trapping-math`):
1. **SIMD Vectorization:** GCC treats floating-point addition as associative: $(a + b) + c \equiv a + (b + c)$.
2. **Parallel Lane Accumulation:** It uses packed single-precision vector instructions (`addps`) over 128-bit `%xmm0` registers, maintaining four independent accumulators in parallel:
   - Lane 0: `arr[0] + arr[4] + arr[8] + ...` (all the large `10000.0` terms)
   - Lane 1: `arr[1] + arr[5] + arr[9] + ...` (small terms `1e-4`, `5e-5`, etc.)
   - Lane 2: `arr[2] + arr[6] + arr[10] + ...` (small terms `1e-3`, `0.01`, etc.)
   - Lane 3: `arr[3] + arr[7] + arr[11] + ...` (small terms `2e-4`, `0.002`, etc.)
3. **Horizontal Vector Reduction:** After the loop finishes, lines `113f`–`114f` shuffle and add the four lanes together.

### 4.4 The Mechanism of Numerical Divergence: Precision Truncation

Single-precision IEEE 754 float32 uses 1 sign bit, 8 exponent bits, and 23 explicit fraction bits (giving 24 bits of significand precision, $\approx 7.22$ decimal digits).
- The unit of least precision (ULP) for a float around $X = 10,000$ is:
  $$\text{ULP}(10000) = 2^{\lfloor \log_2(10000) \rfloor - 23} = 2^{13 - 23} = 2^{-10} = \frac{1}{1024} \approx 0.0009765$$
- When the accumulator reaches $100,000$ or $1,000,000$, $\text{ULP}$ grows to $0.0078125$ and $0.0625$.
- In **`-O2` and `-O3` (Sequential)**:
  `10000.0` is added first. When the small terms ($10^{-4}, 10^{-3}, 5 \times 10^{-5}$) are subsequently added to the running sum, they are smaller than the significand's lowest bit and are **completely rounded away** (catastrophic truncation). Thus, none of the small terms contribute, and the sum ends up as exactly $10,000,000.00000000$ (`0x4b189680`).
- In **`fastmath` (Vectorized)**:
  The small terms accumulate in Lanes 1, 2, and 3 among themselves. Because their partial sums are small, no precision truncation occurs. The sum of all small terms across 1,000 repetitions equals:
  $$1000 \times (10^{-4} + 10^{-3} + 2 \times 10^{-4} + 5 \times 10^{-5} + 0.01 + 0.002 + 10^{-4}) = 13.45$$
  When this partial sum ($\approx 13.45$) is finally added to the $10,000,000$ accumulated in Lane 0 during the horizontal reduction, $\text{ULP}(10^7) = 2^{23-23} = 1.0$. The $13.45$ rounds to $13.0$, yielding:
  $$10,000,000.0 + 13.0 = 10,000,013.00000000 \quad (\text{hex } \mathbf{0x4b18968d})$$

The difference between `0x4b189680` and `0x4b18968d` is precisely 13 in the lowest significant bits, completely destroying bit-for-bit reproducibility.

---

## 5. Darnit Reproducibility Plugin Audit Outputs

We audited `experiments/02-c-ctypes` using darnit's `reproducibility` framework:

```bash
uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all
```

### 5.1 CLI Audit Output (`--show-all`)

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
INFO: Auditing /home/jd/open_Source/LFX/Ossf/darnit/experiments/02-c-ctypes with 5 controls
INFO: Project context for when-clause evaluation: {'platform': 'github', 'languages': []}

=== reproducibility Audit Results ===

Total: 5 | Pass: 0 | Fail: 0 | Warn: 5 | N/A: 0


--- Warnings ---
  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
  ⚠ RE-01.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
```

### 5.2 JSON Output Evidence (`-o json`)

```json
{
  "framework": "reproducibility",
  "results": [
    {
      "id": "RE-01.01",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 1,
      "sieve_phase": "manual",
      "evidence": {
        "lock_files_found": [],
        "loose_manifests_found": [],
        "verification_steps": [
          "Check that dependency files pin exact versions (not ranges like >=1.0)",
          "For Python: verify uv.lock or requirements.txt has exact versions",
          "For Node: verify package-lock.json or yarn.lock exists",
          "For Rust: verify Cargo.lock is committed",
          "For Go: verify go.sum exists and is committed"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "deterministic",
          "checks_performed": ["handler:repro_deps_pinned"],
          "result": {
            "outcome": "inconclusive",
            "message": "No dependency files found — cannot determine if deps are pinned",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": ["handler:manual"],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-02.01",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 2,
      "sieve_phase": "manual",
      "evidence": {
        "files_scanned": ["Makefile"],
        "violations_found": [],
        "deferred_found": [],
        "strong_signal": null,
        "verification_steps": [
          "Review all CI files (GitHub Actions, GitLab CI, CircleCI, Jenkinsfile, etc.) for network-fetch commands during build",
          "Review Makefiles, build scripts (scripts/build*, scripts/install*), and Dockerfiles for the same",
          "Check for curl, wget, pip install (without --no-index), npm install (without --ci), brew install in build steps",
          "Verify all dependencies come from the lock file, not fetched live at build time",
          "For a PASS without a strong signal, confirm via Witness attestation, Nix flake build, or Bazel network sandbox"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": ["handler:repro_hermetic_build"],
          "result": {
            "outcome": "inconclusive",
            "message": "No suspicious patterns found in 1 scanned file(s) — grep absence alone cannot confirm hermeticity; a strong signal (Witness, Nix, Bazel sandbox) or manual review is needed",
            "confidence": 0.4
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": ["handler:manual"],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-01.02",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 1,
      "sieve_phase": "manual",
      "evidence": {
        "env_files_found": [],
        "verification_steps": [
          "Check for one of: Dockerfile, flake.nix, .devcontainer/, Vagrantfile",
          "Verify it pins the base OS and tool versions",
          "Confirm the declared environment is actually used in CI"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "deterministic",
          "checks_performed": ["handler:repro_build_env_declared"],
          "result": {
            "outcome": "inconclusive",
            "message": "No build environment declaration found",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": ["handler:manual"],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-03.01",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 3,
      "sieve_phase": "manual",
      "evidence": {
        "files_checked": [],
        "reproducibility_signals": [],
        "verification_steps": [
          "Run the build twice and compare checksums of output artifacts",
          "Check reprotest or diffoscope output if available",
          "Look for timestamps or random seeds embedded in build output",
          "Verify SOURCE_DATE_EPOCH is set in CI to normalize timestamps"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": ["handler:repro_bit_for_bit"],
          "result": {
            "outcome": "inconclusive",
            "message": "No reproducibility signals found — manual verification required",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": ["handler:manual"],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-02.02",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 2,
      "sieve_phase": "manual",
      "evidence": {
        "files_checked": [],
        "provenance_signals": [],
        "verification_steps": [
          "Check CI workflow for sigstore/cosign signing steps",
          "Look for .intoto.jsonl or attestation files in releases",
          "Verify SLSA provenance is generated (slsa-github-generator or equivalent)"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": ["handler:repro_provenance_exists"],
          "result": {
            "outcome": "inconclusive",
            "message": "No provenance attestation steps found in CI workflows",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": ["handler:manual"],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    }
  ],
  "summary": {
    "total": 5,
    "pass": 0,
    "fail": 0,
    "warn": 5,
    "na": 0
  }
}
```

---

## 6. Evaluation Table

| Control ID | Name | Status | Agree? | Analysis |
|:---|:---|:---:|:---:|:---|
| **RE-01.01** | `DependenciesPinned` | **WARN** | **Disagree with Scope / Blind Spot** | Darnit only looks for higher-level language lock files (`uv.lock`, `Cargo.lock`, `package-lock.json`). Because this experiment uses pure Python + C with a Makefile, it found no lock files and returned `INCONCLUSIVE` (confidence 0.0), falling back to `WARN`. It **failed to audit C ABI dependencies**, shared libraries (`libc`, `libm`), or compiler toolchain versions. |
| **RE-01.02** | `BuildEnvDeclared` | **WARN** | **Disagree with Scope / Blind Spot** | Darnit looks strictly for `Dockerfile`, `flake.nix`, `shell.nix`, `.devcontainer`, `Vagrantfile`, `.tool-versions`, `.nvmrc`, and `.python-version`. It **completely ignores the `Makefile`** as an environment/build declaration and does not check whether the C compiler (`gcc`), sysroot, or libc version are declared or pinned. |
| **RE-02.01** | `HermeticBuild` | **WARN** | **Critical Disagree with Substance** | `repro_hermetic_build` found and scanned `Makefile`, but reported: *"No suspicious patterns found in 1 scanned file(s)"*. Why? Because its scanner **only checks for network commands** (`curl`, `wget`, `pip install`, `npm install`, `apt-get install`). It **completely ignored the `gcc` compiler invocations** and **completely ignored `-ffast-math`**, which directly destroys numerical reproducibility. |
| **RE-02.02** | `ProvenanceExists` | **WARN** | **Agree with Status** | Checks CI workflows for Sigstore / Cosign / SLSA. Because no CI workflows exist in this subproject, it safely returns `INCONCLUSIVE` (`WARN`). |
| **RE-03.01** | `BitForBitReproducible` | **WARN** | **Critical Disagree with Substance** | The handler checks CI workflows for `SOURCE_DATE_EPOCH`, `reprotest`, or `diffoscope`. It returns `INCONCLUSIVE` (`WARN`). In reality, **the build produces three completely non-reproducible binary shared libraries** and divergent numerical output under standard optimization flags, yet darnit provides zero insight into compiler flags or ELF reproducibility. |

---

## 7. Deep Analysis: Answers to NSF Proposal Questions

### 7.1 Does darnit notice there is a compilation step at all?
**No.** Darnit does not have any semantic or structural understanding of compilation.
- In `repro_hermetic_build_handler`, the function `_iter_build_files()` discovers `Makefile` because the filename matches `("Makefile", "GNUmakefile", "makefile")`.
- However, the file is treated merely as a text document scanned by `_scan_line()`.
- `_scan_line()` matches only against a tuple of network fetch strings:
  ```python
  _SUSPICIOUS_PATTERNS = (
      "curl ", "wget ", "pip install ", "npm install",
      "yarn install", "apt-get install", "brew install"
  )
  ```
- Darnit does not check if the Makefile contains compilation rules, whether a C/C++ compiler (`gcc`, `clang`, `cc`, `nvcc`, `rustc`) is invoked, whether object files (`.o`) or shared libraries (`.so`, `.dylib`, `.dll`) are generated, or whether source files (`sum.c`) are linked. It is entirely oblivious to the compilation step.

### 7.2 Does it mention the compiler or flags anywhere?
**No.** 
- Neither the string `gcc`, the compiler name, nor optimization flags (`-O2`, `-O3`, `-ffast-math`, `-fassociative-math`, `-Ofast`, `-march=native`, `-mtune=native`) appear anywhere in:
  - CLI stdout/stderr.
  - JSON evidence fields (`evidence`).
  - Pass history and check outcome messages (`message`).
  - Recommended manual verification steps (`verification_steps`).
- The verification steps for `RE-02.01` only state:
  *"Check for curl, wget, pip install (without --no-index), npm install (without --ci), brew install in build steps"*.
- The toolchain, compiler version, and compiler flags are completely absent from darnit's conceptual model.

### 7.3 Does `repro_hermetic_build` or `repro_build_env_declared` flag anything in the `Makefile`?
**No.**
1. **`repro_build_env_declared`**:
   Does not scan or open `Makefile` at all. Its lookup table is hardcoded to:
   ```python
   env_files = {
       "Dockerfile": "Docker",
       "flake.nix": "Nix flake",
       "shell.nix": "Nix shell",
       ".devcontainer": "Dev container",
       "Vagrantfile": "Vagrant",
       ".tool-versions": "asdf version manager",
       ".nvmrc": "Node version manager",
       ".python-version": "pyenv",
   }
   ```
   If a repository declares its toolchain via `Makefile` (`CC = gcc-13`, `CFLAGS = ...`), CMake (`CMakeLists.txt`, `CMakePresets.json`), or Meson (`meson.build`), `repro_build_env_declared` completely ignores them and returns `INCONCLUSIVE` (confidence 0.0).
2. **`repro_hermetic_build`**:
   Opens `Makefile`, strips comments, and runs `_scan_line()` on each line:
   - Line 1: `CC ?= gcc` $\rightarrow$ classified as `"safe"`.
   - Line 2: `CFLAGS_COMMON = -fPIC -shared` $\rightarrow$ classified as `"safe"`.
   - Line 7: `$(CC) -O2 $(CFLAGS_COMMON) sum.c -o libsum.so` $\rightarrow$ classified as `"safe"`.
   - Line 10: `$(CC) -O3 $(CFLAGS_COMMON) sum.c -o libsum.so` $\rightarrow$ classified as `"safe"`.
   - Line 13: `$(CC) -O3 -ffast-math $(CFLAGS_COMMON) sum.c -o libsum.so` $\rightarrow$ classified as `"safe"`.
   
   Because no network tokens match, `repro_hermetic_build` records `violations_found: []` and returns:
   `"No suspicious patterns found in 1 scanned file(s) — grep absence alone cannot confirm hermeticity; a strong signal (Witness, Nix, Bazel sandbox) or manual review is needed"`.
   It does not flag `-ffast-math` or unpinned `gcc`.

---

## 8. Repo Hygiene & Idempotency Logs

### 8.1 Repo Hygiene Verification (`git status --porcelain`)

We verified whether running `darnit audit` produces any side-effect files (caches, temp files, or build artifacts).

#### Before Auditing:
```bash
$ git status --porcelain experiments/02-c-ctypes
?? experiments/02-c-ctypes/
```

#### During Auditing:
Executed multiple runs of `darnit audit experiments/02-c-ctypes --framework reproducibility --show-all` and with `-o json`.

#### After Auditing:
```bash
$ git status --porcelain experiments/02-c-ctypes
?? experiments/02-c-ctypes/
```
No `.cache`, `.darnit`, or temporary artifacts were created in `experiments/02-c-ctypes/`. Repo hygiene is **verified clean**.

### 8.2 Audit Idempotency (3 Consecutive Runs)

We ran `darnit audit` three consecutive times against the unchanged `experiments/02-c-ctypes` directory.

#### Trial 1: Standard Invocations (Randomized Python Hash Seed)
```bash
uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_raw1.txt 2>&1
uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_raw2.txt 2>&1
uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_raw3.txt 2>&1

diff -u /tmp/audit_e2_raw1.txt /tmp/audit_e2_raw2.txt
```

**Diff Output:**
```diff
--- /tmp/audit_e2_raw1.txt
+++ /tmp/audit_e2_raw2.txt
@@ -20,8 +20,8 @@
 --- Warnings ---
-  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-01.02: WARN - Could not automatically verify - manual verification required
-  ⚠ RE-01.01: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-01.01: WARN - Could not automatically verify - manual verification required
```

*Finding:* This confirms **Bug Report #2 from Experiment 1**: `packages/darnit/src/darnit/config/merger.py:424` iterates over an unordered Python `set`, which varies randomly between process invocations according to `PYTHONHASHSEED`.

#### Trial 2: Deterministic Hash Seed (`PYTHONHASHSEED=0`)
```bash
PYTHONHASHSEED=0 uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_seed1.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_seed2.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/02-c-ctypes --framework reproducibility --show-all > /tmp/audit_e2_seed3.txt 2>&1

diff -u /tmp/audit_e2_seed1.txt /tmp/audit_e2_seed2.txt && diff -u /tmp/audit_e2_seed2.txt /tmp/audit_e2_seed3.txt
```

**Diff Output:**
```text
(0 differences — 100% byte-for-byte identical across runs)
```

---

## 9. Bug Reports Formatted for `darnitdevorg/darnit`

### Bug Report 4: `repro_hermetic_build` ignores compiler invocations and non-deterministic compiler flags in Makefiles and build scripts

```markdown
### Summary
`repro_hermetic_build` scans Makefiles, build scripts, and Dockerfiles, but only checks for network fetch commands (`curl`, `wget`, `pip install`, etc.). It completely ignores compiler invocations (`gcc`, `clang`, `cc`, `g++`, `rustc`) and fails to detect non-deterministic optimization flags (e.g. `-ffast-math`, `-Ofast`, `-fassociative-math`, `-march=native`, `-mtune=native`) or missing debug/path prefix maps (`-fdebug-prefix-map`, `-ffile-prefix-map`).

### Environment
- darnit version: dev / main branch
- Plugin: `darnit-reproducibility` v0.1.0
- Target: C / C++ compiled extensions (Makefiles, CMake, Meson)

### Steps to Reproduce
1. Create a `Makefile` that compiles C code with `-ffast-math`:
   ```makefile
   all:
       gcc -O3 -ffast-math -fPIC -shared sum.c -o libsum.so
   ```
2. Run `darnit audit . --framework reproducibility --show-all`.

### Expected Behavior
`repro_hermetic_build` or `repro_bit_for_bit` should detect that compilation is occurring and warn/fail when non-deterministic or non-associative floating-point flags like `-ffast-math` or machine-dependent flags like `-march=native` are specified without build isolation or deterministic constraints.

### Actual Behavior
`repro_hermetic_build` returns `INCONCLUSIVE` (confidence 0.4, converted to `WARN`):
```text
"No suspicious patterns found in 1 scanned file(s) — grep absence alone cannot confirm hermeticity; a strong signal (Witness, Nix, Bazel sandbox) or manual review is needed"
```
No mention of `gcc`, `-ffast-math`, or compilation steps is made in the evidence or output.

### Proposed Enhancement
In `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`:
1. Add a scanner for non-deterministic compiler flags in build files:
   ```python
   _NON_DETERMINISTIC_COMPILER_FLAGS = (
       "-ffast-math",
       "-Ofast",
       "-fassociative-math",
       "-march=native",
       "-mtune=native",
   )
   ```
2. If any of these flags are detected in `Makefile` or build scripts, flag them as an explicit reproducibility violation or high-risk warning.
```

---

### Bug Report 5: `repro_build_env_declared` ignores Makefiles, toolchain files, and native C/C++ compiler definitions

```markdown
### Summary
`repro_build_env_declared` returns `INCONCLUSIVE` ("No build environment declaration found") for repositories that build native C/C++ software with `Makefile`, `CMakeLists.txt`, `CMakePresets.json`, or `meson.build`, because its detection dictionary is limited to container, Nix, and interpreted language version files.

### Steps to Reproduce
1. Create a C project containing `Makefile` with toolchain definitions (`CC = gcc-13`, `CFLAGS = ...`).
2. Run `darnit audit . --framework reproducibility`.

### Actual Behavior
`repro_build_env_declared` reports:
```text
"No build environment declaration found"
```
Its `evidence.verification_steps` only prompts the user for:
```text
"Check for one of: Dockerfile, flake.nix, .devcontainer/, Vagrantfile"
```

### Proposed Enhancement
Extend `repro_build_env_declared_handler` to recognize native build toolchain declarations:
1. Support checking `CMakePresets.json` or CMake toolchain files (`CMAKE_TOOLCHAIN_FILE`).
2. Check for explicit compiler specifications in `Makefile` (e.g. pinned compiler versions or sysroot definitions).
3. Update `verification_steps` to mention C/C++ compiler toolchain pinning when C source files (`.c`, `.cpp`, `.h`) are present in the project context.
```

---

### Bug Report 6: `repro_deps_pinned` lacks inspection for C/C++ library dependencies and system pkg-config packages

```markdown
### Summary
`repro_deps_pinned` only checks for higher-level package manager lock files (`uv.lock`, `poetry.lock`, `Cargo.lock`, `package-lock.json`, etc.). For projects containing C/C++ code, native shared library dependencies (e.g. `libc`, `libblas`, `libssl`, `pkg-config`) are completely uninspected, leading to `INCONCLUSIVE` (WARN) even if unpinned system libraries or C ABI dependencies are present.

### Proposed Enhancement
1. When `c` or `cpp` is detected in `ctx.project_context["languages"]`, check for C/C++ dependency management manifests:
   - Conan (`conan.lock`, `conanfile.txt`)
   - vcpkg (`vcpkg.json`, `vcpkg-configuration.json`)
   - Meson wrap files (`subprojects/*.wrap`)
   - `pkg-config` / `.pc` version constraints in Makefiles
2. Provide specific verification guidance in `verification_steps` addressing system C shared library ABI stability and toolchain pinning.
```
