// Multi-file fixture: utility functions.
// Has a static helper to test ambiguity.

#include "types.h"
#include <stdio.h>
#include <string.h>

static void log_internal(const char* prefix, const char* msg) {
    printf("[%s] %s\n", prefix, msg);
}

void log_message(const char* msg) {
    log_internal("INFO", msg);
}

int process_and_validate(Record* r) {
    if (r == NULL) {
        log_message("null record");
        return STATUS_ERROR;
    }
    int val = compute_hash(r);
    if (val < 0) {
        return STATUS_ERROR;
    }
    return STATUS_OK;
}

int compute_hash(Record* r) {
    int hash = r->id * 31;
    for (int i = 0; r->name[i]; i++) {
        hash = hash * 31 + r->name[i];
    }
    return hash;
}
