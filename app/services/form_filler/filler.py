"""Narrative + fillable PDF -> filled PDF.

Example:
    result = filler.fill("ics_201.pdf", narrative, "ics_201_filled.pdf")

The LLM provider, host, model and timeout are configured through
app.core.config. Ollama remains the default provider; llama.cpp can be
selected with LLM_PROVIDER=llama_cpp.

fill() builds the schema (template.py), sends the prompt + narrative + schema
to the configured provider, validates the extracted data, maps the answer
back to widget names and writes the filled PDF. It returns every
intermediate step so callers (the benchmark) can save them.
"""

import json
import os

from pypdf import PdfWriter

from app.core.config import OLLAMA_MODEL as _OLLAMA_MODEL
from app.services.llm import default_model, generate
from app.services.llm.options import OPTIONS as OPTIONS
from . import template
from .geometry import (
    CHECKBOX,
    RADIOBUTTON,
    SIGNATURE,
    drop_null_parents,
    on_state,
    page_widgets,
)

# Backwards compatibility for existing tests and integrations.
OLLAMA_MODEL = _OLLAMA_MODEL

with open(
    os.path.join(os.path.dirname(__file__), "prompt.txt"),
    "r",
    encoding="utf-8",
) as f:
    PROMPT = f.read()


def validate_extracted_data(data, schema, narrative):
    """Apply conservative validation to model-generated form data.

    Removes obvious cross-column copying in tables and normalizes the
    checkbox sentinel "Off" when it appears in ordinary text columns.

    This is a targeted safeguard, not a complete semantic validator.
    """
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")

    properties = schema.get("properties", {})

    for field_name, field_schema in properties.items():
        if field_schema.get("type") != "array":
            continue

        rows = data.get(field_name)
        if not isinstance(rows, list):
            continue

        item_schema = field_schema.get("items", {})
        item_properties = item_schema.get("properties", {})

        # Identify relevant columns using their schema descriptions.
        name_columns = [
            key
            for key, spec in item_properties.items()
            if "name" in spec.get("description", "").lower()
        ]

        position_columns = [
            key
            for key, spec in item_properties.items()
            if "position" in spec.get("description", "").lower()
        ]

        contact_columns = [
            key
            for key, spec in item_properties.items()
            if "contact" in spec.get("description", "").lower()
        ]

        for row in rows:
            if not isinstance(row, dict):
                continue

            # "Off" is a checkbox sentinel, not a missing text value.
            # Preserve enum-constrained strings.
            for key, spec in item_properties.items():
                if (
                    spec.get("type") == "string"
                    and not spec.get("enum")
                    and row.get(key) == "Off"
                ):
                    row[key] = ""

            # Clear position/contact values only when they exactly duplicate
            # a name in the same row.
            for name_key in name_columns:
                name = row.get(name_key)
                if not isinstance(name, str) or not name.strip():
                    continue

                normalized_name = name.strip().casefold()

                for key in position_columns + contact_columns:
                    value = row.get(key)
                    if (
                        isinstance(value, str)
                        and value.strip().casefold() == normalized_name
                    ):
                        row[key] = ""

    return data


def fill(pdf_path, narrative, out_path=None, model=None, description=""):
    """Fill a PDF from a narrative and optionally write the completed PDF.

    Returns:
        A dictionary containing schema, tables, groups, prompt,
        response_text and values.
    """
    schema, tables, groups = template.create_template(pdf_path)
    strip_empty_descriptions(schema["properties"])

    prompt = build_prompt(narrative, schema, description)

    # Resolve the model through the provider factory. An explicitly supplied
    # model wins; otherwise the selected provider supplies its configured
    # default (OLLAMA_MODEL or LLAMA_CPP_MODEL).
    selected_model = model if model else default_model()
    response_text = call_model(prompt, schema, selected_model)

    # Parse and validate the model output before mapping values to widgets.
    extracted_data = json.loads(response_text)
    extracted_data = validate_extracted_data(
        extracted_data,
        schema,
        narrative,
    )

    # Tables come back as arrays of rows; map them to widget names.
    values = template.expand_output(extracted_data, tables, groups)

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
            item_properties = prop["items"].get("properties", {})
            strip_empty_descriptions(item_properties)

    return props


def build_prompt(narrative, schema, description=""):
    """Build the model prompt from the narrative and target schema."""
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
    """Write extracted values into the corresponding PDF form fields."""
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
