"""


The exact same prompt is used for every model.
"""

SYSTEM_PROMPT = """
You are a text classification system.

Classify the given text into exactly one of these four labels:

positive
negative
neutral
mixed

Definitions:

positive:
The text expresses a clearly favorable or approving opinion.

negative:
The text expresses a clearly unfavorable or critical opinion.

neutral:
The text is factual or descriptive without a clearly favorable
or unfavorable opinion.

mixed:
The text contains both favorable and unfavorable opinions.

Return ONLY one label:
positive
negative
neutral
mixed

Do not explain your answer.
Do not add punctuation.
Do not use Markdown.
"""


def build_messages(text: str):
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": text,
        },
    ]