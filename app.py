import os
import sys
from re import sub, search
from pickle import dumps, loads
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from chainlit.server import app
from chainlit.context import init_http_context
from fastapi import Request
from twilio.rest import Client
from twilio.http.async_http_client import AsyncTwilioHttpClient
from utils.helpers import init_connection, get_agent_executor
load_dotenv()

port = int(os.getenv("PORT", 8000))
database_name = os.getenv("DB_NAME", "chattabot")

# twilio config
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_phone = os.getenv("TWILIO_PHONE")

# pattern to identify business name
pattern = r"I want to ask about ([\w\_\-\s]+)\.*"


# initialize variables
async def startup(business_name, to_phone_number=None):
    """
    Given a business name 
      - Make connection to MongoDB
      - Get relevant documents
      - Construct langchain agent executor

    Returns agent executor
    """
    agent_executor = None
    # initiate mongodb connection
    conn = await init_connection()
    # index into database
    db = conn[database_name]
    # only continue if the collection already exists in db
    if business_name in db.list_collection_names():
        # get data from mongodb
        collection = db[business_name]
        agent_executor = await get_agent_executor(collection)
        # initialize chat history for the phone number
        if to_phone_number is not None:
            db_chat_history = conn["chat_history"]
            coll_chat_history = db_chat_history[to_phone_number]
            coll_chat_history.delete_many({})
            coll_chat_history.insert_one(
                {"_id": business_name, "history": dumps([])}
            )
    # close db connection
    conn.close()
    return agent_executor


async def create_answer(agent_executor, chat_history, question):
    """
    Create an answer given 
      - langchain agent executor
      - previous chat history 
      - a new question
    """
    result = await agent_executor.ainvoke(
        {"input": question, "chat_history": chat_history}
    )
    answer = result['output']
    answer = sub("^System: ", "", sub("^\\??\n\n", "", answer))
    chat_history.extend(
        (HumanMessage(content=question), AIMessage(content=answer))
    )
    return answer, chat_history


async def send_sms(message, to_phone_number):
    """ Send SMS text message and return the message id """
    http_client = AsyncTwilioHttpClient()
    client = Client(account_sid, auth_token, http_client=http_client)
    message = await client.messages.create_async(
        body=message,
        from_=from_phone,
        to=to_phone_number
    )
    return message.status, message.sid


async def business_init(is_init, to_phone_number):

    name = is_init[1]
    name = ''.join(c for c in name.lower() if c.isalnum())
    ag_ex = await startup(name, to_phone_number)
    if ag_ex is None:
        answer = "I don't know about this business. Please ask me about a business that I know about."
    else:
        answer = "Sure. Ask me anything!"
    return answer


async def answer_question(question, to_phone_number):

    # pull up chat history data for the phone number from the database
    conn = await init_connection()
    db_chat_history = conn["chat_history"]
    coll_db_history = db_chat_history[to_phone_number]
    chat_history_data = next(coll_db_history.find({}))
    business_name = chat_history_data["_id"]
    # chat history has to be unpickled to be parsed
    chat_history = loads(chat_history_data["history"], encoding="bytes")

    # pull up the agent executor from the database
    db = conn[database_name]
    collection = db[business_name]

    # construct agent executor
    agent_executor = await get_agent_executor(collection)
    answer, chat_history = await create_answer(agent_executor, chat_history, question)
    # chat history has to be pickled to be dumped into db
    chat_history = dumps(chat_history)
    coll_db_history.update_one(
        {"history": {"$exists": True}},
        {"$set": {"history": chat_history}}
    )
    # close database connection
    conn.close()
    return answer


@app.post("/sms")
async def chat(request: Request):
    """Respond to incoming calls with a simple text message."""
    # set http context
    init_http_context()
    # receive question in SMS
    fm = await request.form()
    to_phone_number = fm.get("From")
    question = fm.get("Body")
    is_init = search(pattern, question)
    if is_init:
        answer = await business_init(is_init, to_phone_number)
    elif question == "I am done.":
        os.execl(sys.executable, sys.executable, *sys.argv)
    else:
        answer = await answer_question(question, to_phone_number)
    mstatus, msid = await send_sms(answer, to_phone_number)
    print(f"Message status: {mstatus}; message SID: {msid}\n")
    return {"answer": answer, "question": question}


if __name__ == "__main__":
    app.run(debug=True, port=port)
