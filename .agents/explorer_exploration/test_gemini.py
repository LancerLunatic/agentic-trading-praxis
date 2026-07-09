import os
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

print("Initializing Gemini Client...")
print("GEMINI_API_KEY present:", bool(os.environ.get("GEMINI_API_KEY")))
try:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", timeout=10)
    print("Sending test message...")
    response = llm.invoke([HumanMessage(content="Hello, response in 1 word.")])
    print("Response received:", response.content)
except Exception as e:
    print("Error calling Gemini API:", e)
