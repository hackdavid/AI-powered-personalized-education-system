import re


def latex_to_plain(text: str) -> str:
    """Convert LaTeX math to readable plain text for embedding.
    ONLY used for content_plain. Never for content field.
    """
    if not text:
        return ""

    # Remove block equation markers
    text = text.replace("$$", "")
    # Remove inline equation markers
    text = text.replace("$", "")

    # Fractions: \frac{a}{b} → a over b
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1 over \2", text)

    # Arrows: \xrightarrow{text} → ->
    text = re.sub(r"\\x(?:left|right)arrow\{[^}]*\}", "->", text)

    # Subscripts: _{text} → sub text
    text = re.sub(r"_\{([^}]*)\}", r" sub \1", text)
    text = re.sub(r"_([a-zA-Z0-9])", r" sub \1", text)

    # Superscripts: ^{text} → to the text
    text = re.sub(r"\^\{([^}]*)\}", r" to the \1", text)
    text = re.sub(r"\^([a-zA-Z0-9])", r" to the \1", text)

    # Greek letters: \alpha → alpha
    text = re.sub(r"\\(alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega)", r"\1", text)

    # Common LaTeX commands
    text = re.sub(r"\\sqrt\{([^}]*)\}", r"square root of \1", text)
    text = re.sub(r"\\sum", "sum", text)
    text = re.sub(r"\\int", "integral", text)
    text = re.sub(r"\\prod", "product", text)
    text = re.sub(r"\\infty", "infinity", text)
    text = re.sub(r"\\pm", "plus or minus", text)
    text = re.sub(r"\\times", "times", text)
    text = re.sub(r"\\div", "divided by", text)
    text = re.sub(r"\\neq", "not equal to", text)
    text = re.sub(r"\\leq", "less than or equal to", text)
    text = re.sub(r"\\geq", "greater than or equal to", text)
    text = re.sub(r"\\approx", "approximately", text)
    text = re.sub(r"\\cdot", " dot ", text)

    # Remove remaining backslash commands
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text)

    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def strip_markdown(text: str) -> str:
    """Remove markdown formatting for plain text version."""
    if not text:
        return ""
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Remove code blocks
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    return text.strip()
