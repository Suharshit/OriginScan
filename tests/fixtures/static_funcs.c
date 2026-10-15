// Test fixture — static functions only (no public API).
// Tests is_static detection (PRD task 2.2).

#include <string.h>

static int state = 0;

static void set_state(int s) {
    state = s;
}

static int get_state(void) {
    return state;
}

static char* copy_string(const char* src) {
    size_t len = strlen(src);
    char* dst = (char*)malloc(len + 1);
    if (dst) {
        memcpy(dst, src, len + 1);
    }
    return dst;
}
