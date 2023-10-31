from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import openai
from flask_cors import CORS


# Set the OpenAI API key
openai.api_key = "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"
app = Flask(__name__)

CORS(app)
# Configure server-side session
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)


# Initialize conversation history with the system message
conversation_history = [
    {
        "role": "system",
        "content": (
            "You are a Personalized SQL Teacher with expertise in andragogical practices. "
            "Your primary goals are to be polite, provide comprehensive answers with relevant examples, "
            "and display data tables in tabular/markdown format for easy interpretation by the user. "
            "Whenever a user asks to practice, you will create suitable tables with appropriate attributes and data. "
            "Then, you'll display them in tabular form and generate relevant questions to test the user's understanding. "
            "It's essential to verify and provide feedback on the answers given by the user."
        ),
    }
]


# Separate function for GPT-3 response
def generateChatResponse(prompt):
    conversation_history.append({"role": "user", "content": prompt})
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=conversation_history
    )

    try:
        answer = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": answer})
    except:
        answer = "Oops answer failed to generate, please try again or come back later"

    return answer


# Root endpoint to serve the frontend HTML
@app.route("/")
def index():
    session.clear()
    return render_template("index.html", **locals())


# Endpoint for GPT API completions
@app.route("/callapi", methods=["POST"])
def callapi():
    data = request.get_json()
    prompt = data["prompt"]
    res = {}  # result
    try:
        res["answer"] = generateChatResponse(prompt)
        return jsonify(res), 200
    except Exception as e:  # Here's where we handle general exceptions
        res["error"] = "Server error: " + str(e)
        return jsonify(res), 500  # Sending a 500 Internal Server Error status


# Future routes for user authentication
@app.route("/register", methods=["GET", "POST"])
def register():
    pass


@app.route("/login", methods=["GET", "POST"])
def login():
    pass


@app.route("/quit", methods=["POST"])
def quit():
    session.clear()
    return jsonify({"status": "Session cleared"}), 200


@app.route("/profile")
def profile():
    pass


if __name__ == "__main__":
    app.run(port="5500", debug=True)
