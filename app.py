from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
import openai
from flask_cors import CORS
import os
import mysql.connector
from mysql.connector import Error


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
def generateChatResponse(prompt, topic=""):
    # Retrieve user's personal details from session
    first_name = session.get("firstname")
    age = session.get("age")
    profession = session.get("profession")
    proficiency = session.get("proficiency")

    # If user wants to learn about a specific topic
    if topic:
        personalized_prompt = f"{first_name}, who is a {profession} aged {age} with {proficiency} proficiency, wants to learn about {topic}. Give a brief summary along with an example."
    else:
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


def fetch_all_topics_from_db():
    topics = {}
    try:
        # Establishing the database connection
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        # Check if connection was successful
        if connection.is_connected():
            cursor = connection.cursor()

            query = """
             SELECT c.Concept, o.`Operation Name`
            FROM concepts c
            JOIN concepts_operations co ON c.ConceptID = co.ConceptID
            JOIN operations o ON co.OperationID = o.OperationID
            ORDER BY o.`Operation Name`, c.Importance DESC
            """

            cursor.execute(query)

            # Fetch all the resulting rows
            result = cursor.fetchall()

            for concept, operation in result:
                if operation not in topics:
                    topics[operation] = []
                topics[operation].append(concept)

            cursor.close()

    except Error as e:
        print("Error while connecting to MySQL", e)
    finally:
        # Closing the database connection
        if connection.is_connected():
            connection.close()
            print("MySQL connection is closed")

    return topics


@app.route("/fetch_all_topics")
def fetch_all_topics():
    topics = fetch_all_topics_from_db()
    return jsonify(topics)


# Root endpoint to serve the frontend HTML
@app.route("/")
def index():
    session.clear()
    return render_template("login.html", **locals())


@app.route("/generate_sql_overview")
def generate_sql_overview():
    overview_prompt = "Generate an overview for SQL. Do not go into the technical details, just mention the use of SQL, how it fits in the technological landscape, and other relevant information."
    return jsonify({"overview": generateChatResponse(overview_prompt)})


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


# User registration
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
                "reason",
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
        reason = data.get("reason")

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
            # Insert the new user into the database
            insert_query = "INSERT INTO users (Username, password, firstname, lastname, Age, Profession, Proficiency, Reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
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
                    reason,
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


# User Login
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
            query = "SELECT username, firstname, age, profession, proficiency, Reason FROM users WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            user_record = cursor.fetchone()
            cursor.close()
            connection.close()
            # If user exists and password matches
            if user_record:
                username, firstname, age, profession, proficiency, reason = user_record
                session["loggedin"] = True
                session["username"] = username  # Setting session with username
                session["firstname"] = firstname
                session["age"] = age
                session["profession"] = profession
                session["proficiency"] = proficiency
                session["reason"] = reason
                session["conversation_history"] = conversation_history
                # Add a system message to include the user's details in the conversation context
                personalized_context = {
                    "role": "system",
                    "content": f"Remember to address the user by their first name : {firstname}. Answer questions as if user is {age} years old, and is a {profession}. Adapt responses, as if the user was {proficiency} at SQL. Remember, user wants to learn SQL because of the following reason: {reason}",
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


# Home Page
@app.route("/home")
def home():
    if "loggedin" in session and session["loggedin"]:
        return render_template("index.html", show_options=True)
    else:
        # Redirect to the login page
        return redirect(url_for("login"))


# Quit functionality
@app.route("/quit", methods=["POST"])
def quit():
    learned_topics = session.get("learned_topics", [])
    session.clear()
    return jsonify(learned_topics=learned_topics)


# After selecting topic to learn, generate a basic overview
@app.route("/learn_topic", methods=["POST"])
def learn_topic():
    data = request.get_json()
    topic = data["topic"]
    # Call the modified generateChatResponse function with the topic
    response = generateChatResponse("", topic=topic)
    return jsonify({"response": response})


# After finishing topic, submit confidence score to user_confidence table
@app.route("/submit_confidence_score", methods=["POST"])
def submit_confidence_score():
    data = request.get_json()
    topic = data.get("topic")
    score = int(data.get("score"))
    username = session.get("username")

    # adding topics to list of learned topics to be displayed on quit
    if "learned_topics" not in session:
        session["learned_topics"] = []
    session["learned_topics"].append(topic)

    # Add logic to insert the confidence score into the database
    try:
        # Establishing the database connection
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        # Check if connection was successful
        if connection.is_connected():
            cursor = connection.cursor()
            query = "SELECT UserID FROM users WHERE username = %s"
            # Check if the username already exists
            cursor.execute(query, (username,))
            result = cursor.fetchone()
            user_id = result[0]

            cursor.execute(
                "SELECT ConceptID FROM concepts WHERE Concept = %s", (topic,)
            )
            concept_id = cursor.fetchone()[0]

            # print(f"ConceptID: {concept_id}, Topic: {topic}")
            # concept ID is fine

            # Prepare the insert statement
            insert_stmt = (
                "INSERT INTO user_confidence (UserID, ConceptID, Concept, Confidence) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE Confidence = VALUES(Confidence)"
            )
            data_tuple = (user_id, concept_id, topic, score)
            cursor.execute(insert_stmt, data_tuple)
            connection.commit()

            return jsonify({"message": "Confidence score submitted successfully"}), 200
    except mysql.connector.Error as e:
        print("Error while connecting to MySQL", e)
        return jsonify({"message": "Failed to submit confidence score"}), 500
    finally:
        # Closing the database connection
        if connection.is_connected():
            cursor.close()
            connection.close()

    # If user_id is not in session, or any other issue
    return jsonify({"message": "Failed to submit confidence score"}), 400


@app.route("/get_prerequisite", methods=["POST"])
def get_prerequisite():
    data = request.get_json()
    topic = data.get("topic")

    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )
        cursor = connection.cursor()
        query = "SELECT Prerequisite FROM concepts WHERE Concept = %s"
        cursor.execute(query, (topic,))
        prerequisite = cursor.fetchone()

        if prerequisite:
            return jsonify({"prerequisite": prerequisite[0]})
        else:
            return jsonify({"prerequisite": "No prerequisite found"}), 404

    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


# Display suggested topics
@app.route("/suggested_topics")
def suggested_topics():
    username = session.get("username")
    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        if connection.is_connected():
            cursor = connection.cursor()

            # Get the user ID based on the username
            cursor.execute("SELECT UserID FROM users WHERE Username = %s", (username,))
            user_id_result = cursor.fetchone()
            if user_id_result:
                user_id = user_id_result[0]

                # Get the concepts where the user's confidence score is null or less than 3
                cursor.execute(
                    """
                    SELECT c2.Concept, o.`Operation Name`
                    FROM concepts AS c1
                    INNER JOIN user_confidence AS uc ON c1.Concept = uc.Concept
                    INNER JOIN concepts AS c2 ON c1.Concept = c2.Prerequisite
                    LEFT JOIN concepts_operations AS co ON c2.ConceptID = co.ConceptID
                    LEFT JOIN operations AS o ON co.OperationID = o.OperationID
                    WHERE uc.UserID = %s AND uc.Confidence >= 3 AND 
                    NOT EXISTS (
                        SELECT 1
                        FROM user_confidence AS uc2
                        WHERE uc2.UserID = uc.UserID
                        AND uc2.ConceptID = c2.ConceptID
                    )
                    ORDER BY c2.Importance DESC
                    LIMIT 8
                    """,
                    (user_id,),
                )

                high_confidence_topics = cursor.fetchall()

                # Create a list to hold all suggested topics including high and low confidence
                suggested_topics = []

                # Process high confidence topics
                for concept, operation in high_confidence_topics:
                    suggested_topics.append(
                        {"Concept": concept, "Operation Name": operation}
                    )

                if len(suggested_topics) < 8:
                    # if less than 8 suggestions, then look for low confidence topics
                    cursor.execute(
                        """
                        use sqlwizard;
                        SELECT c.Concept, o.`Operation Name`
                        FROM concepts AS c
                        LEFT JOIN user_confidence AS uc ON c.ConceptID = uc.ConceptID AND uc.UserID = %s
                        LEFT JOIN concepts_operations AS co ON c.ConceptID = co.ConceptID
						LEFT JOIN operations AS o ON co.OperationID = o.OperationID
                        WHERE (uc.Confidence IS NULL OR uc.Confidence < 3) AND c.concept NOT IN (%s)
                        LIMIT %s
                        """,
                        (
                            user_id,
                            ", ".join(["%s"] * len(high_confidence_topics)),
                            8 - len(high_confidence_topics),
                        ),
                    )
                    # low_confidence_concepts = [row[0] for row in cursor.fetchall()]
                    low_confidence_topics = cursor.fetchall()
                    # print(low_confidence_concepts)
                    for concept, operation in low_confidence_topics:
                        suggested_topics.append(
                            {"Concept": concept, "Operation Name": operation}
                        )
                print(suggested_topics)

                if len(suggested_topics) == 0:  # for new users
                    suggested_topics.append(
                        {"Concept": "SQL Basics", "Operation Name": "Creation"}
                    )
                    suggested_topics.append(
                        {"Concept": "SELECT statement", "Operation Name": "Retrieval"}
                    )
                    suggested_topics.append(
                        {"Concept": "WHERE clause", "Operation Name": "Retrieval"}
                    )
                    suggested_topics.append(
                        {"Concept": "NULL values", "Operation Name": "Miscellaneous"}
                    )
                    suggested_topics.append(
                        {"Concept": "Data Types", "Operation Name": "Miscellaneous"}
                    )
                    suggested_topics.append(
                        {"Concept": "Constraints", "Operation Name": "Creation"}
                    )

                    # high_confidence_prereq += low_confidence_concepts

                return jsonify(suggested_topics[:8])
            else:
                return jsonify({"message": "User not found"}), 404

    except mysql.connector.Error as e:
        print("Error while connecting to MySQL", e)
        return jsonify({"message": "Failed to fetch suggested topics"}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

    return jsonify({"message": "No suggestions available"}), 404


# Fetch Live Database data
def get_table_data():
    tables = [
        "students",
        "courses",
        "enrollments",
    ]
    data = {}
    connection = mysql.connector.connect(
        host="localhost",
        database="sandbox",
        user="readonly_user",
        password="sandbox789",
    )
    if connection is None:
        return None
    try:
        cursor = connection.cursor()
        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            columns = [desc[0] for desc in cursor.description]
            data[table] = {"columns": columns, "rows": cursor.fetchall()}
    except Exception as e:
        print(f"Error fetching table data: {e}")
        return None
    finally:
        connection.close()
    return data


# Route for sandbox mode
@app.route("/sandbox", methods=["GET", "POST"])
def sandbox():
    if request.method == "POST":
        query = request.form["query"]
        try:
            connection = mysql.connector.connect(
                host="localhost",
                database="sandbox",
                user="readonly_user",
                password="sandbox789",
            )
            if connection is None:
                return jsonify({"error": "Database connection failed"}), 500
            cursor = connection.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            return jsonify(results)

        except Exception as e:
            return jsonify({"error": str(e)}), 400
        finally:
            if connection.is_connected():
                connection.close()

    else:
        # Render the sandbox HTML page

        tables_data = get_table_data()
        if tables_data is None:
            return "Error fetching table data", 500
        return render_template("sandbox.html", tables_data=tables_data)


@app.route("/display_completed_topics", methods=["GET"])
def display_completed_topics():
    # Check if username is in session
    if "username" not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    username = session["username"]
    connection = None
    try:
        connection = mysql.connector.connect(
            host="localhost",
            database="sqlwizard",
            user="root",
            password=db_password,
        )
        cursor = connection.cursor()

        # Fetch the userID based on the username from the session
        user_id_query = "SELECT UserID FROM users WHERE Username = %s"
        cursor.execute(user_id_query, (username,))
        result = cursor.fetchone()

        # If no result, the user is not found
        if not result:
            return jsonify({"success": False, "message": "User not found"}), 404

        user_id = result[0]

        # fetch the completed topics and confidence levels
        topics_query = """
            SELECT 
                c.Concept, 
                GROUP_CONCAT(DISTINCT o.`Operation Name` ORDER BY o.`Operation Name` ASC SEPARATOR ', ') AS `Operations`,
                uc.Confidence

            FROM 
                user_confidence uc
            JOIN 
                concepts c ON uc.ConceptID = c.ConceptID
            JOIN 
                concepts_operations co ON c.ConceptID = co.ConceptID
            JOIN 
                operations o ON co.OperationID = o.OperationID
            WHERE 
                uc.UserID = %s
            GROUP BY 
                c.Concept, uc.Confidence
            """
        cursor.execute(topics_query, (user_id,))
        topics = cursor.fetchall()

        # If no topics found, return an appropriate message
        if not topics:
            return jsonify({"success": False, "message": "No topics found"}), 404

        # Transform the topics into a list of dictionaries to jsonify them
        # topics_list = [
        #     {"concept": concept, "confidence": confidence}
        #     for concept, confidence in topics
        # ]
        return jsonify(topics)

    except mysql.connector.Error as e:
        return jsonify({"success": False, "message": "Database error: " + str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/view_progress")
def view_progress():
    if "username" not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401
    username = session["username"]

    connection = None
    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )
        cursor = connection.cursor()

        # Fetch the userID based on the username from the session
        user_id_query = "SELECT UserID FROM users WHERE Username = %s"
        cursor.execute(user_id_query, (username,))
        result = cursor.fetchone()

        # If no result, the user is not found
        if not result:
            return jsonify({"success": False, "message": "User not found"}), 404

        user_id = result[0]

        cursor = connection.cursor(dictionary=True)

        # Fetch the total number of topics per operation
        total_topics_query = """
        SELECT op.OperationID, op.`Operation Name`, COUNT(co.ConceptID) as TotalTopics
        FROM operations op
        LEFT JOIN concepts_operations co ON op.OperationID = co.OperationID
        GROUP BY op.OperationID
        """
        cursor.execute(total_topics_query)
        total_topics_results = cursor.fetchall()

        # Fetch the completed topics per operation for the logged-in user
        completed_topics_query = """
        SELECT 
            op.OperationID, 
            op.`Operation Name`, 
            COUNT(DISTINCT uc.ConceptID) as CompletedTopics
        FROM 
            operations op
        JOIN 
            concepts_operations co ON op.OperationID = co.OperationID
        JOIN 
            user_confidence uc ON co.ConceptID = uc.ConceptID
        WHERE 
            uc.UserID = %s
        GROUP BY 
            op.OperationID;

        """
        cursor.execute(completed_topics_query, (user_id,))
        completed_topics_results = cursor.fetchall()

        # Combine both results to form the final data structure
        operations_data = {
            op["OperationID"]: {
                "name": op["Operation Name"],
                "total": 0,
                "completed": 0,
            }
            for op in total_topics_results
        }

        for op in total_topics_results:
            operations_data[op["OperationID"]]["total"] = op["TotalTopics"]

        for op in completed_topics_results:
            operations_data[op["OperationID"]]["completed"] = op["CompletedTopics"]

        # Prepare data for the graph
        graph_data = {
            "operations": [op["Operation Name"] for op in total_topics_results],
            "totalTopics": [op["total"] for op in operations_data.values()],
            "completedTopics": [op["completed"] for op in operations_data.values()],
        }

        return jsonify(graph_data)

    except mysql.connector.Error as e:
        return jsonify({"success": False, "message": "Database error: " + str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    app.run(port="5500", debug=True)
