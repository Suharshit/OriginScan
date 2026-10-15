// Test fixture — syntax errors to test error tolerance (PRD task 2.4).
// The parser must extract valid symbols despite the broken code.

#include <stdio.h>

#define GOOD_MACRO 42

typedef struct {
    int valid_field;
} ValidStruct;

// This function is valid
int good_function(int x) {
    return x + GOOD_MACRO;
}

// Intentionally broken syntax — missing closing brace
int broken_function(int x {
    return x;

// Another valid function after the error
void after_error(void) {
    printf("recovered\n");
}
