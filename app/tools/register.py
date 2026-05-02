from app.core.tool_registry import ToolRegistry
from app.tools.builtin_tools import (
    calculator,
    analyze_text,
    convert_units,
    get_weather,
    get_current_time,
    search_knowledge,
    CalculatorInput,
    KnowledgeSearchInput,
    TextAnalysisInput,
    UnitConversionInput,
    GetCurrentTimeInput,
    WeatherLookupInput,
)
from app.tools.memory_tools import (
    memory_append_session_summary,
    memory_read,
    MemoryAppendSessionSummaryInput,
    MemoryReadInput,
)
from app.tools.validator import create_tool_spec


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(create_tool_spec(
        name="calculator",
        description="Calculate a math expression and return the result.",
        model_cls=CalculatorInput,
        handler=calculator,
    ))

    registry.register(create_tool_spec(
        name="get_current_time",
        description="Get the current local time for a city.",
        model_cls=GetCurrentTimeInput,
        handler=get_current_time,
    ))

    registry.register(create_tool_spec(
        name="convert_units",
        description="Convert length, mass, or temperature values between units.",
        model_cls=UnitConversionInput,
        handler=convert_units,
    ))

    registry.register(create_tool_spec(
        name="analyze_text",
        description="Analyze text and return character, word, and line counts.",
        model_cls=TextAnalysisInput,
        handler=analyze_text,
    ))

    registry.register(create_tool_spec(
        name="get_weather",
        description="Get deterministic demo weather for a supported city.",
        model_cls=WeatherLookupInput,
        handler=get_weather,
    ))

    registry.register(create_tool_spec(
        name="search_knowledge",
        description="Search the local agent framework knowledge base.",
        model_cls=KnowledgeSearchInput,
        handler=search_knowledge,
    ))

    registry.register(create_tool_spec(
        name="memory_read",
        description=(
            "Read existing document memory only. Use this when the user asks to "
            "view, recall, retrieve, inspect, or search stored memory. Do not use "
            "this tool to remember, save, store, append, or record new information."
        ),
        model_cls=MemoryReadInput,
        handler=memory_read,
    ))

    registry.register(create_tool_spec(
        name="memory_append_session_summary",
        description=(
            "Save new information into session memory. Use this when the user asks "
            "to remember, save, store, record, keep in memory, note for later, or "
            "append a fact/preference/decision/summary to memory. This tool writes "
            "new memory; it is not for reading existing memory."
        ),
        model_cls=MemoryAppendSessionSummaryInput,
        handler=memory_append_session_summary,
        side_effect_policy="non_idempotent",
    ))

    return registry
