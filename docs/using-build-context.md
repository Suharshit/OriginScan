# Using build_context — Quick Start for P5

> P4 deliverable (PRD task 3.8). Shows how to call `build_context` at L1 and L2.

## Basic Usage

```python
from originscan.context.builders import build_context

# Slot ID format for PathResolver: "function_name@path/to/file.c"
ctx = build_context("process_record@src/vuln.c", level="L1")

print(ctx["text"])      # Prompt-ready code context
print(ctx["tokens"])    # Token count
print(ctx["items"])     # What was included
```

## Levels

```python
# L1 — function only
ctx_l1 = build_context("foo@src/a.c", "L1")

# L2 — function + same-file types, macros, globals, helpers
ctx_l2 = build_context("foo@src/a.c", "L2")

# L3 — not yet available (Phase 4)
```

## Custom Token Caps

```python
# Override cap for a single call
ctx = build_context("foo@src/a.c", "L2", cap=3000)

# Override caps per level
ctx = build_context("foo@src/a.c", "L2", caps={"L1": 1500, "L2": 5000, "L3": 12000})
```

## Custom Token Counter

```python
from originscan.context.tokens import create_counter

# Use a different tiktoken encoding
counter = create_counter("o200k_base")
ctx = build_context("foo@src/a.c", "L2", counter=counter)

# Use whitespace counting (fast, for testing)
from originscan.context.tokens import WhitespaceCounter
ctx = build_context("foo@src/a.c", "L1", counter=WhitespaceCounter())
```

## Lower-Level API

```python
from originscan.context.builders import build_l1, build_l2
from originscan.context.parser import parse_file
from originscan.context.tokens import create_counter

# Parse the file yourself
symbols = parse_file("src/a.c")
target = next(s for s in symbols if s.name == "foo")
counter = create_counter()

# Build L1
ctx = build_l1(target, counter, cap=2000)

# Build L2
ctx = build_l2(target, symbols, counter, cap=6000, per_item_limit=1500)
```

## Output Format

The `text` field uses clear delimiters:

```
// === TARGET FUNCTION (src/a.c:10-42) ===
int foo(int x) {
    return bar(x) + MAGIC_NUMBER;
}
// === FILE CONTEXT: types ===
typedef struct { int id; } Record;
// === FILE CONTEXT: macros ===
#define MAGIC_NUMBER 42
// === FILE CONTEXT: globals ===
static int counter = 0;
// === HELPER: bar (src/a.c:5-8) ===
static int bar(int x) { return x * 2; }
```

## Guarantees

1. **Token cap is a hard limit:** `ctx["tokens"] <= cap` always holds.
2. **Deterministic:** same input always produces the same output.
3. **No network calls:** context building is fully local.
4. **items list:** tells you exactly what was included (for debugging and reports).

## Integration with P5's Runner

```python
# P5 calls build_context with a slot_id from the dataset
from originscan.context.builders import build_context

for slot in dataset:
    for level in ["L1", "L2"]:
        ctx = build_context(slot.id, level)
        finding = detect(ctx, detector="gpt-4", run=1)
        results.append({"slot": slot.id, "level": level, **finding})
```

The `SlotResolver` protocol will be updated in Phase 5 to work with
P2's slot format. For now, use `function_name@file_path`.
