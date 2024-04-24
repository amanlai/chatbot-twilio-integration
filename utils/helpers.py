from zipfile import ZipFile
from io import BytesIO
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import ConnectionFailure
import certifi
from os import getenv
from .agents import get_agent_executor as executor

mongo_uri = getenv("MONGO_URI")
persist_directory = getenv("PERSIST_DIRECTORY", "db")


def init_connection():
    try:
        client = MongoClient(
            mongo_uri,
            server_api=ServerApi('1'),
            tlsCAFile=certifi.where()
        )
        print("Connection to MongoDB successful")
    except ConnectionFailure as e:
        print(f"Connection failed: {e}")
        return
    return client


def copy_from_collection(collection):
    # get list of attributes from MongoDB
    index_files, system_message, temperature = [
        next(collection.find({key: {"$exists": True}}), {}).get(key) 
        for key in ("index_files", "system_message", "temperature")
    ]
    # read the archived index files from mongodb into a binary stream
    index_files = BytesIO(index_files)
    # extract the index files into the persist directory
    with ZipFile(index_files) as zip_file:
        zip_file.extractall(persist_directory)
    # now that we have the index files stored in persist directory
    # we can get the vector stores from them
    vector_store = FAISS.load_local(
        persist_directory, 
        OpenAIEmbeddings(), 
        allow_dangerous_deserialization=True
    )
    return vector_store, system_message, temperature


def get_agent_executor(collection):
    """
    A convenience function that copies data from collection and
    builds the agent executor from them and returns it
    """
    vs, sys_msg, temp = copy_from_collection(collection)
    return executor(vs, sys_msg, temp)