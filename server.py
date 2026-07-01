import base64
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
import plotly.express as px
from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("Plotly Data Visualizer")

SUPPORTED_CHARTS = (
    "scatter",
    "line",
    "bar",
    "histogram",
    "box",
    "violin",
    "pie",
    "heatmap",
    "area",
    "density_heatmap",
    "scatter_matrix",
)
SUPPORTED_FORMATS = ("html", "png", "svg")
SUPPORTED_THEMES = (
    "plotly",
    "plotly_white",
    "plotly_dark",
    "ggplot2",
    "seaborn",
    "simple_white",
    "presentation",
    "xgridoff",
    "ygridoff",
    "gridon",
    "none",
)

PRECONTEXT_PROMPT = """Use tools in this sequence for chart answers:
1) Use Semantic Search/SQL MCP first to run queries and fetch result rows.
2) Transform DB rows into Plotly tool input payloads.
3) Use Plotly MCP tools to generate charts resize to show it in the chat UI.
4) Save the generated chart to a local file and return the saved file path in the response. 
5) Show the saved chart in the chat UI directly as image with the file path.
6) Automatically open the chart file after saving for immediate viewing.
"""

SCHEMA_PLAYBOOK = {
    "tables": {
        "projects": ["id", "name", "status", "projectType", "progress", "startDate", "latestDueDate", "companyId"],
        "task": ["id", "taskId", "taskName", "description", "status", "priority", "startDate", "endDate", "progress", "projectId", "companyId"],
        "subtasks": ["id", "subtaskId", "subtaskName", "description", "status", "priority", "startDate", "endDate", "progress", "taskId", "companyId", "spentTime", "estimationTime"],
        "goals": ["id", "companyId", "ownerId", "createdById", "createdAt", "updatedAt"],
        "comments": ["id", "userId", "leaveId", "comment", "commentDate", "createdAt", "updatedAt"],
        "task_updates": ["id", "updateNotes", "taskId", "companyId", "createdById", "createdAt", "updatedAt"]
    },
    "recommended_queries": [
        {
            "question": "How many tasks are in each status?",
            "sql": "SELECT status, COUNT(*) AS task_count FROM task GROUP BY status ORDER BY task_count DESC;",
            "chart": "bar",
            "x": "status",
            "y": "task_count",
        },
        {
            "question": "What is the task status split?",
            "sql": "SELECT status, COUNT(*) AS task_count FROM task GROUP BY status ORDER BY task_count DESC;",
            "chart": "pie",
            "labels": "status",
            "values": "task_count",
        },
        {
            "question": "Count goals by owner?",
            "sql": "SELECT \"ownerId\", COUNT(*) AS goal_count FROM goals GROUP BY \"ownerId\" ORDER BY goal_count DESC;",
            "chart": "bar",
            "x": "ownerId",
            "y": "goal_count",
        },
        {
            "question": "How many tasks are created per project?",
            "sql": "SELECT p.name AS project_name, COUNT(t.id) AS task_count FROM projects p LEFT JOIN task t ON p.id = t.projectId GROUP BY project_name ORDER BY task_count DESC;",
            "chart": "bar",
            "x": "project_name",
            "y": "task_count",
        },
        {
            "question": "How do task progress values vary by priority?",
            "sql": "SELECT priority, progress FROM task WHERE progress IS NOT NULL;",
            "chart": "box",
            "x": "priority",
            "y": "progress",
        },
        {
            "question": "How many task updates happened over time?",
            "sql": "SELECT DATE_TRUNC('month', createdAt)::date AS update_month, COUNT(*) AS updates FROM task_updates GROUP BY update_month ORDER BY update_month;",
            "chart": "line",
            "x": "update_month",
            "y": "updates",
        }
    ],
}


def _normalize_data(data: Any) -> dict[str, Any]:
    # Handle double-encoded JSON strings
    for _ in range(3):
        if isinstance(data, str):
            data = data.strip()
            try:
                data = json.loads(data)
            except Exception:
                break
                
    if isinstance(data, list):
        return {"rows": data}
        
    if isinstance(data, dict):
        # Unwrap semantic search / smart query / SQL execution formats
        for key in ("results", "data", "rows"):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass
                if isinstance(val, list):
                    return {"rows": val}
        return data
        
    raise ValueError("data must be a dict, list of rows, or a JSON string")


def _to_list(val: Any) -> list[Any] | None:
    if val is None:
        return None
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return [item.strip() for item in val.split(",") if item.strip()]
    return [val]


def _data_to_dataframe(chart_data: dict[str, Any]) -> pd.DataFrame:
    rows = chart_data.get("rows")
    if rows is not None:
        df = pd.DataFrame(rows)
    else:
        x_data = chart_data.get("x")
        y_data = chart_data.get("y")
        if x_data is None and y_data is None:
            raise ValueError("data must include either 'rows' or one of 'x'/'y' fields")
        df = pd.DataFrame({"x": x_data, "y": y_data})
        
    # Auto-detect and format date/time columns
    for col in df.columns:
        if df[col].dtype == object or isinstance(df[col].dtype, pd.CategoricalDtype):
            col_lower = col.lower()
            is_date_col = any(k in col_lower for k in ("date", "time", "created", "updated", "period"))
            
            first_val = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
            is_date_str = False
            if isinstance(first_val, str):
                if re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}', first_val.strip()):
                    is_date_str = True
                    
            if is_date_col or is_date_str:
                try:
                    df[col] = pd.to_datetime(df[col])
                except Exception:
                    pass
    return df


def _build_figure(
    chart_type: str,
    chart_data: dict[str, Any],
    title: str | None = None,
    x_title: str | None = None,
    y_title: str | None = None,
    theme: str = "plotly",
) -> Any:
    chart_type = chart_type.lower().strip()
    if chart_type not in SUPPORTED_CHARTS:
        raise ValueError(f"Unsupported chart type '{chart_type}'")

    if chart_type == "heatmap":
        df = None
        try:
            df = _data_to_dataframe(chart_data)
        except Exception:
            pass

        z_values = chart_data.get("z_values") or chart_data.get("z")

        if df is not None and isinstance(z_values, str) and z_values in df.columns:
            x_col = chart_data.get("x_column") or chart_data.get("x")
            y_col = chart_data.get("y_column") or chart_data.get("y")
            if not isinstance(x_col, str) or x_col not in df.columns:
                x_col = df.columns[0]
            if not isinstance(y_col, str) or y_col not in df.columns:
                y_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

            pivoted = df.pivot_table(index=y_col, columns=x_col, values=z_values, aggfunc="sum")
            fig = px.imshow(pivoted, title=title, labels=dict(x=x_col, y=y_col, color=z_values))
        elif isinstance(z_values, list):
            fig = px.imshow(z_values, title=title)
        else:
            raise ValueError("heatmap requires a 2D list of values or a pivoted table column name for z")

    elif chart_type == "density_heatmap":
        df = _data_to_dataframe(chart_data)
        x_col = chart_data.get("x_column") or chart_data.get("x")
        y_col = chart_data.get("y_column") or chart_data.get("y")

        if not isinstance(x_col, str) or x_col not in df.columns:
            x_col = df.columns[0] if len(df.columns) > 0 else None
        if not isinstance(y_col, str) or y_col not in df.columns:
            y_col = df.columns[1] if len(df.columns) > 1 else None

        z_col = chart_data.get("z_column") or chart_data.get("z")
        if not isinstance(z_col, str) or z_col not in df.columns:
            z_col = df.columns[2] if len(df.columns) > 2 else None

        fig = px.density_heatmap(df, x=x_col, y=y_col, z=z_col, title=title)

    elif chart_type == "scatter_matrix":
        df = _data_to_dataframe(chart_data)
        dimensions = chart_data.get("dimensions")
        if not dimensions:
            numeric_columns = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
            dimensions = numeric_columns[:5]
        if not dimensions:
            raise ValueError("scatter_matrix requires numeric columns or explicit dimensions")
        fig = px.scatter_matrix(df, dimensions=dimensions, title=title)

    elif chart_type == "pie":
        df = None
        try:
            df = _data_to_dataframe(chart_data)
        except Exception:
            pass

        labels_col = chart_data.get("labels_column") or chart_data.get("x_column") or chart_data.get("x")
        values_col = chart_data.get("values_column") or chart_data.get("y_column") or chart_data.get("y")

        if df is not None and isinstance(labels_col, str) and labels_col in df.columns and isinstance(values_col, str) and values_col in df.columns:
            fig = px.pie(df, names=labels_col, values=values_col, title=title)
        else:
            labels = chart_data.get("labels", chart_data.get("x"))
            values = chart_data.get("values", chart_data.get("y"))
            if isinstance(labels, str) and df is not None and labels in df.columns:
                labels = df[labels].tolist()
            if isinstance(values, str) and df is not None and values in df.columns:
                values = df[values].tolist()

            if labels is None or values is None:
                if df is not None and len(df.columns) >= 2:
                    labels = df[df.columns[0]].tolist()
                    values = df[df.columns[1]].tolist()
                else:
                    raise ValueError("pie requires data labels/x and values/y columns or lists")
            fig = px.pie(names=labels, values=values, title=title)

    else:
        df = _data_to_dataframe(chart_data)
        x_col = chart_data.get("x_column") or chart_data.get("x")
        y_col = chart_data.get("y_column") or chart_data.get("y")

        if isinstance(x_col, str) and x_col in df.columns:
            pass
        elif len(df.columns) > 0:
            x_col = df.columns[0]
        else:
            x_col = "x"

        if isinstance(y_col, str) and y_col in df.columns:
            pass
        elif len(df.columns) > 1:
            y_col = df.columns[1]
        else:
            y_col = None

        actual_y = y_col if (isinstance(y_col, str) and y_col in df.columns) else None

        if chart_type == "scatter":
            fig = px.scatter(
                df,
                x=x_col,
                y=actual_y or x_col,
                color=chart_data.get("color") if (isinstance(chart_data.get("color"), str) and chart_data.get("color") in df.columns) else None,
                size=chart_data.get("size") if (isinstance(chart_data.get("size"), str) and chart_data.get("size") in df.columns) else None,
                hover_name=chart_data.get("label") if (isinstance(chart_data.get("label"), str) and chart_data.get("label") in df.columns) else None,
                title=title,
            )
        elif chart_type == "line":
            color_col = chart_data.get("color_column") or chart_data.get("color")
            if isinstance(color_col, str) and color_col in df.columns:
                fig = px.line(df, x=x_col, y=actual_y, color=color_col, title=title)
            else:
                fig = px.line(df, x=x_col, y=actual_y, title=title)
        elif chart_type == "bar":
            orientation = chart_data.get("orientation", "v")
            color_col = chart_data.get("color_column") or chart_data.get("color")
            if not (isinstance(color_col, str) and color_col in df.columns):
                color_col = None
            barmode_val = chart_data.get("barmode", "group")
            
            if orientation == "h":
                fig = px.bar(df, x=actual_y, y=x_col, color=color_col, barmode=barmode_val, orientation=orientation, title=title)
            else:
                fig = px.bar(df, x=x_col, y=actual_y, color=color_col, barmode=barmode_val, orientation=orientation, title=title)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x_col, y=actual_y, title=title)
        elif chart_type == "box":
            fig = px.box(df, x=x_col, y=actual_y, title=title)
        elif chart_type == "area":
            fig = px.area(df, x=x_col, y=actual_y, title=title)
        else:
            fig = px.violin(df, x=x_col, y=actual_y, title=title)

    fig.update_layout(template=theme)
    if x_title:
        fig.update_xaxes(title_text=x_title)
    if y_title:
        fig.update_yaxes(title_text=y_title)
    return fig


def _resolve_writable_output_dir() -> Path | None:
    """
    Find a directory we can actually write to. Tries, in order:
    1. An explicit override via CHART_OUTPUT_DIR env var (if set and writable).
    2. The system temp dir (always writable in virtually every deployment,
       unlike an app's working directory, which may be mounted read-only).
    3. cwd()/chart_outputs, kept as a last-ditch legacy fallback.
    Returns None if nothing is writable, so callers can fall back to an
    in-memory-only response instead of raising.
    """
    candidates = []
    env_dir = os.environ.get("CHART_OUTPUT_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path(tempfile.gettempdir()) / "chart_outputs")
    candidates.append(Path.cwd() / "chart_outputs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write_test_{os.getpid()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue
    return None


def _format_output(
    fig: Any,
    output_format: str,
    output_file: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    output_format = output_format.lower().strip()
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported output format '{output_format}'")

    file_extension = output_format
    auto_name = f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.{file_extension}"

    output_path: Path | None
    if output_file:
        # Caller gave an explicit path; honor it, but don't let a bad path
        # crash the whole call if its parent isn't writable either.
        output_path = Path(output_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            output_path = None
    else:
        output_dir = _resolve_writable_output_dir()
        output_path = (output_dir / auto_name) if output_dir else None

    if output_format == "html":
        fig.update_layout(width=None, height=None, autosize=True)
        plotly_config = {
            "displaylogo": False,
            "modeBarButtonsToRemove": [
                "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"
            ],
            "responsive": True
        }
        # Keep chart HTML self-contained so iframe rendering works even when
        # cdn.plot.ly is blocked/unavailable in the user's browser/network.
        html_content = fig.to_html(include_plotlyjs=True, full_html=True, config=plotly_config)

        saved = False
        file_path_str = None
        if output_path is not None:
            try:
                output_path.write_text(html_content, encoding="utf-8")
                saved = True
                file_path_str = str(output_path.resolve())
            except OSError:
                saved = False

        payload = {
            "saved": saved,
            "format": "html",
            "file_path": file_path_str,
            "html": html_content,
            "message": (
                "Interactive HTML chart saved successfully."
                if saved
                else "Could not write to disk (no writable directory found); "
                     "returning chart HTML inline instead."
            ),
            "metadata": metadata or {},
        }
        return json.dumps(payload)

    image_bytes = fig.to_image(format=output_format)
    encoded = base64.b64encode(image_bytes).decode("utf-8")

    saved = False
    file_path_str = None
    if output_path is not None:
        try:
            output_path.write_bytes(image_bytes)
            saved = True
            file_path_str = str(output_path.resolve())
        except OSError:
            saved = False

    payload = {
        "saved": saved,
        "format": output_format,
        "file_path": file_path_str,
        "message": (
            f"{output_format.upper()} chart saved successfully."
            if saved
            else f"Could not write {output_format.upper()} to disk; "
                 "returning base64-encoded image inline instead."
        ),
        "metadata": metadata or {},
        "encoding": "base64",
        "content": encoded,
    }
    return json.dumps(payload)


def _build_axis_metadata(
    chart_type: str,
    chart_data: dict[str, Any],
    title: str,
    x_title: str,
    y_title: str,
    width: int,
    height: int,
    theme: str,
) -> dict[str, Any]:
    x_column = chart_data.get("x_column", "x")
    y_column = chart_data.get("y_column", "y")
    x_axis_label = x_title or x_column
    y_axis_label = y_title or y_column

    if chart_type == "pie":
        x_axis_label = x_title or chart_data.get("labels_column", "labels")
        y_axis_label = y_title or chart_data.get("values_column", "values")

    return {
        "chart_type": chart_type,
        "title": title,
        "theme": theme,
        "dimensions": {"width": width, "height": height},
        "axes": {
            "x_axis": {"column": x_column, "label": x_axis_label},
            "y_axis": {"column": y_column, "label": y_axis_label},
        },
    }


def _infer_chart_type_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"chart_type": "bar", "reason": "No rows; bar is used as a safe default.", "mapping": {}}

    columns = list(rows[0].keys())
    if len(columns) < 2:
        return {
            "chart_type": "bar",
            "reason": "At least two columns are needed; bar is a safe fallback.",
            "mapping": {"x": columns[0]} if columns else {},
        }

    # Analyze column data types
    col_types = {}
    col_uniques = {}
    
    for col in columns:
        vals = [row.get(col) for row in rows]
        numeric_count = sum(1 for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool))
        is_numeric = numeric_count >= max(1, int(len(vals) * 0.7))
        
        is_date = False
        date_pattern = r'^\d{4}[-/]\d{2}[-/]\d{2}'
        if any(isinstance(v, str) and re.match(date_pattern, v.strip()) for v in vals if v):
            is_date = True
        elif any(isinstance(v, (datetime, pd.Timestamp)) for v in vals):
            is_date = True
            
        col_uniques[col] = len(set(v for v in vals if v is not None))
        
        if is_numeric:
            col_types[col] = "numeric"
        elif is_date:
            col_types[col] = "date"
        else:
            col_types[col] = "categorical"

    numeric_cols = [c for c in columns if col_types[c] == "numeric"]
    date_cols = [c for c in columns if col_types[c] == "date"]
    categorical_cols = [c for c in columns if col_types[c] == "categorical"]

    # Pattern 1: Multi-series line chart (1 date, 1 categorical, 1 numeric)
    if date_cols and categorical_cols and numeric_cols:
        return {
            "chart_type": "line",
            "reason": "Time-series data with category categories found. Creating a multi-series line chart.",
            "mapping": {"x": date_cols[0], "y": numeric_cols[0], "color_column": categorical_cols[0]}
        }

    # Pattern 2: Grouped/Stacked Bar chart (2 categorical, 1 numeric)
    if len(categorical_cols) >= 2 and numeric_cols:
        c1, c2 = categorical_cols[0], categorical_cols[1]
        if col_uniques[c2] > col_uniques[c1]:
            c1, c2 = c2, c1
        return {
            "chart_type": "bar",
            "reason": "Two categorical dimensions and a numeric value found. Suggesting grouped bar chart.",
            "mapping": {"x": c1, "y": numeric_cols[0], "color_column": c2, "barmode": "group"}
        }

    # Pattern 3: Simple time series
    if date_cols and numeric_cols:
        return {
            "chart_type": "line",
            "reason": "Date-like column with numeric values suggests a trend chart.",
            "mapping": {"x": date_cols[0], "y": numeric_cols[0]}
        }

    # Pattern 4: Status / priority distributions (1 categorical with few unique values, 1 numeric)
    if len(categorical_cols) == 1 and numeric_cols:
        cat = categorical_cols[0]
        num = numeric_cols[0]
        if col_uniques[cat] <= 8:
            return {
                "chart_type": "pie",
                "reason": f"Distribution of {cat} has few categories, best displayed as a pie chart.",
                "mapping": {"labels": cat, "values": num}
            }
        else:
            is_progress = any(k in num.lower() for k in ("progress", "percent", "rate"))
            if is_progress:
                return {
                    "chart_type": "bar",
                    "reason": "Progress vs category is best shown as a horizontal bar chart.",
                    "mapping": {"x": cat, "y": num, "orientation": "horizontal"}
                }
            return {
                "chart_type": "bar",
                "reason": "Categorical column with numeric values fits bar chart comparison.",
                "mapping": {"x": cat, "y": num}
            }

    # Pattern 5: Two numeric columns
    if len(numeric_cols) >= 2:
        return {
            "chart_type": "scatter",
            "reason": "Two numeric columns fit scatter relationship analysis.",
            "mapping": {"x": numeric_cols[0], "y": numeric_cols[1]}
        }

    # Fallback
    first_col = columns[0]
    second_col = columns[1]
    return {
        "chart_type": "bar",
        "reason": "General categorical comparison fallback.",
        "mapping": {"x": first_col, "y": second_col},
    }


@mcp.tool()
def create_chart(
    chart_type: Literal["scatter", "line", "bar", "histogram", "box", "violin", "pie", "heatmap", "area", "density_heatmap", "scatter_matrix"],
    data: Any,
    title: str = "Chart",
    x_column: str | None = None,
    y_column: str | None = None,
    color_column: str | None = None,
    barmode: str | None = None,
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
    theme: str = "plotly",
    width: Annotated[int, Field(ge=100, le=2000)] = 800,
    height: Annotated[int, Field(ge=100, le=2000)] = 600,
) -> str:
    """
    Create charts with flexible configuration. Automatically infers columns if not provided.
    """
    if theme not in SUPPORTED_THEMES:
        raise ValueError(f"Unsupported theme '{theme}'")

    chart_data = _normalize_data(data)
    
    if "rows" in chart_data and isinstance(chart_data["rows"], list) and len(chart_data["rows"]) > 0:
        available_cols = list(chart_data["rows"][0].keys())
        if not x_column:
            x_column = available_cols[0] if available_cols else None
        if not y_column:
            y_column = available_cols[1] if len(available_cols) > 1 else None

    if x_column:
        chart_data["x_column"] = x_column
    if y_column:
        chart_data["y_column"] = y_column
    if color_column:
        chart_data["color_column"] = color_column
    if barmode:
        chart_data["barmode"] = barmode

    fig = _build_figure(chart_type, chart_data, title=title, x_title=x_title, y_title=y_title, theme=theme)
    fig.update_layout(width=width, height=height)
    
    metadata = _build_axis_metadata(chart_type, chart_data, title, x_title, y_title, width, height, theme)
    if "rows" in chart_data and isinstance(chart_data["rows"], list):
        metadata["row_count"] = len(chart_data["rows"])
        metadata["columns"] = list(chart_data["rows"][0].keys()) if chart_data["rows"] else []
        
    return _format_output(fig, output_format, output_file, metadata)


@mcp.tool()
def create_scatter_plot(
    x_data: Any = None,
    y_data: Any = None,
    x: Any | None = None,
    y: Any | None = None,
    data: Any | None = None,
    x_column: str | None = None,
    y_column: str | None = None,
    labels: Any = None,
    colors: Any = None,
    sizes: Any = None,
    color_column: str | None = None,
    size_column: str | None = None,
    label_column: str | None = None,
    title: str = "Scatter Plot",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Specialized scatter plot creation. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        
        if color_column:
            normalized["color"] = color_column
        elif isinstance(colors, str):
            normalized["color"] = colors
            
        if size_column:
            normalized["size"] = size_column
        elif isinstance(sizes, str):
            normalized["size"] = sizes
            
        if label_column:
            normalized["label"] = label_column
        elif isinstance(labels, str):
            normalized["label"] = labels
            
        return create_chart(
            chart_type="scatter",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(x_data) or _to_list(x)
    resolved_y = _to_list(y_data) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'x_data' and 'y_data' lists.")
        
    payload = {
        "x": resolved_x,
        "y": resolved_y,
        "label": _to_list(labels),
        "color": _to_list(colors),
        "size": _to_list(sizes)
    }
    return create_chart(
        chart_type="scatter",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_bar_chart(
    categories: Any = None,
    values: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    color_column: str | None = None,
    barmode: Literal["group", "stack", "relative"] = "group",
    orientation: Literal["vertical", "horizontal"] = "vertical",
    title: str = "Bar Chart",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Bar chart for categorical data. Supports direct list passing or DataFrame/rows query input.
    """
    orientation_value = "v" if orientation == "vertical" else "h"
    if data is not None:
        normalized = _normalize_data(data)
        normalized["orientation"] = orientation_value
        normalized["barmode"] = barmode
        if color_column:
            normalized["color_column"] = color_column
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="bar",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(categories) or _to_list(x)
    resolved_y = _to_list(values) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'categories'/'values' lists.")
        
    payload = {"x": resolved_x, "y": resolved_y, "orientation": orientation_value, "barmode": barmode}
    if color_column:
        payload["color_column"] = color_column
    return create_chart(
        chart_type="bar",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_line_chart(
    x_data: Any = None,
    y_data: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    color_column: str | None = None,
    line_name: str = "Series",
    title: str = "Line Chart",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Line chart for time series data. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        if color_column:
            normalized["color_column"] = color_column
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="line",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(x_data) or _to_list(x)
    resolved_y = _to_list(y_data) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'x_data'/'y_data' lists.")
        
    rows = [{x_title or "x": resolved_x[i], y_title or line_name: resolved_y[i]} for i in range(min(len(resolved_x), len(resolved_y)))]
    payload = {"rows": rows, "x_column": x_title or "x", "y_column": y_title or line_name}
    if color_column:
        payload["color_column"] = color_column
    return create_chart(
        chart_type="line",
        data=payload,
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_histogram_chart(
    values: Any = None,
    x: Any = None,
    data: Any = None,
    x_column: str | None = None,
    title: str = "Histogram",
    x_title: str = "Value",
    y_title: str = "Count",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Histogram for distribution analysis. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        return create_chart(
            chart_type="histogram",
            data=normalized,
            x_column=x_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(values) or _to_list(x)
    if resolved_x is None:
        raise ValueError("Must provide either 'data' with columns or 'values'/'x' list.")
        
    payload = {"x": resolved_x}
    return create_chart(
        chart_type="histogram",
        data=payload,
        x_column="x",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_box_plot(
    categories: Any = None,
    values: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    title: str = "Box Plot",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Box plot for spread and outlier analysis. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="box",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(categories) or _to_list(x)
    resolved_y = _to_list(values) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'categories'/'values' lists.")
        
    payload = {"x": resolved_x, "y": resolved_y}
    return create_chart(
        chart_type="box",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_violin_plot(
    categories: Any = None,
    values: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    title: str = "Violin Plot",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Violin plot for distribution shape across groups. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="violin",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(categories) or _to_list(x)
    resolved_y = _to_list(values) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'categories'/'values' lists.")
        
    payload = {"x": resolved_x, "y": resolved_y}
    return create_chart(
        chart_type="violin",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_pie_chart(
    labels: Any = None,
    values: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    title: str = "Pie Chart",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Pie chart for composition analysis. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="pie",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(labels) or _to_list(x)
    resolved_y = _to_list(values) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'labels'/'values' lists.")
        
    payload = {"labels": resolved_x, "values": resolved_y, "labels_column": "labels", "values_column": "values"}
    return create_chart(
        chart_type="pie",
        data=payload,
        x_title="Category",
        y_title="Value",
        title=title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_area_chart(
    x_data: Any = None,
    y_data: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    title: str = "Area Chart",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Area chart for cumulative trend visualization. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="area",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(x_data) or _to_list(x)
    resolved_y = _to_list(y_data) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'x_data'/'y_data' lists.")
        
    payload = {"x": resolved_x, "y": resolved_y}
    return create_chart(
        chart_type="area",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_density_heatmap(
    x_data: Any = None,
    y_data: Any = None,
    x: Any = None,
    y: Any = None,
    data: Any = None,
    x_column: str | None = None,
    y_column: str | None = None,
    title: str = "Density Heatmap",
    x_title: str = "",
    y_title: str = "",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Density heatmap for concentrated regions in bivariate data. Supports direct list passing or DataFrame/rows query input.
    """
    if data is not None:
        normalized = _normalize_data(data)
        x_col = x_column or (x if isinstance(x, str) else None)
        y_col = y_column or (y if isinstance(y, str) else None)
        return create_chart(
            chart_type="density_heatmap",
            data=normalized,
            x_column=x_col,
            y_column=y_col,
            title=title,
            x_title=x_title,
            y_title=y_title,
            output_format=output_format,
            output_file=output_file,
        )
        
    resolved_x = _to_list(x_data) or _to_list(x)
    resolved_y = _to_list(y_data) or _to_list(y)
    if resolved_x is None or resolved_y is None:
        raise ValueError("Must provide either 'data' with columns or 'x_data'/'y_data' lists.")
        
    payload = {"x": resolved_x, "y": resolved_y}
    return create_chart(
        chart_type="density_heatmap",
        data=payload,
        x_column="x",
        y_column="y",
        title=title,
        x_title=x_title,
        y_title=y_title,
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def create_scatter_matrix(
    data: Any,
    dimensions: list[str] | None = None,
    title: str = "Scatter Matrix",
    output_format: Literal["html", "png", "svg"] = "html",
    output_file: str | None = None,
) -> str:
    """
    Scatter matrix for multi-variable correlation exploration.
    """
    normalized = _normalize_data(data)
    normalized["dimensions"] = dimensions
    return create_chart(
        chart_type="scatter_matrix",
        data=normalized,
        title=title,
        x_title="Multiple Numeric Dimensions",
        y_title="Multiple Numeric Dimensions",
        output_format=output_format,
        output_file=output_file,
    )


@mcp.tool()
def get_supported_charts() -> str:
    """
    List supported chart types and features.
    """
    payload = {
        "chart_types": list(SUPPORTED_CHARTS),
        "output_formats": list(SUPPORTED_FORMATS),
        "themes": list(SUPPORTED_THEMES),
        "features": {
            "static_images_png": "High-quality raster images for documents, presentations, and print materials",
            "vector_graphics_svg": "Scalable vector graphics with crisp rendering at any size and small file size",
            "export_requirement": "Kaleido package required for PNG/SVG export",
            "flexible_data_input": "dict, list-of-rows, or JSON string",
            "fastmcp_validation": "decorator-based tools with type validation",
            "detailed_output_metadata": "Every response includes chart metadata with explicit x_axis and y_axis labels",
        },
        "specialized_tools": [
            "create_histogram_chart",
            "create_box_plot",
            "create_violin_plot",
            "create_pie_chart",
            "create_area_chart",
            "create_density_heatmap",
            "create_scatter_matrix",
        ],
        "precontext_prompt": PRECONTEXT_PROMPT,
        "schema_playbook": SCHEMA_PLAYBOOK,
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def suggest_chart_from_data(
    data: Any,
    user_question: str = "",
) -> str:
    """
    Suggest the best chart type and column mapping from query result rows.
    """
    normalized = _normalize_data(data)
    rows = normalized.get("rows")
    if rows is None:
        df = _data_to_dataframe(normalized)
        rows = df.to_dict(orient="records")

    suggestion = _infer_chart_type_from_rows(rows)
    payload = {
        "user_question": user_question,
        "suggestion": suggestion,
        "recommended_next_step": "Use create_chart with the suggested chart_type and mapping.",
        "precontext_prompt": PRECONTEXT_PROMPT,
    }
    return json.dumps(payload, indent=2)


if __name__ == "__main__":
    mcp.run()
