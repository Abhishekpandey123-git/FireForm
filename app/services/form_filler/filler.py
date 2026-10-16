
"""Narrative + fillable PDF -> filled PDF.

    result = filler.fill("ics_201.pdf", narrative, "ics_201_filled.pdf")

The LLM provider, host, model and timeout are configured through
app.core.config. Ollama remains the default provider; llama.cpp can be
selected with LLM_PROVIDER=llama_cpp.

fill() builds the schema (template.py), sends the prompt + narrative + schema
to the configured provider, maps the answer back to widget names and writes
the filled PDF. It returns every intermediate step so callers (the benchmark)
can save them.
"""

import json
import os

from pypdf import PdfWriter

from app.core.config import OLLAMA_MODEL as _OLLAMA_MODEL
from app.services.llm import default_model, generate

from . import template
from .geometry import (
    CHECKBOX,
    RADIOBUTTON,
    SIGNATURE,
    drop_null_parents,
    on_state,
    page_widgets,
)

OLLAMA_MODEL = _OLLAMA_MODEL

with open(
    os.path.join(os.path.dirname(__file__), "prompt.txt"),
    "r",
    encoding="utf-8",
) as f:
    PROMPT = f.read()


def fill(pdf_path, narrative, out_path=None, model=None, description=""):
    """Fill pdf_path from the narrative. Writes the PDF when out_path is given.

    Returns {schema, tables, groups, prompt, response_text, values}: the
    schema sent to the selected LLM provider, the exact prompt, the raw model
    output, and the flat {widget name: value} dict used to fill the PDF.
    """
    schema, tables, groups = template.create_template(pdf_path)
    strip_empty_descriptions(schema["properties"])

    prompt = build_prompt(narrative, schema, description)
    response_text = call_model(prompt, schema, model or default_model())

    # Tables come back as arrays of rows; map them to widget names.
    values = template.expand_output(json.loads(response_text), tables, groups)

    if out_path:
        write_pdf(pdf_path, values, out_path)

    return {
        "schema": schema,
        "tables": tables,
        "groups": groups,
        "prompt": prompt,
        "response_text": response_text,
        "values": values,
    }


def strip_empty_descriptions(props):
    """Remove empty descriptions recursively from JSON Schema properties."""
    for prop in props.values():
        if prop.get("description") == "":
            del prop["description"]
        if "items" in prop:
            strip_empty_descriptions(prop["items"]["properties"])
    return props


def build_prompt(narrative, schema, description=""):
    """Build the model prompt from the narrative and target schema."""
    # Omit the template description entirely when blank.
    context = (
        f"<template_description>\n{description}\n</template_description>\n\n"
        if description
        else ""
    )

    user_content = (
        context
        + "<incident_narrative>\n"
        + narrative
        + "\n</incident_narrative>\n\n<target_json_schema>\n"
        + json.dumps(schema["properties"], indent=2, ensure_ascii=False)
        + "\n</target_json_schema>"
    )

    return PROMPT.rstrip() + "\n\n" + user_content


def call_model(prompt, schema, model):
    """Generate schema-constrained JSON using the configured LLM provider."""
    return generate(prompt, schema, model)


def write_pdf(pdf_path, values, out_path):
    """Write the extracted values into the corresponding PDF form fields."""
    new_doc = PdfWriter(clone_from=pdf_path)

    # pypdf sets checkboxes by appearance-state name ("/Yes"), not "Yes".
    for page in new_doc.pages:
        drop_null_parents(page)
        page_values = {}

        for widget in page_widgets(page):
            if widget.field_type == SIGNATURE:
                continue

            value = values.get(widget.field_name, "")

            if widget.field_type in (CHECKBOX, RADIOBUTTON):
                value = on_state(widget) if value == "Yes" else "/Off"

            page_values[widget.field_name] = (
                "" if value is None else str(value)
            )

        if page_values:
            new_doc.update_page_form_field_values(page, page_values)

    new_doc.write(out_path)
