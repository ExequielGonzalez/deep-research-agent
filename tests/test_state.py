import pytest
from langgraph.graph import END, START, StateGraph

from deep_research_agent.domain.models import ResearchRequest, SearchProvider, SourceRecord
from deep_research_agent.domain.state import ResearchGraphState, build_initial_state, merge_notes, merge_sources


def test_build_initial_state_sets_iteration_guards():
    request = ResearchRequest(query="Map AI chip vendors")
    state = build_initial_state("thread-1", request, max_iterations=7)

    assert state["thread_id"] == "thread-1"
    assert state["request"].query == "Map AI chip vendors"
    assert state["iteration_count"] == 0
    assert state["max_iterations"] == 7


def test_note_and_source_reducers_preserve_prior_data():
    source_a = SourceRecord(source_id="a", title="Alpha", url="https://alpha.example", provider=SearchProvider.TAVILY, snippet="v1")
    updated_source_a = source_a.model_copy(update={"snippet": "v2"})
    source_b = SourceRecord(source_id="b", title="Beta", url="https://beta.example", provider=SearchProvider.SERPER)

    merged_notes = merge_notes(["first note"], ["first note", "second note"])
    merged_sources = merge_sources([source_a], [updated_source_a, source_b])

    assert merged_notes == ["first note", "second note"]
    assert [source.source_id for source in merged_sources] == ["a", "b"]
    assert merged_sources[0].snippet == "v2"


def test_source_reducer_deduplicates_by_canonical_url_and_merges_task_ids():
    source_a = SourceRecord(
        source_id="src-1",
        title="Alpha",
        url="https://alpha.example?utm_source=x",
        canonical_url="https://alpha.example",
        provider=SearchProvider.TAVILY,
        task_ids=["task-1"],
    )
    source_b = SourceRecord(
        source_id="src-2",
        title="Alpha duplicate",
        url="https://alpha.example?ref=dup",
        canonical_url="https://alpha.example",
        provider=SearchProvider.SERPER,
        task_ids=["task-2"],
        snippet="updated snippet",
    )

    merged_sources = merge_sources([source_a], [source_b])

    assert len(merged_sources) == 1
    assert merged_sources[0].source_id == "src-1"
    assert merged_sources[0].snippet == "updated snippet"
    assert merged_sources[0].task_ids == ["task-1", "task-2"]


@pytest.mark.asyncio
async def test_langgraph_state_uses_accumulating_reducers():
    source_a = SourceRecord(source_id="a", title="Alpha", url="https://alpha.example", provider=SearchProvider.TAVILY, snippet="v1")
    source_b = SourceRecord(source_id="b", title="Beta", url="https://beta.example", provider=SearchProvider.SERPER)
    updated_source_a = source_a.model_copy(update={"snippet": "v2"})

    async def first(_: ResearchGraphState):
        return {"sources": [source_a], "notes": ["first"]}

    async def second(_: ResearchGraphState):
        return {"sources": [updated_source_a, source_b], "notes": ["first", "second"]}

    builder = StateGraph(ResearchGraphState)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    app = builder.compile()

    result = await app.ainvoke(build_initial_state("thread-2", ResearchRequest(query="What changed?"), max_iterations=3))

    assert [source.source_id for source in result["sources"]] == ["a", "b"]
    assert result["sources"][0].snippet == "v2"
    assert result["notes"] == ["first", "second"]
