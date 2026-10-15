// Multi-file fixture: shared types header.

#ifndef TYPES_H
#define TYPES_H

#define STATUS_OK 0
#define STATUS_ERROR 1

typedef struct {
    int id;
    char name[64];
} Record;

// Forward declarations
Record create_record(int id, const char* name);
int process_and_validate(Record* r);
int compute_hash(Record* r);
void log_message(const char* msg);
void print_result(int code);

#endif
