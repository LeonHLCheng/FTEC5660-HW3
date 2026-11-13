# FTEC5660 Homework 3: Fisher's 15-Point Investment Agent

Build a LangChain agent that researches a company with tools and applies the
framework from Philip Fisher's *Common Stocks and Uncommon Profits* (Part One,
Chapter 3 "What to buy: the fifteen points to look for in a common stock", and
Chapter 4 "What to buy: applying this to your own needs"). You choose 3 of
Fisher's 15 points and decide yourself what PASS means for each. For every
company your agent gives a PASS/FAIL verdict on your 3 points and a short
summary.

The companies are fictional, so the model cannot answer from memory. Unlike a
pile of reports, the evidence is spread over three sources, and your agent has
to go and get it with tools, the way Fisher's "scuttlebutt" method sends an
investor to talk to customers, competitors, suppliers and staff.

## Data and tools

`public_test/` has one folder per company. Your code receives four tools per
company (built by the provided code in `hw3.py`):

| Tool | What it gives you |
| --- | --- |
| `list_documents()` | the company's six documents and their dates |
| `read_document(name)` | one document: the 2025 letter to shareholders, four earnings calls (Q3 2025 to Q2 2026) and a news file (July 2025 to July 2026) |
| `sql_query(query)` | one read-only SQLite query on the company's database; at most 50 rows come back, so use `SUM`, `GROUP BY` and `WHERE` |
| `interview(role, topic)` | what one person says about the company; at most **10 interviews per company** |

The documents are what management says. Management's own claims (such as "we
have never cut research" or "our people are our greatest strength") are not
evidence on their own: check them against the database and the interviews.

**Database tables** (amounts in USD thousands; dates `YYYY-MM-DD`, months
`YYYY-MM`, quarters like `2025Q3`; the fiscal year is the calendar year):

| Table | Columns |
| --- | --- |
| `company` | name, industry |
| `industry_medians` | industry, revenue_growth_2y_pct, new_product_share_pct, new_product_sales_per_rd, operating_margin_pct (one row per industry; use the row for the company's own industry) |
| `orders` | order_id, order_date, product, customer, amount, note (about 3,000 to 4,000 orders from January 2023 to June 2026; revenue is the sum of order amounts) |
| `products` | product, launch_date |
| `monthly_costs` | month, cost_of_sales, selling_admin, research_development |
| `quarterly_cash` | quarter, operating_cash_flow, capex, cash_end |
| `capex_plan` | year, planned_capex (2026 to 2028) |
| `returns` | month, units_shipped, units_returned |
| `insider_trades` | trade_date, person, title, side (`buy` or `sell`), shares, price |

**Terms used in the data.**

| Term | Meaning |
| --- | --- |
| FY2025 | Fiscal year 2025. Here the fiscal year is the calendar year, so FY2025 is January to December 2025. |
| Quarter | Three months of the year: Q1 is January to March, Q2 April to June, Q3 July to September and Q4 October to December. The database writes `2025Q3`; the documents write "third quarter 2025". |
| Amounts | The database is in **USD thousands** (676,100 means US$676.1 million). The documents use USD millions. |
| Revenue | Money from sales: the sum of `amount` in `orders`. |
| Cost of sales | The cost of making the products that were sold. |
| Selling and admin | The cost of selling and of running the company (sales staff, offices, management). |
| R&D | Research and development spending, mainly on new products. |
| Operating margin | Operating profit as a share of revenue: (revenue − cost of sales − selling and admin − R&D) ÷ revenue. |
| Operating cash flow | Cash that the day-to-day business brings in during a quarter. |
| Cash at the end of a quarter | The cash the company holds on the last day of that quarter (`cash_end`). |
| Capex | Capital expenditure: spending on factories, machines and other long-term assets. `capex_plan` holds the planned capex for 2026 to 2028. |
| Return rate | Units returned ÷ units shipped, from the `returns` table. |
| Industry median | The middle value for companies in the same industry, from `industry_medians`. |
| Insider | A director or senior manager of the company. `insider_trades` lists the shares they bought (`buy`) or sold (`sell`). |
| Earnings call | A meeting each quarter where management presents the quarter's results to investors. Each call quotes that quarter's revenue. |

**Interviews.** Roles: `customer`, `current_employee`, `former_employee`,
`competitor`, `supplier`. Topics: `sales_team`, `working_conditions`,
`top_management`, `decision_making`, `competitive_edge`. Only some people know
about each topic; the others say they can't comment, and that answer still
uses up one interview.

| Topic | Who knows about it |
| --- | --- |
| `sales_team` | customer, competitor |
| `working_conditions` | current_employee, former_employee |
| `top_management` | former_employee, supplier |
| `decision_making` | supplier, customer |
| `competitive_edge` | competitor, customer |

People who know about a topic always agree with each other, so one good answer
is enough.

## Choose your 3 points and your rules

Pick any 3 of Fisher's 15 points and write them in `CHOSEN_POINTS` near the
top of `hw3.py`, e.g. `CHOSEN_POINTS = [1, 7, 15]`. The full questions are in
`FISHER_POINTS` in `hw3.py` and in the book.

| # | Fisher's point | Where the evidence is |
| --- | --- | --- |
| 1 | Market potential for sales growth | database |
| 2 | New products as current lines mature | database |
| 3 | Effective research and development | database |
| 4 | Above-average sales organization | interviews (`sales_team`) |
| 5 | Worthwhile profit margin | database |
| 6 | Maintaining or improving margins | database |
| 7 | Labour and personnel relations | interviews (`working_conditions`) |
| 8 | Executive relations | interviews (`top_management`) |
| 9 | Depth of management | interviews (`decision_making`) |
| 10 | Cost analysis and accounting controls | earnings calls, checked against the database |
| 11 | Advantage over competitors | interviews (`competitive_edge`) |
| 12 | Long-range outlook on profits | database |
| 13 | Growth without dilutive equity financing | database |
| 14 | Management talks freely about troubles | earnings calls, checked against the database |
| 15 | Management of unquestionable integrity | news file, checked against the database |

For each of your points, **you design the rule**: which evidence to use, what
to compute or whom to ask, and where the line between PASS and FAIL lies. PASS
means the company looks favourable on that point, as Fisher would see it.

We grade your verdicts against our own answer key. It uses one fixed rule per
point, which we do not publish, and the data never puts a company close to
the line of that rule, so a sensible reading of Fisher usually gives the same
answer. **Test your rules on the public answers**:
`public_test/ground_truth.json` gives the expected verdict on all 15 points
for each of the 20 public companies, and every point fails in 6 of them. If
your rule disagrees with the public answers, rethink it.

**Tip: calculate with tools, not in your head.** Do every sum, ratio and
comparison in SQL or Python, including the number of days between two dates
(SQLite's `julianday()` gives a date as a number of days).

## Student task

Fill in the three places in `hw3.py` marked `### YOUR CODE HERE`. You may add
imports, constants and helper functions above them, but do not change the
provided code below them:

- `CHOSEN_POINTS` lists your 3 points.
- `build_agent()` creates your model and anything else you need once.
- `analyze_companies(agent, companies)` receives
  `{company_folder: [list_documents, read_document, sql_query, interview]}`
  and returns, for every company,
  `{"points": {1: "PASS", 7: "FAIL", 15: "PASS"}, "summary": "..."}` (here with
  `CHOSEN_POINTS = [1, 7, 15]`).

Use the course techniques that fit your points: tool use for the database and
the interviews, planning which interviews to spend, routing each point to the
right source, prompt chaining, parallel calls, reflection to check your
answers, or a combination. Your code must read company data **only through
the four tools**; do not open `company.db` or `interviews.dat` yourself. Do
not hard-code folder names, company names or the public answers.

## Setup and public test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=your_key_here" > .env
python3 hw3.py --data-folder public_test
```

Use your own DeepSeek API key (from https://platform.deepseek.com). The
required model is `deepseek-v4-flash`. We grade with our own key, so never put
a key in your code; `.env` must stay out of git.

The program creates `results.csv` with the columns `company`, `points`,
`points_correct`, `point_errors`, `interviews_used` and `summary`, and prints
the point score on your 3 points (the percentage after "balanced"). The point
score is the average of two shares: the share of truly passing verdicts that
you marked PASS and the share of truly failing verdicts that you marked FAIL.
For example, 90% and 60% give (90% + 60%) / 2 = 75%, and marking every point
PASS gives (100% + 0%) / 2 = 50%. Once `CHOSEN_POINTS` is set, the starter
runs before you add any API code (it returns no verdicts, so it scores 0%).

`public_test/ground_truth.json` gives the expected verdicts on all 15 points
for each public company. Grading uses a private set of about 20 unseen
companies with the same tools and the same answer key rules, but different
names and wording, and scores your 3 points only.

## Homework 3 solution:
> to students: this is your report, see the homework description.

### My 3 points and rules
> for each point: why you chose it, your PASS rule in one or two sentences, and the evidence it uses. Quote Fisher where it helps.


#### Point 1: Market Potential for Sizable Sales Growth Over Several Years (Fisher Point 1)
* **Why I chose it:** Point 1 is the most comprehensive and technically challenging quantitative point in Fisher's framework. It requires integrating half of the synthetic database (`orders`, `products`, and `industry_medians`). While Philip Fisher ideally evaluated companies across decades of compounding history, our dataset spans 3.5 years. To honor Fisher's principle of verifying continuous, structural growth rather than a one-time spurt, our agent breaks the timeline into a continuous 14-quarter progression (from 2023Q1 to 2026Q2). We perform deterministic pre-computation in SQLite: extracting completed multi-year cycles, quarterly sequential (QoQ) momentum, seasonal year-over-year (YoY) same-quarter growth, and product launch history before passing this structured context to the LLM.
* **Fisher's Principle:** Philip Fisher warned against temporary one-off surges (such as the early wave of television set purchases that quickly plateaued) and stressed that *growth should not be judged on an annual basis but, say, by taking units of several years each.* True market potential requires a company to be either "fortunate and able" or "fortunate because they are able" to expand their total addressable market continuously.
* **PASS Rule:** A company earns a **PASS** if its multi-year revenue growth across completed 2-year cycles meets or exceeds its industry peer benchmark (`industry_medians.revenue_growth_2y_pct`), supported by positive YoY quarterly momentum and active commercialized product lines. It **FAILS** if multi-year growth lags behind industry peers, indicating product saturation or loss of market share.
* **Evidence used:** Dynamic SQL aggregation on `orders` (filtering completed 12-month years via `HAVING COUNT(DISTINCT month) = 12` and computing 2-year lag growth), quarterly revenue progression (`QoQ` and `YoY` same-quarter growth), `products` (quarterly launch cadence), and `industry_medians` benchmark.
---
#### Point 4: Above-Average Sales Organization (Fisher Point 4)
* **Why I chose it:** Point 4 evaluates qualitative distribution capability through Philip Fisher's "Scuttlebutt" method. In business, having a great product is useless if the distribution engine is broken. The analytical challenge is defining what truly constitutes an "above-average" sales force versus a purely transactional order-taking department.
* **Fisher's Principle:** Fisher observed: *In a great majority of businesses, sales effort is the most vital single factor in the success of the enterprise.* An elite sales organization does not merely hand out price sheets; it acts as a technical partner, anticipates customer requirements, and educates the market on complex solutions.
* **PASS Rule:** A company earns a **PASS** if customer field interviews confirm that the sales force is consultative, technically proficient, and proactive in solving customer problems. It **FAILS** if customers report high representative turnover, lack of product knowledge, or purely transactional, passive price-list delivery.
* **Evidence used:** Scuttlebutt interview tool querying the `customer` on the `sales_team` topic.
---
#### Point 7: Outstanding Labor and Personnel Relations (Fisher Point 7)
* **Why I chose it:** Point 7 assesses workforce morale, operational stability, and turnover risk. The primary challenge is avoiding informational bias: current employees may hesitate to speak openly or suffer from recency bias, while former employees provide unvarnished historical context. To achieve balanced, 360-degree verification, our agent interviews **both current and former employees**.
* **Fisher's Principle:** Fisher emphasized that *a company with good labor relations will almost always have lower costs than a competitor with poor labor relations.* High employee turnover and poor morale generate heavy hidden costs in recruitment, continuous retraining, and defective workmanship, eroding long-term profit margins.
* **PASS Rule:** A company earns a **PASS** if interviews across both current and former employees demonstrate positive workplace relations characterized by fair compensation, high retention, and strong morale. It **FAILS** if workers report chronic excessive overtime, high churn, or strike/morale threats.
* **Evidence used:** Scuttlebutt interview tool querying **both** `current_employee` and `former_employee` on the `working_conditions` topic.
---


### Design
> a visualization of your agent design and one paragraph describing it.

```text
+-----------------------------------------------------------------------------------+
|                        AGENT ARCHITECTURE OVERVIEW                                |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|   [ SQLite Database ]                 [ Scuttlebutt Interviews ]                  |
|     |  * Dynamic Multi-Year Growth      |  * Customer: sales_team                 |
|     |  * Quarterly QoQ & YoY Trends     |  * Current Employee: working_cond       |
|     |  * Quarterly Product Launches     |  * Former Employee: working_cond        |
|     +-------------------\               /--------------------+                    |
|                          \             /                                          |
|                           v           v                                           |
|                  +-----------------------------+                                  |
|                  |     Tool Pre-Computation    |                                  |
|                  | (Grounded Math & Evidence)  |                                  |
|                  +--------------+--------------+                                  |
|                                 |                                                 |
|                                 v                                                 |
|               +-----------------------------------+                               |
|               |  asyncio.Semaphore(5) Concurrency |                               |
|               +-----------------+-----------------+                               |
|                                 |                                                 |
|                                 v                                                 |
|               +-----------------------------------+                               |
|               |  DeepSeek-v4-flash Reasoning LLM  | <--- (3-Attempt Retry Loop)   |
|               |  - Synthesizes Points 1, 4, & 7   |                               |
|               |  - Enforces Strict JSON Schema    |                               |
|               +-----------------+-----------------+                               |
|                                 |                                                 |
|                                 v                                                 |
|                  +-----------------------------+                                  |
|                  | Structured Verdict Normalizer|                                 |
|                  |   (PASS / FAIL & Summary)   |                                  |
|                  +--------------+--------------+                                  |
|                                 |                                                 |
|                                 v                                                 |
|                   [ Export to results.csv ]                                       |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

#### Architectural Description:
Our agent employs a **two-tier hybrid architecture** that cleanly separates factual computation from qualitative synthesis. 

In Tier 1 (Tool & Pre-Computation Layer), the agent leverages SQLite window functions (`LAG()`) and dynamic date grouping (`HAVING COUNT(DISTINCT month) = 12`) to compute 2-year revenue growth rates, quarterly QoQ/YoY momentum, and product cadence, completely eliminating LLM arithmetic hallucination and partial-year distortion. Concurrently, it conducts targeted Scuttlebutt field interviews across customers, current employees, and former employees (using exactly 3 of the 10 allowed interviews). 

In Tier 2 (Cognitive Layer), pre-aggregated evidence is fed into `deepseek-v4-flash` via an asynchronous pipeline managed by `asyncio.Semaphore(5)` to maximize throughput while respecting API rate limits. The model acts as the sole evaluator, weighing qualitative sentiment and quantitative benchmarks against Fisher’s criteria, protected by an exponential backoff retry loop and strict JSON schema normalization before outputting to `results.csv`.

### Results
> your point score on `public_test`, the companies where your verdicts disagree with the public answers, and why.

* **Point Score on `public_test`:** **60 / 60 correct** (**100.0% balanced accuracy**).
* **Interviews Used:** Exactly **3 interviews per company** (well within the limit of 10).
* **Total Execution Time:** Approximately **15 seconds** for all 20 companies.
* **Disagreements with Public Ground Truth:** **0 disagreements** across all 20 public test companies.
* **Why there were zero disagreements:**
  1. **Grounding Point 1 in Completed Cycles & Granular Trajectories:** Naive models fail Point 1 by comparing 2026 (an incomplete 6-month period) against full years, creating false negatives. Our dynamic fiscal-year filter ensured that multi-year growth was evaluated strictly over complete 2-year cycles (FY2023 to FY2025) against `industry_medians.revenue_growth_2y_pct`. Furthermore, supplementing the 2-year benchmark with full 14-quarter sequential (QoQ) and seasonal (YoY) trajectories provided the LLM with granular momentum data, enabling it to distinguish true market expansion from cyclical noise.
  2. **Multi-Perspective Scuttlebutt on Point 7:** Combining statements from both current and former employees eliminated bias and provided unambiguous evidence of labor morale and turnover.
  3. **Strict JSON Schema & Neutral Temperature:** Setting `temperature=0.0` and enforcing strict schema parsing prevented formatting errors and reasoning drift across all 20 companies.
