# Ensure your dependencies are installed with:
# pip install -r requirements.txt

# Load env keys from .env (REDIS_KEY, WANDB_KEY, OPENAI_API_KEY, etc.)
from dotenv import load_dotenv
load_dotenv()

import os
import weave
import openai
from openai import OpenAI

# Find your OpenAI API key at: https://platform.openai.com/api-keys
# Add OPENAI_API_KEY=sk-... to your .env file
weave.init("viswanathkothe-syracuse-university/weavehacks")
client = openai.OpenAI(
    # The custom base URL points to W&B Inference
    base_url='https://api.inference.wandb.ai/v1',

    # Get your API key from https://wandb.ai/authorize
    # Consider setting it in the environment as OPENAI_API_KEY instead for safety
    api_key=os.getenv("WANDB_KEY"),

    # Optional: Team and project for usage tracking
    project="viswanathkothe-syracuse-university/weavehacks",
)
@weave.op
def create_completion(message: str, client: openai.OpenAI) -> str:
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message}
        ],
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    message = "Tell me a joke."
    print(create_completion(message, client))
