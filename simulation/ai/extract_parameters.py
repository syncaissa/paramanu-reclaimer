"""Extract candidate parameter values from a text with a local or hosted LLM.

Output rows are UNVERIFIED until a person checks each quote against the
source. Works with any OpenAI-compatible chat-completions endpoint.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request

PROMPT = """You extract physical data from scientific text.
Question: {ask}
Return JSON: {{"values": [{{"quantity": str, "value": number, "units": str,
"quote": exact sentence from the text, "location": page/section if known}}]}}.
Use only values stated in the text. If none, return {{"values": []}}.

TEXT:
{text}"""


def ask_llm(text: str, ask: str) -> list[dict]:
    url = os.environ["PARAMANU_LLM_URL"].rstrip("/") + "/chat/completions"
    body = {"model": os.environ["PARAMANU_LLM_MODEL"], "temperature": 0,
            "messages": [{"role": "user", "content": PROMPT.format(ask=ask, text=text[:60000])}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    if os.environ.get("PARAMANU_LLM_KEY"):
        req.add_header("Authorization", "Bearer " + os.environ["PARAMANU_LLM_KEY"])
    with urllib.request.urlopen(req, timeout=300) as resp:
        content = json.load(resp)["choices"][0]["message"]["content"]
    start, end = content.find("{"), content.rfind("}")
    return json.loads(content[start:end + 1]).get("values", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="plain-text file of the paper or data sheet")
    ap.add_argument("--ask", required=True)
    ap.add_argument("--out", default="extracted_unverified.csv")
    args = ap.parse_args()
    text = open(args.source, encoding="utf-8", errors="replace").read()
    rows = ask_llm(text, args.ask)
    # keep only values whose quote really appears in the source
    kept = [r for r in rows if r.get("quote") and r["quote"] in text]
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, ["source", "quantity", "value", "units", "quote", "location", "verified"])
        if fh.tell() == 0:
            w.writeheader()
        for r in kept:
            w.writerow({"source": args.source, **{k: r.get(k, "") for k in
                        ("quantity", "value", "units", "quote", "location")}, "verified": "no"})
    print(f"{len(kept)} of {len(rows)} values kept (quote found verbatim); written to {args.out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
