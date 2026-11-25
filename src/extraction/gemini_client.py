import json
import os
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.extraction.prompts import ORDER_EXTRACTION_PROMPT 
from src.models.order import OrderData

logger = logging.getLogger(__name__)

load_dotenv()

# Explicitly set api_version to v1beta to enable JSON mode
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options={"api_version": "v1beta"}
)


def extract_order_from_image(image_path: str) -> OrderData:
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    

    logger.info("Sending image to Gemini for extraction...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ORDER_EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    json_data = json.loads(response.text)
    return OrderData(**json_data)