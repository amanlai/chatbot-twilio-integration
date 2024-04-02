import os
from re import sub
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from chainlit.server import app
from chainlit.context import init_http_context
from fastapi import Request
from twilio.rest import Client
from twilio.http.async_http_client import AsyncTwilioHttpClient
from utils.helpers import init_connection, get_agent_executor
load_dotenv()

# port = int(os.getenv("PORT", 8000))
database_name = os.getenv("DB_NAME", "chattabot")
business_name = os.getenv("BUSINESS_NAME")
chat_history_db = os.getenv("CHAT_HISTORY_DB", "chat_history")
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_phone = os.getenv("TWILIO_PHONE")


async def create_answer(agent_executor, chat_history, question):
    """
    Create an answer given 
      - langchain agent executor
      - previous chat history 
      - a new question
    """
    ch = [
        HumanMessage(content=x) if i % 2 == 0 else AIMessage(content=x)
        for i, x in enumerate(chat_history)
    ]
    result = await agent_executor.ainvoke(
        {"input": question, "chat_history": ch}
    )
    answer = result["output"]
    answer = sub("^System: ", "", sub("^\\??\n\n", "", answer))
    return answer


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


@app.post("/sms")
async def chat(request: Request):
    """Respond to incoming calls with a simple text message."""
    # set http context
    init_http_context()
    # receive question in SMS
    fm = await request.form()
    to_phone_number = fm.get("From")
    question = fm.get("Body")

    conn = await init_connection()
    # get agent executor
    db = conn[database_name]
    collection = db[business_name]
    agent_executor = await get_agent_executor(collection)
    # get chat history
    db_chat_history = conn[chat_history_db]
    coll_chat_history = db_chat_history[to_phone_number]
    chat_history_data = next(coll_chat_history.find({}), {"history": []})
    chat_history = chat_history_data["history"]
    # get answers
    answer = await create_answer(agent_executor, chat_history, question)

    # send SMS back
    mstatus, msid = await send_sms(answer, to_phone_number)

    # update the chat history of this phone number
    chat_history.extend((question, answer))
    coll_chat_history.delete_many({})
    coll_chat_history.insert_one({"history": chat_history})
    conn.close()

    print(f"Message status: {mstatus}; message SID: {msid}\n")
    return {"answer": answer, "question": question}


if __name__ == "__main__":
    app.run(debug=True)
