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
