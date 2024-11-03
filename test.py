from fastapi import FastAPI, Form
import mysql.connector
from fastapi.middleware.cors import CORSMiddleware
from mysql.connector import Error

try:
    print("Connecting to the database...")
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="mydb",
    )
    if conn.is_connected():
        print("Database connected!")
    else:
        print("Failed to connect.")
except Error as e:
    print(f"Error: {e}")
finally:
    if conn.is_connected():
        conn.close()
        print("Connection closed.")
