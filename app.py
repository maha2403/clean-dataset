
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
import pandas as pd
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "dataset_cleaning_secret_key"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def read_dataset(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin1")


@app.route("/")
def home():

    original_file = session.get("original_file")
    cleaned_file = session.get("cleaned_file")

    df = None
    stats = None
    preview = None

    if original_file:
        try:
            if cleaned_file and os.path.exists(
                os.path.join(UPLOAD_FOLDER, cleaned_file)
            ):
                df = read_dataset(cleaned_file)
            else:
                df = read_dataset(original_file)

            original_df = read_dataset(original_file)

            total_cells = df.shape[0] * df.shape[1]

            missing_percentage = (
                (df.isna().sum().sum() / total_cells) * 100
                if total_cells > 0 else 0
            )

            duplicate_percentage = (
                (df.duplicated().sum() / len(df)) * 100
                if len(df) > 0 else 0
            )

            quality_score = round(
                max(
                    0,
                    100 - missing_percentage - duplicate_percentage
                ), 2
            )

            stats = {
                "rows": len(df),
                "columns": len(df.columns),
                "missing": int(df.isna().sum().sum()),
                "duplicates": int(df.duplicated().sum()),

                "original_rows": len(original_df),
                "original_missing": int(
                    original_df.isna().sum().sum()
                ),
                "original_duplicates": int(
                    original_df.duplicated().sum()
                ),

                "missing_percentage": round(
                    missing_percentage, 2
                ),

                "duplicate_percentage": round(
                    duplicate_percentage, 2
                ),

                "quality_score": quality_score
            }

            preview = df.head(10).to_html(
                classes="data-table",
                index=False,
                border=0
            )

        except Exception as e:
            flash(f"Unable to read dataset: {e}", "error")
            session.clear()

    return render_template(
        "index.html",
        stats=stats,
        preview=preview,
        uploaded=bool(original_file),
        cleaned=bool(cleaned_file)
    )


@app.route("/upload", methods=["POST"])
def upload():

    if "file" not in request.files:
        flash("Please select a CSV file.", "error")
        return redirect(url_for("home"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("home"))

    if not file.filename.lower().endswith(".csv"):
        flash("Only CSV files are supported.", "error")
        return redirect(url_for("home"))

    try:
        unique_name = (
            str(uuid.uuid4()) + "_" +
            secure_filename(file.filename)
        )

        file_path = os.path.join(UPLOAD_FOLDER, unique_name)

        file.save(file_path)

        df = read_dataset(unique_name)

        if len(df.columns) == 0:
            raise ValueError("CSV file has no columns.")

        session["original_file"] = unique_name
        session.pop("cleaned_file", None)

        flash("Dataset uploaded successfully!", "success")

    except Exception as e:
        flash(f"Upload failed: {e}", "error")

    return redirect(url_for("home"))


@app.route("/clean", methods=["POST"])
def clean():

    original_file = session.get("original_file")

    if not original_file:
        flash("Please upload a dataset first.", "error")
        return redirect(url_for("home"))

    try:
        df = read_dataset(original_file)

        if "duplicates" in request.form:
            df = df.drop_duplicates()

        if "empty_rows" in request.form:
            df = df.dropna(how="all")

        if "missing" in request.form:

            for column in df.columns:

                if df[column].isna().any():

                    if pd.api.types.is_numeric_dtype(df[column]):

                        median_value = df[column].median()

                        if pd.notna(median_value):
                            df[column] = df[column].fillna(
                                median_value
                            )

                    else:

                        mode_values = df[column].mode(
                            dropna=True
                        )

                        if not mode_values.empty:
                            df[column] = df[column].fillna(
                                mode_values.iloc[0]
                            )

        cleaned_name = (
            "cleaned_" + str(uuid.uuid4()) + ".csv"
        )

        cleaned_path = os.path.join(
            UPLOAD_FOLDER, cleaned_name
        )

        df.to_csv(cleaned_path, index=False)

        session["cleaned_file"] = cleaned_name

        flash("Dataset cleaned successfully!", "success")

    except Exception as e:
        flash(f"Cleaning failed: {e}", "error")

    return redirect(url_for("home"))


@app.route("/download")
def download():

    cleaned_file = session.get("cleaned_file")

    if not cleaned_file:
        flash("Please clean your dataset first.", "error")
        return redirect(url_for("home"))

    file_path = os.path.join(
        UPLOAD_FOLDER, cleaned_file
    )

    if not os.path.exists(file_path):
        flash("Cleaned file not found.", "error")
        return redirect(url_for("home"))

    return send_file(
        file_path,
        as_attachment=True,
        download_name="cleaned_dataset.csv"
    )


@app.route("/reset")
def reset():

    session.clear()

    flash("Workspace reset successfully.", "success")

    return redirect(url_for("home"))


@app.errorhandler(413)
def file_too_large(error):

    flash("File size must be less than 16 MB.", "error")

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
