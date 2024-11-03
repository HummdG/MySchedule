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
parser = JsonOutputParser(pydantic_object=CourseSchedule)

# Generate format instructions
format_instructions = parser.get_format_instructions()

# Initialize OpenAI with memory
llm = ChatOpenAI(model="gpt-4")
memory = ConversationBufferMemory()
conversation = ConversationChain(llm=llm, memory=memory, verbose=True)

# Prompt template
prompt_template = PromptTemplate(
    input_variables=["topic", "duration", "time_constraints", "resources", "format_instructions"],
    template="""
    Create a detailed daily learning schedule for {topic} over a duration of {duration} starting from 30 october 2024.
    Consider the following time constraints: {time_constraints}.
    Include the following types of resources: {resources}.
    
    The schedule should be structured as a JSON object as shown below:
    {{
            "week_number": 1,
            "start_date": "2024-11-15",
            "end_date": "2024-11-21",
            "activities": [
                {{
                    "day": "Monday",
                    "date": "2024-11-15",
                    "topics": ["Introduction to Python", "Environment Setup"],
                    "estimated_time": 2.0,
                    "resources": [
                        {{
                            "type": "video",
                            "title": "Intro to Python",
                            "link": "https://example.com/intro-to-python"
                        }},
                        {{
                            "type": "article",
                            "title": "Setting Up Python",
                            "link": "https://example.com/setting-up-python"
                        }}
                    ]
                }}
            ]
        }}
    
    Give me for each week, then I am going to say more and then you give another week till you finish so you don't run out of
    your max output token limit.
    EACH WEEK SHOULD ONLY END ON SUNDAY SO AFTER SUNDAY A NEW WEEK SHOULD COMMENCE.
    ONLY GIVE JSON OUTPUT
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

    # Prepare the prompt
    prompt = prompt_template.format(
        topic=learning_topic,
        duration=duration,
        time_constraints=time_constraints,
        resources=resources_str,
        format_instructions=format_instructions
    )

    # Run the conversation with memory
    response = conversation.predict(input=prompt)

    response2 = conversation.predict("more")

    try:
        schedule_json = json.loads(response)
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