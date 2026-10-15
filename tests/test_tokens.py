"""Tests for originscan.context.tokens — token counting."""

from __future__ import annotations

from originscan.context.tokens import (
    TiktokenCounter,
    TokenCounter,
    WhitespaceCounter,
    create_counter,
)

# -----------------------------------------------------------------------
# Protocol conformance
# -----------------------------------------------------------------------


class TestProtocol:
    def test_tiktoken_is_token_counter(self) -> None:
        counter = TiktokenCounter()
        assert isinstance(counter, TokenCounter)

    def test_whitespace_is_token_counter(self) -> None:
        counter = WhitespaceCounter()
        assert isinstance(counter, TokenCounter)


# -----------------------------------------------------------------------
# TiktokenCounter
# -----------------------------------------------------------------------


class TestTiktokenCounter:
    def test_empty_string(self) -> None:
        counter = TiktokenCounter()
        assert counter.count("") == 0

    def test_single_word(self) -> None:
        counter = TiktokenCounter()
        result = counter.count("hello")
        assert result >= 1

    def test_code_snippet(self) -> None:
        counter = TiktokenCounter()
        code = "int main() { return 0; }"
        result = counter.count(code)
        assert result > 0

    def test_name(self) -> None:
        counter = TiktokenCounter()
        assert counter.name == "tiktoken:cl100k_base"

    def test_custom_encoding(self) -> None:
        counter = TiktokenCounter("o200k_base")
        assert "o200k_base" in counter.name
        assert counter.count("hello world") > 0

    def test_deterministic(self) -> None:
        counter = TiktokenCounter()
        text = "void foo(int x) { return x + 1; }"
        assert counter.count(text) == counter.count(text)

    def test_longer_text_more_tokens(self) -> None:
        counter = TiktokenCounter()
        short = "int x;"
        long = "int x; int y; int z; double w; float f; char c;"
        assert counter.count(long) > counter.count(short)


# -----------------------------------------------------------------------
# WhitespaceCounter
# -----------------------------------------------------------------------


class TestWhitespaceCounter:
    def test_empty_string(self) -> None:
        counter = WhitespaceCounter()
        assert counter.count("") == 0

    def test_single_word(self) -> None:
        counter = WhitespaceCounter()
        assert counter.count("hello") == 1

    def test_multiple_words(self) -> None:
        counter = WhitespaceCounter()
        assert counter.count("int main ( ) { }") == 6

    def test_name(self) -> None:
        counter = WhitespaceCounter()
        assert counter.name == "whitespace"

    def test_deterministic(self) -> None:
        counter = WhitespaceCounter()
        text = "some code here"
        assert counter.count(text) == counter.count(text)


# -----------------------------------------------------------------------
# Factory
# -----------------------------------------------------------------------


class TestCreateCounter:
    def test_default_is_tiktoken(self) -> None:
        counter = create_counter()
        assert isinstance(counter, TiktokenCounter)

    def test_whitespace_by_name(self) -> None:
        counter = create_counter("whitespace")
        assert isinstance(counter, WhitespaceCounter)

    def test_custom_encoding(self) -> None:
        counter = create_counter("o200k_base")
        assert isinstance(counter, TiktokenCounter)
        assert "o200k_base" in counter.name
