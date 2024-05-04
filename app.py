from os import getenv
from dotenv import load_dotenv
from langchain_mongodb import MongoDBChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from chainlit.server import app
# import chainlit as cl
from chainlit.context import init_http_context
from fastapi import Request
from twilio.rest import Client
from twilio.http.async_http_client import AsyncTwilioHttpClient
from utils.helpers import init_connection, get_agent_executor
load_dotenv()

chat_history_db = getenv("CHAT_HISTORY_DB", "chat_history")
account_sid = getenv("TWILIO_ACCOUNT_SID")
auth_token = getenv("TWILIO_AUTH_TOKEN")
from_phone = getenv("TWILIO_PHONE")
mongo_uri = getenv("MONGO_URI")
debug = getenv("DEBUG", 'False') == 'True'
async_mode_on = getenv("ASYNC_MODE_ON", 'True') == 'True'


async def create_answer(question, phone_number):
    """
    Create an answer given 
      - previous chat history 
      - a new question
    """
    # instantiate chat history instance
    ch = MongoDBChatMessageHistory(
        session_id=phone_number,
        connection_string=mongo_uri,
        database_name=chat_history_db,
        collection_name=phone_number,
    )

    if question == "Delete chat history.":
        ch.clear()
        return "Chat history deleted."

    # construct the agent and generate answer
    with init_connection() as conn:
        agent_executor = get_agent_executor(conn)
        result = await agent_executor.ainvoke(
            {"input": question, "chat_history": ch.messages}
        )
        if debug:
            print(f"result: {result}")
        answer = result["output"]
    
    # add the most recent message exchange to db
    await ch.aadd_messages(
        [HumanMessage(content=question), AIMessage(content=answer)]
    )
    
    # close chat history db connection
    ch.client.close()
    return answer


async def send_sms(msg, to_phone_number):
    """ Send SMS text message and return the message id """
    
    http_client = AsyncTwilioHttpClient()
    client = Client(
        username=account_sid, 
        password=auth_token, 
        http_client=http_client
    )
    message = await client.messages.create_async(
    # message = client.messages.create(
        body=msg,
        from_=from_phone,
        to=to_phone_number
    )
    await http_client.close()

    return message.status, message.sid


@app.post("/sms")
async def chat(request: Request):
    """Respond to incoming calls with a simple text message."""
    # receive question in SMS
    fm = await request.form()
    to_phone_number = fm.get("From")
    question = fm.get("Body")

    if debug:
        print(f"This is the question (from {to_phone_number}): {question}.\n\n")

    # set http context
    init_http_context(user=to_phone_number)

    # get answers
    answer = await create_answer(question, to_phone_number)
    # send SMS back
    mstatus, msid = await send_sms(answer, to_phone_number)

    if debug:
        print(f"\nThis is the generated answer:\n{answer}\n\n")
        print(f"Message status: {mstatus}; message SID: {msid}\n")

    return {"answer": answer, "question": question}


if __name__ == "__main__":
    app.run(debug=debug)


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
