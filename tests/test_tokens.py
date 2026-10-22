"""Tests for originscan.context.tokens — token counting."""

from __future__ import annotations

import pytest

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
    @pytest.mark.requires_tiktoken
    def test_tiktoken_is_token_counter(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        assert isinstance(counter, TokenCounter)

    def test_whitespace_is_token_counter(self) -> None:
        counter = WhitespaceCounter()
        assert isinstance(counter, TokenCounter)


# -----------------------------------------------------------------------
# TiktokenCounter
# -----------------------------------------------------------------------


@pytest.mark.requires_tiktoken
class TestTiktokenCounter:
    def test_empty_string(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        assert counter.count("") == 0

    def test_single_word(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        result = counter.count("hello")
        assert result >= 1

    def test_code_snippet(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        code = "int main() { return 0; }"
        result = counter.count(code)
        assert result > 0

    def test_name(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        assert counter.name == "tiktoken:cl100k_base"

    def test_custom_encoding(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter("o200k_base")
        assert "o200k_base" in counter.name
        assert counter.count("hello world") > 0

    def test_deterministic(self, use_tiktoken: None) -> None:
        counter = TiktokenCounter()
        text = "void foo(int x) { return x + 1; }"
        assert counter.count(text) == counter.count(text)

    def test_longer_text_more_tokens(self, use_tiktoken: None) -> None:
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
    @pytest.mark.requires_tiktoken
    def test_default_is_tiktoken(self, use_tiktoken: None) -> None:
        counter = create_counter()
        assert isinstance(counter, TiktokenCounter)

    def test_whitespace_by_name(self) -> None:
        counter = create_counter("whitespace")
        assert isinstance(counter, WhitespaceCounter)

    @pytest.mark.requires_tiktoken
    def test_custom_encoding(self, use_tiktoken: None) -> None:
        counter = create_counter("o200k_base")
        assert isinstance(counter, TiktokenCounter)
        assert "o200k_base" in counter.name

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ORIGINSCAN_TOKENIZER env var overrides the name argument."""
        monkeypatch.setenv("ORIGINSCAN_TOKENIZER", "whitespace")
        counter = create_counter("cl100k_base")
        assert isinstance(counter, WhitespaceCounter)
