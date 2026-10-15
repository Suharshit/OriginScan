// Test fixture — preprocessor-heavy code with #ifdef blocks and nested macros.
// Exercises PRD tasks 2.2 and 2.6.

#include <stdio.h>

#define BASE_VALUE 10
#define SCALE(x) ((x) * 2)
#define OFFSET(x, y) (SCALE(x) + (y))
#define CLAMP(val, lo, hi) ((val) < (lo) ? (lo) : ((val) > (hi) ? (hi) : (val)))

#ifdef _WIN32
#define PLATFORM_NAME "Windows"
#else
#define PLATFORM_NAME "Unix"
#endif

typedef unsigned long ulong;

#ifdef USE_FLOAT
typedef float real_t;
#else
typedef double real_t;
#endif

struct Config {
    int base;
    real_t scale;
    char name[64];
};

#ifndef MAX_ITEMS
#define MAX_ITEMS 256
#endif

static int item_count = 0;

static void reset_items(void) {
    item_count = 0;
}

int compute_value(int input) {
    int scaled = SCALE(input);
    int offset = OFFSET(input, BASE_VALUE);
    return CLAMP(scaled + offset, 0, MAX_ITEMS);
}

#ifdef ENABLE_DEBUG
void debug_print(const struct Config* cfg) {
    printf("[DEBUG] base=%d scale=%.2f name=%s\n",
           cfg->base, cfg->scale, cfg->name);
}
#endif

void print_platform(void) {
    printf("Platform: %s\n", PLATFORM_NAME);
}
