from flask import Flask, render_template, request, jsonify
from collections import Counter
import requests
import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

OPENFDA_URL = "https://api.fda.gov/drug/event.json"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")
@app.route("/")
def hello():
    return render_template("index.html")


@app.route("/search")
def search():
    return render_template("search.html")

@app.route("/api/search")
def api_search():
    drug_name = request.args.get("drug", "").strip()

    if not drug_name:
        return jsonify({"error": "Please enter a drug name"}), 400
    try:
        response = requests.get(OPENFDA_URL, params={
            "search": f'patient.drug.medicinalproduct:"{drug_name}"',
            "limit": 100
        })
        data = response.json()

        if "results" not in data:
            return jsonify({"error": "No results found for that drug"}), 404
        results = []
        all_reactions = []
        serious_counts = {"Serious": 0, "Not Serious": 0, "Unknown": 0}
        date_counts = Counter()

        for event in data["results"]:
            reactions =[r["reactionmeddrapt"] for r in event.get("patient", {}).get("reaction", [])]
            all_reactions.extend(reactions)

            # Count Severity
            s = event.get("serious", "Unknown")
            if s == "1":
                serious_counts["Serious"] += 1
            elif s == "2":
                serious_counts["Not Serious"] += 1
            else:
                serious_counts["Unknown"] += 1

            # Count by date (group by month)
            raw_date = event.get("receiptdate", "")
            if len(raw_date) >= 6:
                month_key = f"{raw_date[:4]}-{raw_date[4:6]}"
                date_counts[month_key] += 1

            results.append({
                "date": event.get("receiptdate", "Unknown"),
                "serious": event.get("serious", "Unknown"),
                "reactions": reactions,
            })

        # Count top 10 most common reactions
        reaction_counts = Counter(all_reactions).most_common(10)

        # Sort timeline by date
        sorted_dates = sorted(date_counts.items())

        chart_data = {
            "labels": [r[0] for r in reaction_counts],
            "values": [r[1] for r in reaction_counts],
            "serious_labels": list(serious_counts.keys()),
            "serious_values": list(serious_counts.values()),
            "timeline_dates": [d[0] for d in sorted_dates],
            "timeline_counts": [d[1] for d in sorted_dates],
        }

        return jsonify({"results": results, "chart_data": chart_data})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/insights")
def api_insights():
    drug_name = request.args.get("drug", "").strip()
    reactions = request.args.get("reactions", "")
    serious = request.args.get("serious", "")
    total = request.args.get("total", "")

    if not drug_name:
        return jsonify({"error": "No drug specified"}), 400

    prompt = f"""You are a pharmacovigilance expert. Analyze the following FDA adverse event data 
for the drug "{drug_name}" and provide a clear, helpful summary for a general audience.

Data summary:
- Total reports analyzed: {total}
- Top reported reactions: {reactions}
- Severity breakdown: {serious}

Please provide:
1. A brief overview of what this data shows
2. Key patterns or concerns in the adverse reactions
3. Context about the severity of reports
4. A reminder that adverse event reports don't prove the drug caused the reaction

Keep it concise, informative, and easy to understand. Use 3-4 short paragraphs."""

    try:
        response = model.generate_content(prompt)
        return jsonify({"insights": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)