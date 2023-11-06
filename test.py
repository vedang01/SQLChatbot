import os
import mysql.connector

db_password = os.getenv("DB_PASSWORD")


try:
    # Replace 'hostname', 'user', 'password', and 'database' with your details
    connection = mysql.connector.connect(
        host="localhost", user="root", password=db_password, database="sqlwizard"
    )
    cursor = connection.cursor()
    cursor.execute("select * from users")
    # Fetch all the rows and do something with them or just clear them
    results = cursor.fetchall()
    for row in results:
        print(row)
    if connection.is_connected():
        print("MySQL connection is successful.")
        # Don't forget to close the connection
        connection.close()
except mysql.connector.Error as e:
    print(f"Error connecting to MySQL: {e}")
finally:
    if connection.is_connected():
        # Close the cursor and connection
        cursor.close()
        connection.close()
        print("MySQL connection is closed")

# import os

# api_key = os.getenv("OPENAI_API_KEY")
# if api_key is None:
#     raise ValueError("No OpenAI API key found in environment variables.")
