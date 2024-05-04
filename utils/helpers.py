from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_openai import OpenAIEmbeddings
from pymongo import MongoClient
# from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from os import getenv
from .agents import get_agent_executor as executor
from dotenv import load_dotenv
load_dotenv()

# async_mode_on = getenv("ASYNC_MODE_ON", 'True') == 'True'
mongo_uri = getenv("MONGO_URI")
database_name = getenv("DB_NAME", "documents")
config_db_name = getenv("CONFIG_VARS_DB", "config_vars")
business_name = getenv("BUSINESS_NAME")
index_name = getenv("VECTOR_SEARCH_INDEX_NAME", "business_description")
debug = getenv("DEBUG", 'False') == 'True'
local = getenv("LOCAL", 'False') == 'True'
default_temperature = float(getenv("TEMPERATURE", 0.1))
default_system_message = getenv("SYSTEM_MESSAGE", "")
search_type = getenv("SEARCH_TYPE", "similarity")
k = int(getenv("k", 5))


def init_connection():
    try:
        if local:
            from pymongo.server_api import ServerApi
            import certifi
            client = MongoClient(
                mongo_uri,
                server_api=ServerApi('1'),
                tlsCAFile=certifi.where()
            )
        else:
            # if async_mode_on:
            #     client = AsyncIOMotorClient(mongo_uri)
            # else:
            client = MongoClient(mongo_uri)
        if debug:
            print("Connection to MongoDB successful")
    except ConnectionFailure as e:
        print(f"Connection failed: {e}")
        return
    return client


def copy_from_collection(conn):

    # connect to mongodb collection
    db = conn[database_name]
    config_db = conn[config_db_name]
    collection = db[business_name]
    config_vars = config_db[business_name]

    # get vector store
    vector_store = MongoDBAtlasVectorSearch(
        collection=collection, 
        embedding=OpenAIEmbeddings(), 
        index_name=index_name
    )
    # get the retriever
    retriever = vector_store.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k}
    )

    # get list of attributes from MongoDB
    system_message = next(
        config_vars.find(
            {"system_message": {"$exists": True}}
        ), 
        {}
    ).get("system_message", default_system_message)
    temperature = next(
        config_vars.find(
            {"temperature": {"$exists": True}}
        ), 
        {}
    ).get("temperature", default_temperature)

    # system_message = (config_vars.find_one(
    #     {"system_message": {"$exists": True}}
    # ) or {}).get("system_message", default_system_message)
    # temperature = (await config_vars.find_one(
    #     {"temperature": {"$exists": True}}
    # ) or {}).get("temperature", default_temperature)

    if debug:
        # test_question = "What time is breakfast on sunday?"
        # print(f"Test question: {test_question}")
        # print(f"Test answer: {retriever.invoke(test_question)}")
        print(f"System message: {system_message}")
        print(f"Temperature: {temperature}")

    return retriever, system_message, temperature


def get_agent_executor(conn):
    """
    A convenience function that copies data from collection and
    builds the agent executor from them and returns it
    """
    retriever, sys_msg, temp = copy_from_collection(conn)
    return executor(retriever, sys_msg, temp)
