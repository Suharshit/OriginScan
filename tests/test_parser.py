"""Tests for originscan.context.parser — symbol extraction from C/C++."""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.parser import (
    C_LANGUAGE,
    CPP_LANGUAGE,
    Symbol,
    detect_language,
    parse_file,
    parse_source,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# -----------------------------------------------------------------------
# detect_language
# -----------------------------------------------------------------------


class TestDetectLanguage:
    def test_c_extensions(self) -> None:
        assert detect_language(Path("foo.c")) is C_LANGUAGE
        assert detect_language(Path("foo.h")) is C_LANGUAGE

    def test_cpp_extensions(self) -> None:
        for ext in (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"):
            assert detect_language(Path(f"foo{ext}")) is CPP_LANGUAGE

    def test_unknown_extension(self) -> None:
        assert detect_language(Path("foo.py")) is None
        assert detect_language(Path("foo.java")) is None


# -----------------------------------------------------------------------
# parse_source — simple C
# -----------------------------------------------------------------------


class TestParseSourceSimpleC:
    """Parse the simple.c fixture via parse_source."""

    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        src = (FIXTURES / "simple.c").read_text(encoding="utf-8")
        return parse_source(src, C_LANGUAGE, "tests/fixtures/simple.c")

    def test_extracts_functions(self, symbols: list[Symbol]) -> None:
        funcs = [s for s in symbols if s.kind == "function"]
        names = [f.name for f in funcs]
        assert "internal_helper" in names
        assert "process_record" in names
        assert "print_record" in names
        assert "main" in names

    def test_static_detection(self, symbols: list[Symbol]) -> None:
        helper = next(s for s in symbols if s.name == "internal_helper")
        assert helper.is_static is True

        main = next(s for s in symbols if s.name == "main")
        assert main.is_static is False

    def test_extracts_macros(self, symbols: list[Symbol]) -> None:
        macros = [s for s in symbols if s.kind == "macro"]
        names = [m.name for m in macros]
        assert "BUFFER_SIZE" in names
        assert "MAX" in names

    def test_extracts_typedefs(self, symbols: list[Symbol]) -> None:
        typedefs = [s for s in symbols if s.kind == "typedef"]
        names = [t.name for t in typedefs]
        assert "uint" in names
        assert "Record" in names

    def test_extracts_enum(self, symbols: list[Symbol]) -> None:
        enums = [s for s in symbols if s.kind == "enum"]
        names = [e.name for e in enums]
        assert "Status" in names

    def test_extracts_globals(self, symbols: list[Symbol]) -> None:
        globs = [s for s in symbols if s.kind == "global"]
        names = [g.name for g in globs]
        assert "global_counter" in names

    def test_global_is_static(self, symbols: list[Symbol]) -> None:
        gc = next(s for s in symbols if s.name == "global_counter")
        assert gc.is_static is True

    def test_line_numbers_are_positive(self, symbols: list[Symbol]) -> None:
        for s in symbols:
            assert s.start_line >= 1
            assert s.end_line >= s.start_line

    def test_deterministic_order(self, symbols: list[Symbol]) -> None:
        """Same input must produce identical output (design.md §0 rule 4)."""
        src = (FIXTURES / "simple.c").read_text(encoding="utf-8")
        symbols2 = parse_source(src, C_LANGUAGE, "tests/fixtures/simple.c")
        assert symbols == symbols2

    def test_text_is_nonempty(self, symbols: list[Symbol]) -> None:
        for s in symbols:
            assert len(s.text.strip()) > 0


# -----------------------------------------------------------------------
# parse_source — syntax errors (error tolerance)
# -----------------------------------------------------------------------


class TestErrorTolerance:
    """Parser must extract valid symbols despite parse errors (FR-4)."""

    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        src = (FIXTURES / "syntax_error.c").read_text(encoding="utf-8")
        return parse_source(src, C_LANGUAGE, "tests/fixtures/syntax_error.c")

    def test_no_crash(self, symbols: list[Symbol]) -> None:
        """Must not raise on broken syntax."""
        assert isinstance(symbols, list)

    def test_extracts_valid_function(self, symbols: list[Symbol]) -> None:
        names = [s.name for s in symbols if s.kind == "function"]
        assert "good_function" in names

    def test_extracts_macro_despite_error(self, symbols: list[Symbol]) -> None:
        macros = [s.name for s in symbols if s.kind == "macro"]
        assert "GOOD_MACRO" in macros

    def test_extracts_typedef_despite_error(self, symbols: list[Symbol]) -> None:
        typedefs = [s.name for s in symbols if s.kind == "typedef"]
        assert "ValidStruct" in typedefs


# -----------------------------------------------------------------------
# parse_source — #ifdef / macro-heavy
# -----------------------------------------------------------------------


class TestIfdefMacros:
    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        src = (FIXTURES / "ifdef_macros.c").read_text(encoding="utf-8")
        return parse_source(src, C_LANGUAGE, "tests/fixtures/ifdef_macros.c")

    def test_extracts_nested_macros(self, symbols: list[Symbol]) -> None:
        macros = [s.name for s in symbols if s.kind == "macro"]
        assert "BASE_VALUE" in macros
        assert "SCALE" in macros
        assert "OFFSET" in macros
        assert "CLAMP" in macros

    def test_extracts_ifdef_macros(self, symbols: list[Symbol]) -> None:
        macros = [s.name for s in symbols if s.kind == "macro"]
        # PLATFORM_NAME and MAX_ITEMS defined inside #ifdef/#ifndef
        assert "PLATFORM_NAME" in macros
        assert "MAX_ITEMS" in macros

    def test_extracts_functions(self, symbols: list[Symbol]) -> None:
        funcs = [s.name for s in symbols if s.kind == "function"]
        assert "compute_value" in funcs
        assert "print_platform" in funcs
        assert "reset_items" in funcs

    def test_extracts_struct(self, symbols: list[Symbol]) -> None:
        structs = [s.name for s in symbols if s.kind == "struct"]
        assert "Config" in structs

    def test_conditional_typedef(self, symbols: list[Symbol]) -> None:
        typedefs = [s.name for s in symbols if s.kind == "typedef"]
        assert "ulong" in typedefs
        # At least one real_t should be extracted (depends on which branch
        # tree-sitter picks without a preprocessor)
        assert "real_t" in typedefs


# -----------------------------------------------------------------------
# parse_source — static functions
# -----------------------------------------------------------------------


class TestStaticFunctions:
    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        src = (FIXTURES / "static_funcs.c").read_text(encoding="utf-8")
        return parse_source(src, C_LANGUAGE, "tests/fixtures/static_funcs.c")

    def test_all_functions_are_static(self, symbols: list[Symbol]) -> None:
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) >= 3
        for f in funcs:
            assert f.is_static is True, f"{f.name} should be static"

    def test_static_global(self, symbols: list[Symbol]) -> None:
        globs = [s for s in symbols if s.kind == "global"]
        state = next((g for g in globs if g.name == "state"), None)
        assert state is not None
        assert state.is_static is True


# -----------------------------------------------------------------------
# parse_source — C++
# -----------------------------------------------------------------------


class TestCppParsing:
    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        src = (FIXTURES / "cpp_class.cpp").read_text(encoding="utf-8")
        return parse_source(src, CPP_LANGUAGE, "tests/fixtures/cpp_class.cpp")

    def test_extracts_class_as_struct(self, symbols: list[Symbol]) -> None:
        """C++ classes are represented as struct kind."""
        structs = [s for s in symbols if s.kind == "struct"]
        names = [s.name for s in structs]
        assert "Point" in names

    def test_extracts_out_of_class_method(self, symbols: list[Symbol]) -> None:
        """Point::distanceTo defined outside the class."""
        funcs = [s for s in symbols if s.kind == "function"]
        names = [f.name for f in funcs]
        # Should find the qualified name or just "distanceTo"
        assert any("distanceTo" in n for n in names)

    def test_extracts_enum_class(self, symbols: list[Symbol]) -> None:
        enums = [s for s in symbols if s.kind == "enum"]
        names = [e.name for e in enums]
        assert "Color" in names

    def test_extracts_typedef(self, symbols: list[Symbol]) -> None:
        typedefs = [s for s in symbols if s.kind == "typedef"]
        names = [t.name for t in typedefs]
        assert "PointList" in names

    def test_static_function_in_namespace(self, symbols: list[Symbol]) -> None:
        funcs = [s for s in symbols if s.kind == "function"]
        static_funcs = [f for f in funcs if f.is_static]
        names = [f.name for f in static_funcs]
        assert "increment_count" in names

    def test_bounding_box_struct(self, symbols: list[Symbol]) -> None:
        structs = [s for s in symbols if s.kind == "struct"]
        names = [s.name for s in structs]
        assert "BoundingBox" in names


# -----------------------------------------------------------------------
# parse_file
# -----------------------------------------------------------------------


class TestParseFile:
    def test_parse_c_file(self) -> None:
        symbols = parse_file(FIXTURES / "simple.c")
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) >= 4

    def test_parse_cpp_file(self) -> None:
        symbols = parse_file(FIXTURES / "cpp_class.cpp")
        assert len(symbols) > 0

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_file(FIXTURES / "nonexistent.c")

    def test_unknown_extension(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized"):
            parse_file(FIXTURES / ".." / "test_parser.py")

    def test_file_path_in_symbol(self) -> None:
        symbols = parse_file(FIXTURES / "simple.c")
        for s in symbols:
            assert "simple.c" in s.file
