// Multi-file fixture: main entry point.
// Tests cross-file call graph resolution.

#include "utils.h"
#include "types.h"

int main(int argc, char* argv[]) {
    Record r = create_record(1, "test");
    int result = process_and_validate(&r);
    print_result(result);
    return 0;
}

void print_result(int code) {
    if (code == STATUS_OK) {
        log_message("Success");
    } else {
        log_message("Failed");
    }
}
