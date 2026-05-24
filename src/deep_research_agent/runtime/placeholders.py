from __future__ import annotations

from deep_research_agent.domain.state import ResearchGraphState


async def planner_node(state: ResearchGraphState) -> ResearchGraphState:
    raise NotImplementedError("Planner node is reserved for a later implementation phase.")


async def search_node(state: ResearchGraphState) -> ResearchGraphState:
    raise NotImplementedError("Search node is reserved for a later implementation phase.")


async def extract_node(state: ResearchGraphState) -> ResearchGraphState:
    raise NotImplementedError("Extract node is reserved for a later implementation phase.")


async def reflect_node(state: ResearchGraphState) -> ResearchGraphState:
    raise NotImplementedError("Reflect node is reserved for a later implementation phase.")


async def synthesize_node(state: ResearchGraphState) -> ResearchGraphState:
    raise NotImplementedError("Synthesize node is reserved for a later implementation phase.")
