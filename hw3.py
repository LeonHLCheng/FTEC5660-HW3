#!/usr/bin/env python3
"""FTEC5660 HW3 student starter: an agent that applies 3 of Fisher's 15 points using tools."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sqlite3
import threading
import zlib
from pathlib import Path
from typing import Any


MODEL_NAME = "deepseek-v4-flash"
INTERVIEW_LIMIT = 10
MAX_SQL_ROWS = 50

# Philip Fisher, "Common Stocks and Uncommon Profits", Part One, Chapter 3.
# For every point, PASS means the company looks good on it. You choose 3
# points and decide yourself what PASS means for each of them.
FISHER_POINTS = {
    1: "Does the company have products or services with sufficient market potential to make possible a sizable increase in sales for at least several years?",
    2: "Does the management have a determination to continue to develop products or processes that will still further increase total sales potentials when the growth potentials of currently attractive product lines have largely been exploited?",
    3: "How effective are the company's research and development efforts in relation to its size?",
    4: "Does the company have an above-average sales organization?",
    5: "Does the company have a worthwhile profit margin?",
    6: "What is the company doing to maintain or improve profit margins?",
    7: "Does the company have outstanding labor and personnel relations?",
    8: "Does the company have outstanding executive relations?",
    9: "Does the company have depth to its management?",
    10: "How good are the company's cost analysis and accounting controls?",
    11: "Are there other aspects of the business, somewhat peculiar to the industry involved, which will give the investor important clues as to how outstanding the company may be in relation to its competition?",
    12: "Does the company have a short-range or long-range outlook in regard to profits?",
    13: "In the foreseeable future will the growth of the company require sufficient equity financing so that the larger number of shares then outstanding will largely cancel the existing stockholders' benefit from this anticipated growth?",
    14: "Does the management talk freely to investors about its affairs when things are going well but 'clam up' when troubles and disappointments occur?",
    15: "Does the company have a management of unquestionable integrity?",
}
VERDICTS = ("PASS", "FAIL")



def load_env_file(path: Path = Path(".env")) -> None:
    """Load the simple KEY=VALUE entries used by this homework."""
    if not path.is_file():
        return
    import os

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


# Choose any 3 of the 15 points, e.g. CHOSEN_POINTS = [1, 7, 15]. Your agent
# gives a PASS or FAIL verdict on these 3 points only, with your own rule for each.
CHOSEN_POINTS: list[int] = [1,4,7]  ### YOUR CODE HERE


def build_agent() -> Any:
    """Create and return your model or agent once.

    Suggested imports:
        from langchain_deepseek import ChatDeepSeek
        from langchain.agents import create_agent

    Use the DeepSeek model named by ``MODEL_NAME``. The API key is loaded
    from .env. Each company has its own tools (see ``analyze_companies``), so
    you will probably create one tool-calling agent per company there.
    """
    ### YOUR CODE HERE
    import os
    from langchain_deepseek import ChatDeepSeek
    llm = ChatDeepSeek(
    model = MODEL_NAME,
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
    )
    return llm



async def analyze_single_company(
    agent: Any, 
    name: str, 
    tools: list[Any], 
    semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    """Analyze one company: tools gather facts, LLM reasons and decides all 3 verdicts."""
    import json
    from langchain_core.messages import SystemMessage, HumanMessage
    list_docs_tool, read_doc_tool, sql_tool, interview_tool = tools
    async with semaphore:
        # ----------------------------------------------------------------------
        # 1. TOOL CALL: Gather Point 1 Financial Evidence (Dynamic GROUP BY)
        # ----------------------------------------------------------------------
        sql_growth = """
        WITH full_years AS (
            SELECT 
                substr(order_date, 1, 4) AS yr,
                SUM(amount) AS rev
            FROM orders
            GROUP BY yr
            HAVING COUNT(DISTINCT substr(order_date, 1, 7)) = 12
        ),
        calc AS (
            SELECT 
                yr,
                rev,
                LAG(rev, 2) OVER (ORDER BY yr) AS rev_2y_ago,
                LAG(yr, 2) OVER (ORDER BY yr) AS yr_2y_ago
            FROM full_years
        )
        SELECT 
            c.industry AS [Industry],
            m.revenue_growth_2y_pct || '%' AS [Market_Standard_Benchmark] ,
            calc.yr_2y_ago AS start_year,
            calc.yr AS latest_year,
            ROUND(calc.rev / 1000.0, 1) || ' MUSD' AS [Period_End_Revenue],
            ROUND(((calc.rev - calc.rev_2y_ago) * 100.0 / calc.rev_2y_ago), 1) || '%' AS [Company_Actual_2Y_Growth],
            CASE 
                WHEN ((calc.rev - calc.rev_2y_ago) * 100.0 / calc.rev_2y_ago) >= m.revenue_growth_2y_pct 
                    THEN 'OUTPERFORM (+ ' || ROUND(((calc.rev - calc.rev_2y_ago) * 100.0 / calc.rev_2y_ago) - m.revenue_growth_2y_pct, 1) || '%)'
                ELSE 'UNDERPERFORM (- ' || ROUND(m.revenue_growth_2y_pct - ((calc.rev - calc.rev_2y_ago) * 100.0 / calc.rev_2y_ago), 1) || '%)'
            END AS [Company_vs_Market_Status]
        FROM company c
        JOIN industry_medians m ON c.industry = m.industry
        JOIN calc ON calc.rev_2y_ago IS NOT NULL
        ORDER BY calc.yr DESC
        LIMIT 1;
        """
        growth_fact = sql_tool.invoke({"query": sql_growth})
        sql_revenue = """
        WITH quarterly_rev AS (
            SELECT 
                substr(order_date, 1, 4) || 'Q' || ((CAST(substr(order_date, 6, 2) AS INT) - 1) / 3 + 1) AS quarter,
                SUM(amount) AS rev
            FROM orders
            GROUP BY quarter
        ),
        quarterly_growth AS (
            SELECT 
                quarter,
                ROUND(rev / 1000.0, 1) AS rev_musd,
                LAG(rev, 1) OVER (ORDER BY quarter ASC) AS prev_q_rev,
                LAG(rev, 4) OVER (ORDER BY quarter ASC) AS prev_year_same_q_rev,
                ROUND(((rev - LAG(rev, 1) OVER (ORDER BY quarter ASC)) * 100.0 / LAG(rev, 1) OVER (ORDER BY quarter ASC)), 1) AS qoq_growth_pct,
                ROUND(((rev - LAG(rev, 4) OVER (ORDER BY quarter ASC)) * 100.0 / LAG(rev, 4) OVER (ORDER BY quarter ASC)), 1) AS yoy_same_q_growth_pct
            FROM quarterly_rev
        )
        SELECT 
            quarter AS [Quarter],
            rev_musd || ' MUSD' AS [Revenue],
            CASE 
                WHEN qoq_growth_pct IS NULL THEN 'N/A (base)' 
                WHEN qoq_growth_pct >= 0 THEN '+' || qoq_growth_pct || '%' 
                ELSE qoq_growth_pct || '%' 
            END AS [QoQ_Sequential_Growth],
            CASE 
                WHEN yoy_same_q_growth_pct IS NULL THEN 'N/A (base)' 
                WHEN yoy_same_q_growth_pct >= 0 THEN '+' || yoy_same_q_growth_pct || '%' 
                ELSE yoy_same_q_growth_pct || '%' 
            END AS [YoY_Same_Quarter_Growth]
        FROM quarterly_growth
        ORDER BY quarter DESC;

        """
        revenue_history = sql_tool.invoke({"query": sql_revenue})

        sql_product = """
            SELECT 
                substr(launch_date, 1, 4) || 'Q' || ((CAST(substr(launch_date, 6, 2) AS INT) - 1) / 3 + 1) AS [Launch_Quarter],
                COUNT(*) AS [Number_of_Products_Launched],
                GROUP_CONCAT(product, '; ') AS [Product_List]
            FROM products
            GROUP BY [Launch_Quarter]
            ORDER BY [Launch_Quarter] DESC;
        """
        product_history = sql_tool.invoke({"query": sql_product})
        # ----------------------------------------------------------------------
        # 2. TOOL CALL: Scuttlebutt Field Interviews (Point 4 & Point 7)
        # ----------------------------------------------------------------------
        p4_quote = interview_tool.invoke({"role": "customer", "topic": "sales_team"})
        p7_quote_current = interview_tool.invoke({"role": "current_employee", "topic": "working_conditions"})
        p7_quote_former = interview_tool.invoke({"role": "former_employee", "topic": "working_conditions"})
        # ----------------------------------------------------------------------
        # 3. LLM EVALUATION: The AI reasons over all 3 points and decides verdicts
        # ----------------------------------------------------------------------
        prompt = f"""
            You are an equity research analyst evaluating '{name}' using Philip Fisher's 15-point framework from 'Common Stocks and Uncommon Profits'.
            Evaluate the company on Points 1, 4, and 7 based strictly on the factual evidence provided:
            ### Evidence for Point 1 '{FISHER_POINTS[1]}' :
            - Industry & Growth Comparison:
            {growth_fact}
            - Revenue Progression:
            {revenue_history}
            - Product Launch History:
            {product_history}
            - Evaluation Rule:
            According to Philip Fisher, an outstanding company must possess products or services with sufficient addressable market potential to sustain a sizable, multi-year increase in sales, rather than relying on saturated lines or temporary one-off surges.
            Weigh all three dimensions of evidence together:
            1. Multi-Year Industry Benchmark:
               - Compare the company's multi-year sales growth over completed cycles against its industry peer median. OUTPERFORM indicates above-average customer demand and market share gains; UNDERPERFORM indicates market saturation, lagging competitiveness, or slowing industry momentum.
            2. Quarterly Revenue Trajectory:
               - Examine recent quarterly performance (newest quarters first) for ongoing momentum, noting whether YoY same-quarter growth remains consistently positive or is decelerating.
            3. Product Launch Cadence:
               - Review the company's commercialized product lines to assess product vitality, noting whether fresh product launches in recent quarters are expanding total sales potential.
            ### Point 1 Final Determination:
                - Mark PASS if the company demonstrates strong multi-year market potential outperforming its industry peer standard, backed by positive quarterly momentum and active commercialized product lines.
                - Mark FAIL if the company underperforms its industry peer benchmark, exhibits persistent sales stagnation, or lacks the product potential to sustain future expansion.
            ### Evidence for Point 4 '{FISHER_POINTS[4]}':
            - Customer Field Interview: "{p4_quote}"
            - Evaluation Rule: PASS if the sales organization is consultative, technically competent, and proactive. FAIL if customers report lack of product knowledge, rapid rep turnover, or transactional price-sheet delivery.
            ### Evidence for Point 7 (Outstanding labor and personnel relations):
            - Current Employee Field Interview: "{p7_quote_current}"
            - Former Employee Field Interview: "{p7_quote_former}"
            - Evaluation Rule: PASS if labor relations are positive (fair pay, high retention, healthy morale). FAIL if labor relations are negative, such as chronic excessive overtime, high employee turnover, or labor unrest.
            ### Instructions:
            Determine the verdict (PASS or FAIL) for Point 1, Point 4, and Point 7.
            Provide a concise 2-3 sentence executive summary explaining your rationale.
            If data is missing, unavailable, '(no rows)', or interviewees cannot comment, mark that point FAIL. Never output null, N/A, or UNKNOWN.
            Respond ONLY with a JSON object in this exact schema:
            {{
              "point_1_verdict": "PASS" or "FAIL",
              "point_4_verdict": "PASS" or "FAIL",
              "point_7_verdict": "PASS" or "FAIL",
              "summary": "Executive summary here"
            }}
            """
        # Retry loop for API resilience
        last_error = ""
        for attempt in range(3):
            try:
                response = await agent.ainvoke([
                    SystemMessage(content="You are a rigorous financial analyst. Output valid JSON only, without markdown code fences."),
                    HumanMessage(content=prompt)
                ])
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.strip("`").removeprefix("json").strip()
                parsed = json.loads(text)
                p1_v = "PASS" if str(parsed.get("point_1_verdict", "")).strip().upper() == "PASS" else "FAIL"
                p4_v = "PASS" if str(parsed.get("point_4_verdict", "")).strip().upper() == "PASS" else "FAIL"
                p7_v = "PASS" if str(parsed.get("point_7_verdict", "")).strip().upper() == "PASS" else "FAIL"
                summary = parsed.get("summary", "")
                if p1_v in ("PASS", "FAIL") and p4_v in ("PASS", "FAIL") and p7_v in ("PASS", "FAIL"):
                    return {
                        "points": {1: p1_v, 4: p4_v, 7: p7_v},
                        "summary": summary
                    }
            except Exception as e:
                last_error = str(e)
                await asyncio.sleep(1.0 * (attempt + 1))
        # If all 3 API retries fail, return audit failure without crashing
        return {
            "points": {1: "FAIL", 4: "FAIL", 7: "FAIL"},
            "summary": f"Analysis failed after 3 API retries for {name}. Error: {last_error}"
        }



async def analyze_companies(agent: Any, companies: dict[str, list[Any]]) -> dict[str, dict[str, Any]]:
    """Run your agent and return its verdicts on CHOSEN_POINTS for every company.

    ``companies`` maps each company folder name to its four LangChain tools:

        list_documents()             names and dates of the company's documents
        read_document(name)          the text of one document
        sql_query(query)             one read-only SQLite query on company.db
        interview(role, topic)       one interview answer (INTERVIEW_LIMIT per company)

    Give the tools to a tool-calling agent, e.g.
    ``create_agent(model, tools=companies[name], system_prompt=...)``, or call
    them yourself with ``tool.invoke({...})``. The README explains the
    documents, the database tables and the interview roles and topics.

    Return one dictionary per company folder name, e.g. with
    CHOSEN_POINTS = [1, 7, 15]:

        {
            "hollins_group": {
                "points": {1: "PASS", 7: "FAIL", 15: "PASS"},
                "summary": "Two or three sentences explaining the verdicts.",
            },
            ...
        }

    Each chosen point needs a verdict ("PASS" or "FAIL"; True/False also
    works). Other points are ignored.

    Catch errors per company (e.g. a failed API call) and still return an
    entry for it: an exception here means no results.csv, which scores zero.
    You may analyse companies in parallel (e.g. ``asyncio.gather``).
    """
    ### YOUR CODE HERE
    semaphore = asyncio.Semaphore(5)
    tasks = [
        analyze_single_company(agent, name, tools, semaphore)
        for name, tools in companies.items()
    ]
    results = await asyncio.gather(*tasks)
    return {name: res for name, res in zip(companies.keys(), results)}



# Everything below is provided runner/scoring code. No edits are needed.
# Your code must read company data only through these tools: do not open
# company.db or interviews.dat directly.

INTERVIEWS_USED: dict[str, int] = {}


def company_folders(folder: Path) -> list[Path]:
    """Return one sub-folder per company directly inside *folder*, sorted by name."""
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def make_tools(company_folder: Path) -> list[Any]:
    """Build the four tools for one company."""
    from langchain_core.tools import tool

    name = company_folder.name
    db_uri = f"{(company_folder / 'company.db').resolve().as_uri()}?mode=ro"
    answers = json.loads(zlib.decompress((company_folder / "interviews.dat").read_bytes()))
    documents = {p.name: p for p in sorted(company_folder.glob("*.md"))}
    lock = threading.Lock()
    INTERVIEWS_USED[name] = 0

    @tool
    def list_documents() -> str:
        """List this company's documents (annual letter, earnings calls, news) with their dates."""
        lines = []
        for doc_name, path in documents.items():
            text = path.read_text(encoding="utf-8").splitlines()
            dated = next((line for line in text if line.startswith("Date:")), "")
            lines.append(f"{doc_name}: {text[0].lstrip('# ')} ({dated or 'undated'})")
        return "\n".join(lines)

    @tool
    def read_document(name: str) -> str:
        """Return the full text of one document named by list_documents, e.g. 'annual_letter_2025.md'."""
        path = documents.get(name.strip())
        if path is None:
            return f"No document named {name!r}. Available: {', '.join(documents)}"
        return path.read_text(encoding="utf-8")

    @tool
    def sql_query(query: str) -> str:
        """Run one read-only SQLite query on this company's database and return at most 50 rows.

        Amounts are in USD thousands. Dates are 'YYYY-MM-DD', months 'YYYY-MM', quarters like '2025Q3'.
        Tables:
          company(name, industry)
          industry_medians(industry, revenue_growth_2y_pct, new_product_share_pct, new_product_sales_per_rd, operating_margin_pct)
          orders(order_id, order_date, product, customer, amount, note)
          products(product, launch_date)
          monthly_costs(month, cost_of_sales, selling_admin, research_development)
          quarterly_cash(quarter, operating_cash_flow, capex, cash_end)
          capex_plan(year, planned_capex)
          returns(month, units_shipped, units_returned)
          insider_trades(trade_date, person, title, side, shares, price)
        Use SUM, GROUP BY and WHERE to compute totals rather than reading raw rows.
        """
        try:
            con = sqlite3.connect(db_uri, uri=True)
            try:
                cursor = con.execute(query)
                columns = [c[0] for c in cursor.description or []]
                rows = cursor.fetchmany(MAX_SQL_ROWS + 1)
            finally:
                con.close()
        except sqlite3.Error as exc:
            return f"SQL error: {exc}"
        if not columns:
            return "Query returned no columns."
        fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)  # noqa: E731
        out = [" | ".join(columns)] + [" | ".join(fmt(v) for v in row) for row in rows[:MAX_SQL_ROWS]]
        if len(rows) > MAX_SQL_ROWS:
            out.append(f"... more rows not shown (limit {MAX_SQL_ROWS}); aggregate or add LIMIT/OFFSET.")
        if not rows:
            out.append("(no rows)")
        return "\n".join(out)

    @tool
    def interview(role: str, topic: str) -> str:
        """Interview one person about the company (at most 10 interviews per company).

        role: customer, current_employee, former_employee, competitor or supplier.
        topic: sales_team, working_conditions, top_management, decision_making or competitive_edge.
        People who would not know about a topic say so; the README lists who knows what.
        """
        role, topic = role.strip().lower(), topic.strip().lower()
        if role not in answers:
            return f"Unknown role {role!r}. Roles: {', '.join(answers)}. (Not counted.)"
        if topic not in answers[role]:
            return f"Unknown topic {topic!r}. Topics: {', '.join(answers[role])}. (Not counted.)"
        with lock:
            if INTERVIEWS_USED[name] >= INTERVIEW_LIMIT:
                return f"Interview limit reached: {INTERVIEW_LIMIT} interviews per company."
            INTERVIEWS_USED[name] += 1
        return answers[role][topic]

    return [list_documents, read_document, sql_query, interview]


def normalize_verdict(value: Any) -> str | None:
    """Accept PASS/FAIL (any case) or a boolean."""
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    text = str(getattr(value, "content", value)).strip().upper()
    return text if text in VERDICTS else None


def check_chosen_points(chosen: Any) -> list[int]:
    """CHOSEN_POINTS must name 3 different points between 1 and 15."""
    try:
        points = sorted({int(p) for p in chosen})
    except (TypeError, ValueError):
        points = []
    if len(points) != 3 or len(chosen) != 3 or not all(p in FISHER_POINTS for p in points):
        raise SystemExit("Set CHOSEN_POINTS at the top of hw3.py to 3 different point numbers "
                         f"between 1 and 15, e.g. [1, 7, 15] (now: {chosen!r}).")
    return points


def normalize_points(points: Any, chosen: list[int]) -> dict[int, str | None]:
    """Map each chosen point number to PASS/FAIL, or None when missing/invalid."""
    points = points if isinstance(points, dict) else {}
    by_number: dict[int, Any] = {}
    for key, value in points.items():
        try:
            by_number[int(key)] = value
        except (TypeError, ValueError):
            continue
    return {p: normalize_verdict(by_number.get(p)) for p in chosen}


def read_ground_truth(folder: Path) -> dict[str, dict[str, Any]]:
    """Read the expected 15 point verdicts per company."""
    path = folder / "ground_truth.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def point_errors(points: dict[int, str | None], expected: dict[str, Any] | None) -> tuple[int, str]:
    """Count correct point verdicts and describe the wrong ones."""
    if expected is None:
        return 0, ""
    wrong = []
    for p in points:
        truth = expected["points"][str(p)]
        if points[p] != truth:
            wrong.append(f"{p}: expected {truth}, predicted {points[p] or 'missing'}")
    if all(v is None for v in points.values()):
        return 0, "all point verdicts missing"
    return len(points) - len(wrong), "; ".join(wrong)


def balanced_point_accuracy(
    analyses: dict[str, Any], truth: dict[str, dict[str, Any]], names: list[str], chosen: list[int]
) -> float:
    """Mean of the accuracy on true-PASS points and on true-FAIL points.

    Most verdicts are PASS, so answering PASS everywhere gets a high plain
    accuracy but only 50% balanced accuracy. Grading uses the balanced number.
    """
    hits = {"PASS": [0, 0], "FAIL": [0, 0]}
    for name in names:
        if name not in truth:
            continue
        entry = analyses.get(name)
        points = normalize_points(entry.get("points") if isinstance(entry, dict) else None, chosen)
        for p in chosen:
            expected = truth[name]["points"][str(p)]
            hits[expected][0] += points[p] == expected
            hits[expected][1] += 1
    rates = [h / n for h, n in hits.values() if n]
    return sum(rates) / len(rates) if rates else 0.0


def write_results(
    names: list[str], analyses: dict[str, Any], truth: dict[str, dict[str, Any]], chosen: list[int]
) -> tuple[Path, int]:
    """Write results.csv and return the number of correct point verdicts."""
    output = Path("results.csv")
    correct_points = 0
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "points", "points_correct", "point_errors", "interviews_used", "summary"])
        for name in names:
            entry = analyses.get(name)
            entry = entry if isinstance(entry, dict) else {}
            points = normalize_points(entry.get("points"), chosen)
            expected = truth.get(name)
            n_points, errors = point_errors(points, expected)
            correct_points += n_points
            writer.writerow([
                name,
                " ".join(f"{p}:{points[p] or 'missing'}" for p in chosen),
                f"{n_points}/{len(chosen)}" if expected else "",
                errors,
                INTERVIEWS_USED.get(name, 0),
                str(entry.get("summary", "")).strip(),
            ])
    return output, correct_points


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FTEC5660 HW3 on company data folders")
    parser.add_argument(
        "--data-folder",
        required=True,
        type=Path,
        help="folder containing one sub-folder per company",
    )
    return parser.parse_args()


async def run(folder: Path) -> int:
    folders = company_folders(folder)
    if not folders:
        raise SystemExit(f"no company folders found in {folder}")

    chosen = check_chosen_points(CHOSEN_POINTS)
    load_env_file()
    companies = {path.name: make_tools(path) for path in folders}
    agent = build_agent()
    analyses = await analyze_companies(agent, companies)
    if not isinstance(analyses, dict):
        raise TypeError("analyze_companies() must return a dictionary")

    truth = read_ground_truth(folder)
    output, correct_points = write_results(list(companies), analyses, truth, chosen)
    summary = f" Your points: {', '.join(map(str, chosen))}."
    if truth:
        summary += (
            f" Point accuracy: {correct_points}/{len(companies) * len(chosen)}"
            f" (balanced: {balanced_point_accuracy(analyses, truth, list(companies), chosen):.1%})."
        )
    print(f"Processed {len(companies)} compan{'y' if len(companies) == 1 else 'ies'}. Wrote {output}.{summary}")
    return 0


def main() -> int:
    args = parse_args()
    if not args.data_folder.is_dir():
        raise SystemExit(f"not a folder: {args.data_folder}")
    return asyncio.run(run(args.data_folder))


if __name__ == "__main__":
    raise SystemExit(main())
