import os
import json
import datetime
from datetime import timedelta
from flask import Flask, request, jsonify, render_template # type: ignore
from flask_cors import CORS # type: ignore
import requests # type: ignore
import fitz  # type: ignore # PyMuPDF
import boto3 # type: ignore
import random

# -------------------------------
# Flask Setup
# -------------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24) # "42c49afbd77de45bb67d01c4278a9b24"  # not strictly used now
CORS(app, supports_credentials=True)

# -------------------------------
# Configuration / Secrets
# -------------------------------
def load_dict_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

secrets_file = "C:\\Users\\Anubhab Roy\\Downloads\\Nekko_WorkFiles\\Teverse\\Bot_backend\\secrets.json"
SECRETS = load_dict_from_json(secrets_file)

aws_access_key_id = SECRETS["aws_access_key_id"]
aws_secret_access_key = SECRETS["aws_secret_access_key"]
INFERENCE_PROFILE_ARN = SECRETS["INFERENCE_PROFILE_ARN"]
REGION = SECRETS["REGION"]

bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION,
                              aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key)

# -------------------------------
# (Optional) Document Analysis
# -------------------------------

def extract_text_from_pdf(uploaded_file):
    # uploaded_file should be a file-like object (e.g., BytesIO)
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    extracted_text = ""
    
    for page in pdf_document:
        extracted_text += page.get_text() + "\n"
    
    pdf_document.close()
    return extracted_text.strip()

with open("document.pdf", "rb") as f:
    company_info_text = extract_text_from_pdf(f)

# -------------------------------
# LLM Call Function
# -------------------------------
def call_llm_api(conversation_history):
    retries = 5
    # Build the system message with your PDF content
    system_message = f"""
    You are Teverse website Chatbot. Below is the company information and product details:
    {company_info_text}
    At TEVERSE, they are an energetic IT consulting startup driven by innovation. They specializes in agile, tailored solutions that empower businesses, accelerate digital transformation, and optimize technology infrastructure.
    At TEVERSE, they elevate businesses with innovative Cloud, AI, and Security solutions—powering transformation, unleashing AI potential, and securing your digital future.

    Your job is to:
    0. Collect Customer Details Such as Name and Mobile Number Mandatorily and if possible other information such as Email, Organisation Name as well.
    1. Present the latest and exciting product offerings by Teverse.
    2. Be empathetic and address the customer's pain points.
    3. Respond normally if the query is unrelated.
    4. Provide 'info@teverse.com.au' if the user asks for the sales team contact and also provide their phone number '+610289124160'.
    5. Engage in a normal conversation.

    Since this is for a chatbot, Please avoid using markdown formatting. Keep your answers short and suitable for a chat environment.
    """
    messages = [{"role": "system", "content": system_message}] + conversation_history

    # Prepare the request payload
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(messages)
            }
        ]
    }

    for attempt in range(retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=INFERENCE_PROFILE_ARN,
                contentType='application/json',
                accept='application/json',
                body=json.dumps(payload)
            )
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']

        except bedrock_runtime.exceptions.ThrottlingException:
            wait_time = 2 ** attempt + random.uniform(0, 1)
            print(f"Throttled. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)

        except Exception as e:
            return f"An error occurred: {str(e)}"

    return "Failed after several retries due to throttling."

# -------------------------------
# Conversations Folder
# -------------------------------
CONVERSATIONS_FOLDER = "conversations"
if not os.path.exists(CONVERSATIONS_FOLDER):
    os.makedirs(CONVERSATIONS_FOLDER)

# ---------------------------------------------------------
# Helper: Find newest JSON file in last 1 minute
# ---------------------------------------------------------
def latest_file_in_last_minute(folder, cutoff):
    """
    Return the path of the single newest .json file if itss
    within the last minute; else None.
    """
    newest_path = None
    newest_ctime = None
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            file_path = os.path.join(folder, filename)
            ctime = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
            # If file was created after cutoff, consider it
            if ctime >= cutoff:
                # Keep track of whichever is newest
                if newest_ctime is None or ctime > newest_ctime:
                    newest_ctime = ctime
                    newest_path = file_path
    return newest_path

# -------------------------------
# Routes
# -------------------------------
@app.route('/')
def index():
    # Just render index.html
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_query = data.get("user_query", "").strip()
    if not user_query:
        return jsonify({"error": "No user query provided"}), 400

    now = datetime.datetime.now()
    one_minute_ago = now - datetime.timedelta(seconds=180)

    # 1) Find the single newest conversation file in the last minute
    latest_path = latest_file_in_last_minute(CONVERSATIONS_FOLDER, one_minute_ago)
    if latest_path is not None:
        # Load existing conversation
        with open(latest_path, "r", encoding="utf-8") as f:
            combined_history = json.load(f)
    else:
        # No recent file => start a blank conversation
        combined_history = []

    # 2) Add the user's new message
    combined_history.append({"role": "user", "content": user_query})

    # 3) Call your LLM
    try:
        reply = call_llm_api(combined_history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # 4) Append the bot's response
    combined_history.append({"role": "assistant", "content": reply})

    # 5) Overwrite the same file if it exists, or create a brand-new file
    if not latest_path:
        latest_path = os.path.join(
            CONVERSATIONS_FOLDER,
            f"chat_{now.strftime('%Y%m%d_%H%M%S')}.json"
        )

    print("Conversation file will be saved at:", os.path.abspath(latest_path))
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(combined_history, f, indent=4)

    return jsonify({"reply": reply})

# -------------------------------
# Main
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
