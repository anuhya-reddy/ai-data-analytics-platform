let chart;

async function ask() {

    const question = document.getElementById("question").value;

    if (!question) return;

    //  Loading state
    document.getElementById("insightsBox").innerText = "Generating insights...";

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ question: question })
        });

        const data = await res.json();

        console.log("API RESPONSE:", data);

        // ======================
        // KPI
        // ======================
        const total = data.values.reduce((a, b) => a + b, 0);

        document.getElementById("totalSales").innerText =
            "₹ " + total.toLocaleString();

        document.getElementById("topItem").innerText =
            data.labels[0] || "-";

        document.getElementById("totalCount").innerText =
            data.labels.length;

        // ======================
        // TABLE (UNCHANGED)
        // ======================
        let table = document.getElementById("resultTable");

        if (data.result.length > 0) {

            let html = "<tr>";

            for (let key in data.result[0]) {
                html += `<th>${key}</th>`;
            }
            html += "</tr>";

            data.result.forEach(row => {
                html += "<tr>";
                for (let key in row) {
                    html += `<td>${row[key]}</td>`;
                }
                html += "</tr>";
            });

            table.innerHTML = html;

        } else {
            table.innerHTML = "<tr><td>No data found</td></tr>";
        }

        // ======================
        // CHART (UPGRADED)
        // ======================
        const ctx = document.getElementById("myChart");

        if (chart) chart.destroy();

        //  AUTO SWITCH chart type
        const chartType = data.chart_type || "bar";

        chart = new Chart(ctx, {
            type: chartType,
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,

                    //  GRADIENT
                    backgroundColor: function(context) {
                        const chart = context.chart;
                        const {ctx, chartArea} = chart;

                        if (!chartArea) return;

                        const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
                        gradient.addColorStop(0, "rgba(20,184,166,0.2)");
                        gradient.addColorStop(1, "rgba(20,184,166,0.8)");

                        return gradient;
                    },

                    borderColor: "#14B8A6",
                    borderWidth: 2,
                    borderRadius: chartType === "bar" ? 8 : 0,
                    fill: chartType === "line",
                    tension: 0.3
                }]
            },
            options: {
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        grid: {
                            color: "#E5E7EB"
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });

        // ======================
        // INSIGHTS (FORMAT FIX)
        // ======================
        document.getElementById("insightsBox").innerHTML =
            (data.insights || "No insights available")
                .replace(/\*\*(.*?)\*\*/g, "<b>$1</b>")  // bold support
                .replace(/\n/g, "<br>");               // line breaks

    } catch (error) {

        console.error("ERROR:", error);

        document.getElementById("insightsBox").innerText =
            "⚠️ Something went wrong (check backend)";
    }
}

async function uploadFile() {
    const fileInput = document.getElementById("fileInput");
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a file");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", {
        method: "POST",
        body: formData
    });

    const data = await res.json();
    alert(data.message);
}
async function connectDB() {

    const payload = {
        host: document.getElementById("dbHost").value,
        user: document.getElementById("dbUser").value,
        password: document.getElementById("dbPass").value,
        database: document.getElementById("dbName").value,
        table: document.getElementById("dbTable").value
    };

    const res = await fetch("/connect-db", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    alert(data.message);
}
function showSection(type) {

    const fileSection = document.getElementById("fileSection");
    const dbSection = document.getElementById("dbSection");

    const fileBtn = document.getElementById("fileBtn");
    const dbBtn = document.getElementById("dbBtn");

    if (type === "file") {
        fileSection.style.display = "block";
        dbSection.style.display = "none";

        fileBtn.classList.add("active");
        dbBtn.classList.remove("active");
    } else {
        fileSection.style.display = "none";
        dbSection.style.display = "block";

        dbBtn.classList.add("active");
        fileBtn.classList.remove("active");
    }
}