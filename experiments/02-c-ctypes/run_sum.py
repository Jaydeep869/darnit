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
