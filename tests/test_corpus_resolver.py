"""Tests for CorpusResolver on P4's multi-file fixture, with a made-up AI body."""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.builders import PathResolver, build_context
from originscan.context.callgraph import CallGraph
from originscan.context.index import RepoIndex
from originscan.context.tokens import WhitespaceCounter
from originscan.exp.corpus import CorpusResolver, VersionSource

MULTIFILE = Path(__file__).parent / "fixtures" / "multifile"
UTILS = MULTIFILE / "utils.c"

# Made-up AI body for compute_hash: different code, one line shorter than the
# original, and it calls a same-file helper (log_message) the original does not.
AI_BODY = """{
    /* AI version */
    int h = 7;
    log_message("hashing");
    return h ^ r->id;
}"""


@pytest.fixture()
def versions() -> dict[str, VersionSource]:
    return {
        "compute_hash-human": VersionSource("human", "compute_hash", "utils.c", UTILS),
        "compute_hash-ai": VersionSource(
            "ai", "compute_hash", "utils.c", UTILS, ai_body=AI_BODY
        ),
    }


@pytest.fixture()
def resolver(versions: dict[str, VersionSource]):
    with CorpusResolver(versions) as r:
        yield r


@pytest.fixture(scope="module")
def index() -> RepoIndex:
    return RepoIndex.build(MULTIFILE, commit="test_corpus_resolver")


@pytest.fixture(scope="module")
def graph(index: RepoIndex) -> CallGraph:
    return CallGraph.build(index)


def context(resolver, version_id, level, index=None, graph=None):
    return build_context(
        version_id, level, resolver=resolver, counter=WhitespaceCounter(),
        index=index, graph=graph,
    )


# -----------------------------------------------------------------------
# Human versions: the original file
# -----------------------------------------------------------------------


def test_human_reads_original_file(resolver: CorpusResolver) -> None:
    target, symbols = resolver.resolve("compute_hash-human")
    ref_target, ref_symbols = PathResolver().resolve(f"compute_hash@{UTILS}")
    assert target.text == ref_target.text
    assert [(s.kind, s.name, s.text) for s in symbols] == [
        (s.kind, s.name, s.text) for s in ref_symbols
    ]
    # Labelled with the repo-relative path, so IDs match the repo's call graph
    assert target.file == "utils.c"


# -----------------------------------------------------------------------
# AI versions: AI body swapped into a temp copy
# -----------------------------------------------------------------------


def test_ai_swaps_only_the_body(resolver: CorpusResolver) -> None:
    original = UTILS.read_bytes()
    target, symbols = resolver.resolve("compute_hash-ai")

    assert target.text.startswith("int compute_hash(Record* r) {")  # signature kept
    assert "/* AI version */" in target.text
    assert "r->name[i]" not in target.text  # original body gone

    # Every other symbol in the file is unchanged
    _, human_symbols = resolver.resolve("compute_hash-human")
    others = {(s.kind, s.name, s.text) for s in symbols if s.name != "compute_hash"}
    human_others = {(s.kind, s.name, s.text) for s in human_symbols if s.name != "compute_hash"}
    assert others == human_others

    assert UTILS.read_bytes() == original  # original file never written


def test_ai_temp_copy_is_outside_repo_and_removed_on_close(
    versions: dict[str, VersionSource],
) -> None:
    resolver = CorpusResolver(versions)
    copy = resolver.swapped_copy("compute_hash-ai")
    assert copy.exists()
    assert copy.suffix == ".c"
    assert MULTIFILE.resolve() not in copy.resolve().parents
    resolver.close()
    assert not copy.exists()


def test_swap_keeps_crlf_line_endings(tmp_path: Path) -> None:
    src = tmp_path / "crlf.c"
    src.write_bytes(b"int f(int x) {\r\n    return x;\r\n}\r\n")
    v = VersionSource("ai", "f", "crlf.c", src, ai_body="{\n    return x + 1;\n}")
    with CorpusResolver({"f-ai": v}) as r:
        swapped = r.swapped_copy("f-ai").read_bytes()
    assert swapped == b"int f(int x) {\r\n    return x + 1;\r\n}\r\n"


# -----------------------------------------------------------------------
# build_context at every level, for both versions
# -----------------------------------------------------------------------


@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
@pytest.mark.parametrize("version_id", ["compute_hash-human", "compute_hash-ai"])
def test_build_context_all_levels(
    resolver: CorpusResolver,
    index: RepoIndex,
    graph: CallGraph,
    version_id: str,
    level: str,
) -> None:
    ctx = context(resolver, version_id, level, index, graph)
    assert ctx["tokens"] > 0
    assert ctx["items"][0].startswith("function:compute_hash@utils.c:")
    assert ("/* AI version */" in ctx["text"]) == version_id.endswith("-ai")


def test_ai_l2_follows_the_ai_body(resolver: CorpusResolver) -> None:
    """L2 helpers come from the AI body: it calls log_message, the original does not."""
    ai = context(resolver, "compute_hash-ai", "L2")
    human = context(resolver, "compute_hash-human", "L2")
    assert any("log_message" in item for item in ai["items"])
    assert not any("log_message" in item for item in human["items"])


def test_human_l3_includes_callers(
    resolver: CorpusResolver, index: RepoIndex, graph: CallGraph
) -> None:
    ctx = context(resolver, "compute_hash-human", "L3", index, graph)
    assert any(item.startswith("function:main@main.c") for item in ctx["items"])


@pytest.mark.xfail(
    strict=True,
    reason="Known gap: the CallGraph is built over the original repo, so an AI "
    "version's function ID (new line range) is not in it and L3 drops its callers.",
)
def test_ai_l3_includes_callers(
    resolver: CorpusResolver, index: RepoIndex, graph: CallGraph
) -> None:
    ctx = context(resolver, "compute_hash-ai", "L3", index, graph)
    assert any(item.startswith("function:main@main.c") for item in ctx["items"])


# -----------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------


def test_ai_version_needs_body() -> None:
    with pytest.raises(ValueError):
        VersionSource("ai", "compute_hash", "utils.c", UTILS)


def test_human_version_rejects_body() -> None:
    with pytest.raises(ValueError):
        VersionSource("human", "compute_hash", "utils.c", UTILS, ai_body=AI_BODY)


def test_body_must_be_a_block() -> None:
    with pytest.raises(ValueError):
        VersionSource("ai", "compute_hash", "utils.c", UTILS, ai_body="return 0;")


def test_unknown_version_id(resolver: CorpusResolver) -> None:
    with pytest.raises(ValueError, match="unknown version_id"):
        resolver.resolve("nope")


def test_missing_function() -> None:
    v = VersionSource("ai", "no_such_fn", "utils.c", UTILS, ai_body="{ return 0; }")
    with CorpusResolver({"x": v}) as r, pytest.raises(ValueError, match="found 0"):
        r.resolve("x")
