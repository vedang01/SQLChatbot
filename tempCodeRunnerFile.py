from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
import openai
from flask_cors import CORS
import os
import mysql.connector


db_password = os.getenv("DB_PASSWORD")


# Set the OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")
app = Flask(__name__)

CORS(app)
# Configure server-side session
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Initialize conversation history with the system message
conversation_history = [
    {
        "role": "system",
        "content": "You are a Personalized SQL Teacher with expertise in andragogical practices. Your primary goals are to be polite, provide comprehensive answers with relevant examples, and display data tables in tabular format for easy interpretation by the user. Whenever a user asks to practice, you will create suitable tables with appropriate attributes and data. Then, you'll display them in tabular form and generate relevant questions to test the user's understanding. DO NOT show the answers while displaying questions;let the users give answers. It's essential to verify and provide feedback on the answers given by the user.",
    }
]


# Separate function for GPT-3 response
def generateChatResponse(prompt):
    # Retrieve user's personal details from session
    first_name = session.get("firstname")
    age = session.get("age")
    profession = session.get("profession")
    proficiency = session.get("proficiency")

    # Personalize the prompt with the user's details
    personalized_prompt = f"{first_name}, who is a {profession} aged {age} with {proficiency} proficiency, asks: {prompt}"

    # Include the personalized prompt in the conversation history
    session["conversation_history"].append(
        {"role": "user", "content": personalized_prompt}
    )

    # session["conversation_history"].append({"role": "user", "content": prompt})
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=session["conversation_history"]
    )

    try:
        answer = response.choices[0].message.content
        session["conversation_history"].append({"role": "assistant", "content": answer})
        display_prompt = prompt
        display_answer = answer.replace(
            personalized_prompt, display_prompt
        )  ##removing the personalized preamble, so user can see the answer only

    except:
        display_answer = (
            "Oops answer failed to generate, please try again or come back later"
        )

    return display_answer


# Separate function for GPT-3 response
def isSQLrelated(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",  ##you can improve this classifier
                "content": "You are an AI trained to classify 'user' prompt as SQL-related or not. A prompt is considered SQL-related if it pertains to database queries, SQL commands, data manipulation or retrieval, table structure, or SQL functions. Non-SQL related prompts include general programming questions, non-technical queries and personal opinions. Respond 'yes' if the prompt is classified as SQL related; otherwise, respond 'no'. When in doubt, classify prompt as SQL-related.",
            },
            {"role": "user", "content": prompt},  # Current prompt to classify
        ],
    )

    try:
        answer = response.choices[0].message.content
    except:
        answer = "SQL classifier failed"

    return answer


import mysql.connector
from mysql.connector import Error


def fetch_topics():
    topics = []
    try:
        # Establishing the database connection
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        # Check if connection was successful
        if connection.is_connected():
            cursor = connection.cursor()

            query = "SELECT DISTINCT concept FROM concepts WHERE readonly=1"

            cursor.execute(query)

            # Fetch all the resulting rows
            result = cursor.fetchall()

            # Process the fetched data
            topics = [item[0] for item in result]

            cursor.close()

    except Error as e:
        print("Error while connecting to MySQL", e)
    finally:
        # Closing the database connection
        if connection.is_connected():
            connection.close()
            print("MySQL connection is closed")

    return topics


# Root endpoint to serve the frontend HTML
@app.route("/")
def index():
    session.clear()
    return render_template("login.html", **locals())


# Endpoint for GPT API completions
@app.route("/callapi", methods=["POST"])
def callapi():
    data = request.get_json()
    prompt = data["prompt"]
    res = {}  # result
    try:
        ###maybe try out some prompt engineering here
        res["answer"] = generateChatResponse(prompt)
        return jsonify(res), 200
    except Exception as e:  # Here's where we handle general exceptions
        res["error"] = "Server error: " + str(e)
        return jsonify(res), 500  # Sending a 500 Internal Server Error status


# Endpoint for SQL classifier
@app.route("/SQLclassifier", methods=["POST"])
def SQLclassifier():
    data = request.get_json()
    prompt = data["prompt"]
    res = {}  # result
    res["error"] = None
    is_sql = False
    try:
        response = isSQLrelated(prompt)
        is_sql = True if response.lower() == "yes" else False
        res["is_sql"] = is_sql
        return jsonify(res), 200

    except Exception as e:  # Here's where we handle general exceptions
        res["error"] = "Server error: " + str(e)
        res["is_sql"] = is_sql
        res["classifier_failed"] = True
        return jsonify(res), 500  # Sending a 500 Internal Server Error status


# Future routes for user authentication
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        # When the route is accessed via a GET request, render the registration form
        return render_template("register.html")
    else:
        data = request.get_json()
        # Validate the existence of all required fields
        if not all(
            k in data
            for k in (
                "username",
                "password",
                "first_name",
                "last_name",
                "confirm_password",
                "age",
                "profession",
                "proficiency",
            )
        ):
            return (
                jsonify({"success": False, "message": "All fields are required"}),
                400,
            )

        username = data.get("username")
        password = data.get("password")
        age = data.get("age")
        profession = data.get("profession")
        proficiency = data.get("proficiency")
        first_name = data.get("first_name")
        last_name = data.get("last_name")

        try:
            connection = mysql.connector.connect(
                host="localhost",
                database="sqlwizard",
                user="root",
                password=db_password,
            )
            cursor = connection.cursor()
            query = "SELECT UserID FROM users WHERE username = %s"

            # Check if the username already exists
            cursor.execute(query, (username,))
            if cursor.fetchone():
                return (
                    jsonify({"success": False, "message": "Username already exists"}),
                    409,
                )

            # Validate age as an integer
            try:
                age = int(data.get("age"))
            except ValueError:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Invalid age; it must be a number.",
                        }
                    ),
                    400,
                )
            ## HASH PASSWORD BEFORE STORAGE
            # Insert the new user into the database
            insert_query = "INSERT INTO users (Username, password, firstname, lastname, Age, Profession, Proficiency) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(
                insert_query,
                (
                    username,
                    password,
                    first_name,
                    last_name,
                    age,
                    profession,
                    proficiency,
                ),
            )
            connection.commit()

            # Close the connection
            cursor.close()
            connection.close()

            # Return a success message
            return (
                jsonify(
                    {"success": True, "message": "You are registered successfully!"}
                ),
                201,
            )

        except mysql.connector.Error as e:
            print("Database error: ", str(e))  # Log to console

            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Registration failed due to database error: "
                        + str(e),
                    }
                ),
                500,
            )

        except Exception as e:
            print("Server error: ", str(e))  # Log to console

            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Registration failed due to a server error: "
                        + str(e),
                    }
                ),
                500,
            )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # When the route is accessed via a GET request, render the registration form
        return render_template("login.html")
    else:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return (
                jsonify(
                    {"success": False, "message": "Username and password are required"}
                ),
                400,
            )
        # Connect to the database
        try:
            connection = mysql.connector.connect(
                host="localhost",
                database="sqlwizard",
                user="root",
                password=db_password,
            )
            cursor = connection.cursor()
            # Query to select the user
            query = "SELECT username, firstname, age, profession, proficiency FROM users WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            user_record = cursor.fetchone()
            cursor.close()
            connection.close()
            # If user exists and password matches
            if user_record:
                username, firstname, age, profession, proficiency = user_record
                session["loggedin"] = True
                session["username"] = username  # Setting session with username
                session["firstname"] = firstname
                session["age"] = age
                session["profession"] = profession
                session["proficiency"] = proficiency

                session["conversation_history"] = conversation_history
                # Add a system message to include the user's details in the conversation context
                personalized_context = {
                    "role": "system",
                    "content": f"Remember to address the user by their first name : {firstname}. Answer questions as if user is {age} years old, and is a {profession}. Adapt responses, as if the user was {proficiency} at SQL.",
                }
                session["conversation_history"].append(personalized_context)
                # Redirect to a home page or profile page on successful login
                return jsonify({"success": True}), 200

            else:
                # Invalid credentials
                return (
                    jsonify({"success": False, "message": "Invalid credentials"}),
                    401,
                )
        except mysql.connector.Error as e:
            print("Database error: ", str(e))  # Log to console

            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Login failed due to database error: " + str(e),
                    }
                ),
                500,
            )

        except Exception as e:
            print("Server error: ", str(e))  # Log to console

            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Login failed due to a server error: " + str(e),
                    }
                ),
                500,
            )


@app.route("/home")
def home():
    if "loggedin" in session and session["loggedin"]:
        return render_template("index.html")
    else:
        # Redirect to the login page
        return redirect(url_for("login"))


@app.route("/quit", methods=["POST"])
def quit():
    session.clear()
    return jsonify({"status": "Session cleared"}), 200


@app.route("/practice")
def practice():
    ##Fetch topics from database which are readonly
    topics = fetch_topics()
    return render_template("practice.html", topics=topics)


@app.route("/start_test", methods=["POST"])
def start_test():
    selected_topic = request.form.get("topic")
    selected_difficulty = request.form.get("difficulty")

    # use selected_topic and selected_difficulty to determine which questions to present to the user

    return redirect(
        url_for("test", topic=selected_topic, difficulty=selected_difficulty)
    )


@app.route("/test", methods=["GET", "POST"])
def test():
    if request.method == "POST":
        # ... process the user's answers ...
        # ... interact with the database and GPT model ...
        # ... provide feedback or scoring ...
        ##else:
        # ... set up the test page based on the topic and difficulty ...
        ##return render_template("test.html", ...)
        return render_template("test.html")


@app.route("/get_previous_score")
def get_previous_score():
    topic = request.args.get("topic")
    username = session.get("username")
    print("User ID from session:", username)

    # Initialize the default score as None or suitable default
    previous_score = None

    try:
        # Establishing the database connection
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        query = """
        SELECT Score FROM performance
        WHERE Username = %s AND Concept = %s
        ORDER BY TestDate DESC
        LIMIT 1
        """
        cursor = connection.cursor()
        cursor.execute(query, (username, topic))

        # Fetch the result
        result = cursor.fetchone()
        if result:
            previous_score = result[0]
    except Error as e:
        print("Error while connecting to MySQL", e)
    finally:
        # Closing the database connection
        if connection.is_connected():
            cursor.close()
            connection.close()

    # Return the previous score as JSON
    return jsonify({"score": previous_score or "Test not taken yet"})


@app.route("/sandbox", methods=["GET", "POST"])
def sandbox():
    pass


##this is for running SQL queries against a live database

if __name__ == "__main__":
    app.run(port="5500", debug=True)
