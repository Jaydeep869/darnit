"""Experiment 1: Deterministic NumPy under OpenBLAS thread reduction.

This experiment tests numerical associativity and bit-for-bit reproducibility
under varied OpenBLAS thread counts (OPENBLAS_NUM_THREADS).
"""

import hashlib
import os
import sys
import time
import numpy as np


def main() -> None:
    thread_env = os.environ.get("OPENBLAS_NUM_THREADS", "unset (default)")
    omp_env = os.environ.get("OMP_NUM_THREADS", "unset")
    
    # 1. Fix seed for reproducibility
    seed = 42
    np.random.seed(seed)

    # 2. Generate large float32 matrices (2500 x 2500)
    dim = 2500
    t0 = time.perf_counter()
    a = np.random.rand(dim, dim).astype(np.float32)
    b = np.random.rand(dim, dim).astype(np.float32)

    # 3. Perform reduction operation sensitive to floating-point associativity
    # Matrix multiplication (sgemm) decomposes across BLAS worker threads.
    # OpenBLAS thread chunking reorders floating-point accumulations.
    c = np.dot(a, b)

    # Column summation reduction across axis 0
    result = np.sum(c, axis=0)
    elapsed = time.perf_counter() - t0

    # 4. Compute cryptographic SHA-256 digest of exact result buffer bytes
    result_bytes = result.tobytes()
    digest = hashlib.sha256(result_bytes).hexdigest()

    # Output details
    print(f"Matrix Dimension: {dim}x{dim}, dtype={result.dtype}")
    print(f"Random Seed: {seed}")
    print(f"OPENBLAS_NUM_THREADS: {thread_env}")
    print(f"OMP_NUM_THREADS: {omp_env}")
    print(f"Elapsed Time: {elapsed:.4f}s")
    print(f"SHA-256 Digest: {digest}")


if __name__ == "__main__":
    main()
