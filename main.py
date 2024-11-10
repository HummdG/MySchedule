from fastapi import FastAPI, Form
from pydantic import BaseModel
from typing import Optional, Dict, List
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_core.runnables import RunnablePassthrough
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
import json
import mysql.connector
from datetime import datetime, timedelta
from langchain_core.output_parsers import JsonOutputParser
from datetime import date
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

app = FastAPI()

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="password",
    database="myschedule_db",
)
cursor = db.cursor()

# Pydantic model for form data
class ScheduleForm(BaseModel):
    learning_topic: str
    duration: str
    time_constraints: str
    include_books: bool
    include_videos: bool
    include_online_courses: bool

# Define the nested models
class Resource(BaseModel):
    type: str
    title: str
    link: str

class Activity(BaseModel):
    day: str
    date: date
    topics: List[str]
    estimated_time: float
    resources: List[Resource]

class Week(BaseModel):
    week_number: int
    start_date: date
    end_date: date
    activities: List[Activity]

class CourseSchedule(BaseModel):
    weeks: List[Week]

# Create the parser
# parser = JsonOutputParser(pydantic_object=CourseSchedule)

# Generate format instructions
# format_instructions = parser.get_format_instructions()

# Initialize OpenAI with memory
llm = ChatOpenAI(model="gpt-4-turbo")
# memory = ConversationBufferMemory()
# conversation = ConversationChain(llm=llm, memory=memory, verbose=True)

# Prompt template
prompt_template = PromptTemplate(
    input_variables=["topic", "duration", "time_constraints", "resources"],
    template = """
Generate a Learning Schedule

- Topic: "{topic}"
- Total Duration: "{duration}"
- Start Date: "October 30, 2024"
- Time Constraints: {time_constraints} 
- Required Resource Types: {resources}

Schedule Guidelines:
1. Output the schedule as a JSON array of objects.
2. Include study activities for each day (Monday to Sunday) unless specified in time constraints.
3. For each activity, specify:
   - Day of the week and Date
   - Topics covered
   - Estimated study time (in hours)
   - Resources with type, title, and URL or chapter if applicable. Give real URLs, book names, video titles, or articles. Do not make up URLs or resources.
4. If the start date is not a Monday, include only the days from the start date until Sunday of that week.
5. Provide URLs for videos and specify book chapters or article links with valid and authentic sources.
6. Do not include made-up URLs or content. Use genuine resources such as official books, courses, or reputable educational platforms like YouTube, Coursera, edX, etc.
7. For videos prefer suggesting youtube videos and if you can pplease give the channel name as well in the title.
8. You can suggest multiple resources for each activity if required.

An example of the expected JSON Format is as follows:
    {{
        "week_number": "",
        "start_date": "",
        "end_date": "",
        "activities": [
            {{
                "day": "",
                "date": "",
                "topics": [""],
                "estimated_time": 0.0,
                "resources": [
                    {{
                        "type": "",
                        "title": "",
                        "link": ""
                    }}
                ]
            }}
        ]
    }},
    {{
        "week_number": "",
        "start_date": "",
        "end_date": "",
        "activities": [
            {{
                "day": "",
                "date": "",
                "topics": [""],
                "estimated_time": 0.0,
                "resources": [
                    {{
                        "type": "",
                        "title": "",
                        "chapter": "",
                        "link": ""
                    }}
                ]
            }}
        ]
    }}

Instructions:
- Provide the first 2 weeks of the schedule for now.
- Refer to JSON format as shown above.
- ONLY OUTPUT THE JSON ARRAY AND NOT ANYTHING ELSE. DONT FORMAT THE OUTPUT FOR BETTER VISUAL READABILITY. JUST GIVE
THE JSON.
"""

)

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/create_schedule")
async def create_schedule(
    learning_topic: str = Form(...),
    duration: str = Form(...),
    time_constraints: str = Form(...),
    include_books: bool = Form(...),
    include_videos: bool = Form(...),
    include_online_courses: bool = Form(...)
):
    # Construct resources string
    resources = []
    if include_books:
        resources.append("books")
    if include_videos:
        resources.append("videos")
    if include_online_courses:
        resources.append("online courses")
    resources_str = ", ".join(resources)

    # Define a new graph
    workflow = StateGraph(state_schema=MessagesState)


    # Define the function that calls the model
    def call_model(state: MessagesState):
        response = llm.invoke(state["messages"])
        return {"messages": response}


    # Define the (single) node in the graph
    workflow.add_edge(START, "model")
    workflow.add_node("model", call_model)

    # Add memory
    memory = MemorySaver()
    conversation = workflow.compile(checkpointer=memory)

    # Prepare the prompt
    prompt = prompt_template.format(
        topic=learning_topic,
        duration=duration,
        time_constraints=time_constraints,
        resources=resources_str,
        # format_instructions=format_instructions
    )
    query = prompt

    input_messages = [HumanMessage(query)]
    input_messages.append(HumanMessage("Format the output to just have JSON so remove everything outside of the JSON array if needed."))
    config = {"configurable": {"thread_id": "1"}}
    output = conversation.invoke({"messages": input_messages}, config=config)
    response = output["messages"][-1].content
    output["messages"][-1].pretty_print()  # output contains all messages in state

    # Run the conversation with memory
    x = []
    # response = conversation(prompt)
    x.append(json.loads(response))

    while (response != '"Done"'):
        response = conversation.predict(input = f"""
                                     Have you given all weeks for the specified duration of "{duration}", if not give the 
                                     next 2 weeks (or 1 depending on if total weeks in duration were odd or even) in JSON. If you have given all weeks just output "Done"
                                     """)
        if (response != '"Done"'):
            x.append(response)

    print(x)
    try:
        schedule_json = json.loads(x[0])
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON response"}

    # Insert into database
    cursor.execute("""
    INSERT INTO Schedules (learning_topic, duration, time_constraints, schedule_details)
    VALUES (%s, %s, %s, %s)
    """, (learning_topic, duration, time_constraints, json.dumps(schedule_json)))
    db.commit()

    return {"message": "Schedule created successfully", "schedule": schedule_json}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)