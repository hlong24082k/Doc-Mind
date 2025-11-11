import json
from typing import Union


class PostProcessor:
    """
    Post-processes the raw LLM output to extract structured data.
    """

    def __init__(self):
        pass

    def process(self, llm_output: str, return_json: bool = False) -> Union[str, dict]:
        """
        Extracts the JSON part from the LLM's output.
        Assumes the LLM output is a string that might contain text before or after a JSON object.
        """
        try:
            # Find the first and last curly braces to isolate the JSON
            start_index = llm_output.find('{')
            end_index = llm_output.rfind('}')

            if start_index == -1 or end_index == -1:
                raise ValueError("No JSON object found in LLM output.")

            json_string = llm_output[start_index : end_index + 1]

            if return_json:
                return json.loads(json_string)
            return json_string
        except Exception as e:
            raise ValueError(f"Error extracting JSON from LLM output: {e}")
