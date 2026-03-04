"""
EVA's brain — a LangGraph StateGraph with ReAct tool loop.

Graph: START → think → tool calls? → yes → tools → think
                                    → no  → END
"""

from datetime import datetime

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from config import logger
from eva.actions.action_buffer import ActionBuffer
from eva.agent.constructor import PromptConstructor
from eva.tools import load_tools


def build_graph(model_name: str, action_buffer: ActionBuffer, checkpointer=None):
    """Build and compile EVA's brain graph.

    Returns a compiled StateGraph ready for ainvoke().
    """

    # Tools — auto-discovered from eva/tools/
    tools = load_tools(action_buffer)

    # LLM with tools bound
    llm = init_chat_model(model_name, temperature=0.8).bind_tools(tools)

    # Prompt constructor (loads persona + instructions from disk once)
    constructor = PromptConstructor()

    # -- Nodes ---------------------------------------------------------------

    async def think(state: MessagesState):
        """Inject fresh system prompt, call LLM."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        system = constructor.build_system(timestamp)

        response = await llm.ainvoke([SystemMessage(content=system)] + state["messages"])

        usage = response.usage_metadata
        if usage:
            logger.debug(
                f"LLM({model_name}) — "
                f"in: {usage['input_tokens']/1000:.1f}k  "
                f"out: {usage['output_tokens']/1000:.1f}k"
            )

        return {"messages": [response]}

    def route(state: MessagesState):
        """ReAct routing: tool calls → tools, otherwise → END."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "__end__"

    # -- Build graph ---------------------------------------------------------

    builder = StateGraph(MessagesState)
    builder.add_node("think", think)
    builder.add_node("tools", ToolNode(tools))

    builder.set_entry_point("think")
    builder.add_conditional_edges("think", route)
    builder.add_edge("tools", "think")

    return builder.compile(checkpointer=checkpointer)
