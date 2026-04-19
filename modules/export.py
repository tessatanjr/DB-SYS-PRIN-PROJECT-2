# Export analysis results to text or JSON files

import json
from PySide6.QtWidgets import QFileDialog, QMessageBox


def export_results(parent_widget, last_result):
    if not last_result:
        return None

    path, _ = QFileDialog.getSaveFileName(
        parent_widget, "Export Results", "query_analysis",
        "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
    )
    if not path:
        return None

    try:
        if path.endswith(".json"):
            export = {
                "sql":             last_result["sql"],
                "total_cost":      last_result["total_cost"],
                "annotations":     last_result["annotations"],
                "aqp_comparisons": last_result["aqp_comparisons"],
                "qep_json":        last_result["qep"]["json"],
                "qep_text":        last_result["qep"]["text"],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2, default=str)
        else:
            with open(path, "w", encoding="utf-8") as f:
                r = last_result
                f.write("=" * 60 + "\n")
                f.write("SQL QUERY PLAN ANALYSIS REPORT\n")
                f.write("=" * 60 + "\n\n")

                f.write("SQL Query:\n")
                f.write(r["sql"] + "\n\n")

                f.write("-" * 60 + "\n")
                f.write("ANNOTATIONS:\n")
                f.write("-" * 60 + "\n")
                for ann in r["annotations"]:
                    f.write(f"\n[{ann['clause']}] {ann['sql_text']}\n")
                    for a in ann["annotations"]:
                        f.write(f"  >> {a}\n")

                f.write("\n" + "-" * 60 + "\n")
                f.write("QEP (Text Format):\n")
                f.write("-" * 60 + "\n")
                f.write(r["qep"]["text"] + "\n")

                f.write("\n" + "-" * 60 + "\n")
                f.write("AQP COST COMPARISONS:\n")
                f.write("-" * 60 + "\n")
                f.write(f"QEP Total Cost: {r['total_cost']:.2f}\n\n")
                for c in r["aqp_comparisons"]:
                    f.write(
                        f"  Disabled {c['operator_name']}: "
                        f"cost={c['aqp_cost']:.2f}, "
                        f"ratio={c['cost_ratio']}x\n"
                    )

                f.write("\n" + "=" * 60 + "\n")

        return path
    except Exception as e:
        QMessageBox.critical(parent_widget, "Export Error", f"Failed to export:\n{e}")
        return None
