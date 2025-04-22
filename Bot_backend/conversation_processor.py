import os, json, time, re, datetime, requests  # type: ignore
import boto3 # type: ignore

# --- Load secrets ---
def load_dict_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

secrets_file = "../secrets.json"
SECRETS = load_dict_from_json(secrets_file)

aws_access_key_id = SECRETS["aws_access_key_id"]
aws_secret_access_key = SECRETS["aws_secret_access_key"]
INFERENCE_PROFILE_ARN = SECRETS["INFERENCE_PROFILE_ARN"]
REGION = SECRETS["REGION"]

bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION,
                              aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key)

def call_llm_api(system_message, user_query):
    # Combine system and user messages
    messages = system_message + user_query

    # Prepare the request payload
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": messages
            }
        ]
    }

    try:
        # Invoke the model (Claude)
        response = bedrock_runtime.invoke_model(
            modelId=INFERENCE_PROFILE_ARN,  # Use the ARN for your inference profile
            contentType='application/json',
            accept='application/json',
            body=json.dumps(payload)
        )

        # Parse and return the response
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except Exception as e:
        return f"An error occurred: {str(e)}"

# --- LLM Call for Lead Extraction ---
def extract_lead_details_from_conversation(conversation):
    extraction_prompt = """
    You are tasked with extracting the following details from this conversation:
    - Name (if provided)
    - Phone Number
    - Email
    - Any pain points or comments shared by the user

    Return the information as a JSON object in the following format:
    ```json
        {
        "name": "",
        "phone": "",
        "email": "",
        "pain_points": ""
        }
    ```
    """
    
    user_query = f"The Conversation so far: {json.dumps(conversation)}"

    answer = call_llm_api(extraction_prompt, user_query)
    print("LLM response:\n", answer)
    try:
        # return json.loads(answer[7:-3])
        return json.loads(answer.split("```json")[1].split("```")[0])
    except:
        # return json.loads(answer[3:-3])
        try:
            return json.loads(answer)
        except:
            return json.loads(answer.split("```")[1].split("```")[0])

# --- File paths and folders ---
CONV_FOLDER = "conversations"
CONTACTS_FOLDER = "contacts"

if not os.path.exists(CONTACTS_FOLDER):
    os.makedirs(CONTACTS_FOLDER)

# Instead of a set, use a dict to store each file's last processed modification time.
processed_files = {}  # key: filename, value: last processed modification timestamp

while True:
    files = os.listdir(CONV_FOLDER)
    for file in files:
        if file.endswith(".json"):
            filepath = os.path.join(CONV_FOLDER, file)
            try:
                # Get the file's current modification time
                mod_time = os.path.getmtime(filepath)
                
                # Check if this file has not been processed or has been updated
                if file not in processed_files or mod_time > processed_files[file]:
                    with open(filepath, "r", encoding="utf-8") as f:
                        conversation = json.load(f)
                    
                    # Extract lead details using the LLM
                    lead_data = extract_lead_details_from_conversation(conversation)
                    lead = lead_data
                    
                    if lead.get("name") and lead.get("phone"):
                        contact_file = os.path.join(CONTACTS_FOLDER, f"lead_{file}")
                        with open(contact_file, "w", encoding="utf-8") as cf:
                            json.dump(lead, cf, indent=4)
                        print(f"[{datetime.datetime.now()}] Extracted and saved lead from {file} to {contact_file}")
                    else:
                        print(f"[{datetime.datetime.now()}] Lead details not complete in {file}.")
                    
                    # Update processed_files with current modification time
                    processed_files[file] = mod_time
            except Exception as e:
                print(f"Error processing {file}: {e}")
    # Wait before checking again (e.g., 10 seconds)
    time.sleep(10)
