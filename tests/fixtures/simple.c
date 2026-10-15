// Test fixture — simple C file with various symbol types.
// Used by tests to verify parser extraction.

#include <stdio.h>
#include <stdlib.h>

#define BUFFER_SIZE 256
#define MAX(a, b) ((a) > (b) ? (a) : (b))

typedef unsigned int uint;

typedef struct {
    int id;
    char name[BUFFER_SIZE];
    double value;
} Record;

enum Status {
    STATUS_OK = 0,
    STATUS_ERROR = 1,
    STATUS_PENDING = 2
};

static int global_counter = 0;

static int internal_helper(int x) {
    return x * 2 + global_counter;
}

int process_record(Record* rec) {
    if (rec == NULL) {
        return STATUS_ERROR;
    }
    rec->value = internal_helper(rec->id);
    global_counter++;
    return STATUS_OK;
}

void print_record(const Record* rec) {
    printf("Record[%d]: %s = %.2f\n", rec->id, rec->name, rec->value);
}

int main(int argc, char* argv[]) {
    Record r = {1, "test", 0.0};

    int status = process_record(&r);
    if (status == STATUS_OK) {
        print_record(&r);
    }

    int m = MAX(r.id, global_counter);
    printf("Max: %d\n", m);

    return 0;
}
