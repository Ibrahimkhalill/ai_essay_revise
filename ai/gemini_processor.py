import google.generativeai as genai
import os
import re
import json
from typing import List, Dict, Tuple, Any

# Configure the Gemini API
# In a production environment, use environment variables for API keys
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", "AIzaSyAgpKTlCi3_QPyoeTv9mFgpCxIBXWjszwA"
)
genai.configure(api_key=GEMINI_API_KEY)

# Set up the model
model = genai.GenerativeModel("gemini-2.0-flash")


def get_essay_type(essay_text: str) -> int:
    """
    Use Gemini AI to classify the essay type.
    Returns the essay type ID (1: Argumentative, 2: Narrative, 3: Literary Analysis)
    """
    prompt = f"""
    Analyze the following essay and determine its type. Choose from:
    1. Argumentative Essay
    2. Narrative Essay
    3. Literary Analysis Essay

    Only respond with the number (1, 2, or 3).

    Essay:
    {essay_text[:4000]}  # Limit to first 4000 chars to stay within token limits
    """

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Extract the number from the response
        if "1" in response_text or "argumentative" in response_text.lower():
            return 1
        elif "2" in response_text or "narrative" in response_text.lower():
            return 2
        elif "3" in response_text or "literary" in response_text.lower():
            return 3
        else:
            # Default to argumentative if unclear
            return 1
    except Exception as e:
        print(f"Error classifying essay: {e}")
        # Default to argumentative if there's an error
        return 1


def analyze_essay(
    essay_text: str, essay_type: int, rules: List[Tuple]
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Use Gemini AI to analyze and revise the essay.
    Returns a list of revisions and the revised text.
    """
    # Convert essay type ID to name
    essay_type_names = {1: "Argumentative", 2: "Narrative", 3: "Literary Analysis"}
    essay_type_name = essay_type_names.get(essay_type, "Argumentative")

    # Format rules for the prompt
    rules_text = "\n".join([f"- {rule[0]}: {rule[1]}" for rule in rules])

    # Split essay into paragraphs to process in chunks
    paragraphs = essay_text.split("\n\n")
    all_revisions = []
    revised_paragraphs = []

    # Process each paragraph separately to stay within token limits
    for i, paragraph in enumerate(paragraphs):
        if not paragraph.strip():
            revised_paragraphs.append(paragraph)
            continue

        prompt = f"""
        You are an expert essay editor. Analyze and improve the following paragraph from a {essay_type_name} essay.

        Apply these revision rules:
        {rules_text}

        For each issue you find:
        1. Identify the original text
        2. Provide a revised version
        3. Explain the reason for the change

        Return your analysis in this JSON format:
        {{
            "revisions": [
                {{
                    "original": "original text with issue",
                    "revised": "improved text",
                    "reason": "explanation of the change",
                    "position": {i}
                }}
            ],
            "revised_paragraph": "full revised paragraph"
        }}

        Only respond with the JSON. Paragraph to analyze:

        {paragraph}
        """

        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Extract JSON from response
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)

            # Clean up any markdown formatting
            response_text = response_text.replace("```json", "").replace("```", "")

            # Parse JSON response
            result = json.loads(response_text)

            # Add revisions to the list
            all_revisions.extend(result.get("revisions", []))

            # Add revised paragraph
            revised_paragraphs.append(result.get("revised_paragraph", paragraph))

        except Exception as e:
            print(f"Error processing paragraph {i}: {e}")
            # If there's an error, keep the original paragraph
            revised_paragraphs.append(paragraph)

    # Join paragraphs back together
    revised_text = "\n\n".join(revised_paragraphs)

    return all_revisions, revised_text


def generate_summary(essay_text: str, revisions: List[Dict[str, Any]]) -> str:
    """
    Generate a summary of the revisions made to the essay.
    """
    prompt = f"""
    You are an expert essay editor. Create a concise summary of the revisions made to an essay.

    Number of revisions: {len(revisions)}

    Key revision categories:
    - Grammar and punctuation
    - Style and clarity
    - Structure and organization
    - Content and arguments

    Based on these revisions, provide a 3-5 sentence summary of the main improvements made to the essay.

    Revisions:
    {json.dumps(revisions[:10])}  # Limit to first 10 revisions to stay within token limits
    """

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "Summary generation failed. Please review the individual revisions."
