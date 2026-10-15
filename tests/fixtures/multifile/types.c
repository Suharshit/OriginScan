// Multi-file fixture: type definitions and factory functions.

#include "types.h"
#include <string.h>

Record create_record(int id, const char* name) {
    Record r;
    r.id = id;
    strncpy(r.name, name, sizeof(r.name) - 1);
    r.name[sizeof(r.name) - 1] = '\0';
    return r;
}
