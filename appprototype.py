from flask import Flask, render_template, request, jsonify
import openai
from flask_cors import CORS

# Set the OpenAI API key
openai.api_key = "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"
app = Flask(__name__)

CORS(app)


# Separate function for GPT-3 response
def generateChatResponse(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a chatbot"},
            {"role": "user", "content": prompt},
        ],
    )

    try:
        answer = response.choices[0].message.content
    except:
        answer = "Oops answer failed to generate, please try again or come back later"

    return answer


# Root endpoint to serve the frontend HTML
@app.route("/")
def index():
    return render_template("index2.html", **locals())


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


@app.route("/logout")
def logout():
    pass


@app.route("/profile")
def profile():
    pass


if __name__ == "__main__":
    app.run(port="5500", debug=True)
