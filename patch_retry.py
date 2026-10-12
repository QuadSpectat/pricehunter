def sub(p, old, new):
    s = open(p, encoding="utf-8").read()
    assert old in s, (p, old[:60])
    open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))


sub(
    "pricehunter/llm.py",
    """        text = await self.complete(
            system + "\nRespond with a single JSON value and nothing else.",
            user,
            image=image,
            max_tokens=max_tokens,
        )
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            raise ResolverError("LLM returned no JSON")
        try:
            return json.loads(m.group())
        except json.JSONDecodeError as e:
            raise ResolverError(f"LLM returned invalid JSON: {e}") from e""",
    """        error = "LLM returned no JSON"
        for _attempt in range(2):  # the model occasionally emits broken JSON: retry once
            text = await self.complete(
                system + "\nRespond with a single JSON value and nothing else. "
                "Escape any double quotes inside strings.",
                user,
                image=image,
                max_tokens=max_tokens,
            )
            m = re.search(r"[\[{].*[\]}]", text, re.S)
            if not m:
                error = "LLM returned no JSON"
                continue
            try:
                return json.loads(m.group())
            except json.JSONDecodeError as e:
                error = f"LLM returned invalid JSON: {e}"
        raise ResolverError(error)""",
)

sub(
    "pricehunter/costs.py",
    "        generic: bool = False,\n",
    "        generic: bool = False,\n        cheapest_estimated: bool = False,\n",
)
sub(
    "pricehunter/costs.py",
    "            if generic and current_price_usd is None:",
    """            if cheapest_estimated:
                basis += " - ROUGH: the cheapest offer's shipping/tax is estimated, not quoted"
            if generic and current_price_usd is None:""",
)
sub(
    "pricehunter/pipeline.py",
    "            generic=not product.model,\n",
    """            generic=not product.model,
            cheapest_estimated=bool(
                report.cheapest and report.cheapest.landed and report.cheapest.landed.estimated
            ),
""",
)
print("ok")
