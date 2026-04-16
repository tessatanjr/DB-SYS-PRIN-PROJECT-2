"""LLM client setup and chat functions for OpenAI, Claude, and Ollama."""

import json
import re
from openai import OpenAI
from anthropic import AnthropicFoundry


# Provider presets: (default_endpoint, models_list, needs_api_key)
PROVIDER_PRESETS = {
    "OpenAI":  ("https://sc3020-db.openai.azure.com/openai/v1/",
                ["gpt-4.1-nano", "gpt-5-nano", "gpt-5.4-nano"], True),
    "Claude":  ("https://sc3020-claude-resource.openai.azure.com/anthropic",
                ["claude-haiku-4-5"], True),
    "Ollama":  ("http://localhost:11434/v1/",
                [], False),
}

# Module-level LLM config — set via set_llm_config() from the GUI
_llm_config = {
    "provider": "OpenAI",
    "endpoint": PROVIDER_PRESETS["OpenAI"][0],
    "api_key": "",
    "model": PROVIDER_PRESETS["OpenAI"][1][0],
}


def set_llm_config(provider, api_key, model, endpoint):
    """Configure the LLM client."""
    _llm_config["provider"] = provider
    _llm_config["api_key"] = api_key
    _llm_config["model"] = model
    _llm_config["endpoint"] = endpoint


def _get_llm_client():
    provider = _llm_config["provider"]
    api_key = _llm_config["api_key"]
    model = _llm_config["model"]
    endpoint = _llm_config["endpoint"]

    if not model or not endpoint:
        return None, None
    if provider != "Ollama" and not api_key:
        return None, None

    if provider == "Claude":
        client = AnthropicFoundry(api_key=api_key, base_url=endpoint)
    else:
        client = OpenAI(
            base_url=endpoint,
            api_key=api_key if api_key else "ollama",
        )

    return client, model


def _chat_completion(client, model, messages, temperature=0.4, max_tokens=1000):
    """Chat completion supporting OpenAI-compatible and Anthropic Foundry clients."""
    if isinstance(client, AnthropicFoundry):
        system_text = ""
        claude_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                claude_messages.append({"role": m["role"], "content": m["content"]})
        kwargs = {"model": model, "messages": claude_messages,
                  "temperature": temperature, "max_tokens": max_tokens}
        if system_text:
            kwargs["system"] = system_text.strip()
        response = client.messages.create(**kwargs)
        return response.content[0].text
    else:
        response = client.chat.completions.create(
            model=model, messages=messages,
        )
        return response.choices[0].message.content.strip()


def llm_enhance_annotations(sql_query, operators, aqp_comparisons, annotations):
    client, deployment = _get_llm_client()
    if not client:
        return annotations

    context = {
        "sql_query": sql_query,
        "operators": operators,
        "aqp_comparisons": aqp_comparisons,
        "template_annotations": [
            {"clause": a["clause"], "sql_text": a["sql_text"],
             "annotations": a["annotations"]}
            for a in annotations
        ],
    }

    prompt = (
        "You are a database query plan expert. Given an SQL query, its execution plan "
        "details, alternative plan cost comparisons, and template annotations, rewrite "
        "each annotation into a clear, concise, and insightful natural language explanation.\n\n"
        "Guidelines:\n"
        "- Explain HOW each part of the query is executed (scan type, join algorithm, etc.)\n"
        "- Explain WHY the optimizer chose that operator over alternatives, using cost ratios\n"
        "- Keep each annotation to 1-3 sentences, be specific with numbers\n"
        "- Do NOT add information not supported by the data\n"
        "- Use plain English understandable by someone learning databases\n\n"
        "Return ONLY a valid JSON array where each element has:\n"
        '  {"clause": "<clause name>", "annotations": ["<rewritten annotation 1>", ...]}\n\n'
        f"Data:\n{json.dumps(context, default=str)}"
    )

    try:
        content = _chat_completion(
            client, deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=2000,
        )
        # Strip markdown code fences
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
        if fence_match:
            content = fence_match.group(1).strip()
        bracket_start = content.find("[")
        bracket_end = content.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            content = content[bracket_start:bracket_end + 1]
        else:
            brace_start = content.find("{")
            brace_end = content.rfind("}")
            if brace_start != -1 and brace_end != -1:
                content = "[" + content[brace_start:brace_end + 1] + "]"

        enhanced = json.loads(content)
        if isinstance(enhanced, dict):
            enhanced = [enhanced]

        enhanced_map = {e["clause"]: e["annotations"] for e in enhanced}
        for ann in annotations:
            if ann["clause"] in enhanced_map:
                ann["annotations"] = enhanced_map[ann["clause"]]

        return annotations

    except Exception as e:
        print(f"LLM enhancement failed, using template annotations: {e}")
        return annotations


def llm_chat(user_message, sql_query, qep_text, operators, aqp_comparisons, chat_history):
    client, deployment = _get_llm_client()
    if not client:
        return ("LLM not configured. Enter your API Key\n"
                "in the connection settings panel at the top.")

    system_msg = (
        "You are a helpful database query plan expert assistant. "
        "The user has submitted an SQL query and you have access to its "
        "query execution plan (QEP), operator details, and alternative plan "
        "cost comparisons. Answer the user's questions about the query, its "
        "execution plan, performance, and possible optimizations.\n\n"
        "Be concise, specific, and reference actual costs/operators from the data. "
        "If the user asks something unrelated to the query plan, politely redirect.\n\n"
        f"=== SQL QUERY ===\n{sql_query}\n\n"
        f"=== QEP (TEXT) ===\n{qep_text}\n\n"
        f"=== OPERATORS ===\n{json.dumps(operators, default=str)}\n\n"
        f"=== AQP COST COMPARISONS ===\n{json.dumps(aqp_comparisons, default=str)}"
    )

    messages = [{"role": "system", "content": system_msg}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        return _chat_completion(client, deployment, messages=messages,
                                temperature=0.4, max_tokens=1000)
    except Exception as e:
        return f"LLM error: {e}"
