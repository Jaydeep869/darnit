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
