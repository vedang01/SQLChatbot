from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
import openai
from flask_cors import CORS
import os
import mysql.connector
from mysql.connector import Error


app = Flask(__name__)
CORS(app)
# Configure server-side session

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

# make sure to set this via CLI
db_password = os.getenv("DB_PASSWORD")
openai.api_key = os.getenv("OPENAI_API_KEY")
app.secret_key = os.getenv("FLASK_SECRET_KEY")


# Initialize conversation history with the system message
conversation_history = [
    {
        "role": "system",
        "content": "You are a Personalized SQL Teacher with expertise in andragogical practices. Your primary goals are to be polite, provide comprehensive answers with relevant examples, and display data tables in tabular format for easy interpretation by the user. Whenever a user asks to practice, you will create suitable tables with appropriate attributes and data. Then, you'll display them in tabular form and generate relevant questions to test the user's understanding. DO NOT show the answers while displaying questions;let the users give answers. It's essential to verify and provide feedback on the answers given by the user. If you wish to display a table, format as an HTML table(IMPORTANT)",
    }
]


# Function to return GPT3.5 API response
def generateChatResponse(prompt, topic=""):
    # Retrieve user's personal details from session
    # These details will be used in the personalization prompt
    first_name = session.get("firstname")
    age = session.get("age")
    profession = session.get("profession")
    proficiency = session.get("proficiency")
    reason = session.get("reason")

    # If user wants to learn about a specific topic
    if topic:
        personalized_prompt = f"{first_name}, who is a {profession} aged {age} with {proficiency} proficiency, wants to learn about {topic}. Remember, he is learning SQL because of the reason: {reason}. In your answer, try relating it to the aforementioned reason, and to their profession : {profession}. Give a brief summary along with an example. Format your responses with appropriate line breaks for bullet points. Also please display any tables in HTML format. Remember to populate these tables with appropriate data. IT IS IMPORTANT THAT YOU DO NOT ASK THE USERS TO PRACTICE. Instead, append the line 'Feel free to ask any further questions. If you're ready, try practicing this concept in Sandbox Mode.' at the end of your response."
    else:
        # User wants to ask SQL wizard a general question
        personalized_prompt = f"{first_name}, who is a {profession} aged {age} with {proficiency} proficiency, asks: {prompt}. Format your responses with appropriate line breaks for bullet points. Also please display any tables in HTML format. Remember to refer to previous conversations as a reference to what the user asks, and also the reason why the user wants to learn SQL: {reason}, and to their profession: {profession}. Try to relate your answer to the aforementioned reason and profession. Give an example to support your explanation. IT IS IMPORTANT THAT YOU DO NOT ASK THE USERS TO PRACTICE. Instead, append the line 'Feel free to ask any further questions. If you're ready, try practicing this concept in Sandbox Mode.' at the end of your response."

    # Include the personalized prompt in the conversation history
    session["conversation_history"].append(
        {"role": "user", "content": personalized_prompt}
    )

    # API call
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
            "Answer failed to generate, please try again or come back later"
        )

    return display_answer


# Function to classify user prompts as SQL or Non SQL related
def isSQLrelated(prompt):

    # Adding conversation history to the classifier, so it knows the context of the conversation
    messages = session.get("conversation_history", []) + [
        {
            "role": "system",
            "content": "You are an AI trained to classify 'user' prompt as SQL-related or not. A prompt is considered SQL-related if it pertains to database queries, SQL commands, data manipulation or retrieval, table structure, or even general data-related questions and examples. If a prompt is a follow up to an SQL related prompt, then it is SQL related as well. Non-SQL related prompts are those that clearly deviate from SQL and data, including general questions, non-technical queries, and personal opinions. Please make sure to have a look at the whole conversation history before classifying as Non-SQL related. The conversation might suggest that the user prompt is simply a follow up response. In that case, it is SQL-related. Respond 'yes' if the prompt is classified as SQL related; otherwise, respond 'no'. When in doubt, classify prompt as SQL-related. Most(99%) prompts will be classified as SQL-related.",
        },
        {"role": "user", "content": prompt},  # Current prompt to classify
    ]

    # API CALL
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)

    try:
        answer = response.choices[0].message.content
    except:
        answer = "SQL classifier failed"

    return answer


# Function to fetch all topics from database with their operations
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

            # Query that return all concepts and their associated operations using joins
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

            # Create a dictionary
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

    return topics


# Fetch Live Database data for sandbox mode
def get_table_data():

    # List of tables in backend sandbox database
    # Add to this list in case more tables are added to sandbox database
    tables = [
        "students",
        "courses",
        "enrollments",
    ]
    data = {}

    # A new connection has been formed for a read only user that cannot perform write operations on the live database

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

            # Fetching all data from the backend tables
            cursor.execute(f"SELECT * FROM {table}")
            columns = [desc[0] for desc in cursor.description]
            data[table] = {"columns": columns, "rows": cursor.fetchall()}
    except Exception as e:
        print(f"Error fetching table data: {e}")
        return None
    finally:
        connection.close()
    return data


# Root endpoint to serve the frontend HTML
@app.route("/")
def index():
    session.clear()
    return render_template("login.html", **locals())


# Endpoint for GPT API completions
@app.route("/callapi", methods=["POST"])
def callapi():
    data = request.get_json()

    # data prompt contains user prompt captured by frontend
    prompt = data["prompt"]
    res = {}  # result
    try:
        res["answer"] = generateChatResponse(prompt)
        return jsonify(res), 200
    except Exception as e:
        res["error"] = "Server error: " + str(e)
        return jsonify(res), 500


# User registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        # When the route is accessed via a GET request, render the registration form
        return render_template("register.html")
    else:
        # POST request, insert data into backend table
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

        # extracting all information from the frontend form
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
            print("Server error: ", str(e))

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

        # POST request, get user from backend and store information in session
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
            query = "SELECT userid, username, firstname, age, profession, proficiency, Reason FROM users WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            user_record = cursor.fetchone()
            cursor.close()
            connection.close()

            # If user exists and password matches
            if user_record:
                userID, username, firstname, age, profession, proficiency, reason = (
                    user_record
                )

                # Storing user details in session for later use
                session["loggedin"] = True
                session["userID"] = userID
                session["username"] = username
                session["firstname"] = firstname
                session["age"] = age
                session["profession"] = profession
                session["proficiency"] = proficiency
                session["reason"] = reason
                session["conversation_history"] = conversation_history

                # Add a system message to include the user's details in the conversation context
                personalized_context = {
                    "role": "system",
                    "content": f"Remember to address the user by their first name : {firstname}. Answer questions as if user is {age} years old, and is a {profession}. Adapt responses, as if the user was a(n) {proficiency} at SQL. Remember, user wants to learn SQL because of the following reason: {reason}",
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


# Returns all topics from database
@app.route("/fetch_all_topics")
def fetch_all_topics():
    topics = fetch_all_topics_from_db()
    return jsonify(topics)


# Route to generate SQL overview
@app.route("/generate_sql_overview")
def generate_sql_overview():

    # This acts as a user prompt
    overview_prompt = "Generate a beginner-friendly introduction to SQL. Explain the use of SQL, and how it fits in the technological landscape. Do not add technical jargon or any SQL commands. Format your response beautifully in HTML. Add line breaks and new lines."
    return jsonify({"overview": generateChatResponse(overview_prompt)})


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

        # Return true or false based on the classifier's output
        res["is_sql"] = is_sql
        return jsonify(res), 200

    except Exception as e:
        res["error"] = "Server error: " + str(e)
        res["is_sql"] = is_sql
        res["classifier_failed"] = True
        return jsonify(res), 500


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
    user_id = session.get("userID")

    # adding topics to list of learned topics to be displayed on quit
    if "learned_topics" not in session:
        session["learned_topics"] = []
    session["learned_topics"].append(topic)

    # logic to insert the confidence score into the database
    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        # Check if connection was successful
        if connection.is_connected():
            cursor = connection.cursor()

            # retrieve concept ID from database using concept name
            cursor.execute(
                "SELECT ConceptID FROM concepts WHERE Concept = %s", (topic,)
            )
            concept_id = cursor.fetchone()[0]

            # insert user confidence values into table
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


# Get prerequisite of the selected topic
@app.route("/get_prerequisite", methods=["POST"])
def get_prerequisite():
    data = request.get_json()
    topic = data.get("topic")

    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )
        cursor = connection.cursor()

        # Query to get prerequisite of a particular concept chosen by the user
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
    # Create a list to hold all suggested topics including high and low confidence
    suggested_topics = []
    user_id = session.get("userID")
    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        if connection.is_connected():
            cursor = connection.cursor()

            if user_id:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM user_confidence
                    WHERE UserID = %s
                    """,
                    (user_id,),
                )
                completed_topics_count = cursor.fetchone()[0]

                # For new users with no completed topics, suggest predefined topics
                # concept names should match exactly with the names in the database
                if completed_topics_count == 0:
                    suggested_topics.append(
                        {"Concept": "SQL Basics", "Operation Name": "Creation"}
                    )
                    suggested_topics.append(
                        {"Concept": "'SELECT' Statement", "Operation Name": "Retrieval"}
                    )
                    suggested_topics.append(
                        {"Concept": "'WHERE' Clause", "Operation Name": "Retrieval"}
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
                    return jsonify(suggested_topics)

                # if not a new user

                # For completed topics confidence greater than 3, suggest a new topic for which the
                # completed topic is a prerequisite
                # make sure the suggested topic is not already completed by the user
                # joined with operations table to get the associated operation for that topic
                # ordered by importance of the topic in the SQL learning journey
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

                # Process high confidence topics
                for concept, operation in high_confidence_topics:
                    suggested_topics.append(
                        {"Concept": concept, "Operation Name": operation}
                    )

                if len(suggested_topics) < 8:
                    # if less than 8 suggestions, then look for low confidence topics
                    # low confidence topics are those completed topics with confidence less than 3
                    # also look for topics that are not completed by the user
                    # make sure no topic is already suggested by the previous query
                    cursor.execute(
                        """
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
                    low_confidence_topics = cursor.fetchall()

                    for concept, operation in low_confidence_topics:
                        suggested_topics.append(
                            {"Concept": concept, "Operation Name": operation}
                        )

                # These are default suggested topics for new users
                # if user completes all topics with a confidence greater than or equal to 3, then these topics
                # will be shown too
                # if len(suggested_topics) == 0:
                #     suggested_topics.append(
                #         {"Concept": "SQL Basics", "Operation Name": "Creation"}
                #     )
                #     suggested_topics.append(
                #         {"Concept": "SELECT statement", "Operation Name": "Retrieval"}
                #     )
                #     suggested_topics.append(
                #         {"Concept": "WHERE clause", "Operation Name": "Retrieval"}
                #     )
                #     suggested_topics.append(
                #         {"Concept": "NULL values", "Operation Name": "Miscellaneous"}
                #     )
                #     suggested_topics.append(
                #         {"Concept": "Data Types", "Operation Name": "Miscellaneous"}
                #     )
                #     suggested_topics.append(
                #         {"Concept": "Constraints", "Operation Name": "Creation"}
                #     )

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


# Route to display completed topics for a user
@app.route("/display_completed_topics", methods=["GET"])
def display_completed_topics():
    if "username" not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401
    user_id = session.get("userID")
    connection = None
    try:
        connection = mysql.connector.connect(
            host="localhost",
            database="sqlwizard",
            user="root",
            password=db_password,
        )
        cursor = connection.cursor()

        # fetch the completed topics and confidence levels
        # join with operations table to find associated operation of each completed topic
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

        return jsonify(topics)

    except mysql.connector.Error as e:
        return jsonify({"success": False, "message": "Database error: " + str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


# View progress route used to generate graph data
@app.route("/view_progress")
def view_progress():
    if "username" not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401
    user_id = session.get("userID")

    connection = None
    try:
        connection = mysql.connector.connect(
            host="localhost", database="sqlwizard", user="root", password=db_password
        )

        cursor = connection.cursor(dictionary=True)

        # Fetch the total number of topics per operation
        # This is the red bar in the graph
        total_topics_query = """
        SELECT op.OperationID, op.`Operation Name`, COUNT(co.ConceptID) as TotalTopics
        FROM operations op
        LEFT JOIN concepts_operations co ON op.OperationID = co.OperationID
        GROUP BY op.OperationID
        """
        cursor.execute(total_topics_query)
        total_topics_results = cursor.fetchall()

        # Fetch the completed topics per operation for the logged-in user
        # This is th green bar in the graph
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


# Route for sandbox mode
@app.route("/sandbox", methods=["GET", "POST"])
def sandbox():
    # POST request if query is run against database
    if request.method == "POST":
        # user query taken from front end
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


# Quit functionality
@app.route("/quit", methods=["POST"])
def quit():
    # Get learned topics to display at the end of session
    learned_topics = session.get("learned_topics", [])

    # Clear all session data, including conversation history
    session.clear()
    return jsonify(learned_topics=learned_topics)


# App running on port 5500
if __name__ == "__main__":
    app.run(port="5500", debug=True)
