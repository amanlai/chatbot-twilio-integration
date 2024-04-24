from os import getenv
import chainlit as cl
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from langchain_openai import ChatOpenAI
from .tools import get_tools
from .prompts import get_prompt

stream = getenv("STREAM", 'True') == 'True'
verbose = getenv("VERBOSE", 'True') == 'True'
model_name = getenv("MODEL_NAME", 'gpt-4-turbo')


def build_tools(vector_store, k=5):
    """
    Creates the list of tools to be used by the Agent Executor
    """
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )

    retriever_tool = create_retriever_tool(
        retriever,
        "search_document",
        """Searches and retrieves information from the vector store """
        """to answer questions whose answers can be found there.""",
    )

    tools = [*get_tools(), retriever_tool]
    return tools


def get_agent_executor(vector_store, system_message, temperature):
    """
    Create a langchain agent executor
    """
    prompt = get_prompt(system_message)
    llm = ChatOpenAI(model=model_name, temperature=temperature)
    tools = build_tools(vector_store)
    agent = create_openai_tools_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        max_iterations=15,
        handle_parsing_errors=True,
        early_stopping_method='generate',
        callbacks=[cl.AsyncLangchainCallbackHandler(stream_final_answer=stream)]
    )
    return agent_executor