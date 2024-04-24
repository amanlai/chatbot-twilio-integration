from os import getenv
from re import sub
from dotenv import load_dotenv
# from langchain_core.messages import AIMessage, HumanMessage
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from chainlit.server import app
# import chainlit as cl
from chainlit.context import init_http_context
from fastapi import Request
from twilio.rest import Client
from twilio.http.async_http_client import AsyncTwilioHttpClient
from utils.helpers import init_connection, get_agent_executor
load_dotenv()

# port = int(getenv("PORT", 8000))
database_name = getenv("DB_NAME", "chattabot")
business_name = getenv("BUSINESS_NAME")
chat_history_db = getenv("CHAT_HISTORY_DB", "chat_history")
account_sid = getenv("TWILIO_ACCOUNT_SID")
auth_token = getenv("TWILIO_AUTH_TOKEN")
from_phone = getenv("TWILIO_PHONE")
mongo_uri = getenv("MONGO_URI")


async def create_answer(agent_executor, question, phone_number):
    """
    Create an answer given 
      - langchain agent executor
      - previous chat history 
      - a new question
    """
    # ch = [
    #     HumanMessage(content=x) if i % 2 == 0 else AIMessage(content=x)
    #     for i, x in enumerate(chat_history)
    # ]
    ch = MongoDBChatMessageHistory(
        session_id=phone_number,
        connection_string=mongo_uri,
        database_name=chat_history_db,
        collection_name=phone_number,
    )

    result = await agent_executor.ainvoke(
        {"input": question, "chat_history": ch.messages}
    )
    answer = result["output"]
    answer = sub("^System: ", "", sub("^\\??\n\n", "", answer))

    # add the most recent message exchange to db
    ch.add_user_message(question)
    ch.add_ai_message(answer)
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

    conn = init_connection()
    # get agent executor
    db = conn[database_name]
    collection = db[business_name]
    agent_executor = get_agent_executor(collection)
    conn.close()

    # get chat history
    # db_chat_history = conn[chat_history_db]
    # coll_chat_history = db_chat_history[to_phone_number]
    # chat_history_data = next(coll_chat_history.find({}), {"history": []})
    # chat_history = chat_history_data["history"]
    # get answers
    answer = await create_answer(agent_executor, question, to_phone_number)

    # send SMS back
    mstatus, msid = await send_sms(answer, to_phone_number)

    # update the chat history of this phone number
    # chat_history.extend((question, answer))
    # coll_chat_history.delete_many({})
    # coll_chat_history.insert_one({"history": chat_history})
    # conn.close()

    print(f"Message status: {mstatus}; message SID: {msid}\n")
    return {"answer": answer, "question": question}


if __name__ == "__main__":
    app.run(debug=True)


# # App Hooks
# @cl.on_chat_start
# async def main():

#     """ Startup """

#     conn = init_connection()
#     # get agent executor
#     db = conn[database_name]
#     collection = db[business_name]
#     agent_executor = get_agent_executor(collection)
#     # close db connection
#     conn.close()

#     await cl.Avatar(
#         name='Chatbot', 
#         path="../chainlit-app/public/logo_dark.png"
#     ).send()
#     # wait for user question
#     await cl.Message(
#         content='Ask me anything!',
#         author='Chatbot'
#     ).send()

#     cl.user_session.set('chat_history', [])
#     cl.user_session.set('agent_executor', agent_executor)



# @cl.on_message
# async def on_message(msg):

#     # creating a reply
#     question = msg.content
#     agent_executor = cl.user_session.get('agent_executor')
#     chat_history = cl.user_session.get('chat_history')
#     answer = await create_answer(agent_executor, chat_history, question)
#     chat_history.extend((question, answer))
#     cl.user_session.set('chat_history', chat_history)
#     print(f"\n\nThis is answer: {answer}\n\n")
#     await cl.Message(
#         content=answer,
#         author="Chatbot"
#     ).send()