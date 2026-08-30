import re
import ast
import json

def extract_dict(s: str):
    candidates = re.findall(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL)
    candidates.append(s)

    errors = []
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            errors.append(str(e))

        # Accept responses like "Here is the JSON: {...}" without falling
        # back to Python evaluation for ordinary JSON payloads.
        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate[match.start():].strip())
                return parsed
            except json.JSONDecodeError as e:
                errors.append(str(e))

        start = candidate.find('{')
        end = candidate.rfind('}') + 1  # add 1 to include the closing bracket
        if start < 0 or end <= start:
            continue

        dict_str = candidate[start:end]
        clean_dict_str = dict_str.replace("`", "").replace("\n", "")

        try:
            return ast.literal_eval(clean_dict_str)
        except Exception as e:
            errors.append(str(e))

    return f"error {errors[-1] if errors else 'no JSON object found'}"
    

def extract_info(text_blob):
    """
    Extracts structured information, including URLs, task IDs, and action mappings (label to custom ID), from a given text block.
    This internal helper function parses model responses to retrieve key data.
    
    Args:
        text_blob (str): The text block from which to extract information.
        
    Returns:
        dict: A dictionary containing the extracted information with the following keys:
              - 'task_id' (str, optional): The task ID extracted from the text.
              - 'urls' (list): A list of URLs found in the text.
              - 'actions' (dict): A dictionary mapping labels to custom IDs.
    """
    extracted_data = {
        "task_id": None,
        "urls": [],
        "actions": {} # label -> custom_id
    }

    task_id_match = re.search(r"task_id: `([^`]+)`", text_blob)
    if task_id_match:
        extracted_data["task_id"] = task_id_match.group(1)

    urls = re.findall(r"https?://\S+", text_blob)
    for url in urls:
        if url.endswith('.png') or '/download/' in url:
            cleaned_url = url.rstrip(')')
            if cleaned_url not in extracted_data["urls"]:
                 extracted_data["urls"].append(cleaned_url)

    lines = text_blob.strip().split('\n')
    in_table = False
    header_skipped = False
    separator_skipped = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('|') and '|' in line[1:]:
            if 'label' in line and 'custom_id' in line:
                 header_skipped = True
                 in_table = True
                 continue
            if header_skipped and line.startswith('|---'):
                 separator_skipped = True
                 continue

            if in_table and header_skipped and separator_skipped:
                parts = [part.strip() for part in line.split('|')]
                if len(parts) >= 5:
                    label = parts[2]
                    custom_id = parts[4]
                    if label and custom_id:
                        extracted_data["actions"][label] = custom_id
        else:
            if in_table:
                 in_table = False

    return extracted_data