import pandas as pd
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import json
import math
from sqlalchemy import create_engine
from urllib.parse import quote_plus

app = Flask(__name__)

# =========================
# GLOBAL STATE
# =========================
current_df = None

db_engine = None
db_table = None

DATA_SOURCE = "excel"

# =========================
# AI CLIENT
# =========================
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

# =========================
# PREPROCESSING
# =========================
def preprocess_dynamic(df):
    df = df.copy()
    df.columns = df.columns.str.strip()

    for col in df.columns:
        if "date" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df["Year"] = df[col].dt.year
            df["Month"] = df[col].dt.month
            break

    for col in df.select_dtypes(include="number").columns:
        df[col] = df[col].fillna(0)

    return df

# =========================
# AI INSIGHTS
# =========================
def generate_ai_insights(context_df, question):
    if context_df.empty:
        return "No data available"

    prompt = f"""
User Question:
{question}

Data:
{context_df.to_string(index=False)}

Give 3 short bullet insights.
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return response.choices[0].message.content


def ai_parse_question(df, question):
    columns = list(df.columns)

    prompt = f"""
You are a data analyst.

Dataset columns:
{columns}

User question:
{question}

Return ONLY JSON:
{{
    "group_by": "<column name or null>",
    "metric": "<numeric column>",
    "analysis": "aggregation | trend | growth",
    "limit": 5,
    "sort": "desc"
}}

Rules:
- Choose ONLY from given columns
- metric must be numeric
- group_by must be categorical
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    try:
        raw = response.choices[0].message.content
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except:
        return {
            "group_by": None,
            "metric": df.select_dtypes(include="number").columns[0],
            "analysis": "aggregation",
            "limit": 5,
            "sort": "desc"
        }


def run_query(df, question):

    parsed = ai_parse_question(df, question)

    group_by = parsed.get("group_by")
    metric = parsed.get("metric")
    analysis = parsed.get("analysis")
    limit = parsed.get("limit", 5)
    sort_order = parsed.get("sort", "desc")

    col_map = {c.lower().strip(): c for c in df.columns}

    if metric:
        metric = col_map.get(metric.lower().strip(), df.select_dtypes(include="number").columns[0])
    else:
        metric = df.select_dtypes(include="number").columns[0]

    if group_by:
        group_by = col_map.get(group_by.lower().strip(), None)

    if analysis == "trend" and "Year" in df.columns and "Month" in df.columns:
        result = (
            df.groupby(["Year", "Month"])[metric]
            .sum()
            .reset_index()
            .sort_values(["Year", "Month"])
        )

    else:
        if group_by and group_by in df.columns:
            result = (
                df.groupby(group_by)[metric]
                .sum()
                .sort_values(ascending=(sort_order == "asc"))
                .head(limit)
                .reset_index()
            )
        else:
            total = df[metric].sum()
            result = pd.DataFrame({"Metric": [metric], "Value": [total]})

    insights = generate_ai_insights(result, question)

    return result, insights




# =========================
# DATABASE HELPERS
# =========================
def get_table_schema():
    query = f"""
    SELECT column_name
    FROM information_schema.columns
    WHERE LOWER(table_name) = LOWER('{db_table}')
    AND table_schema = 'public'
    """
    
    df = pd.read_sql(query, db_engine)

    print("COLUMNS FOUND:", df)

    return df["column_name"].tolist()

def generate_sql(question, columns):
    prompt = f"""
You are a SQL expert.

Table: {db_table}
Columns: {columns}

User question: {question}

STRICT RULES:
- ONLY SELECT queries
- Use only given columns
- LIMIT 10 unless specified
- No explanation
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql

def is_safe_sql(sql):
    sql_lower = sql.lower()

    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "create"]

    if not sql_lower.startswith("select"):
        return False

    for word in forbidden:
        if word in sql_lower:
            return False

    return True

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html")

# =========================
# ASK
# =========================
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "")

    try:
        # ======================
        # EXCEL MODE
        # ======================
        if DATA_SOURCE == "excel":

            if current_df is None:
                return jsonify({"error": "Upload Excel first"})

            result, insights = run_query(current_df, question)

        # ======================
        # DB MODE
        # ======================
        else:
            columns = get_table_schema()

            if not columns:
                return jsonify({"error": "Table not found or no columns"})

            sql = generate_sql(question, columns)

            print("AI SQL:", sql)

            if not is_safe_sql(sql):
                return jsonify({"error": "Unsafe query blocked"})

            try:
                result = pd.read_sql(sql, db_engine)
            except Exception as e:
                print("AI SQL FAILED, fallback:", e)
                result = pd.read_sql(f"SELECT * FROM {db_table} LIMIT 10", db_engine)

            insights = generate_ai_insights(result, question)

        # ======================
        # COMMON RESPONSE (SHARED)
        # ======================
        if result.empty:
            return jsonify({
                "result": [],
                "labels": [],
                "values": [],
                "insights": "No data found",
                "chart_type": "bar"
            })

        labels = result[result.columns[0]].astype(str).tolist()
        metric = result.columns[-1]
        values = result[metric].tolist()

        return jsonify({
            "result": result.to_dict(orient="records"),
            "labels": labels,
            "values": values,
            "insights": insights,
            "chart_type": "bar"
        })

    except Exception as e:
        return jsonify({"error": str(e)})

   
       

        

# =========================
# CONNECT DATABASE
# =========================
@app.route("/connect-db", methods=["POST"])
def connect_db():
    global db_engine, db_table, DATA_SOURCE

    data = request.json

    try:
        password = quote_plus(data["password"])

        connection_str = f"postgresql+psycopg2://{data['user']}:{password}@{data['host']}:6543/{data['database']}"
        
        db_engine = create_engine(connection_str)

        # TEST CONNECTION
        test = pd.read_sql("SELECT 1", db_engine)
        print("DB TEST:", test)

        db_table = data["table"]
        DATA_SOURCE = "database"

        return jsonify({"message": "Database connected successfully!"})

    except Exception as e:
        return jsonify({"message": str(e)})
    
    

@app.route("/upload", methods=["POST"])
def upload():
    global current_df, DATA_SOURCE

    file = request.files["file"]

    try:
        if file.filename.endswith(".csv"):
            current_df = pd.read_csv(file)
        else:
            current_df = pd.read_excel(file)

        current_df = preprocess_dynamic(current_df)

        DATA_SOURCE = "excel"

        return jsonify({"message": "File uploaded successfully!"})

    except Exception as e:
        return jsonify({"message": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)




