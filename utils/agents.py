from os import getenv
from chainlit import AsyncLangchainCallbackHandler
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools.retriever import create_retriever_tool
from langchain_openai import ChatOpenAI
from .tools import get_tools
from .prompts import get_prompt

stream = getenv("STREAM", 'True') == 'True'
debug = getenv("DEBUG", 'False') == 'True'
model_name = getenv("MODEL_NAME", 'gpt-3.5-turbo')


def build_tools(retriever):
    """
    Creates the list of tools to be used by the Agent Executor
    """

    retriever_tool = create_retriever_tool(
        retriever,
        "search_document",
        ("""Searches and retrieves information from the vector store """
        """to answer questions whose answers can be found there."""),
    )

    tools = [*get_tools(), retriever_tool]
    return tools


def get_agent_executor(retriever, system_message, temperature):
    """
    Create a langchain agent executor
    """
    prompt = get_prompt(system_message)
    llm = ChatOpenAI(
        model=model_name, 
        temperature=temperature
    )
    tools = build_tools(retriever)
    agent = create_openai_tools_agent(
        llm=llm, 
        tools=tools, 
        prompt=prompt
    )
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=debug,
        max_iterations=15,
        handle_parsing_errors=True,
        return_intermediate_steps=debug,
        early_stopping_method='generate',
        callbacks=[AsyncLangchainCallbackHandler(stream_final_answer=stream)]
    )
    return agent_executor